"""Read-only domain adapters: constructors never initialize or migrate sources.

Reuse domain verification methods through a read-only connection override. SQL
below is limited to versioned discovery indexes; the browser sees domain DTOs.
"""

from contextlib import contextmanager
from pathlib import Path
import json
import hashlib
import sqlite3
import time
from tradee.c01 import Registry, ValidationError
from tradee.c01.domain import fingerprint
from tradee.c02 import MarketStore
from tradee.c03.store import FeatureStore
from tradee.c10 import EstimatorStore
from tradee.c11 import SimulationStore
from tradee.c12 import ResearchStore
from tradee.c13 import PortfolioStore
from tradee.c14 import SignalStore
from tradee.c15 import MonitorStore

APP_IDS = dict(
    c01=0,
    c02=0x54524432,
    c03=0x54524433,
    c06=0x54524436,
    c07=0x54524437,
    c08=0x54524438,
    c09=0x54524439,
    c10=0x54523130,
    c11=0x54523131,
    c12=0x54523132,
    c13=0x54523133,
    c14=0x54523134,
    c15=0x54523135,
)


class SourceError(ValidationError):
    pass


class LockedEvidence(ValidationError):
    pass


class MissingSource(ValidationError):
    pass


class ReadOnly:
    def __init__(self, path, kind, registry=None):
        self.path = str(Path(path).resolve())
        self.kind = kind
        self.clock = time.time
        self.registry = registry
        if not Path(self.path).is_file():
            raise MissingSource(f"{kind}: no configured evidence store")
        with self.connection() as db:
            app = db.execute("PRAGMA application_id").fetchone()[0]
            if (
                app != APP_IDS[kind]
                or db.execute("PRAGMA user_version").fetchone()[0] != 1
            ):
                raise SourceError(f"{kind}: unsupported evidence schema")
            if kind == "c01":
                required = {
                    "observations",
                    "versions",
                    "memberships",
                    "universe_snapshots",
                }
                tables = {
                    r[0]
                    for r in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                if not required <= tables:
                    raise SourceError("c01: unsupported registry schema")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(Path(self.path).as_uri() + "?mode=ro", uri=True, timeout=3)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        try:
            yield db
        finally:
            db.close()


class RegistryReader(ReadOnly, Registry):
    pass


class MarketReader(ReadOnly, MarketStore):
    def dataset(self, h):
        d = super().dataset(h)
        content = dict(d)
        content.pop("dataset_hash")
        if fingerprint(content) != h:
            raise SourceError("Dataset hash verification failed")
        return d

    def replay(self, h, until_ms=None, after_id=None):
        ds = self.dataset(h)
        if ds["event_count"] > 250000:
            raise SourceError("Market read event budget exceeded")
        with self.connection() as db:
            refs = db.execute(
                "SELECT event_id,available_ms FROM dataset_events WHERE dataset_hash=? ORDER BY available_ms,event_id",
                (h,),
            ).fetchmany(250001)
            if len(refs) > 250000:
                raise SourceError("Market read event budget exceeded")
            if (
                len(refs) != ds["event_count"]
                or fingerprint([(r[0], r[1]) for r in refs])
                != ds["event_manifest_sha256"]
            ):
                raise SourceError("Dataset input manifest mismatch")
            byte_count = db.execute(
                "SELECT COALESCE(SUM(LENGTH(e.document)+LENGTH(r.raw)),0) FROM dataset_events d JOIN events e ON e.id=d.event_id JOIN raw_observations r ON r.id=e.raw_id WHERE d.dataset_hash=?",
                (h,),
            ).fetchone()[0]
            if byte_count > 50000000:
                raise SourceError(
                    "Market input byte budget exceeded; pin a narrower dataset"
                )
            rows = db.execute(
                """SELECT e.*,d.available_ms AS replay_available_ms,r.raw,r.sha256 FROM dataset_events d
                JOIN events e ON e.id=d.event_id JOIN raw_observations r ON r.id=e.raw_id
                WHERE d.dataset_hash=? ORDER BY d.available_ms,e.id""",
                (h,),
            ).fetchmany(250001)
        if len(rows) != len(refs):
            raise SourceError("Dataset input missing")
        found = after_id is None
        for row in rows:
            if until_ms is not None and row["replay_available_ms"] > until_ms:
                break
            e = json.loads(row["document"])
            if any(
                e[k] != row[k]
                for k in (
                    "symbol",
                    "instrument_id",
                    "metadata_version",
                    "kind",
                    "event_ms",
                    "received_ms",
                    "available_ms",
                    "final",
                )
            ):
                raise SourceError("Market observation index mismatch")
            semantic = {
                k: v
                for k, v in e.items()
                if k
                not in (
                    "exchange_event_ms",
                    "received_ms",
                    "available_ms",
                    "source",
                    "availability_basis",
                    "raw_sha256",
                )
            }
            if (
                fingerprint(semantic) != row["semantic_hash"]
                or e["raw_sha256"] != row["sha256"]
                or hashlib.sha256(row["raw"]).hexdigest() != row["sha256"]
            ):
                raise SourceError("Market observation integrity mismatch")
            if not found:
                found = row["id"] == after_id
                continue
            yield dict(
                e,
                id=row["id"],
                available_ms=row["replay_available_ms"],
                availability_basis=ds["mode"],
            )
        if not found:
            raise ValidationError("Resume event does not belong to this dataset")


class FeatureReader(ReadOnly, FeatureStore):
    pass


class EstimatorReader(ReadOnly, EstimatorStore):
    pass


class SimulationReader(ReadOnly, SimulationStore):
    pass


class ResearchReader(ReadOnly, ResearchStore):
    pass


class PortfolioReader(ReadOnly, PortfolioStore):
    pass


class SignalReader(ReadOnly, SignalStore):
    pass


class MonitorReader(ReadOnly, MonitorStore):
    pass


READERS = dict(
    c01=RegistryReader,
    c02=MarketReader,
    c03=FeatureReader,
    c10=EstimatorReader,
    c11=SimulationReader,
    c12=ResearchReader,
    c13=PortfolioReader,
    c14=SignalReader,
    c15=MonitorReader,
)


def reader(profile, kind):
    registry = reader(profile, "c01") if kind == "c02" else None
    return READERS.get(kind, ReadOnly)(profile.path(kind), kind, registry=registry)


def indexed(store, query, args=(), limit=5000):
    with store.connection() as db:
        rows = db.execute(query, args).fetchmany(limit + 1)
    if len(rows) > limit:
        raise SourceError("Evidence index budget exceeded; narrow the source workspace")
    return [dict(r) for r in rows]


def document(raw, h=None):
    d = json.loads(raw)
    if h is not None and fingerprint(d) != h:
        raise SourceError("Evidence hash verification failed")
    return d


class AccessPolicy:
    """Deny protected runs/ranges on every read surface, including raw charts."""

    def __init__(self, profile):
        self.profile = profile
        self.checked_runs = set()
        self.locked_runs = set()
        self.locked_experiments = set()
        self.windows = []
        if not profile.path("c12").exists():
            return
        store = reader(profile, "c12")
        for r in indexed(store, "SELECT hash FROM experiments"):
            m = store.manifest(r["hash"])
            e = m["experiment"]
            events = store.events(r["hash"])
            if not any(x["kind"] == "holdout_opened" for x in events):
                self.locked_experiments.add(r["hash"])
                self.locked_runs.update(
                    h for v in e["variants"] for h in v["holdout_runs"]
                )
                test = e["holdout"]["split"]["test"]
                self.windows.append((test["start_ms"], test["end_ms"]))

    def run(self, h):
        if h in self.locked_runs:
            raise LockedEvidence(
                "Final holdout is locked; deliberate C12 access is required"
            )

        if self.windows and h not in self.checked_runs:
            m = reader(self.profile, "c11").manifest(h)
            self.range(*m["decision_window_ms"])
            # Conservatively protect outcome/context tails too: an alternate
            # strategy hash cannot expose a reserved raw-data interval.
            self.range(
                m["dataset"]["start_ms"],
                min(m["dataset"]["end_ms"], m["dataset"]["as_of_ms"] + 1),
            )
            self.checked_runs.add(h)

    def experiment(self, h):
        if h in self.locked_experiments:
            raise LockedEvidence("Final holdout is locked")

    def range(self, start, end):
        if any(start < b and end > a for a, b in self.windows):
            raise LockedEvidence("This interval overlaps reserved final evidence")
