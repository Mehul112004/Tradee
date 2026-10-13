"""Contract validation and invariants, including adversarial provider shapes."""

import copy
from decimal import Decimal
import random
import unittest

from tradee.c01 import Policy, ValidationError
from tradee.c01.domain import decimal_value, fingerprint, normalize, symbol_name
from tests.support import payload, contract, rule


class DomainContractTests(unittest.TestCase):
    def test_nonfinite_and_lossy_decimals_rejected(self):
        for value in (True, False, 0.1, float("inf"), "NaN", "sNaN", "Infinity", "-Infinity", "-0.01", {}, [], None, "bad"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                decimal_value(value)

    def test_small_and_large_decimals_remain_exact(self):
        for value in ("0.00000000000000000001", "123456789012345678901234567890.123456789", "1E-20", "0", 17):
            with self.subTest(value=value):
                self.assertEqual(decimal_value(value), Decimal(value))

    def test_policy_rejects_invalid_ttl_and_container(self):
        for ttl in (True, False, 0, -1, 1.5, "1800", None):
            with self.subTest(ttl=ttl), self.assertRaises(ValidationError):
                Policy(max_age_seconds=ttl)
        for enabled in (None, "BTCUSDT", 42, {"BTCUSDT": 1}):
            with self.subTest(enabled=enabled), self.assertRaises(ValidationError):
                Policy(enabled=enabled)

    def test_policy_detaches_from_mutable_input_and_has_stable_hash(self):
        symbols = ["ETHUSDT", "BTCUSDT", "ETHUSDT"]
        p = Policy(symbols)
        symbols.append("SOLUSDT")
        self.assertEqual(p.enabled, ("BTCUSDT", "ETHUSDT"))
        self.assertEqual(fingerprint(p.document()), fingerprint(Policy().document()))

    def test_symbol_validation_preserves_unicode_and_rejects_separators(self):
        self.assertEqual(symbol_name("币安人生USDT"), "币安人生USDT")
        for value in (None, True, [], "B", "BTC USDT", "BTC/USDT", "BTC\nUSDT", "BTC\x00USDT", "A" * 101):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                symbol_name(value)

    def test_invalid_envelope_matrix(self):
        for value in (None, [], 1, "json", {}, {"symbols": None}, {"symbols": {}}, {"symbols": []}, {"symbols": [1]}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                normalize(value)

    def test_each_required_constraint_missing_is_flagged(self):
        fields = {"PRICE_FILTER": ("minPrice", "maxPrice", "tickSize"),
                  "LOT_SIZE": ("minQty", "maxQty", "stepSize"),
                  "MARKET_LOT_SIZE": ("minQty", "maxQty", "stepSize"),
                  "MIN_NOTIONAL": ("notional",)}
        for kind, keys in fields.items():
            for key in keys:
                with self.subTest(kind=kind, key=key):
                    data = payload()
                    del rule(data, kind)[key]
                    self.assertIn(f"missing_or_invalid:{kind}.{key}", normalize(data)[0]["issues"])

    def test_inverted_bounds_and_disabled_upper_bound(self):
        for kind, low, high in (("PRICE_FILTER", "minPrice", "maxPrice"),
                                ("LOT_SIZE", "minQty", "maxQty"),
                                ("MARKET_LOT_SIZE", "minQty", "maxQty")):
            with self.subTest(kind=kind):
                data = payload()
                rule(data, kind).update({low: "10", high: "1"})
                self.assertIn(f"inverted_bounds:{kind}", normalize(data)[0]["issues"])
                rule(data, kind)[high] = "0"
                self.assertNotIn(f"inverted_bounds:{kind}", normalize(data)[0]["issues"])

    def test_malformed_capabilities_are_quarantined_not_crashes(self):
        for field in ("orderTypes", "timeInForce"):
            for bad in (None, {}, [], [None], [{}], [""], ["MARKET", 1]):
                with self.subTest(field=field, bad=bad):
                    data = payload()
                    contract(data)[field] = bad
                    spec = normalize(data)[0]
                    self.assertIn(f"missing_or_invalid:{field}", spec["issues"])

    def test_known_optional_constraints_cannot_bypass_validation(self):
        for kind, field, bad in (("PERCENT_PRICE", "multiplierUp", "NaN"),
                                  ("PERCENT_PRICE", "multiplierDown", "-1"),
                                  ("MAX_NUM_ORDERS", "limit", -1)):
            with self.subTest(kind=kind):
                data = payload()
                rule(data, kind)[field] = bad
                self.assertIn(f"missing_or_invalid:{kind}.{field}", normalize(data)[0]["issues"])

    def test_shuffled_order_is_semantically_identical(self):
        original = payload()
        expected = {s["symbol"]: fingerprint(s) for s in normalize(original)}
        rng = random.Random(20260919)
        for _ in range(20):
            shuffled = copy.deepcopy(original)
            rng.shuffle(shuffled["symbols"])
            for s in shuffled["symbols"]:
                for key in ("filters", "orderTypes", "timeInForce"):
                    rng.shuffle(s[key])
            self.assertEqual({s["symbol"]: fingerprint(s) for s in normalize(shuffled)}, expected)
        self.assertEqual(original, payload(), "normalization must not mutate source data")

    def test_aliasing_cannot_change_normalized_rules(self):
        data = payload()
        spec = normalize(data)[0]
        rule(data, "PRICE_FILTER")["tickSize"] = "999"
        self.assertEqual(spec["filters"]["PRICE_FILTER"]["tickSize"], "0.10")

    def test_restricted_or_unknown_position_control_fails_closed(self):
        for value in (None, "", "SURPRISE", "LONG", "SHORT", {}):
            with self.subTest(value=value):
                data = payload()
                rule(data, "POSITION_RISK_CONTROL")["positionControlSide"] = value
                self.assertIn("unsupported_position_risk_control", normalize(data)[0]["issues"])

    def test_optional_numeric_filters_validate_all_fields(self):
        for kind, fields in (("PERCENT_PRICE", ("multiplierUp", "multiplierDown", "multiplierDecimal")),
                            ("MAX_NUM_ORDERS", ("limit",)), ("MAX_NUM_ALGO_ORDERS", ("limit",))):
            for field in fields:
                for bad in (None, True, "NaN", "-1", "bad", {}):
                    with self.subTest(kind=kind, field=field, bad=bad):
                        data = payload()
                        if kind == "MAX_NUM_ALGO_ORDERS":
                            contract(data)["filters"].append({"filterType": kind, "limit": 10})
                        rule(data, kind)[field] = bad
                        self.assertIn(f"missing_or_invalid:{kind}.{field}", normalize(data)[0]["issues"])

    def test_valid_optional_filters_and_absence_are_supported(self):
        data = payload()
        contract(data)["filters"].append({"filterType": "MAX_NUM_ALGO_ORDERS", "limit": 10})
        self.assertEqual(normalize(data)[0]["issues"], [])
        optional = {"PERCENT_PRICE", "MAX_NUM_ORDERS", "MAX_NUM_ALGO_ORDERS", "POSITION_RISK_CONTROL"}
        contract(data)["filters"] = [f for f in contract(data)["filters"] if f["filterType"] not in optional]
        self.assertEqual(normalize(data)[0]["issues"], [])

    def test_fractional_integer_constraints_and_zero_multipliers_rejected(self):
        for kind, field, value in (("MAX_NUM_ORDERS", "limit", "1.5"),
                                   ("PERCENT_PRICE", "multiplierDecimal", "1.5"),
                                   ("PERCENT_PRICE", "multiplierUp", "0"),
                                   ("PERCENT_PRICE", "multiplierDown", "0")):
            with self.subTest(kind=kind, field=field):
                data = payload()
                rule(data, kind)[field] = value
                self.assertIn(f"missing_or_invalid:{kind}.{field}", normalize(data)[0]["issues"])
