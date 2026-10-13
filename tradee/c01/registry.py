"""Append-only observations and deterministic, observation-time universe queries."""

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

from .domain import Policy, ValidationError, canonical, fingerprint, normalize


class Registry:
    def __init__(self, path="data/c01.sqlite3", clock=time.time):
        self.path, self.clock = str(path), clock
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValidationError(f"Unsupported registry schema version {version}")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY, observed_ms INTEGER NOT NULL,
                    source TEXT NOT NULL, accepted INTEGER NOT NULL,
                    raw TEXT, raw_sha256 TEXT, error TEXT);
                CREATE INDEX IF NOT EXISTS observation_time ON observations(observed_ms, id);
                CREATE TABLE IF NOT EXISTS versions (
                    hash TEXT PRIMARY KEY, symbol TEXT NOT NULL,
                    instrument_id TEXT NOT NULL, spec TEXT NOT NULL,
                    first_observed_ms INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS version_symbol ON versions(symbol);
                CREATE TABLE IF NOT EXISTS memberships (
                    observation_id INTEGER NOT NULL REFERENCES observations(id),
                    symbol TEXT NOT NULL, version_hash TEXT NOT NULL REFERENCES versions(hash),
                    PRIMARY KEY(observation_id, symbol));
                CREATE INDEX IF NOT EXISTS membership_symbol ON memberships(symbol, observation_id);
                CREATE TABLE IF NOT EXISTS universe_snapshots (
                    hash TEXT PRIMARY KEY, document TEXT NOT NULL);
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _time(self, supplied=None):
        value = int(self.clock() * 1000) if supplied is None else supplied
        if type(value) is not int or value < 0 or value > int(self.clock() * 1000):
            raise ValidationError("Observation/query time must be a nonnegative past or current UTC millisecond timestamp")
        return value

    def _failure(self, source, error, raw=None):
        with self.connection() as db:
            db.execute("INSERT INTO observations(observed_ms,source,accepted,raw,error) VALUES(?,?,0,?,?)",
                       (self._time(), source, raw, str(error)))

    def refresh(self, provider):
        try:
            result = provider.fetch()
        except Exception as exc:
            self._failure(provider.endpoint, exc)
            raise
        return self.ingest(result.raw, result.source, result.received_ms)

    def ingest(self, raw, source="fixture", observed_ms=None):
        """Import a newly observed response, never fabricate an earlier receipt time."""
        try:
            when = self._time(observed_ms)
            payload = json.loads(raw)
            specs = normalize(payload)
            # canonical rejects non-finite JSON values even in unrecognized fields.
            canonical(payload)
            import hashlib
            raw_hash = hashlib.sha256(raw.encode()).hexdigest()
            with self.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                last = db.execute("SELECT MAX(observed_ms) FROM observations WHERE accepted=1").fetchone()[0]
                if last is not None and when < last:
                    raise ValidationError("Cannot append an observation before existing accepted history")
                previous = {r[0] for r in db.execute("SELECT DISTINCT symbol FROM memberships")}
                oid = db.execute("INSERT INTO observations(observed_ms,source,accepted,raw,raw_sha256) VALUES(?,?,1,?,?)",
                                 (when, source, raw, raw_hash)).lastrowid
                changes = 0
                for spec in specs:
                    prior = db.execute("SELECT instrument_id,spec FROM versions WHERE symbol=?", (spec["symbol"],)).fetchall()
                    if any(r["instrument_id"] != spec["instrument_id"] or "identity_conflict" in json.loads(r["spec"])["issues"] for r in prior):
                        spec["issues"] = sorted(set(spec["issues"] + ["identity_conflict"]))
                    digest = fingerprint(spec)
                    inserted = db.execute("INSERT OR IGNORE INTO versions VALUES(?,?,?,?,?)",
                                          (digest, spec["symbol"], spec["instrument_id"], canonical(spec), when))
                    changes += inserted.rowcount
                    db.execute("INSERT INTO memberships VALUES(?,?,?)", (oid, spec["symbol"], digest))
            missing = sorted(previous - {s["symbol"] for s in specs})
            return {"observation_id": oid, "observed_ms": when, "symbols": len(specs),
                    "new_versions": changes, "missing_from_response": missing,
                    "quarantined_records": sum(bool(s["issues"]) for s in specs)}
        except (ValueError, TypeError, sqlite3.Error) as exc:
            self._failure(source, exc, raw)
            raise

    def universe(self, policy=None, as_of_ms=None, save=False):
        policy = policy or Policy()
        when = self._time(as_of_ms)
        with self.connection() as db:
            # All reads below must share one SQLite snapshot during a refresh.
            db.execute("BEGIN IMMEDIATE" if save else "BEGIN")
            latest = db.execute("SELECT * FROM observations WHERE accepted=1 AND observed_ms<=? ORDER BY observed_ms DESC,id DESC LIMIT 1", (when,)).fetchone()
            records = db.execute("""
                SELECT * FROM (
                    SELECT m.symbol, m.version_hash, v.spec, o.observed_ms, o.source, o.id AS observation_id,
                    ROW_NUMBER() OVER (PARTITION BY m.symbol ORDER BY o.observed_ms DESC,o.id DESC) AS n
                    FROM memberships m JOIN observations o ON o.id=m.observation_id
                    JOIN versions v ON v.hash=m.version_hash WHERE o.observed_ms<=?
                ) WHERE n=1 ORDER BY symbol
            """, (when,)).fetchall()
            mapped = {r["symbol"]: r for r in records}
            decisions = []
            for symbol in sorted(set(mapped) | set(policy.enabled)):
                record = mapped.get(symbol)
                if record is None:
                    decisions.append({"symbol": symbol, "state": "unknown", "reasons": ["no_observed_metadata"],
                                      "instrument_id": None, "version_hash": None, "last_observed_ms": None, "source": None})
                    continue
                spec = json.loads(record["spec"])
                excluded, unknown = [], []
                if not spec["scope_supported"]:
                    excluded.append("outside_crypto_usdt_perpetual_scope")
                if symbol not in policy.enabled:
                    excluded.append("not_enabled")
                if spec["status"] != "TRADING":
                    (unknown if spec["status"] is None else excluded).append("not_trading")
                unknown.extend(spec["issues"])
                if record["observation_id"] != latest["id"]:
                    unknown.append("missing_from_latest_response")
                if when - record["observed_ms"] >= policy.max_age_seconds * 1000:
                    unknown.append("stale_metadata")
                if type(spec["onboardDate"]) is int and spec["onboardDate"] > when:
                    excluded.append("before_reported_onboard_time")
                decisions.append({"symbol": symbol, "state": "ineligible" if excluded else "unknown" if unknown else "eligible",
                                  "reasons": sorted(set(excluded + unknown)), "instrument_id": spec["instrument_id"],
                                  "version_hash": record["version_hash"], "last_observed_ms": record["observed_ms"], "source": record["source"]})
            document = {"schema_version": 1, "as_of_ms": when, "policy": policy.document(),
                        "policy_hash": fingerprint(policy.document()), "observation_id": latest["id"] if latest else None,
                        "evidence_policy": "observed_by_as_of; effective rule-change times unknown; policy supplied explicitly",
                        "members": [d["symbol"] for d in decisions if d["state"] == "eligible"], "decisions": decisions}
            digest = fingerprint(document)
            if save:
                db.execute("INSERT OR IGNORE INTO universe_snapshots VALUES(?,?)", (digest, canonical(document)))
            return {"snapshot_hash": digest, **document}

    def snapshot(self, digest):
        with self.connection() as db:
            row = db.execute("SELECT document FROM universe_snapshots WHERE hash=?", (digest,)).fetchone()
            if row is None:
                raise ValidationError("Unknown saved universe snapshot")
            return {"snapshot_hash": digest, **json.loads(row[0])}

    def version(self, digest):
        with self.connection() as db:
            row = db.execute("SELECT * FROM versions WHERE hash=?", (digest,)).fetchone()
            if row is None:
                raise ValidationError("Unknown metadata version")
            return {"version_hash": digest, "first_observed_ms": row["first_observed_ms"],
                    "effective_from_ms": None, "spec": json.loads(row["spec"])}

    def history(self, symbol):
        with self.connection() as db:
            return [dict(r) for r in db.execute("""SELECT o.id AS observation_id,o.observed_ms,o.source,m.version_hash
                FROM memberships m JOIN observations o ON o.id=m.observation_id
                WHERE m.symbol=? ORDER BY o.observed_ms,o.id""", (symbol,))]

    def health(self, policy=None):
        policy = policy or Policy()
        snapshot = self.universe(policy)
        with self.connection() as db:
            row = db.execute("SELECT id,observed_ms,accepted,error FROM observations ORDER BY id DESC LIMIT 1").fetchone()
            counts = {table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                      for table in ("observations", "versions", "universe_snapshots")}
        enabled = [d for d in snapshot["decisions"] if d["symbol"] in policy.enabled]
        ready = bool(enabled) and all(d["state"] == "eligible" for d in enabled)
        return {"ready": ready, "last_attempt": dict(row) if row else None,
                "members": snapshot["members"], "enabled_decisions": enabled, "counts": counts}
