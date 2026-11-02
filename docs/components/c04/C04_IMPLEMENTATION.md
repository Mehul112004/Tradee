# C04 market-context prerequisites

Implemented 1 November 2026 as authorized prerequisites for liquidity sweeps, EMA200 rejection and key-level retests. Those strategy families are **not defined or implemented in this increment**. C04 produces continuous observations; entry filters, regime thresholds and routing remain future strategy decisions.

## Scope and dependencies

`ContextEngine` consumes pinned C02 events through one C03 `FeatureEngine`. Each immutable `MarketStateSnapshot` contains the primary feature snapshot and all configured timeframe snapshots evaluated at the identical input prefix. Only completed, already available candles contribute. Each frame preserves its own target, age, validity and readiness; primary readiness does not certify other frames.

Measurements: EMA200/current-prior values; EMA200 distance in ATR14 units; five-bar EMA200 slope per bar in ATR14 units; ATR14; ATR/close; return dispersion; relative quote volume; candle taker imbalance. Observed spread, quote age and top-of-book notionals are optional diagnostics. Missing quotes do not block candle context. These are not full depth or evidence of resting stops. There are no trend/range labels, fitted regimes, probabilities, cross-asset predictors or calendar filters.

`ContextConfig` freezes timeframes, seed tolerance, quote freshness, candle grace and optional `[output_start_ms, output_end_ms)` target-open limits. Defaults `15m/1h/4h` are measurement presets, not a selected strategy horizon. Earlier dataset history still warms the engine when output starts later.

## EMA200 readiness

C03 adds `ema200`, `ema200_prior`, `ema200_distance_atr14` and `ema200_slope5_atr14` without changing the existing fourteen-feature baseline or old definitions. EMA uses an SMA seed over 200 closes, then `alpha=2/201`. Nominal minima are 200, 201, 200 and 205 contiguous bars respectively. Slope is `(EMA200[t]-EMA200[t-5])/(5*ATR14[t])`; distance is `(close[t]-EMA200[t])/ATR14[t]`.

At the existing seed-weight tolerance `1e-6`, EMA200 stabilizes after **1582** contiguous bars, its prior value after **1583**, and the slope after **1587**. Complete stable C04 context therefore needs 1587 bars: about 16.53 days at 15m, 66.13 days at 1h and 264.5 days at 4h. Gaps reset the recursive segment. A non-null value at 200 bars does not establish readiness. Zero ATR makes normalized measurements undefined.

## Operation and evidence

```sh
python -m tradee context explain
python -m tradee context run DATASET_HASH --config configs/c04_observations.json
python -m tradee context summary RUN_HASH
python -m tradee context records RUN_HASH --limit 20
python -m tradee context snapshot SNAPSHOT_HASH
python -m tradee context manifest RUN_HASH
python -m tradee context lineage LINEAGE_HASH
```

Global `--db` precedes `context`; `--market-db` and `--observation-db` precede its subcommand. Default output is `data/c04.sqlite3`, separate from registry/market stores. Commands replay local data without exchange connections. Historical/live callers share `ContextEngine.advance(event)`.

The manifest pins configuration, C02 dataset, complete child C03 manifest and producer source hash. Snapshots retain input prefix, feature identity and lineage. New corrections produce `trigger=revision` observations while retaining old snapshots. Atomic output/lineage/checkpoint commits support restart and idempotency. `completed` means all pinned events were consumed, not complete market history or full feature readiness.

The engines retain C03's prefix-reconstruction cost characteristics. Multi-year throughput, operational deployment and predictive value remain unvalidated. Source changes produce new research identities; old frozen releases retain their hashes. See [verification](C04_VERIFICATION.md) and [C05](../c05/C05_IMPLEMENTATION.md).

These measurements are not automatically wired into quick Analysis sessions. Before integrating a pilot, review [the analysis-flow contract](../../dashboard/ANALYSIS_FLOW.md#contract-for-the-next-pilot-strategy-pass), especially native-history versus canonical-minute inputs, multi-timeframe acquisition and the existing bootstrap/retention limits. Quick exploratory watching itself requires no research release.
