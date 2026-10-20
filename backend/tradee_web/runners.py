"""Explicit bounded paper runner, independently owned from the API/job worker.

No collector, Telegram transport, shell command or exchange order is started.
Pausing notifications does not stop the paper book; stopping this runner does.
"""

import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from .state import WebState
from .config import load_settings
from tradee.c01 import ValidationError


def initialize(state):
    with state.connection() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS runners(id TEXT PRIMARY KEY,workspace TEXT,session TEXT,monitor TEXT,state TEXT,heartbeat_ms INTEGER,stop_requested INTEGER,cycles INTEGER,document TEXT)"""
        )


def catalog(state, workspace):
    initialize(state)
    with state.connection() as db:
        rows = db.execute(
            "SELECT * FROM runners WHERE workspace=? ORDER BY heartbeat_ms DESC LIMIT 100",
            (workspace,),
        ).fetchall()
    now = int(time.time() * 1000)
    return [
        dict(
            r,
            document=json.loads(r["document"]),
            heartbeat_stale=now - r["heartbeat_ms"] > 15000,
        )
        for r in rows
    ]


def start(settings, workspace, d):
    state = WebState(settings.state_path)
    initialize(state)
    now = int(time.time() * 1000)
    with state.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT id FROM runners WHERE workspace=? AND session=? AND state IN ('starting','running','awaiting_start')",
            (workspace, d["session"]),
        ).fetchone()
        if row:
            raise ValidationError(
                "Runner ownership already reserved; inspect its heartbeat and request a stop before recovery"
            )
        uid = uuid.uuid4().hex
        db.execute(
            "INSERT INTO runners VALUES(?,?,?,?,?,?,?,?,?)",
            (
                uid,
                workspace,
                d["session"],
                d["monitor"],
                "starting",
                now,
                0,
                0,
                json.dumps(d),
            ),
        )
    command = [
        sys.executable,
        "-m",
        "backend.tradee_web.runners",
        "--id",
        uid,
        "--state",
        str(settings.state_path),
    ]
    if os.environ.get("TRADEE_WEB_CONFIG"):
        command += ["--config", os.environ["TRADEE_WEB_CONFIG"]]
    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        update(state, uid, "failed", 0)
        raise
    return dict(
        runner_id=uid,
        state="starting",
        session=d["session"],
        monitor=d["monitor"],
        external_send=False,
    )


def stop(settings, workspace, session):
    state = WebState(settings.state_path)
    initialize(state)
    with state.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT id FROM runners WHERE workspace=? AND session=? AND state IN ('starting','running','awaiting_start')",
            (workspace, session),
        ).fetchone()
        if not row:
            raise ValidationError("No owned runner for this session")
        db.execute("UPDATE runners SET stop_requested=1 WHERE id=?", (row[0],))
    return dict(
        runner_id=row[0],
        state="stop_requested",
        note="The current atomic core tick completes before stopping; notification pause is separate",
    )


def recover(settings, workspace, session):
    state = WebState(settings.state_path)
    initialize(state)
    import hashlib

    lockpath = (
        str(settings.state_path)
        + ".runner-"
        + workspace
        + "-"
        + hashlib.sha256(session.encode()).hexdigest()
        + ".lock"
    )
    with open(lockpath, "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValidationError(
                "Runner still owns its process lock; request a stop and wait for the current tick"
            )
        with state.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT id FROM runners WHERE workspace=? AND session=? AND state IN ('starting','running','awaiting_start')",
                (workspace, session),
            ).fetchall()
            # An unstarted reservation younger than 15s may be acquiring its lock.
            if any(
                r["heartbeat_ms"] > int(time.time() * 1000) - 15000
                for r in db.execute(
                    "SELECT heartbeat_ms FROM runners WHERE workspace=? AND session=? AND state='starting'",
                    (workspace, session),
                )
            ):
                raise ValidationError(
                    "Runner is still starting; wait for its ownership handshake"
                )
            db.execute(
                "UPDATE runners SET state='interrupted',stop_requested=1 WHERE workspace=? AND session=? AND state IN ('starting','running','awaiting_start')",
                (workspace, session),
            )
    return dict(recovered=[r[0] for r in rows], runner_started=False)


def update(state, uid, status, cycles):
    with state.connection() as db:
        db.execute(
            "UPDATE runners SET state=?,heartbeat_ms=?,cycles=? WHERE id=?",
            (status, int(time.time() * 1000), cycles, uid),
        )


def run(settings, uid):
    from .operations import execute

    state = WebState(settings.state_path)
    initialize(state)
    with state.connection() as db:
        row = db.execute("SELECT * FROM runners WHERE id=?", (uid,)).fetchone()
    if row is None:
        raise ValidationError("Unknown runner reservation")
    if row["state"] != "starting" or row["stop_requested"]:
        return
    d = json.loads(row["document"])
    cycles = 0
    deadline = time.monotonic() + 7200
    lockpath = (
        str(settings.state_path)
        + ".runner-"
        + row["workspace"]
        + "-"
        + __import__("hashlib").sha256(row["session"].encode()).hexdigest()
        + ".lock"
    )
    try:
        with open(lockpath, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            while time.monotonic() < deadline and cycles < d["max_cycles"]:
                with state.connection() as db:
                    stop_requested = db.execute(
                        "SELECT stop_requested FROM runners WHERE id=?", (uid,)
                    ).fetchone()[0]
                if stop_requested:
                    break
                from .projections import Repository

                repo = Repository(settings, settings.profile(row["workspace"]))
                head = repo.session(row["session"])
                spec = head["manifest"]["spec"]
                now = int(time.time() * 1000)
                from tradee.c14 import SessionSpec

                contract = SessionSpec.from_dict(spec)
                stamp = now - contract.runtime.source_settle_ms
                if stamp < spec["start_ms"]:
                    update(state, uid, "awaiting_start", cycles)
                else:
                    update(state, uid, "running", cycles)
                    execute(
                        settings, row["workspace"], "tick", dict(session=row["session"])
                    )
                    execute(
                        settings,
                        row["workspace"],
                        "forward_observe",
                        dict(monitor=row["monitor"]),
                    )
                    cycles += 1
                    if stamp >= contract.tail_end_ms:
                        break
                # Keep stop response and heartbeat bounded even with long intervals.
                remaining = d["interval_seconds"]
                while remaining > 0:
                    step = min(0.5, remaining)
                    time.sleep(step)
                    remaining -= step
                    with state.connection() as db:
                        if db.execute(
                            "SELECT stop_requested FROM runners WHERE id=?", (uid,)
                        ).fetchone()[0]:
                            remaining = 0
                    update(
                        state,
                        uid,
                        "awaiting_start" if stamp < spec["start_ms"] else "running",
                        cycles,
                    )
            update(state, uid, "stopped", cycles)
    except Exception:
        update(state, uid, "failed", cycles)
    finally:
        state.event(row["workspace"], "runner_changed", dict(id=uid))


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--id", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--config")
    a = p.parse_args()
    settings = load_settings(a.config)
    settings.state_path = Path(a.state).resolve()
    run(settings, a.id)
