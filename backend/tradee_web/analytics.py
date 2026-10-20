"""Display-only projections. Never supply admission or statistical decisions.

Exact core outputs remain in every response. Decimal arithmetic is used only for
unit-preserving display transforms (drawdown, ledger signs, fixed-bin counts).
"""

from decimal import Decimal, localcontext
from collections import Counter


def funded(repo, name, at_ms=None):
    p = repo.portfolio(name, at_ms)
    if not p["available"]:
        return p
    with localcontext() as ctx:
        ctx.prec = 400
        peak = Decimal(p["report"]["metrics"]["initial_equity_usdt"])
        rows = []
        for sample in p["samples"]:
            value = sample["equity_usdt"]
            dd = None
            fraction = None
            if value is not None:
                equity = Decimal(value)
                peak = max(peak, equity)
                dd = str(equity - peak)
                fraction = str((equity - peak) / peak) if peak else None
            rows.append(
                dict(
                    at_ms=sample["at_ms"], drawdown_usdt=dd, drawdown_fraction=fraction
                )
            )
        exposure = p["risk"]["exposure"]
        equity = p["risk"]["equity_usdt"]
        risk = []
        for key, field in [
            ("gross_notional_usdt", "gross_notional_fraction"),
            ("stop_risk_usdt", "total_risk_fraction"),
            ("collateral_reserved_usdt", "collateral_fraction"),
            ("absolute_beta_notional_usdt", "absolute_beta_notional_fraction"),
            ("worst_stress_loss_usdt", "max_stress_loss_fraction"),
        ]:
            risk.append(
                dict(
                    name=key,
                    value=exposure[key],
                    limit=(
                        None
                        if equity is None
                        else str(Decimal(equity) * Decimal(p["policy"][field]))
                    ),
                )
            )
    return dict(
        drawdown=rows,
        risk=risk,
        distribution=distribution([t["outcome"] for t in p["trades"]]),
        source_report=p["report_hash"],
        scope=p["scope"],
        sampling="none",
        drawdown_contract="equity minus running known peak, starting with initial capital; unknown values are gaps",
    )


def distribution(outcomes):
    edges = [
        None,
        Decimal("-2"),
        Decimal("-1"),
        Decimal("0"),
        Decimal("1"),
        Decimal("2"),
        None,
    ]
    labels = ["< -2", "[-2, -1)", "[-1, 0)", "[0, 1)", "[1, 2)", "≥ 2"]
    bins = [dict(name=name, count=0, rows=[]) for name in labels]
    omitted = 0
    for o in outcomes:
        if o.get("label_status") != "mature" or o.get("net_r") is None:
            omitted += 1
            continue
        value = Decimal(o["net_r"])
        for i in range(6):
            if (edges[i] is None or value >= edges[i]) and (
                edges[i + 1] is None or value < edges[i + 1]
            ):
                bins[i]["count"] += 1
                bins[i]["rows"].append(o)
                break
    return dict(
        bins=bins,
        mature=sum(b["count"] for b in bins),
        omitted=omitted,
        units="net R",
        contract="Fixed half-open bins of mature outcomes only; no estimated/unknown outcomes",
    )


def lineage(repo, name, at_ms=None):
    s = repo.session(name, at_ms)
    m = s["manifest"]
    c = s["cycle"]
    nodes = []

    def add(kind, h, label):
        if h:
            nodes.append(dict(kind=kind, hash=h, label=label))

    add("c12", m["research"]["experiment_hash"], "Research experiment")
    add("c10", m["research"]["model_hash"], "Frozen expectancy model")
    add("c14", s["deployment_hash"], "Frozen deployment")
    if c:
        add("c02", c["dataset"]["dataset_hash"], "Pinned market dataset")
        add("c11", c["simulation"]["run_hash"], "Independent simulation")
        add("c13", c["portfolio"]["run_hash"], "Funded replay")
        add("c14", s["cycle_hash"], "Paper cycle")
    return dict(
        nodes=nodes,
        scope=s["view"],
        audit_head=s["audit_head"],
        note="Curated references; artifacts remain subject to access gates",
    )


def coverage_calendar(dataset, quality):
    """UTC-day expected minute coverage; never infer trade/quote completeness."""
    start = dataset["start_ms"]
    end = dataset["end_ms"]
    day = 86400000
    if (end - start) // 60000 > 500000:
        from .readers import SourceError

        raise SourceError(
            "Quality calendar range budget exceeded; pin a smaller dataset"
        )
    if "candle" not in dataset["kinds"]:
        return []
    result = []
    for symbol in quality["symbols"]:
        for boundary in range(start // day * day, end, day):
            lo = max(start, boundary)
            hi = min(end, boundary + day)
            missing = sum(
                max(0, min(hi, g["end_ms"]) - max(lo, g["start_ms"])) // 60000
                for g in symbol["gaps"]
            )
            expected = (hi - lo) // 60000
            result.append(
                dict(
                    symbol=symbol["symbol"],
                    day_ms=boundary,
                    expected=expected,
                    finalized=expected - missing,
                    missing=missing,
                )
            )
    return result
