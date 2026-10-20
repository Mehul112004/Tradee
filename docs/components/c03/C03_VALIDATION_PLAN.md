# C03 validation and research acceptance plan

Approved validation specification — 21 September 2026. C03 is implemented; [C03_VERIFICATION.md](C03_VERIFICATION.md) maps completed checks and remaining scale/research limits. The full offline suite passes 196 tests, including 59 C03 tests. The sections below describe the acceptance criteria; detailed results are in the verification report.

## 1. Independent numerical reference cases

Do not derive expected fixtures by calling the feature function under test. Use hand-derived rational values where possible, a separate high-precision Decimal calculation for log/square-root examples, and explicitly versioned external-library fixtures for compatible named indicators. Record which reference conventions differ.

| Case | Input and convention | Expected output / failure to catch |
| --- | --- | --- |
| SMA and EMA seed | Closes `[1,2,3,4]`, n=3 | SMA seed at index 2 is 2; EMA seed also 2; next EMA is 3. Indices 0–1 unavailable |
| Wilder smoothing | Input `[1,2,3,4]`, n=3 | Seed 2; next `(2*2+4)/3 = 8/3`; distinguish from EMA alpha=1/2 |
| Return aggregation | Closes `[100,110,121]` | One-bar log returns both `ln(1.1)`; two-bar log return `2*ln(1.1)`; simple two-bar return `0.21` |
| True range gap | Prior close 100, current high 108, low 104 | TR=8 rather than high–low=4 |
| ATR seed/update | Previous-close-aware TR sequence `[3,5,4,7]`, n=3 | First ATR=4 after four price bars; next ATR=5; no fabricated TR at index 0 |
| Population/sample distinction | Values `[1,2,3,4,5]` | Population SD=`sqrt(2)`≈1.4142135623730951; sample SD=`sqrt(2.5)`≈1.5811388300841898 |
| Volatility definitions | Four returns each `0.01` | Centered return SD=0; squared-return variation=0.0004; its square root=0.02 |
| Prior return surprise | Prior returns `[-0.01,0,0.01]`, current `0.02` | Prior mean=0; prior SD=`sqrt(0.0002/3)`; standardized surprise≈2.449489742783178 |
| Prior-close z-score | Prior closes `[1,2,3]`, current close 5 | Prior mean=2; SD=`sqrt(2/3)`; z≈3.6742346141747673; current close must not enter baseline |
| Normalized trend | C=110, EMA20=106, EMA50=100, ATR=2, EMA20 five bars ago=101 | Distance=2 ATR; spread=3 ATR; slope=(106−101)/(5×2)=0.5 ATR/bar |
| ATR fraction | ATR=2, close=100 | 0.02, not 2 and not 200 bps unless explicitly converted |
| RSI seed/update | Closes `[100,101,100,101,100]`, n=3 | First RSI at index 3 = 66⅔; next = 44⁴⁄₉ (44.44444444444444) |
| RSI limiting cases | All increasing, all decreasing, all unchanged closes | After proper warm-up: 100, 0, and Tradee's neutral 50 with flat flag; no valid pre-warm-up values |
| Bollinger population convention | Closes `[1,2,3,4,5]`, n=5, k=2 | Middle 3; upper≈5.82842712474619; lower≈0.1715728752538097; width≈1.8856180831641267; `%B`≈0.8535533905932736 |
| Flat bands | Constant close 100, sufficient history | All bands=100; width=0; `%B` null with zero-denominator reason |
| VWAP weighting | Two bars: `(V,Q)=(2,200)` and `(3,330)` | VWAP=530/5=106; not the unweighted average of bar VWAPs, 105 |
| Relative quote volume | Prior quote volumes `[10,20,30]`, current 60 | 60/20=3; including the current bar in the denominator is wrong for this ID |
| Taker imbalance | Total base volume=10, taker-buy base volume=7 | `(14−10)/10=0.4`; values at TB=0 and TB=10 are −1 and +1 |
| Mean trade quote notional | Q=1000, trade count=4 | 250 quote units; count=0 gives null |
| Candle geometry | O=100,H=110,L=90,C=105 | Signed body=.25, upper wick=.25, lower wick=.5, close location=.5 |
| Prior-ATR range | Current range=20, prior ATR=5, current ATR=8 | Feature=4, not 2.5; distinguishes denominator timing |
| Quote spread/size | Bid=99, ask=101, sizes B=3,A=1 | Mid=100; spread=200 bps; bid notional=297; ask notional=101; base-size imbalance=.5 |
| Quote staleness | Quote event at d−5000ms, budget=5000ms | Stale exactly at the boundary; diagnostic event age remains 5000 |
| Session VWAP | Partial collector history beginning after 00:00 UTC | `anchor_incomplete`, not a silently reanchored VWAP |
| Recursive stability | SMA-seeded EMA50 | Nominal value after 50 bars; seed coefficient passes 1e−6 after 346 subsequent updates, 396 bars total |

Before promoting each fixture, check source inputs as well as expected outputs: positive prices, valid OHLC, nonnegative volume, taker volume no greater than total, whole UTC intervals and finalized source observations. Synthetic TR/return arrays can test primitives directly; integration tests must also construct valid prices/bars yielding them.

## 2. Numerical property and boundary matrix

Apply across several fixed random seeds and adversarial explicit examples; randomized tests supplement rather than replace the known answers.

- Scale all prices by a positive constant. Raw price indicators scale accordingly; log returns, normalized trend/ATR/location scores, RSI, relative volume, shape and spread bps stay unchanged where their inputs are scaled consistently. Scale quote volume alongside prices if testing VWAP.
- Scale base/taker volume and corresponding quote volume by the same positive quantity factor. VWAP, relative volume and imbalance stay unchanged; raw notionals scale.
- Check `abs(body)+upper_wick+lower_wick=1`, normalized imbalance bounds and valid RSI range; never clip wrong results just to satisfy a bound.
- Test every feature with exactly one fewer sample than required, exactly the minimum and one extra; recursively derived features must inherit the correct mask.
- Distinguish valid zero ATR/SD/volume from undefined ratios, unavailable source data and absent bars. Test zero-volume bars against nonzero baseline and an all-zero volume baseline.
- Use very small prices, large prices with tiny changes, near-constant windows, alternating extremes and long sequences. Detect overflow/nonfinite output and loss of meaningful distinctions on conversion. Variance must not turn negative through cancellation.
- Validate period types/ranges, empty inputs, duplicate bar IDs, mismatched instruments/timeframes and nonfinite configuration values. No implicit bool-as-integer periods.
- Check EMA/RMA seeds and segment origins are independent of batch chunk size. A correct alpha with an incorrect seed is still a failed test.
- Verify units in serialized definitions; fractions, percentages and basis points cannot share an unlabeled number field.

Use the stated absolute/relative tolerance for finite results; compare masks, seed indices, constituent identities and reason codes exactly. Cross-library comparisons explicitly align initialization and flat/zero cases. MACD/ADX tests are required only if their deferred scope is later approved.

## 3. C02 integration and no-future-data tests

| Scenario | Required result |
| --- | --- |
| Recorded historical download | No feature becomes visible before its actual recorded input availability |
| Explicit modeled dataset | Close-plus-delay schedule is preserved and labeled modeled throughout the feature run |
| Open candle updates | Cannot create/change a closed-candle feature; quote diagnostics remain independently evaluable |
| Missing minute in a 15m bar | No completed 15m feature row from that bucket |
| Missing timeframe bar | Rolling windows crossing it are invalid; recursive state resets and rewarms |
| Delayed gap repair | Current/future state can rebuild after repair availability; previously saved snapshots remain unchanged |
| Old candle corrected after many EMA updates | Rebuild from a checkpoint before the correction or segment origin; no truncated-history approximation |
| Newer candle followed by a late old candle | Current target bar does not move backward; history changes only at the later receipt cursor |
| Two events with identical availability milliseconds | Evaluation after the first event cannot see the second; `as_of_ms` alone is insufficient |
| Appended future events | Evaluating the same earlier prefix gives the same values/masks/lineage; persisted old snapshots never change |
| Different dataset IDs with equal prefixes | Equal feature semantics for the common prefix, without requiring equal run/snapshot container hashes |
| 15m close while 4h bar is open | Only the previous complete and available 4h features may join |
| Latest completed 4h bar is stale/unavailable | Explicit missing/stale required context, not nearest/future bar selection |
| Quote arrives late | Quote event time and receipt/availability both gate eligibility; old event time cannot refresh market freshness |
| Candle-only archive dataset | Quote features missing by design; no fabricated spread/size history |
| UTC midnight and day change | Correct final minute/session association and anchor reset; test leap-day boundaries too |
| Same symbol, different instrument identity | Completely separate feature states; no relisting stitch by ticker text |
| Full final dataset versus prefix execution | A deliberately leaking “compute all rows from latest view” implementation must fail the tests |

Decision times/cursors must be specified in fixtures. A test that compares two paths both using a retrospectively corrected final table does not prove causality.

## 4. Batch, streaming and persistence tests

Historical batch execution, one-event-at-a-time replay and randomly chunked input should yield the same snapshots at identical decision requests. Use the same production evaluator but independent numerical fixtures; this avoids mistaking agreement between two wrong paths for correctness.

Checkpoint at multiple points: before seed completion, at seed completion, mid-window, immediately before a gap, after a correction and just before a UTC anchor rollover. Restart and compare every later value/status/lineage with uninterrupted execution. Reject checkpoints with mismatched feature/config/code/source identities.

Inject a database write failure between feature output and cursor advancement: neither may commit alone. Test idempotent replay of a committed cursor, immutable manifests, defensive copies on read and unknown snapshot/run errors. Confirm input records cannot be mutated by feature computation.

CLI tests cover explanatory definitions, selected feature lists, required-versus-optional readiness, invalid configuration, JSON null/reason codes and an actual subprocess round trip. No network access is required by unit/integration tests.

## 5. Performance characterization and live comparison

After correctness passes, measure a bounded two-symbol sample using the baseline timeframes. Record CPU/wall time, memory, output/database size, normal incremental update cost and worst correction rebuild cost. Report hardware/runtime, sample duration and data/event counts. Do not invent a throughput target or claim full-exchange support from this sample.

Use a small public recorded session for a parity smoke test: feed the same persisted inputs and explicit decision requests to the incremental engine and then batch replay the pinned dataset. Compare completed bars, values, masks and lineage. No trading credentials or orders are needed. This validates C03 integration, not feature profitability or sustained service uptime.

All existing 137 C01/C02 regressions still pass alongside 59 C03 tests. Test counts do not substitute for coverage; the verification report links the numerical, causal, restart, persistence and CLI evidence.

## 6. Deferred incremental-value study

Mathematical correctness and predictive usefulness are separate gates. Once C08/C09/C11/C12 exist:

1. Freeze a base strategy, outcomes, costs, universe, feature candidates and trial budget using development data only. TBot-inspected data remains development data.
2. Compare the same candidate opportunities under a baseline and one added/removed feature family. Preserve matching periods and report feature-induced opportunity loss/missingness.
3. For model inputs, fit preprocessing/selection only on each earlier training fold. For filters or thresholds, choose them within development folds; never tune after viewing the final holdout.
4. Evaluate net expectancy, opportunity count, turnover/costs, exposure, drawdown and uncertainty accounting for overlapping/serially dependent trades. Do not rank indicators by chart appearance or an in-sample correlation alone.
5. Record every attempted feature/parameter variant. Correlated MA/RSI/Bollinger transforms do not supply independent evidence just because they have different names.
6. Report failures and null results. A feature may remain available for diagnostics while being excluded from the strategy.

Rolling z-scores in this C03 spec are deterministic past-window measurements. They are not a license to fit a global scaler on the entire dataset. Future learned transform artifacts must record fit interval, data/config hashes and availability and be supplied by the fold-controlled research workflow.

## 7. Approval and implementation gate

The user approved implementation. The v1 reference engine, baseline configuration, diagnostics, tests, CLI and verification report are complete. Large-universe optimization, sustained runtime validation and predictive ablation remain separately identified work; downstream strategy components are not implemented by this milestone.
