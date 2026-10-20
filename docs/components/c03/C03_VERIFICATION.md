# C03 verification — 21 September 2026

**C03 v1 is implemented and its engineering checks pass.** The approved scope includes the feature catalog, mathematical primitives, causal C02 integration, optional diagnostics, durable runs/checkpoints and CLI. The implementation supplies measurements; profitability, strategy selection and Telegram delivery remain downstream components.

## Delivered scope

- **14 baseline outputs**, configured in [configs/c03_baseline.json](../../../configs/c03_baseline.json), on 15m, 1h, 4h and 1d. Diagnostic 1m evaluation is also supported.
- **43 named feature definitions**, including the baseline, plus parameterized `simple_return_H` for H=1..9999. Families cover returns, SMA/EMA trend, Wilder ATR/RSI, return dispersion and variation, prior-window normalization, exchange-volume VWAP, relative volume, taker imbalance, Bollinger bands, candle geometry, UTC-session VWAP and best-quote diagnostics. MACD/ADX remain deferred as agreed.
- Formula/version hashes, explicit units and parameters, input fields, dependencies, nominal lookbacks, seed policies, separate stability diagnostics and null/reason statuses.
- Finalized-only UTC aggregation; exact availability/event-ID prefixes; gap resets, late repair and full recursive recomputation; immutable historical snapshots. New closes and revision reevaluations have distinct triggers.
- Recorded versus modeled availability, candle/quote freshness, explicit decision requests and source-dependent readiness. Quote diagnostics do not require order-book depth or invent historical quotes.
- Separate SQLite database, immutable run/output records, deduplicated lineage, operational computation timestamps, atomic output/checkpoint transactions, restart and idempotent run continuation.
- `features list`, `explain`, `run`, `snapshot`, `manifest`, `lineage` and `summary`. See [README usage](../../getting-started/README.md#c03-feature-engine).

Production C03 uses the Python standard library. The existing optional `websockets` dependency is used by C02's public capture, not by feature calculations. No exchange credentials were added or read, and no account/order endpoints were used.

## Offline verification

Executed in Conda environment `tradee`, Python **3.13.15**:

```sh
conda run -n tradee python -m unittest discover -s tests -q
```

Result: **196 tests passed in 2.480 seconds** — all **137 existing C01/C02 tests** and **59 new C03 tests**. Local execution was on macOS arm64; this report does not claim that the configured Linux/Python 3.11 CI job has run.

| Evidence | Coverage |
| --- | --- |
| [test_c03_math.py](../../../tests/test_c03_math.py) | Hand-derived EMA/RMA/ATR/RSI and Bollinger fixtures; previous-close TR; population variance; exact-volume VWAP; units, geometry, zero cases; minimum−1/minimum/minimum+1 masks; lagged seed stability; conversion loss; parameterized returns |
| [test_c03_properties.py](../../../tests/test_c03_properties.py) | Three seeded 500-observation sequences against independent 70-digit Decimal EMA/RMA/RSI recurrences; price/volume properties; zero ATR/volume; relevant input validation; readiness at EMA50 stabilization; relisting isolation and availability boundaries |
| [test_c03_oracle.py](../../../tests/test_c03_oracle.py) | Every index and warm-up mask against pinned third-party EMA20/EMA50, ATR14, RSI14 and upper/middle/lower Bollinger outputs |
| [test_c03_catalog.py](../../../tests/test_c03_catalog.py) | Dependency reuse/cycles, definition hashes, strict configuration, units, immutable records and finite-value contracts |
| [test_c03_engine.py](../../../tests/test_c03_engine.py) | Exact same-ms prefix behavior, no-future-prefix evaluation, partial candles, strict complete buckets, gaps and repairs, old corrections after 220 updates, instrument separation, UTC/leap-day reset, quote event-time ordering/staleness, optional readiness, pre-roll, multiple restart points and bounded quote state |
| [test_c03_persistence.py](../../../tests/test_c03_persistence.py) | Actual C02 datasets; modeled replay with decreasing numeric event IDs; resume/idempotency; recorded-download staleness; lineage; checkpoint corruption; conflicting prefixes; database isolation; injected SQL failure and transaction rollback |
| [test_c03_cli.py](../../../tests/test_c03_cli.py) | Actual subprocess definition inspection, invalid configuration, run, resume, manifest/snapshot/lineage round trips |

Tests compare exact statuses, identities and same-runtime snapshot contents. Independent numerical comparisons use `abs_tol=1e-12`, `rel_tol=1e-10`. The test suite does not fetch network data.

### Independent oracle provenance

[Hand-calculated fixtures](../../../tests/fixtures/c03/reference_cases.json) do not call production feature functions. A separate [frozen external fixture](../../../tests/fixtures/c03/talib_0_6_8.json) was generated using:

- TA-Lib Python wrapper **0.6.8**; underlying C library **0.6.4**, build string `Oct 20 2025 20:23:07`.
- NumPy **2.4.1**; TA-Lib compatibility mode 0 and unstable periods 0.
- Explicit input arrays and expected outputs, with JSON nulls for warm-up.

The fixture generator [scripts/generate_c03_oracle.py](../../../scripts/generate_c03_oracle.py) imports no Tradee calculations. Packages were installed only under `/private/tmp/tradee-c03-oracle`; they are not project dependencies and were not installed into the `tradee` environment. Flat RSI is intentionally excluded from cross-library equality: Tradee uses neutral 50 with a flag, while TA-Lib uses 0. The Tradee convention has its own tests.

## Public Binance capture and replay

The sandboxed network attempt failed with a transport error. The authorized public-data retry succeeded. Captured through the existing C01/C02 adapters:

- 25 recently closed BTCUSDT 1m REST candles.
- 53 WebSocket observations, including **one finalized candle** and partial updates.
- **78 pinned events**, producing **26 candle-triggered snapshots**.

One-event-at-a-time processing and batch replay produced identical serialized snapshots, including values, masks, targets, input prefixes and lineage. Persistence through `FeatureStore.run` also succeeded. The capture was replayed again after the final production-code changes.

The smoke configuration selected `log_return_1`, `vwap20`, and `rsi14`, on 1m, with `require_stable=false`. It produced two ready snapshots, including the last one. This tests nominal calculations and actual input plumbing; it does **not** demonstrate default baseline stabilization or long-running live reliability.

- Dataset: `b1e59c5c9ecce1598f1929823e015c9aefae9251398a92d6e20e7cdc4df65bbb`.
- Final run: `1c7e9009c3aa90501e12fa27346c80e2596206a63db2b84a5ce8102aee58b9f9`.
- Final source-tree hash: `147be28da5d5af187abd0510f55a2fce0168fcd6b44888d21676a65ae311b4e7`.

Local capture databases and the report are under `data/c03_verification/live/`, excluded from version control. Recheck the saved session without network access:

```sh
conda run -n tradee python -m scripts.verify_c03 --replay --output data/c03_verification/live
```

## Bounded performance characterization

Command:

```sh
conda run -n tradee python -m scripts.verify_c03 --output data/c03_verification/benchmark_verified
```

Environment: macOS 27.0, arm64, Python 3.13.15. The measurement includes `tracemalloc` overhead and periodic SQLite commits; it is a local characterization, not a service-level benchmark.

| Measurement | Observed |
| --- | ---: |
| Synthetic market duration | 1 day |
| Instruments / finalized minute events | 2 / 2,880 |
| Baseline features / timeframes | 14 / 15m, 1h, 4h, 1d |
| Initial snapshots | 254 |
| Wall / process CPU time | 5.775 s / 5.758 s |
| Median event update | 0.254 ms |
| 95th percentile event update | 8.850 ms |
| Maximum event update in sample | 77.316 ms |
| Old-candle correction, four timeframe reevaluations | 78.664 ms |
| Peak traced Python memory | 21,142,365 bytes |
| Traced Python memory after processing | 6,618,390 bytes |
| SQLite size after correction outputs | 6,238,208 bytes |

Benchmark run: `9a41a1734a3936378885566a13c96340d24d5421a3ec95d45f46be865afa0d8e`, using the same source-tree hash as the final live replay. Raw results are in `data/c03_verification/benchmark_verified/benchmark.json`. Use a new output directory for every benchmark invocation.

Most minute events do not close a requested higher-timeframe bucket, so median event latency is not the cost of a full feature calculation. One day also does not reach default EMA50 stabilization: the fastest configured timeframe has only 96 bars. The measured correction is one old-candle case, **not a worst-case bound**. Traced allocations exclude some native/process memory; SQLite size includes checkpoints and provenance as well as values.

## Implementation refinements and limits

1. **Reference state reconstruction.** The engine retains latest finalized candle observations and reconstructs derived windows/recursive state from their contiguous segment. Checkpoints persist that canonical prefix rather than duplicate numerical caches. Corrections can therefore rebuild from the true origin. This is the correctness-first path allowed by the plan; time and memory grow with candle history, and repeated evaluations can have quadratic aggregate work. Multi-year, many-symbol throughput and optimized incremental caches remain unvalidated. The performance numbers above must not be extrapolated to full-exchange operation.
2. **Quote state is bounded.** Only the newest eligible event-time quote per instrument is retained for future evaluations; late older quotes cannot refresh it. The full observed prefix hash still advances, and prior snapshot lineage remains immutable in storage.
3. **Shared formula dispatch is separate.** `evaluator.py` handles lazy dependency evaluation and numeric status propagation; `engine.py` handles prefixes and decisions. Causality and streaming tests are combined in `test_c03_engine.py`. The finalized-bar wrapper uses C02-compatible dictionaries augmented with revision IDs/metadata rather than introducing a second candle schema.
4. **Automatic decision scope.** `advance`/CLI runs emit after requested finalized candle buckets and after revisions affecting completed history. Quotes update state; independent quote or multi-timeframe context requests use `evaluate` at the explicit current-prefix decision time. C14 will own live scheduling and action timing.
5. **Readiness is intentional.** Default stable EMA50 requires 396 contiguous bars per timeframe, including 396 days for 1d. Historical download receipt is preserved in recorded mode; modeled availability must be an explicit C02 dataset choice. `computed_at_ms` is operational SQLite metadata, excluded from deterministic hashes. Live consumers must additionally respect actual computation completion.
6. **Engineering acceptance is not predictive evidence.** Feature ablations after fees, funding and slippage require the strategy, simulator and walk-forward components. No net-expectancy or trading-performance result is claimed here. Sustained runtime/load checks and downstream research remain open.

No C01/C02 data contract or provider implementation was changed. Existing CI discovers C03 tests automatically. The implementation and documentation are ready for component review and subsequent component work.
