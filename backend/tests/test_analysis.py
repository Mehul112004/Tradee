import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from tradee.c01 import ValidationError
from tradee.c14 import DeliveryResult
from backend.tradee_web.analysis import (
    AnalysisService,
    AnalysisStore,
    validate_spec,
    parse_candles,
    evaluate,
    levels,
    alert_text,
)
from backend.tradee_web.app import create_app
from backend.tradee_web.config import Settings, Profile, KINDS
from .analysis_support import candle, FixtureCandleSource, FixtureFeed


def spec(**overrides):
    return dict(
        name="BTC watch",
        symbols=["BTCUSDT"],
        timeframe="1m",
        strategies=["prior_range_breakout", "ema_pullback_continuation"],
        mode="live",
        history_bars=100,
        telegram=False,
        **overrides,
    )


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.settings = Settings(
            (
                Profile(
                    "local", "Local", {k: str(root / f"{k}.sqlite3") for k in KINDS}
                ),
                Profile(
                    "synthetic",
                    "Synthetic",
                    {k: str(root / f"synthetic_{k}.sqlite3") for k in KINDS},
                    True,
                ),
            ),
            state_path=root / "web.sqlite3",
            operator_token="test",
        )
        self.clock = [1800000000.0]
        self.service = AnalysisService(
            self.settings,
            source=FixtureCandleSource(),
            clock=lambda: self.clock[0],
            feed_factory=FixtureFeed,
        )
        self.service.metadata = lambda *args: None
        self.store = self.service.store
        self.env = patch("os.environ", {"PYTHON_DOTENV_DISABLED": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def create(self, **kwargs):
        value = spec()
        value.update(kwargs)
        return self.store.create("local", value, "key", int(self.clock[0] * 1000))

    def test_settings_and_idempotency(self):
        s = self.create()
        self.assertEqual(s["id"], self.create()["id"])
        with self.assertRaises(ValidationError):
            self.create(name="different")
        for changes in (
            {"symbols": ["BTCUSD"]},
            {"timeframe": "5m"},
            {"strategies": []},
            {"mode": "history", "telegram": True},
            {"history_bars": True},
            {"symbols": ["../../etc"]},
        ):
            d = spec()
            d.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                validate_spec(d)

    def test_closed_candles_validation_and_partial_exclusion(self):
        raw = [
            [0, "100", "101", "99", "100", "10", 59999, "1000", 4, "5", "500", "0"],
            [
                60000,
                "100",
                "101",
                "99",
                "100",
                "10",
                119999,
                "1000",
                4,
                "5",
                "500",
                "0",
            ],
        ]
        self.assertEqual(len(parse_candles(raw, 60000, 90000)), 1)
        for change in (
            lambda d: d[0].__setitem__(2, "90"),
            lambda d: d[0].__setitem__(0, 1),
            lambda d: d.append(d[0]),
        ):
            d = copy.deepcopy(raw)
            change(d)
            with self.assertRaises(ValidationError):
                parse_candles(d, 60000, 180000)

    def test_range_uses_prior_bars_and_not_wick_or_equality(self):
        rows = [candle(t * 60000) for t in range(21)]
        d = spec()
        d["strategies"] = ["prior_range_breakout"]
        rows[-1]["high"] = "500"
        self.assertFalse(evaluate(rows, d, 0)["setups"])
        rows[-1]["close"] = "101"
        self.assertFalse(evaluate(rows, d, 0)["setups"])
        rows[-1]["close"] = "102"
        signal = evaluate(rows, d, 0)["setups"][0]
        self.assertEqual(signal["side"], "long")
        self.assertEqual(signal["trigger_level"], "101")
        self.assertTrue(
            all(l["confirmed_ms"] <= signal["end_ms"] for l in signal["levels"])
        )

    def test_gap_resets_ema_and_range_warmup(self):
        rows = [candle(t * 60000) for t in range(450)]
        result = evaluate(rows, spec(), 0)
        self.assertTrue(all(result["readiness"].values()))
        result = evaluate(rows[:420] + rows[425:], spec(), 0)
        self.assertFalse(result["readiness"]["ema_pullback_continuation"])
        self.assertEqual(result["contiguous_bars"], 25)
        self.assertFalse(
            evaluate(rows[:420] + rows[440:], spec(), 0)["readiness"][
                "prior_range_breakout"
            ]
        )

    def test_shared_ema_strategy_predicate(self):
        from tradee.c03.evaluator import Evaluator
        from tradee.c08.strategy import trend_recovery

        rows = [candle(t * 60000, price=str(100 + t // 8)) for t in range(410)]
        rows += [candle(410 * 60000, price="140"), candle(411 * 60000, price="160")]
        result = evaluate(rows, spec(), 0)
        previous = Evaluator(rows[:-1])
        current = Evaluator(rows)
        expected = trend_recovery(
            rows[-2],
            rows[-1],
            {k: previous.get(k).document() for k in ("ema20", "ema50")},
            {k: current.get(k).document() for k in ("ema20", "ema50")},
        )
        actual = [
            s
            for s in result["setups"]
            if s["strategy"] == "ema_pullback_continuation"
            and s["open_ms"] == rows[-1]["open_ms"]
        ]
        self.assertTrue(expected["long"])
        self.assertEqual([s["side"] for s in actual], ["long"])
        self.assertEqual(actual[0]["trigger_level"], expected["level"])

    def test_levels_require_pivot_confirmation_and_complete_previous_day(self):
        rows = [candle(t * 60000) for t in range(1441)]
        rows[-3]["high"] = "110"
        self.assertNotIn(
            "Confirmed swing high", [l["label"] for l in levels(rows[:-1], 60000)]
        )
        refs = levels(rows, 60000)
        self.assertIn("Confirmed swing high", [l["label"] for l in refs])
        self.assertIn("Previous UTC day · high", [l["label"] for l in refs])
        self.assertNotIn(
            "Previous UTC day · high", [l["label"] for l in levels(rows[1:], 60000)]
        )

    def test_previous_day_rolls_at_midnight_close_including_daily_timeframe(self):
        rows = [candle(t * 60000) for t in range(1440)]
        rows[-1]["high"] = "105"
        refs = {l["label"]: l for l in levels(rows, 60000)}
        self.assertEqual(refs["Previous UTC day · high"]["price"], "105")
        self.assertEqual(refs["Previous UTC day · high"]["confirmed_ms"], 86400000)
        daily = [candle(0, 86400000, "100"), candle(86400000, 86400000, "110")]
        refs = {l["label"]: l for l in levels(daily, 86400000)}
        self.assertEqual(refs["Previous UTC day · high"]["price"], "111")

    def test_display_swings_do_not_bridge_missing_candles(self):
        rows = [candle(t * 60000) for t in (0, 1, 2, 4, 5)]
        rows[2]["high"] = "110"
        self.assertNotIn("Confirmed swing high", [l["label"] for l in levels(rows, 60000)])

    def test_display_levels_preserve_late_receipt_and_market_confirmation(self):
        rows = [candle(t * 60000) for t in range(5)]
        rows[2]["high"] = "110"
        for r in rows:
            r["available_ms"] = r["open_ms"] + 63000
        swing = next(l for l in levels(rows, 60000) if l["label"] == "Confirmed swing high")
        self.assertEqual(swing["confirmed_ms"], 300000)
        self.assertEqual(swing["known_ms"], 303000)

    def test_history_scan_creates_results_without_telegram(self):
        s = self.create(mode="history")
        with patch(
            "backend.tradee_web.analysis.telegram_config",
            side_effect=AssertionError("No send"),
        ):
            self.service.tick("local", s["id"])
        result = self.store.get("local", s["id"])
        self.assertEqual(result["state"], "completed")
        self.assertGreater(result["setup_count"], 0)
        self.assertTrue(all(x["delivery"] == "historical" for x in result["setups"]))
        self.assertTrue(
            result["detail"]["BTCUSDT"]["readiness"]["ema_pullback_continuation"]
        )

    def test_live_pause_resume_stop_and_no_duplicate_setups(self):
        s = self.create()
        self.service.tick("local", s["id"])
        count = self.store.get("local", s["id"])["setup_count"]
        self.service.tick("local", s["id"])
        self.assertEqual(self.store.get("local", s["id"])["setup_count"], count)
        self.store.control("local", s["id"], "pause", int(self.clock[0] * 1000))
        self.clock[0] += 60000
        self.service.tick("local", s["id"])
        self.assertEqual(self.store.get("local", s["id"])["setup_count"], count)
        self.store.control("local", s["id"], "resume", int(self.clock[0] * 1000))
        self.service.tick("local", s["id"])
        self.store.control("local", s["id"], "stop", int(self.clock[0] * 1000))
        with self.assertRaises(ValidationError):
            self.store.control("local", s["id"], "resume", int(self.clock[0] * 1000))

    def pending(self, uid, expiry=None):
        now = int(self.clock[0] * 1000)
        signal = dict(
            id="signal1",
            symbol="BTCUSDT",
            side="long",
            strategy_name="Range breakout",
            end_ms=now,
            expires_ms=expiry or now + 60000,
            explanation="Closed above the prior high",
            price="110",
            trigger_level="101",
        )
        with self.store.connection() as db:
            db.execute(
                "INSERT INTO analysis_setups VALUES(?,?,?,?,?,?,NULL,NULL)",
                ("signal1", uid, "BTCUSDT", now, json.dumps(signal), "pending"),
            )
        return signal

    def test_telegram_durable_claim_no_duplicate_or_ambiguous_retry(self):
        from unittest.mock import Mock

        transport = Mock()
        transport.send.return_value = DeliveryResult("ambiguous", "timeout")
        with patch(
            "backend.tradee_web.analysis.telegram_config",
            return_value=(transport, 12345, 67890),
        ):
            s = self.create(telegram=True)
            sig = self.pending(s["id"])
            self.service.dispatch("local", s["id"])
            self.service.dispatch("local", s["id"])
            transport.send.assert_called_once()
            self.assertEqual(
                self.store.get("local", s["id"])["setups"][0]["delivery"], "ambiguous"
            )
            text = alert_text(s, sig)
            self.assertIn("SETUP OBSERVATION", text)
            self.assertIn("not a validated trade recommendation", text)
            self.assertNotIn("67890", text)

    def test_expired_and_paused_setups_never_send(self):
        from unittest.mock import Mock

        transport = Mock()
        with patch(
            "backend.tradee_web.analysis.telegram_config",
            return_value=(transport, 12345, 67890),
        ):
            s = self.create(telegram=True)
            self.pending(s["id"], int(self.clock[0] * 1000) - 1)
            self.service.dispatch("local", s["id"])
            self.assertEqual(
                self.store.get("local", s["id"])["setups"][0]["delivery"], "expired"
            )
            transport.send.assert_not_called()
            with self.store.connection() as db:
                db.execute("UPDATE analysis_setups SET delivery='pending'")
            self.store.control("local", s["id"], "pause", int(self.clock[0] * 1000))
            self.service.dispatch("local", s["id"])
            transport.send.assert_not_called()

    def test_rate_limit_blocks_other_setups_without_retrying_failed_message(self):
        from unittest.mock import Mock

        transport = Mock()
        transport.send.return_value = DeliveryResult(
            "retry", "telegram_rate_limited", retry_after_ms=30000
        )
        with patch(
            "backend.tradee_web.analysis.telegram_config",
            return_value=(transport, 12345, 67890),
        ):
            s = self.create(telegram=True)
            self.pending(s["id"])
            self.service.dispatch("local", s["id"])
            with self.store.connection() as db:
                old = db.execute(
                    "SELECT * FROM analysis_setups WHERE id='signal1'"
                ).fetchone()
                db.execute(
                    "INSERT INTO analysis_setups VALUES(?,?,?,?,?,?,NULL,NULL)",
                    (
                        "signal2",
                        s["id"],
                        "BTCUSDT",
                        old["end_ms"],
                        old["document"],
                        "pending",
                    ),
                )
            self.clock[0] += 4
            self.service.dispatch("local", s["id"])
            transport.send.assert_called_once()
            self.clock[0] += 27
            self.service.dispatch("local", s["id"])
            self.assertEqual(transport.send.call_count, 2)

    def test_restart_pauses_sessions_and_preserves_uncertain_delivery(self):
        s = self.create()
        self.pending(s["id"])
        with self.store.connection() as db:
            db.execute("UPDATE analysis_setups SET delivery='sending'")
        self.service.start()
        self.service.close()
        h = self.store.get("local", s["id"])
        self.assertEqual(h["state"], "paused")
        self.assertEqual(h["setups"][0]["delivery"], "ambiguous")

    def test_api_auth_workspace_isolation_and_readonly_domain_sources(self):
        app = create_app(self.settings)
        client = TestClient(app)
        self.addCleanup(client.close)
        self.assertEqual(
            client.post("/api/local/analysis", json=spec()).status_code, 401
        )
        headers = {"Authorization": "Bearer test", "Idempotency-Key": "api-create"}
        result = client.post("/api/local/analysis", json=spec(), headers=headers)
        self.assertEqual(result.status_code, 200, result.text)
        uid = result.json()["data"]["id"]
        self.assertEqual(client.get(f"/api/synthetic/analysis/{uid}").status_code, 404)
        self.assertEqual(
            client.post(
                "/api/synthetic/analysis", json=spec(), headers=headers
            ).status_code,
            422,
        )
        self.assertEqual(client.get(f"/api/local/analysis/{uid}").status_code, 200)
        self.assertTrue(
            all(not self.settings.profile("local").path(k).exists() for k in KINDS)
        )
        self.assertEqual(
            client.post(
                f"/api/local/analysis/{uid}/control",
                json={"action": "stop"},
                headers=headers,
            ).status_code,
            200,
        )
        self.assertEqual(
            client.post(
                "/api/local/analysis",
                json=spec(),
                headers={**headers, "Origin": "https://evil.test"},
            ).status_code,
            403,
        )

    def test_new_live_candle_sends_once_and_initial_history_never_sends(self):
        from unittest.mock import Mock

        transport = Mock()
        transport.send.return_value = DeliveryResult("sent", "telegram_accepted", 42)
        self.clock[0] += 3
        with patch(
            "backend.tradee_web.analysis.telegram_config",
            return_value=(transport, 12345, 67890),
        ):
            s = self.create(telegram=True, strategies=["prior_range_breakout"])
            self.service.tick("local", s["id"])
            transport.send.assert_not_called()
            self.clock[0] += 50 * 60
            self.service.tick("local", s["id"])
            transport.send.assert_called_once()
            self.service.tick("local", s["id"])
            transport.send.assert_called_once()
            h = self.store.get("local", s["id"])
            self.assertEqual(h["setups"][0]["delivery"], "sent")
            self.assertEqual(h["setups"][0]["message_id"], 42)

    def test_resume_does_not_send_setups_formed_while_paused(self):
        from unittest.mock import Mock

        transport = Mock()
        self.clock[0] += 3
        with patch(
            "backend.tradee_web.analysis.telegram_config",
            return_value=(transport, 12345, 67890),
        ):
            s = self.create(telegram=True)
            self.service.tick("local", s["id"])
            self.store.control("local", s["id"], "pause", int(self.clock[0] * 1000))
            self.clock[0] += 50 * 60
            self.store.control("local", s["id"], "resume", int(self.clock[0] * 1000))
            self.service.tick("local", s["id"])
            transport.send.assert_not_called()
            self.assertTrue(
                all(
                    x["delivery"] == "historical"
                    for x in self.store.get("local", s["id"])["setups"]
                )
            )

    def test_metadata_uses_real_registry_eligibility(self):
        import time
        from tradee.c01.provider import FetchResult

        raw = (
            Path(__file__).resolve().parents[2] / "tests/fixtures/exchange_info.json"
        ).read_text()
        now = int(time.time() * 1000)
        s = self.create()
        with patch("backend.tradee_web.analysis.BinanceProvider") as provider:
            provider.return_value.fetch.return_value = FetchResult(
                raw, "synthetic:unit metadata", now
            )
            AnalysisService.metadata(self.service, "local", s, now)
            s["spec"]["symbols"] = ["MISSINGUSDT"]
            with self.assertRaisesRegex(ValidationError, "no_observed_metadata"):
                AnalysisService.metadata(self.service, "local", s, now)

    def test_reserved_research_ranges_block_acquisition_and_saved_views(self):
        from unittest.mock import Mock
        from backend.tradee_web.readers import LockedEvidence

        s = self.create()
        self.service.tick("local", s["id"])
        source = self.service.source = Mock()
        with patch(
            "backend.tradee_web.readers.AccessPolicy.range",
            side_effect=LockedEvidence("Reserved evidence"),
        ):
            with self.assertRaises(LockedEvidence):
                self.service.tick("local", s["id"])
            source.fetch.assert_not_called()
            client = TestClient(create_app(self.settings))
            self.addCleanup(client.close)
            self.assertEqual(
                client.get(f"/api/local/analysis/{s['id']}").status_code, 423
            )
            self.assertEqual(client.get("/api/local/analysis").status_code, 423)

    def test_revisions_preserved_and_running_limit_applies_to_resume(self):
        s = self.create()
        row = candle(0)
        self.store.save_bars(s["id"], "BTCUSDT", [row], 1)
        row["high"] = "102"
        self.store.save_bars(s["id"], "BTCUSDT", [row], 2)
        with self.store.connection() as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM analysis_bar_revisions").fetchone()[0],
                2,
            )
        self.store.control("local", s["id"], "pause", 3)
        for i in range(5):
            self.store.create(
                "local", spec(), f"another-{i}", int(self.clock[0] * 1000)
            )
        with self.assertRaisesRegex(ValidationError, "at most five"):
            self.store.control("local", s["id"], "resume", 4)


if __name__ == "__main__":
    unittest.main()
