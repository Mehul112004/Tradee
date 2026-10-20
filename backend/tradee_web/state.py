"""Durable UI requests, event cursors and preferences, separate from core DBs."""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
import uuid
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint

APP_ID = 0x54525742


class WebState:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            tables = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            if tables and db.execute("PRAGMA application_id").fetchone()[0] != APP_ID:
                raise ValidationError("Web state cannot overwrite a domain database")
            if tables and db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValidationError("Unsupported web state schema")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,workspace TEXT,kind TEXT,at_ms INTEGER,document TEXT);
                CREATE TABLE IF NOT EXISTS heads(workspace TEXT,component TEXT,version TEXT,PRIMARY KEY(workspace,component));
                CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY,workspace TEXT,key TEXT,body_hash TEXT,kind TEXT,document TEXT,state TEXT,result TEXT,error TEXT,created_ms INTEGER,updated_ms INTEGER,UNIQUE(workspace,key));
                CREATE TABLE IF NOT EXISTS service_state(name TEXT PRIMARY KEY,document TEXT);
            """)
            db.execute(f"PRAGMA application_id={APP_ID}")
            db.execute("PRAGMA user_version=1")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def event(self, workspace, kind, document):
        with self.connection() as db:
            cur = db.execute(
                "INSERT INTO events(workspace,kind,at_ms,document) VALUES(?,?,?,?)",
                (workspace, kind, int(time.time() * 1000), json.dumps(document)),
            )
            return cur.lastrowid

    def sync(self, workspace, component, value):
        version = fingerprint(value)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT version FROM heads WHERE workspace=? AND component=?",
                (workspace, component),
            ).fetchone()
            if old and old[0] == version:
                return
            db.execute(
                "INSERT INTO heads VALUES(?,?,?) ON CONFLICT(workspace,component) DO UPDATE SET version=excluded.version",
                (workspace, component, version),
            )
            db.execute(
                "INSERT INTO events(workspace,kind,at_ms,document) VALUES(?,?,?,?)",
                (
                    workspace,
                    "resource_changed",
                    int(time.time() * 1000),
                    json.dumps(dict(component=component, version=version)),
                ),
            )

    def events(self, workspace, after=0):
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE workspace=? AND id>? ORDER BY id LIMIT 250",
                (workspace, after),
            ).fetchall()
        return [dict(r, document=json.loads(r["document"])) for r in rows]

    def lookup(self, workspace, key, kind, document):
        if not isinstance(key, str) or not 1 <= len(key) <= 100:
            raise ValidationError("Bounded idempotency key required")
        h = fingerprint(dict(kind=kind, document=document))
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM requests WHERE workspace=? AND key=?", (workspace, key)
            ).fetchone()
        if row is None:
            return None
        if row["body_hash"] != h:
            raise ValidationError("Idempotency key belongs to a different command")
        return self.decode(row)

    def request(self, workspace, key, kind, document):
        if not isinstance(key, str) or not 1 <= len(key) <= 100:
            raise ValidationError("Bounded idempotency key required")
        h = fingerprint(dict(kind=kind, document=document))
        now = int(time.time() * 1000)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT * FROM requests WHERE workspace=? AND key=?", (workspace, key)
            ).fetchone()
            if old:
                if old["body_hash"] != h:
                    raise ValidationError(
                        "Idempotency key belongs to a different command"
                    )
                return self.decode(old)
            if (
                db.execute(
                    "SELECT COUNT(*) FROM requests WHERE state IN ('queued','running')"
                ).fetchone()[0]
                >= 100
            ):
                raise ValidationError("Job queue is full")
            uid = uuid.uuid4().hex
            db.execute(
                "INSERT INTO requests VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uid,
                    workspace,
                    key,
                    h,
                    kind,
                    json.dumps(document),
                    "queued",
                    None,
                    None,
                    now,
                    now,
                ),
            )
        return self.get(uid)

    @staticmethod
    def decode(row):
        d = dict(row)
        for k in ("document", "result"):
            d[k] = None if d[k] is None else json.loads(d[k])
        return d

    def get(self, uid):
        with self.connection() as db:
            row = db.execute("SELECT * FROM requests WHERE id=?", (uid,)).fetchone()
        if row is None:
            raise ValidationError("Unknown operation")
        return self.decode(row)

    def jobs(self, workspace):
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM requests WHERE workspace=? ORDER BY created_ms DESC LIMIT 100",
                (workspace,),
            ).fetchall()
        return [self.decode(r) for r in rows]

    def claim(self):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            r = db.execute(
                "SELECT * FROM requests WHERE state='queued' ORDER BY created_ms LIMIT 1"
            ).fetchone()
            if r is None:
                return None
            db.execute(
                "UPDATE requests SET state='running',updated_ms=? WHERE id=?",
                (int(time.time() * 1000), r["id"]),
            )
        return self.get(r["id"])

    def finish(self, uid, result=None, error=None):
        with self.connection() as db:
            db.execute(
                "UPDATE requests SET state=?,result=?,error=?,updated_ms=? WHERE id=?",
                (
                    "failed" if error else "succeeded",
                    json.dumps(result),
                    error,
                    int(time.time() * 1000),
                    uid,
                ),
            )
        r = self.get(uid)
        self.event(r["workspace"], "job_completed", dict(id=uid, state=r["state"]))
        return r

    def cancel(self, uid):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            r = db.execute("SELECT state FROM requests WHERE id=?", (uid,)).fetchone()
            if not r:
                raise ValidationError("Unknown operation")
            if r["state"] != "queued":
                raise ValidationError(
                    "Only queued work can be cancelled; running core publication is atomic"
                )
            db.execute(
                "UPDATE requests SET state='cancelled',updated_ms=? WHERE id=?",
                (int(time.time() * 1000), uid),
            )
        return self.get(uid)

    def worker_heartbeat(self):
        with self.connection() as db:
            db.execute(
                "INSERT INTO service_state VALUES('worker',?) ON CONFLICT(name) DO UPDATE SET document=excluded.document",
                (json.dumps(dict(at_ms=int(time.time() * 1000))),),
            )

    def worker_status(self):
        with self.connection() as db:
            row = db.execute(
                "SELECT document FROM service_state WHERE name='worker'"
            ).fetchone()
        value = None if row is None else json.loads(row[0])
        return dict(
            state=(
                "not_running"
                if value is None or int(time.time() * 1000) - value["at_ms"] > 15000
                else "connected"
            ),
            last_heartbeat_ms=None if value is None else value["at_ms"],
        )

    def bounds(self, workspace):
        with self.connection() as db:
            return db.execute(
                "SELECT MIN(id),MAX(id) FROM events WHERE workspace=?", (workspace,)
            ).fetchone()

    def prune_events(self):
        # Invalidation history is bounded; the domain journals remain authoritative.
        with self.connection() as db:
            db.execute(
                "DELETE FROM events WHERE id < (SELECT COALESCE(MAX(id),0)-10000 FROM events)"
            )
