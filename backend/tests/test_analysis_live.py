"""Production C02 Collector -> MarketStore -> analysis integration, no network."""

import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from tradee.c01 import Registry
from tradee.c01.provider import ProviderError
from tradee.c02.live import Collector
from backend.tradee_web.analysis import AnalysisService
from backend.tradee_web.analysis_live import C02LiveFeed
from backend.tradee_web.config import Settings, Profile, KINDS
from .analysis_support import (
    FixtureCandleSource,
    FixtureRest,
    fixture_c02_feed,
    stream_frame,
)
from .test_analysis import spec


class CollectorAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.settings = Settings(
            (
                Profile(
                    "local", "Local", {k: str(root / f"{k}.sqlite3") for k in KINDS}
                ),
            ),
            state_path=root / "web.sqlite3",
        )
        self.base = 1800000000000
        self.now = self.base + 30000
        self.clock = lambda: self.now / 1000
        raw = (
            Path(__file__).resolve().parents[2] / "tests/fixtures/exchange_info.json"
        ).read_text()
        Registry(root / "c01.sqlite3", clock=self.clock).ingest(
            raw, source="synthetic:live unit"
        )
        self.no_rest = Mock()
        outer = self

        class ManualFeed(C02LiveFeed):
            # Drive the real Collector.process explicitly to control finality,
            # duplicates, disconnects and event order without wall-clock waits.
            def start(self):
                self.state = "connected"
                self.reload()

        def factory(settings, workspace, session, start, wake, clock):
            return ManualFeed(
                settings, workspace, session, start, wake, clock, rest=outer.no_rest
            )

        self.source = Mock(wraps=FixtureCandleSource())
        self.service = AnalysisService(
            self.settings, source=self.source, clock=self.clock, feed_factory=factory
        )
        self.service.metadata = lambda *args: None
        self.addCleanup(self.service.close)

    def create(self, timeframe="1m", telegram=False):
        doc = spec()
        doc.update(
            timeframe=timeframe, strategies=["prior_range_breakout"], telegram=telegram
        )
        self.s = self.service.store.create("local", doc, "one", self.now)
        self.service.tick("local", self.s["id"])
        self.feed = self.service.feeds[self.s["id"]]
        self.initial = self.head()["setup_count"]
        return self.s

    def head(self):
        return self.service.store.get("local", self.s["id"])

    def push(self, minute=0, final=False, price="200"):
        opened = self.base + minute * 60000
        frame = stream_frame(opened, price=price, final=final, emitted=self.now)
        self.feed.collector.process(frame, "wss://synthetic/c02", self.now)
        self.service.tick("local", self.s["id"])

    def test_forming_candle_changes_chart_but_only_final_creates_setup(self):
        self.create()
        self.assertIsInstance(self.feed.collector, Collector)
        self.assertEqual(
            Path(self.feed.store.path), self.settings.profile("local").path("c02")
        )
        self.push()
        h = self.head()
        market = h["detail"]["BTCUSDT"]
        self.assertEqual(h["setup_count"], self.initial)
        self.assertEqual(market["forming"]["data"]["close"], "200")
        self.assertEqual(market["stream"]["state"], "connected")
        self.assertNotIn(self.base, [b["data"]["open_ms"] for b in market["candles"]])
        self.now = self.base + 63000
        self.push(final=True)
        h = self.head()
        self.assertEqual(h["setup_count"], self.initial + 1)
        self.assertEqual(h["setups"][0]["basis"], "c02_recorded_closed_candle")
        self.assertTrue(h["detail"]["BTCUSDT"]["candles"][-1]["data"]["c02_event_ids"])
        self.source.fetch.assert_called_once()

    def test_duplicate_final_and_late_partial_cannot_realert_or_overwrite_close(self):
        self.create()
        self.now = self.base + 63000
        self.push(final=True)
        count = self.head()["setup_count"]
        self.now += 1000
        self.push(final=True)
        self.now += 1000
        self.push(final=False, price="999")
        self.assertEqual(self.head()["setup_count"], count)
        self.assertEqual(
            self.head()["detail"]["BTCUSDT"]["candles"][-1]["data"]["close"], "200"
        )
        self.source.fetch.assert_called_once()

    def test_fifteen_minute_strategy_waits_for_all_final_minutes(self):
        self.create("15m")
        for minute in range(14):
            self.now = self.base + (minute + 1) * 60000 + 100
            self.push(minute, final=True)
            self.assertEqual(self.head()["setup_count"], self.initial)
        self.now = self.base + 14 * 60000 + 30000
        self.push(14, final=False)
        self.assertEqual(self.head()["setup_count"], self.initial)
        self.now = self.base + 15 * 60000 + 100
        self.push(14, final=True)
        self.assertEqual(self.head()["setup_count"], self.initial + 1)
        self.no_rest.backfill.assert_not_called()

    def test_final_correction_updates_context_without_rewriting_or_duplicating_setup(
        self,
    ):
        self.create()
        self.now = self.base + 63000
        self.push(final=True)
        original = self.head()["setups"][0]
        self.now += 1000
        self.push(final=True, price="100")
        h = self.head()
        self.assertEqual(h["setup_count"], self.initial + 1)
        self.assertEqual(h["setups"][0], original)
        self.assertEqual(h["detail"]["BTCUSDT"]["candles"][-1]["data"]["close"], "100")

    def test_future_availability_cannot_enter_chart_or_strategy_prefix(self):
        self.create()
        self.push(final=False)
        with self.feed.guard:
            self.feed.minutes["BTCUSDT"][self.base]["available_ms"] = self.now + 5000
        self.service.tick("local", self.s["id"])
        self.assertIsNone(self.head()["detail"]["BTCUSDT"]["forming"])
        self.assertEqual(self.head()["setup_count"], self.initial)

    def test_history_scan_does_not_start_a_collector(self):
        d = spec()
        d.update(mode="history")
        s = self.service.store.create("local", d, "history", self.now)
        self.service.tick("local", s["id"])
        self.assertFalse(self.service.feeds)
        self.assertFalse(self.settings.profile("local").path("c02").exists())

    def test_missing_minute_blocks_strategy_until_gap_is_repaired(self):
        self.create("15m")
        for minute in range(15):
            if minute == 5:
                continue
            self.now = self.base + (minute + 1) * 60000 + 100
            self.push(minute, final=True)
        self.assertEqual(self.head()["setup_count"], self.initial)
        self.no_rest.backfill.assert_called_once()
        self.now += 1000
        self.push(5, final=True)
        self.assertEqual(self.head()["setup_count"], self.initial + 1)

    def test_disconnect_has_no_rest_poll_fallback_and_stale_frames_suppress_alerts(
        self,
    ):
        self.create()
        self.push()
        self.feed.store.log(action="disconnected", route="market", error="synthetic")
        self.now += 1000
        self.service.tick("local", self.s["id"])
        h = self.head()
        self.assertEqual(h["detail"]["BTCUSDT"]["stream"]["state"], "reconnecting")
        self.assertTrue(h["detail"]["BTCUSDT"]["stale"])
        self.source.fetch.assert_called_once()
        self.no_rest.backfill.assert_not_called()
        self.feed.state = "connected"
        self.now += 16000
        self.service.tick("local", self.s["id"])
        self.assertEqual(self.head()["detail"]["BTCUSDT"]["stream"]["state"], "stale")

    def test_disconnect_after_detection_is_rechecked_before_telegram_attempt(self):
        transport = Mock()
        with (
            patch(
                "backend.tradee_web.analysis.telegram_config",
                return_value=(transport, 12345, 67890),
            ),
            patch.object(self.service, "dispatch"),
        ):
            self.create(telegram=True)
            self.now = self.base + 63000
            self.push(final=True)
            self.assertEqual(self.head()["setups"][0]["delivery"], "pending")
            self.feed.store.log(action="disconnected", route="market")
            AnalysisService.dispatch(self.service, "local", self.s["id"])
            transport.send.assert_not_called()
            self.assertEqual(self.head()["setups"][0]["delivery"], "suppressed")

    def test_repair_uses_existing_c02_rest_adapter_and_suppresses_backlog(self):
        self.create("15m")
        self.now = self.base + 15 * 60000 + 3000
        self.feed.collector.rest = FixtureRest(self.clock)
        self.feed.collector.repair(
            "BTCUSDT", end_ms=self.base + 15 * 60000, start_ms=self.base
        )
        self.assertEqual(self.feed.suppress_before_ms, self.now)
        self.service.tick("local", self.s["id"])
        self.assertEqual(
            self.head()["detail"]["BTCUSDT"]["candles"][-1]["data"]["open_ms"],
            self.base,
        )
        self.source.fetch.assert_called_once()

    def test_pause_releases_collector_and_resume_creates_a_new_subscription(self):
        self.create()
        first = self.feed
        self.service.store.control("local", self.s["id"], "pause", self.now)
        self.service.release_feeds([])
        self.assertTrue(first.stop.is_set())
        self.service.store.control("local", self.s["id"], "resume", self.now)
        self.service.tick("local", self.s["id"])
        self.assertIsNot(self.service.feeds[self.s["id"]], first)
        self.source.fetch.assert_called_once()

    def test_real_collector_thread_consumes_scripted_socket_and_closes(self):
        self.create("15m")
        session = self.head()
        feed = fixture_c02_feed(
            self.settings, "local", session, self.base, threading.Event(), self.clock
        )
        self.addCleanup(feed.close)
        feed.start()
        # A bounded wait for an actual recorded socket event, not a fake view.
        import time

        deadline = time.monotonic() + 3
        while not feed.last_message_ms and time.monotonic() < deadline:
            feed.wake.wait(0.1)
            feed.wake.clear()
        self.assertGreater(feed.last_message_ms, 0)
        self.assertIsNotNone(feed.view("BTCUSDT")["forming"])
        feed.close()
        self.assertFalse(feed.thread.is_alive())
        with feed.store.connection() as db:
            self.assertGreater(
                db.execute("SELECT count(*) FROM events WHERE final=0").fetchone()[0], 0
            )


if __name__ == "__main__":
    unittest.main()
