"""Deterministic fixtures: private databases, controllable time, no live services."""

import json
from pathlib import Path
import tempfile
import unittest

from tradee.c01 import Registry

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "exchange_info.json"
BASE_TIME = 1_800_000_000_000


def payload():
    return json.loads(FIXTURE_PATH.read_text())


def contract(data, symbol="BTCUSDT"):
    return next(s for s in data["symbols"] if s["symbol"] == symbol)


def rule(data, kind, symbol="BTCUSDT"):
    return next(f for f in contract(data, symbol)["filters"] if f["filterType"] == kind)


class RegistryCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "c01.sqlite3"
        self.now = BASE_TIME
        self.registry = Registry(self.path, clock=lambda: self.now / 1000)
        self.data = payload()

    def ingest(self, data=None):
        return self.registry.ingest(json.dumps(self.data if data is None else data),
                                    source="test:exchangeInfo", observed_ms=self.now)

    def decision(self, symbol="BTCUSDT", **kwargs):
        return next(d for d in self.registry.universe(**kwargs)["decisions"] if d["symbol"] == symbol)

    def counts(self):
        with self.registry.connection() as db:
            return tuple(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                         for table in ("versions", "memberships", "observations"))
