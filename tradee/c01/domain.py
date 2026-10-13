"""Pure contracts and validation. No network or persistence imports."""

from dataclasses import dataclass
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json


class ValidationError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def symbol_name(value):
    # Binance now lists Unicode asset symbols too; preserve its exact identifier.
    if not isinstance(value, str) or not 2 <= len(value) <= 100 or not all(c.isalnum() or c == "_" for c in value):
        raise ValidationError(f"Invalid exchange symbol: {value!r}")
    return value


@dataclass(frozen=True)
class Policy:
    enabled: tuple[str, ...] = ("BTCUSDT", "ETHUSDT")
    max_age_seconds: int = 1800

    def __post_init__(self):
        if not isinstance(self.enabled, (tuple, list, set, frozenset)):
            raise ValidationError("Enabled universe must be a collection of symbols")
        if not self.enabled:
            raise ValidationError("Enabled universe must not be empty")
        object.__setattr__(self, "enabled", tuple(sorted({symbol_name(s) for s in self.enabled})))
        if type(self.max_age_seconds) is not int or self.max_age_seconds <= 0:
            raise ValidationError("max_age_seconds must be a positive integer")

    def document(self):
        return {"schema_version": 1, "provider": "binance", "product": "usdt_crypto_perpetual",
                "enabled": list(self.enabled), "max_age_seconds": self.max_age_seconds}


def decimal_value(value):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValidationError("Trading constraints must use exact decimal strings or integers")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValidationError("Invalid trading constraint") from exc
    if not result.is_finite() or result < 0:
        raise ValidationError("Trading constraint must be finite and nonnegative")
    return result


def normalize(payload):
    """Reject broken envelopes, quarantine individual unsupported/incomplete contracts.

    Raw payloads are retained separately. Unknown filters are preserved and flagged;
    they must never silently become permission to issue a live trade signal.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list) or not payload["symbols"]:
        raise ValidationError("exchangeInfo requires a nonempty symbols array")
    results, seen = [], set()
    known = {"PRICE_FILTER", "LOT_SIZE", "MARKET_LOT_SIZE", "MIN_NOTIONAL", "PERCENT_PRICE",
             "MAX_NUM_ORDERS", "MAX_NUM_ALGO_ORDERS", "POSITION_RISK_CONTROL"}
    required_filters = {"PRICE_FILTER": ("minPrice", "maxPrice", "tickSize"),
                        "LOT_SIZE": ("minQty", "maxQty", "stepSize"),
                        "MARKET_LOT_SIZE": ("minQty", "maxQty", "stepSize"),
                        "MIN_NOTIONAL": ("notional",)}
    for raw in payload["symbols"]:
        if not isinstance(raw, dict):
            raise ValidationError("Invalid symbol record")
        raw = deepcopy(raw)
        symbol = symbol_name(raw.get("symbol"))
        if symbol in seen:
            raise ValidationError(f"Duplicate symbol: {symbol}")
        seen.add(symbol)
        issues = []
        identity = {k: raw.get(k) for k in ("symbol", "baseAsset", "quoteAsset", "marginAsset", "contractType", "onboardDate")}
        for key in ("baseAsset", "quoteAsset", "marginAsset", "contractType", "status", "underlyingType"):
            if not isinstance(raw.get(key), str) or not raw[key]:
                issues.append(f"missing_or_invalid:{key}")
        if type(raw.get("onboardDate")) is not int or raw["onboardDate"] < 0:
            issues.append("missing_or_invalid:onboardDate")
        filters = {}
        if not isinstance(raw.get("filters"), list):
            issues.append("missing_or_invalid:filters")
        else:
            for item in raw["filters"]:
                if not isinstance(item, dict) or not isinstance(item.get("filterType"), str):
                    issues.append("invalid_filter")
                    continue
                kind = item["filterType"]
                if kind in filters:
                    issues.append(f"duplicate_filter:{kind}")
                filters[kind] = item
                if kind not in known:
                    issues.append(f"unsupported_filter:{kind}")
        constraints = {}
        for kind, fields in required_filters.items():
            for field in fields:
                try:
                    value = decimal_value(filters.get(kind, {}).get(field))
                    if field in ("tickSize", "stepSize") and value == 0:
                        raise ValidationError("Zero increment unsupported in C01")
                    constraints[f"{kind}.{field}"] = str(value)
                except ValidationError:
                    issues.append(f"missing_or_invalid:{kind}.{field}")
            keys = ("minPrice", "maxPrice") if kind == "PRICE_FILTER" else ("minQty", "maxQty")
            lo, hi = (constraints.get(f"{kind}.{k}") for k in keys)
            if lo is not None and hi is not None and Decimal(hi) != 0 and Decimal(lo) > Decimal(hi):
                issues.append(f"inverted_bounds:{kind}")
        optional_numeric = {"PERCENT_PRICE": ("multiplierUp", "multiplierDown", "multiplierDecimal"),
                            "MAX_NUM_ORDERS": ("limit",), "MAX_NUM_ALGO_ORDERS": ("limit",)}
        for kind, fields in optional_numeric.items():
            if kind not in filters:
                continue
            for field in fields:
                try:
                    value = decimal_value(filters[kind].get(field))
                    if field in ("limit", "multiplierDecimal") and value != value.to_integral_value():
                        raise ValidationError("Integer constraint required")
                    if field in ("multiplierUp", "multiplierDown") and value == 0:
                        raise ValidationError("Positive multiplier required")
                except ValidationError:
                    issues.append(f"missing_or_invalid:{kind}.{field}")
        if "POSITION_RISK_CONTROL" in filters:
            # Only unrestricted contracts are supported by the initial policy.
            if filters["POSITION_RISK_CONTROL"].get("positionControlSide") != "NONE":
                issues.append("unsupported_position_risk_control")
        for field in ("orderTypes", "timeInForce"):
            value = raw.get(field)
            if not isinstance(value, list) or not value or not all(isinstance(v, str) and v for v in value):
                issues.append(f"missing_or_invalid:{field}")
        scope = (raw.get("contractType") == "PERPETUAL" and raw.get("quoteAsset") == "USDT"
                 and raw.get("marginAsset") == "USDT" and raw.get("underlyingType") == "COIN")
        spec = {"schema_version": 1, "venue": "binance", "product": "usds_futures",
                **identity, "status": raw.get("status"), "underlyingType": raw.get("underlyingType"),
                "deliveryDate": raw.get("deliveryDate"), "filters": filters, "constraints": constraints,
                "orderTypes": sorted(set(raw.get("orderTypes", []))) if isinstance(raw.get("orderTypes"), list) and all(isinstance(v,str) for v in raw["orderTypes"]) else [],
                "timeInForce": sorted(set(raw.get("timeInForce", []))) if isinstance(raw.get("timeInForce"), list) and all(isinstance(v,str) for v in raw["timeInForce"]) else [],
                "triggerProtect": raw.get("triggerProtect"), "marketTakeBound": raw.get("marketTakeBound"),
                "scope_supported": scope, "issues": sorted(set(issues))}
        spec["instrument_id"] = "binance:usds_futures:" + symbol + ":" + fingerprint(identity)[:16]
        results.append(spec)
    return results
