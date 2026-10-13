import copy
from contextlib import redirect_stdout, redirect_stderr
from decimal import Decimal
import io
import json
from pathlib import Path
import tempfile
import ssl
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from tradee.c01 import BinanceProvider, Policy, ProviderError, Registry, ValidationError
from tradee.c01.domain import normalize
from tradee.cli import main
from tradee.c01.provider import verified_urlopen


FIXTURE = json.loads((Path(__file__).parent / "fixtures/exchange_info.json").read_text())
NOW = 1_800_000_000_000


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = NOW
        self.path = Path(self.temp.name) / "registry.sqlite3"
        self.registry = Registry(self.path, clock=lambda: self.now / 1000)
        self.payload = copy.deepcopy(FIXTURE)

    def ingest(self):
        return self.registry.ingest(json.dumps(self.payload), observed_ms=self.now)

    def decisions(self, **kwargs):
        return {d["symbol"]: d for d in self.registry.universe(**kwargs)["decisions"]}

    def btc(self):
        return next(s for s in self.payload["symbols"] if s["symbol"] == "BTCUSDT")

    def test_discovery_separate_from_enabled(self):
        self.ingest()
        self.assertEqual(self.registry.universe()["members"], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(self.decisions()["SOLUSDT"]["reasons"], ["not_enabled"])
        self.assertEqual(self.registry.universe(Policy(("SOLUSDT",)))["members"], ["SOLUSDT"])

    def test_exact_filter_increment_not_display_precision(self):
        self.btc()["pricePrecision"] = 8
        self.ingest()
        spec = self.registry.version(self.decisions()["BTCUSDT"]["version_hash"])["spec"]
        self.assertEqual(Decimal(spec["constraints"]["PRICE_FILTER.tickSize"]), Decimal("0.10"))

    def test_unchanged_refresh_new_observation_same_version(self):
        self.ingest()
        first = self.decisions()["BTCUSDT"]
        self.now += 900_000
        self.btc()["filters"].reverse()
        result = self.ingest()
        self.assertEqual(result["new_versions"], 0)
        self.assertEqual(self.decisions()["BTCUSDT"]["version_hash"], first["version_hash"])
        self.assertEqual(self.decisions()["BTCUSDT"]["last_observed_ms"], self.now)

    def test_as_of_sees_old_rules_and_no_future(self):
        self.ingest()
        first = self.decisions()["BTCUSDT"]["version_hash"]
        self.now += 1000
        self.btc()["status"] = "SETTLING"
        self.ingest()
        self.assertEqual(self.decisions(as_of_ms=NOW)["BTCUSDT"]["version_hash"], first)
        self.assertEqual(self.decisions()["BTCUSDT"]["state"], "ineligible")
        self.assertEqual(self.decisions(as_of_ms=NOW-1)["BTCUSDT"]["reasons"], ["no_observed_metadata"])
        self.assertIsNone(self.registry.version(first)["effective_from_ms"])

    def test_restart_and_saved_snapshot_immutable(self):
        self.ingest()
        saved = self.registry.universe(save=True)
        self.now += 1000
        self.btc()["status"] = "SETTLING"
        self.ingest()
        restarted = Registry(self.path, clock=lambda: self.now / 1000)
        self.assertEqual(restarted.snapshot(saved["snapshot_hash"]), saved)
        self.assertEqual(len(restarted.history("BTCUSDT")), 2)

    def test_policy_hash_and_snapshot_change(self):
        self.ingest()
        a = self.registry.universe()
        b = self.registry.universe(Policy(("SOLUSDT",)))
        self.assertNotEqual(a["policy_hash"], b["policy_hash"])
        self.assertNotEqual(a["snapshot_hash"], b["snapshot_hash"])

    def test_missing_symbol_retained_but_not_refreshed(self):
        self.ingest()
        self.now += 1000
        self.payload["symbols"] = [s for s in self.payload["symbols"] if s["symbol"] != "BTCUSDT"]
        report = self.ingest()
        self.assertEqual(report["missing_from_response"], ["BTCUSDT"])
        d = self.decisions()["BTCUSDT"]
        self.assertEqual(d["state"], "unknown")
        self.assertEqual(d["last_observed_ms"], NOW)
        self.assertIn("missing_from_latest_response", d["reasons"])

    def test_failed_refresh_does_not_advance_freshness(self):
        self.ingest()
        self.now += 1_800_000
        class Broken:
            endpoint = "test"
            def fetch(self):
                raise ProviderError("offline")
        with self.assertRaises(ProviderError):
            self.registry.refresh(Broken())
        self.assertFalse(self.registry.health()["ready"])
        self.assertIn("stale_metadata", self.decisions()["BTCUSDT"]["reasons"])
        self.assertEqual(self.decisions()["BTCUSDT"]["last_observed_ms"], NOW)
        self.assertEqual(self.registry.health()["last_attempt"]["accepted"], 0)

    def test_malformed_envelope_and_duplicates_are_atomic(self):
        self.ingest()
        before = self.registry.universe()
        for bad in ({"symbols": []}, {}, {"symbols": [self.btc(), self.btc()]}, {"symbols": [None]}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    self.registry.ingest(json.dumps(bad))
                self.assertEqual(self.registry.universe(), before)

    def test_invalid_json_logged(self):
        with self.assertRaises(ValueError):
            self.registry.ingest("not json")
        self.assertEqual(self.registry.health()["counts"]["observations"], 1)

    def test_partial_rules_quarantine_only_affected_symbol(self):
        self.btc()["filters"] = []
        self.ingest()
        self.assertEqual(self.decisions()["BTCUSDT"]["state"], "unknown")
        self.assertEqual(self.registry.universe()["members"], ["ETHUSDT"])

    def test_new_filter_is_preserved_and_quarantined(self):
        self.btc()["filters"].append({"filterType": "NEW_RULE", "value": "1"})
        self.ingest()
        decision = self.decisions()["BTCUSDT"]
        self.assertIn("unsupported_filter:NEW_RULE", decision["reasons"])
        self.assertIn("NEW_RULE", self.registry.version(decision["version_hash"])["spec"]["filters"])

    def test_relisting_identity_conflict_remains_quarantined(self):
        self.ingest()
        original = self.btc()["onboardDate"]
        self.now += 1000
        self.btc()["onboardDate"] += 1
        self.ingest()
        self.assertIn("identity_conflict", self.decisions()["BTCUSDT"]["reasons"])
        self.now += 1000
        self.btc()["onboardDate"] = original
        self.ingest()
        self.assertIn("identity_conflict", self.decisions()["BTCUSDT"]["reasons"])

    def test_no_backdated_or_future_observations(self):
        self.ingest()
        for when in (NOW-1, NOW+1):
            with self.assertRaises(ValidationError):
                self.registry.ingest(json.dumps(self.payload), observed_ms=when)
        with self.assertRaises(ValidationError):
            self.registry.universe(as_of_ms=NOW+1)

    def test_explicit_product_filters(self):
        for field, value in (("marginAsset", "USDC"), ("quoteAsset", "USDC"),
                             ("contractType", "CURRENT_QUARTER"), ("underlyingType", "EQUITY")):
            row = copy.deepcopy(self.btc())
            row[field] = value
            self.assertFalse(normalize({"symbols": [row]})[0]["scope_supported"])

    def test_unicode_exchange_symbols_supported(self):
        row = copy.deepcopy(self.btc())
        row["symbol"] = "币安人生USDT"
        self.assertEqual(normalize({"symbols": [row]})[0]["symbol"], row["symbol"])

    def test_invalid_decimal_and_duplicate_filter(self):
        row = copy.deepcopy(self.btc())
        price = next(f for f in row["filters"] if f["filterType"] == "PRICE_FILTER")
        for value in ("NaN", "-1", 0.1, None, "0"):
            price["tickSize"] = value
            self.assertIn("missing_or_invalid:PRICE_FILTER.tickSize", normalize({"symbols": [row]})[0]["issues"])
        row["filters"].append(copy.deepcopy(price))
        self.assertIn("duplicate_filter:PRICE_FILTER", normalize({"symbols": [row]})[0]["issues"])

    def test_policy_validation(self):
        for symbols in ((), ("BTC/USDT",), ("",)):
            with self.assertRaises(ValidationError):
                Policy(symbols)
        self.assertEqual(Policy(("ETHUSDT", "BTCUSDT", "BTCUSDT")).enabled, ("BTCUSDT", "ETHUSDT"))

    def test_nonfinite_raw_payload_is_rejected(self):
        self.payload["unknownField"] = float("nan")
        with self.assertRaises(ValueError):
            self.ingest()
        self.assertFalse(self.registry.health()["ready"])

    def test_unsupported_database_schema_is_rejected(self):
        with self.registry.connection() as db:
            db.execute("PRAGMA user_version=99")
        with self.assertRaisesRegex(ValidationError, "schema version"):
            Registry(self.path)

    def test_cli_offline_roundtrip_and_invalid_time(self):
        args = ["--db", str(Path(self.temp.name) / "cli.sqlite3")]
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(args + ["import", str(Path(__file__).parent / "fixtures/exchange_info.json")]), 0)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(args + ["universe", "--save"]), 0)
        snapshot = json.loads(output.getvalue())
        self.assertEqual(snapshot["members"], ["BTCUSDT", "ETHUSDT"])
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(args + ["snapshot", snapshot["snapshot_hash"]]), 0)
        self.assertEqual(json.loads(output.getvalue()), snapshot)
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(args + ["universe", "--as-of", "2026-09-13T12:00:00"]), 1)

    def test_cli_empty_health_reports_not_ready(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--db", str(self.path), "health"]), 2)


class ProviderTests(unittest.TestCase):
    def test_macos_adds_system_ca(self):
        context = MagicMock()
        with patch.dict("os.environ", {}, clear=True), \
             patch("tradee.c01.provider.sys.platform", "darwin"), \
             patch("tradee.c01.provider.os.path.isfile", return_value=True), \
             patch("tradee.c01.provider.ssl.create_default_context", return_value=context), \
             patch("tradee.c01.provider.urlopen", return_value="response") as opener:
            self.assertEqual(verified_urlopen("request", 15), "response")
        context.load_verify_locations.assert_called_once_with(cafile="/etc/ssl/cert.pem")
        opener.assert_called_once_with("request", timeout=15, context=context)

    def test_tls_defaults_verify_certificates_and_hostname(self):
        with patch("tradee.c01.provider.sys.platform", "linux"), \
             patch("tradee.c01.provider.urlopen") as opener:
            verified_urlopen("request", 15)
        context = opener.call_args.kwargs["context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_explicit_ca_bundle_is_not_overridden(self):
        context = MagicMock()
        with patch.dict("os.environ", {"SSL_CERT_FILE": "/trusted/custom.pem"}), \
             patch("tradee.c01.provider.sys.platform", "darwin"), \
             patch("tradee.c01.provider.ssl.create_default_context", return_value=context), \
             patch("tradee.c01.provider.urlopen"):
            verified_urlopen("request", 15)
        context.load_verify_locations.assert_not_called()

    def test_certificate_failure_is_actionable_and_not_retried(self):
        calls = []
        def opener(*args, **kwargs):
            calls.append(1)
            raise URLError(ssl.SSLCertVerificationError("untrusted"))
        with self.assertRaisesRegex(ProviderError, "SSL_CERT_FILE") as caught:
            BinanceProvider(opener=opener).fetch()
        self.assertTrue(caught.exception.halt_polling)
        self.assertEqual(len(calls), 1)

    def test_success(self):
        provider = BinanceProvider(opener=lambda *a, **k: io.BytesIO(b'{"symbols":[]}'), clock=lambda: 123)
        result = provider.fetch()
        self.assertEqual(result.received_ms, 123000)
        self.assertTrue(result.source.startswith("https://fapi.binance.com"))

    def test_retry_then_success(self):
        sleeps = []
        responses = [URLError("offline"), io.BytesIO(b'{}')]
        def opener(*args, **kwargs):
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        self.assertEqual(BinanceProvider(opener=opener, sleep=sleeps.append).fetch().raw, '{}')
        self.assertEqual(sleeps, [0.5])

    def test_ban_and_client_errors_not_retried(self):
        for code in (418, 403, 451):
            calls = []
            def opener(*args, **kwargs):
                calls.append(1)
                raise HTTPError("test", code, "error", {}, None)
            with self.assertRaises(ProviderError):
                BinanceProvider(opener=opener).fetch()
            self.assertEqual(len(calls), 1)

    def test_respects_retry_after_and_defers_long_waits(self):
        sleeps = []
        def opener(*args, **kwargs):
            raise HTTPError("test", 429, "limited", {"Retry-After": "2"}, None)
        with self.assertRaises(ProviderError):
            BinanceProvider(opener=opener, sleep=sleeps.append).fetch()
        self.assertEqual(sleeps, [2.0, 2.0])
        def long_wait(*args, **kwargs):
            raise HTTPError("test", 429, "limited", {"Retry-After": "120"}, None)
        with self.assertRaisesRegex(ProviderError, "deferred"):
            BinanceProvider(opener=long_wait).fetch()

    def test_bad_json_is_not_retried(self):
        with self.assertRaisesRegex(ProviderError, "invalid JSON"):
            BinanceProvider(opener=lambda *a, **k: io.BytesIO(b'<html>')).fetch()


if __name__ == "__main__":
    unittest.main()
