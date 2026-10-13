"""Real SQLite integration, atomicity, temporal boundaries and interleaved reads."""

from contextlib import contextmanager
import copy
import hashlib
import json
import sqlite3
from unittest.mock import patch

from tradee.c01 import Policy, Registry, ValidationError
from tests.support import BASE_TIME, RegistryCase, contract, rule


class TemporalPersistenceTests(RegistryCase):
    def test_ttl_boundary_and_recovery(self):
        self.ingest()
        for age, state in ((1_799_999, "eligible"), (1_800_000, "unknown"), (1_800_001, "unknown")):
            self.now = BASE_TIME + age
            self.assertEqual(self.decision()["state"], state)
        self.ingest()
        self.assertEqual(self.decision()["state"], "eligible")

    def test_custom_ttl_is_frozen_in_snapshot(self):
        self.ingest()
        self.now += 60_000
        snap = self.registry.universe(Policy(max_age_seconds=60), save=True)
        self.assertEqual(snap["members"], [])
        self.assertEqual(self.registry.universe()["members"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(self.registry.snapshot(snap["snapshot_hash"]), snap)

    def test_equal_timestamp_observations_have_deterministic_order(self):
        first = self.ingest()
        contract(self.data)["status"] = "SETTLING"
        last = self.ingest()
        self.assertGreater(last["observation_id"], first["observation_id"])
        self.assertEqual(self.registry.universe()["observation_id"], last["observation_id"])
        self.assertEqual(self.decision()["state"], "ineligible")

    def test_rule_changes_retain_identity_and_old_rule_version(self):
        self.ingest()
        old = self.decision()
        self.now += 1000
        rule(self.data, "PRICE_FILTER")["tickSize"] = "0.20"
        self.ingest()
        new = self.decision()
        self.assertEqual(old["instrument_id"], new["instrument_id"])
        self.assertNotEqual(old["version_hash"], new["version_hash"])
        self.assertEqual(self.registry.version(old["version_hash"])["spec"]["constraints"]["PRICE_FILTER.tickSize"], "0.10")
        self.assertEqual(self.decision(as_of_ms=BASE_TIME), old)

    def test_failed_refresh_between_successes_is_not_historical_evidence(self):
        self.ingest()
        before = self.registry.universe()
        self.now += 1000
        with self.assertRaises(ValueError):
            self.registry.ingest("{broken")
        self.assertEqual(self.registry.universe(as_of_ms=BASE_TIME), before)
        self.assertEqual(self.decision()["last_observed_ms"], BASE_TIME)
        self.now += 1000
        self.ingest()
        self.assertEqual(len(self.registry.history("BTCUSDT")), 2)

    def test_missing_reappearing_symbol_recovers_without_relisting(self):
        self.ingest()
        first = self.decision()
        missing = copy.deepcopy(self.data)
        missing["symbols"] = [s for s in missing["symbols"] if s["symbol"] != "BTCUSDT"]
        self.now += 1000
        self.ingest(missing)
        self.assertEqual(self.decision()["state"], "unknown")
        self.now += 1000
        self.ingest()
        self.assertEqual(self.decision()["state"], "eligible")
        self.assertEqual(self.decision()["instrument_id"], first["instrument_id"])

    def test_future_onboarding_cannot_be_traded(self):
        contract(self.data)["onboardDate"] = self.now + 1000
        self.ingest()
        self.assertIn("before_reported_onboard_time", self.decision()["reasons"])
        self.now += 1000
        self.assertEqual(self.decision()["state"], "eligible")

    def test_raw_response_and_checksum_are_preserved_exactly(self):
        raw = json.dumps(self.data, indent=4, ensure_ascii=False) + "\n"
        result = self.registry.ingest(raw, source="test:raw")
        with self.registry.connection() as db:
            row = db.execute("SELECT * FROM observations WHERE id=?", (result["observation_id"],)).fetchone()
        self.assertEqual(row["raw"], raw)
        self.assertEqual(row["raw_sha256"], hashlib.sha256(raw.encode()).hexdigest())
        self.assertEqual(self.decision()["source"], "test:raw")

    def test_mid_write_database_failure_rolls_back_entire_refresh(self):
        self.ingest()
        before, counts = self.registry.universe(), self.counts()
        # Fail on the second fixture member, after earlier writes have occurred.
        with self.registry.connection() as db:
            db.execute("""CREATE TRIGGER injected_failure BEFORE INSERT ON memberships
                WHEN NEW.symbol='ETHUSDT' BEGIN SELECT RAISE(ABORT,'injected disk write failure'); END""")
        contract(self.data)["status"] = "SETTLING"
        with self.assertRaisesRegex(sqlite3.IntegrityError, "injected"):
            self.ingest()
        self.assertEqual(self.registry.universe(), before)
        after = self.counts()
        self.assertEqual(after[:2], counts[:2], "no orphan semantic versions or membership rows")
        self.assertEqual(after[2], counts[2] + 1, "only a failure observation is added")
        with self.registry.connection() as db:
            db.execute("DROP TRIGGER injected_failure")
        self.ingest()
        self.assertEqual(self.decision()["state"], "ineligible")

    def test_saved_snapshot_is_idempotent_and_detached_from_caller(self):
        self.ingest()
        original = self.registry.universe(save=True)
        self.assertEqual(self.registry.universe(save=True), original)
        returned = self.registry.snapshot(original["snapshot_hash"])
        returned["members"].clear()
        returned["policy"]["enabled"].clear()
        self.assertEqual(self.registry.snapshot(original["snapshot_hash"]), original)
        self.assertEqual(self.registry.health()["counts"]["universe_snapshots"], 1)

    def test_unknown_record_lookups_fail_explicitly(self):
        for query in (self.registry.version, self.registry.snapshot):
            with self.assertRaises(ValidationError):
                query("missing")
        self.assertEqual(self.registry.history("UNKNOWNUSDT"), [])

    def test_read_during_committed_refresh_is_consistent(self):
        self.ingest()
        with self.registry.connection() as db:
            db.execute("PRAGMA journal_mode=WAL")
        writer = Registry(self.path, clock=lambda: self.now / 1000)
        expected = self.registry.universe()
        changed = copy.deepcopy(self.data)
        contract(changed)["status"] = "SETTLING"
        original_connection = self.registry.connection
        fired = []

        class InterleavedConnection:
            def __init__(self, db):
                self.db = db

            def execute(inner, sql, parameters=()):
                cursor = inner.db.execute(sql, parameters)
                if "SELECT * FROM observations" in sql and not fired:
                    fired.append(True)
                    writer.ingest(json.dumps(changed), observed_ms=self.now)
                return cursor

        @contextmanager
        def interleaved():
            with original_connection() as db:
                yield InterleavedConnection(db)

        with patch.object(self.registry, "connection", interleaved):
            self.assertEqual(self.registry.universe(), expected)
        self.assertTrue(fired)
        self.assertEqual(self.decision()["state"], "ineligible")

    def test_appending_future_observations_preserves_all_earlier_queries(self):
        self.ingest()
        checkpoints = [(self.now, self.registry.universe())]
        for step in range(1, 9):
            self.now += 1000
            contract(self.data)["status"] = "TRADING" if step % 2 else "SETTLING"
            rule(self.data, "MIN_NOTIONAL")["notional"] = str(50 + step)
            self.ingest()
            for when, expected in checkpoints:
                self.assertEqual(self.registry.universe(as_of_ms=when), expected)
            checkpoints.append((self.now, self.registry.universe()))

    def test_invalid_optional_filter_quarantines_only_affected_contract(self):
        rule(self.data, "PERCENT_PRICE")["multiplierUp"] = "NaN"
        self.ingest()
        self.assertEqual(self.decision()["state"], "unknown")
        self.assertEqual(self.decision("ETHUSDT")["state"], "eligible")
        self.assertEqual(self.registry.universe()["members"], ["ETHUSDT"])
        self.assertFalse(self.registry.health()["ready"])
