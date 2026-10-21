# Strategy candidates

C08 detects **potential setups**, before expectancy, execution and portfolio admission. A candidate is not automatically an eligible trade, a funded paper position or a Telegram message.

## Implemented families

| Family | Meaning | Preset |
| --- | --- | --- |
| `prior_range_breakout` | Closed-bar breakout of the preceding completed-bar range; current bar is excluded from that reference range | [Range preset](../../../configs/c08_range_breakout.json) |
| `ema_pullback_continuation` | Closed-bar recovery across EMA20 in the EMA20/EMA50 trend direction, using the defined prior/current snapshots | [Continuation preset](../../../configs/c08_trend_continuation.json) |

Both presets currently target 15-minute long/short candidates. Trend v1 uses fixed EMA20/EMA50 definitions; its range-lookback field is not an alternative trend tuning knob. The exact conditions are in [C08 implementation](../../components/c08/C08_IMPLEMENTATION.md).

## Inspect or run independently

Prerequisites: C01 observations, a pinned C02 dataset and sufficient valid/stable feature history. These local computations do not contact Binance or Telegram.

```sh
conda activate tradee
python -m tradee candidates list
python -m tradee candidates explain prior_range_breakout
python -m tradee candidates explain ema_pullback_continuation
python -m tradee candidates run DATASET_HASH \
  --strategy configs/c08_range_breakout.json --config configs/c08_candidates.json
python -m tradee candidates summary RUN_HASH
python -m tradee candidates records RUN_HASH --limit 100
```

To study the other family, supply `configs/c08_trend_continuation.json`. The dashboard has no separate C08 “run detector” job; its **simulation** job uses declared C11 scenarios to run both families through the shared pipeline. Inspect resulting candidates in Research; prospective admitted/rejected candidates appear in Signals after paper cycles.

## Configuration and result checks

Review timeframe, sides, entry window, cooldown, lookback and explicit metadata/universe policy. Entry expiry is tied to the target closed bar; late receipt does not extend it. Record the complete evaluation inventory, including no-setup, invalid and excluded decisions, rather than only successes.

Zero candidates can be a correct completed result. Check coverage, feature stability and exclusion reasons before changing thresholds. Detection quantity/stop/target/holding behavior belongs to the [scenario/lifecycle](EXECUTION_AND_COSTS.md), not this detector alone. A `swing` label does not automatically extend a preset's timeframe or holding duration.

Related: [features](FEATURE_ENGINE.md), [backtesting](BACKTESTING.md), [signals](SIGNALS.md).
