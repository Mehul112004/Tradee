# C03 — feature engine research and implementation plan

**Status: approved and implemented — 21 September 2026.** The v1 reference engine, optional diagnostics, persistence and CLI are available. Use the `tradee` Conda environment. See [C03_VERIFICATION.md](C03_VERIFICATION.md) for completed checks, implementation refinements and scale limits.

Read this document for architecture and files, [C03_FEATURE_SPEC.md](C03_FEATURE_SPEC.md) for the exact mathematics, and [C03_VALIDATION_PLAN.md](C03_VALIDATION_PLAN.md) for examples and acceptance tests.

## 1. What C03 will do

C03 turns C02's auditable market observations into reusable measurements that historical research and the live runtime calculate in the same way. It will answer “what could we measure at this decision point?” It will not decide that a setup is profitable, label a market regime, pick a strategy, place an order or generate a Telegram message.

Formula correctness requires more than recognizing an indicator name. Its input source, window endpoints, initialization, units, unavailable-data behavior, revision policy and evaluation time all belong to its definition.

Proposed scope: BTCUSDT/ETHUSDT initially, using the same configurable instrument scope as C02. Calculate on 15m, 1h, 4h and UTC 1d candles assembled from finalized one-minute contract candles. Each run requests only its declared timeframes/features; it does not automatically treat every timeframe as another signal. Use the 1m path for fixtures and optional diagnostics. Mark/index prices remain separate series; never silently substitute them for contract closes.

## 2. Dependencies and consumers

| Provider | Interface received | C03 use | Missing or incompatible input |
| --- | --- | --- | --- |
| C02, mandatory | `MarketStore.dataset`, `replay`; normalized finalized events and revision IDs | Authoritative input vintage, replay order, decimal prices/volumes, finality and provenance | Reject an unknown dataset/schema; expose missing inputs rather than fabricate them |
| C02, mandatory | `aggregate` on a finalized **prefix view** | Complete higher-timeframe bars and one-minute constituent lineage | A missing constituent invalidates that bucket; never bridge it as if time were continuous |
| C02, optional quotes | Recorded quote events and availability/event times | Spread, best-size measurements and freshness diagnostics | Optional outputs missing in candle-only research; no historical quote synthesis |
| C01, indirect through C02 | Instrument ID and observed metadata-version references | Keep identities separate and retain lineage | Do not key state by a symbol string alone; do not treat current rules as historical evidence |
| C06, later optional | Versioned derivatives interpretation | Explicit future feature extensions | Not required for bootstrap; no imports from an unimplemented component |
| Explicit run configuration | Feature IDs/parameters, timeframes, warm-up policy, decision cursor | Reproducibility | Unknown IDs, cycles, invalid periods or incompatible modes fail before processing |

| Consumer | What it receives | Ownership boundary |
| --- | --- | --- |
| C04 | Return/trend/volatility measurements | C04 interprets market state |
| C05 | Prices, volatility scales and related measurements | C05 constructs levels/causal anchors |
| C07 | Spread, quote freshness, volatility and participation | C07 estimates execution cost/tradability |
| C08 | Explicit feature snapshots | C08 constructs candidates; no score is invented in C03 |
| C10 | Versioned explanatory variables with missingness | C10 models expectancy/uncertainty using earlier outcomes |
| C11/C12 | Frozen feature runs and replayable manifests | Historical simulation, fold isolation and experimental selection |
| C13 | Available risk/volatility measurements | Portfolio risk and selection |
| C14 | The same engine's incremental output | Live scheduling, readiness gating and delivery |

## 3. Proposed first feature set

Implement the supporting primitives once, then evaluate only requested outputs. A shared registry resolves dependencies such as EMA20 and ATR14 once per instrument/timeframe/configuration.

### Baseline preset: 14 outputs per requested timeframe

| Family | Feature IDs | Why it is present |
| --- | --- | --- |
| Returns | `log_return_1`, `log_return_4`, `log_return_12` | Movement at three explicitly different bar horizons |
| Trend | `ema20_distance_atr14`, `ema20_50_spread_atr14`, `ema20_slope5_atr14` | Distance, relative alignment and rate of movement in comparable units |
| Volatility | `return_sd20`, `atr14_fraction`, `return_surprise20_prior` | Return dispersion, price-range scale and shock relative to earlier returns |
| Location | `close_z20_prior`, `vwap20_distance_atr14` | Location relative to previous prices and execution-volume-weighted price |
| Participation | `relative_quote_volume20_prior`, `taker_base_imbalance20` | Activity relative to the past and aggressive-volume balance |
| Oscillator | `rsi14` | One explicitly seeded momentum oscillator |

These are a proposed **research baseline**, not 14 votes or claims of independent predictive power. Periods 14/20/50 and horizons 1/4/12 are starting conventions to freeze before performance inspection, not optimized settings. Future C08 strategies may select a smaller subset.

### Additional v1 capabilities, disabled in baseline

- Raw SMA20, EMA20/50, TR, ATR14 and rolling VWAP20 as dependencies and inspectable diagnostics.
- Bollinger(20,2) bands, fractional bandwidth and `%B` using explicit population variance.
- Squared-return realized variance/volatility, simple return at an explicitly requested horizon.
- Candle body/wick/location ratios and range relative to prior ATR.
- UTC-session VWAP with complete one-minute coverage from the declared anchor.
- Taker quote imbalance and mean quote notional per reported trade.
- Recorded quote midpoint, spread in bps, best bid/ask notionals, best-size imbalance and ages.

“Disabled” means no computation/storage unless selected or required as a dependency. Optional unavailable quotes must not prevent a candle-only run; a strategy explicitly requiring them will be unready.

### Deferred

MACD and ADX have candidate formulas documented for later review, but no first-version code. Also defer Supertrend, stochastic RSI, Keltner, OBV/CVD, full-depth/order-flow features, volume profiles, swing anchors, derivatives interpretation, cross-asset regimes and fitted ML transforms. Current C02 does not certify gap-free tick/depth history; adding formulas cannot repair that evidence gap.

## 4. Proposed files and their relationships

The paths below are **planned**, not files already created by this research task.

| New file | Main contents | Depends on / used by |
| --- | --- | --- |
| `tradee/c03/__init__.py` | Small public API: definitions, engine, snapshots, run store | Exposes reviewed contracts to later components |
| `tradee/c03/contracts.py` | Immutable `FeatureDefinition`, `FeatureValue`, `FeatureSnapshot`, `RunManifest`; typed statuses | Standard library and shared identity/JSON conventions; used by all C03 modules |
| `tradee/c03/catalog.py` | Versioned IDs, parameters, units, dependency graph, lookbacks, definition hashes and preset expansion | Contracts; consumed by engine/config validation and CLI |
| `tradee/c03/rolling.py` | Bounded rolling windows; stable means/variance; SMA-seeded EMA/RMA; serializable state | Pure numerics; reused by feature modules |
| `tradee/c03/price.py` | Log/simple returns, EMA derivatives, prior-close z-score and candle geometry | Rolling primitives and validated bars |
| `tradee/c03/volatility.py` | True range, Wilder ATR, return dispersion, squared variation, prior-window shock | Rolling primitives and contiguous closes/OHLC |
| `tradee/c03/oscillators.py` | Explicit RSI and Bollinger definitions | Shared smoother/variance primitives; consumed by engine |
| `tradee/c03/participation.py` | Rolling/session VWAP, relative quote volume and taker ratios | Exact input volume sums and C02 complete bar/anchor coverage |
| `tradee/c03/liquidity.py` | Quote selection within a prefix, spread/sizes/ages and stale-input masks | Quote events and explicit decision time; no order-book simulation |
| `tradee/c03/evaluator.py` | Shared lazy dependency evaluation and numerical status propagation | Pure feature modules; introduced to keep the prefix engine separate from formula dispatch |
| `tradee/c03/engine.py` | C02 adapter, finalized prefix state, timeframe alignment, shared dependency evaluation, gap/revision handling, batch/incremental API | Catalog, feature modules, C02 replay/aggregation |
| `tradee/c03/store.py` | Separate SQLite application/schema IDs; immutable runs/snapshots; atomic checkpoints and provenance | Contracts/engine outputs; used by CLI and future C11/C14 |
| `tradee/c03/cli.py` | `features list/explain/run/snapshot` command registration and JSON output | Catalog, engine, run store |
| `configs/c03_baseline.json` | Proposed preset, timeframes, stabilization and freshness policy | Loaded explicitly by CLI; canonicalized into every run |
| `tests/c03_support.py` | Hand-audited synthetic bars/events, independent reference helpers and isolated stores | C01/C02 fixtures only where integration requires them |
| `tests/fixtures/c03/reference_cases.json` | Input vectors, expected numbers/masks and reference provenance | Consumed by numerical tests; never generated by the production implementation |
| `tests/test_c03_math.py` | Formula, seed, denominator and zero-case tests | Pure modules |
| `tests/test_c03_catalog.py` | Definition/version hashes, validation, lookbacks, dependency reuse/cycle rejection | Contracts/catalog |
| `tests/test_c03_engine.py` | Prefix, same-ms cursor, revision, gap, multitimeframe, batch/incremental and checkpoint parity | Combined causality/streaming coverage |
| `tests/test_c03_properties.py` | Independent Decimal recurrences, numerical properties, stability and source boundaries | Pure features and engine |
| `tests/test_c03_oracle.py` | Frozen, version-pinned TA-Lib comparisons | JSON fixtures; no external runtime dependency |
| `tests/test_c03_persistence.py` | Immutable runs, rollback, restart, version mismatch and lineage | C03 store |
| `tests/test_c03_cli.py` | Commands, masks/readiness, JSON, exit codes and actual-process round trip | CLI integration |
| `C03_VERIFICATION.md` | Actual results and limitations, written during implementation | Evidence; not an assertion of tests passing now |
| `scripts/verify_c03.py` | Opt-in benchmark, public Binance capture and offline replay comparison | Separate from ordinary offline tests |
| `scripts/generate_c03_oracle.py` | Reproducible third-party fixture generation | Pinned temporary TA-Lib/NumPy installation only |

Planned edits to existing files: register commands in `tradee/cli.py`; add operational examples to `README.md`; update C03 status in `PLATFORM_PLAN.md`. Existing C01/C02 contracts remain authoritative. If the adapter needs a reusable cursor-aware C02 method, add it only with same-millisecond regression tests; do not silently change `view(as_of_ms)` semantics.

No new runtime package is currently required: standard-library float/math/statistics/decimal plus SQLite are sufficient for the reference-sized first version. Keep optional external indicator libraries in a separate reference-fixture workflow, not as hidden production formula authorities. Record their exact versions if introduced; update dependency/environment files only if needed.

## 5. Input and output contracts

The input adapter wraps C02 aggregates in a `FinalizedBar` contract. C02's current aggregate output has constituent event IDs but no standalone event ID or full provenance envelope. Derive a stable bar-revision ID from instrument, timeframe, open time and the ordered constituent version IDs; retain the dataset availability mode and constituent metadata references. Never discard that lineage when converting a bar to numeric inputs.

`FeatureDefinition` must declare feature ID and formula version, parameters, input fields/kinds, timeframe applicability, units, dependency IDs, current/prior window boundaries, seed rule, minimum bars, missingness/zero cases, gap policy and numeric policy. Definition IDs encode meaningful conventions; changing a seed or `ddof` creates another version.

`FeatureValue` contains a finite number or null, status/reason, nominal warm-up progress, seed-stabilization diagnostics and dependency lineage. Suggested statuses: `valid`, `insufficient_history`, `gap_in_window`, `zero_denominator`, `stale_input`, `missing_source`, `anchor_incomplete`, `unsupported_coverage`, `numeric_error`. A missing feature is never serialized as 0 or NaN.

`FeatureSnapshot` contains instrument ID, timeframe, target bar open/exclusive close, evaluation time and input cursor, dataset/run/config/definition hashes, feature values/readiness masks, input availability bound, lineage/state digest and availability basis. Carry optional input event IDs through a deduplicated lineage table rather than copying months of IDs into every JSON row.

Keep **evaluation semantics** separate from actual computation timestamps. `input_available_ms` bounds source availability; `evaluation_as_of_ms` states the requested information cutoff. A live consumer cannot act before computation finishes. Store `computed_at_ms` as operational metadata and exclude it from deterministic content hashes. Historical runs state their assumed processing latency; they do not use today's computation wall clock as a historical decision time.

`RunManifest` pins the C02 dataset hash, feature/config hashes, code version (including a source-tree fingerprint before Git commits exist), Python/numeric implementation versions, pre-roll origin, target output range, availability mode, decision schedule and checkpoint schema. Feature-run output hashes may differ across datasets even when their common prefix has identical values; test prefix values/lineage, not an impossible equality of different dataset-container IDs.

## 6. Causality, gaps and revisions

**Do not take the final C02 view of an entire dataset and compute all historical feature rows from it.** That would inject later repairs into earlier decisions.

1. Consume `MarketStore.replay` in its pinned `(available_ms,event_id)` order; preserve its modeled ordering when selected.
2. Maintain an incremental latest-finalized prefix view keyed by instrument/kind/bar identity. Ignore partial candles for closed-candle calculations.
3. Assemble higher-timeframe candles only when every constituent is finalized and present in that prefix. Features inherit the slowest required input's availability.
4. At an explicit decision request, compute the target bar using only that prefix. Batch mode calls the same evaluator as incremental mode.
5. A correction is a new observation. It can change future/current evaluations after its availability, never update previously persisted decisions. Recompute affected recursive state from a checkpoint before the corrected bar, or replay the segment from its pinned origin.
6. Preserve immutable prior snapshots and append a new revision for an explicitly requested reevaluation. C14 will decide whether a reevaluation warrants an alert; C03 does not resend signals.

**Same-millisecond ordering:** `C02.view(as_of_ms)` includes all events at that millisecond. It cannot by itself reproduce a decision made after only the first such event. The C03 adapter must keep the exact replay prefix/cursor, including the event ID. This is a concrete integration requirement discovered in the code review.

**Gaps:** strict-contiguous rolling windows. A gap invalidates windows crossing it. Recursive features restart at the next contiguous segment and rewarm; returns never jump across an absent candle. If a later repair reconnects segments, future evaluations can rebuild the state using that newly available evidence. Old snapshots and their reset history remain unchanged.

**Multitimeframe joins:** at a 15m decision use the newest completed, available 1h/4h/1d bar and its valid feature snapshot. Never use an in-progress 4h bar or select a future higher-timeframe close by nearest timestamp. Retain the higher-timeframe bar ID and its age; optional missing context does not silently become a neutral number. A consumer explicitly declares required context and staleness budget. Proposed default candle-context freshness is `decision_ms - bar_end_exclusive_ms < timeframe_ms + 5000`; the five-second allowance is a configurable engineering budget, not measured exchange latency. A missing expected next bar therefore cannot keep the old context fresh indefinitely. Calendar boundaries and freshness are evaluated in UTC.

**Late bars:** event time decides the target chronological bar; receipt order decides when the engine knows it. A late older candle can revise recursive history but must not move the current target bar backward. Closed-bar decision requests are distinguishable from revision reevaluations.

## 7. Warm-up and numerical policy

Expose mathematical validity separately from seed stability. For a single EMA/RMA smoother, the remaining initial-seed coefficient after `k` updates is `(1-alpha)^k`. A proposed engineering threshold of `1e-6` gives:

| Smoother | Nominal input minimum | Additional updates for seed coefficient ≤ 1e-6 | Total contiguous bars for the listed primitive |
| --- | --- | --- | --- |
| EMA20 on closes | 20 | 139 | 159 |
| EMA50 on closes | 50 | 346 | 396 |
| ATR14 / RSI14 input smoothers | 15 price bars | 187 | 202 |

Derived outputs inherit the least stable dependency, including lagged dependencies used in slope. This coefficient bounds the contribution of an initial smoother state, **not absolute error of the final ratio/RSI**. There is no blanket statement that “14 bars are enough for convergence.”

Proposed baseline: calculate diagnostic values once mathematically defined, but `require_stable=true` for baseline readiness. Pre-roll must cover the configured dependency requirements; EMA50 implies 396 contiguous bars at that timeframe. That is 396 days for daily features and can materially reduce available history. This tradeoff is an explicit review decision, not an invisible default. Pre-roll observations are inputs; outputs before the requested evaluation range need not be persisted.

Pin the initialization origin and sufficient pre-roll in the dataset. Never reseed an EMA at every walk-forward test boundary just because a data frame was sliced. Earlier causal feature state can cross a fold boundary; learned fitted state follows different C12 rules.

Use exact source decimals for validation/volume accumulation, then documented finite float64 outputs for analytical functions. No order rounding in C03. Use `math.fsum` and centered two-pass rolling variance initially; do not use unstable `E[x²]-E[x]²` on high-price, low-variance data. Recalculate small rolling windows directly before optimizing incremental removal formulas. Reject nonfinite conversions/results and detect distinctions lost by float conversion; do not disguise them as a flat valid input.

Tentative parity tolerance: `abs(a-b) <= 1e-12 + 1e-10*max(abs(a),abs(b))`. Status masks, seed start indices and event lineage must agree exactly. Validate this budget on ordinary and adversarial magnitudes rather than widening it simply to pass a failing test. Bit-for-bit hashes are required for the same pinned implementation/environment; cross-runtime comparisons use stated numeric tolerances and record different materializations when necessary.

## 8. State and persistence

The implementation uses `data/c03.sqlite3`, distinct from C01/C02, with its own application/schema identifier. Tables hold run manifests, immutable feature snapshots, source-lineage references and engine checkpoints. Checkpoint and associated last output cursor commit atomically. The v1 checkpoint retains the latest finalized candle prefix, newest eligible quote per instrument, cursor, prefix hash and evaluation clock. It reconstructs derived rolling/recursive/anchor state on restart, avoiding independently serialized copies of the same state. Pure rolling/smoother primitives also support serialization. There is no pickle or arbitrary-code deserialization.

A restart rejects incompatible configuration/code/checkpoint schemas. Corrections older than a retained buffer trigger reconstruction from pinned C02 input, not silent partial repair. Keep a simple correct reference path before adding caches. Cache keys include configuration, instrument, timeframe, cursor and source-state digest; symbol/timeframe alone is insufficient.

The first streaming API is an in-process engine receiving normalized events, not another Binance connection. Historical `run` adapts C02 replay to that API; C14 later drives it from persisted live observations. C03 does not duplicate network ingestion or install a daemon.

## 9. Implementation order after approval

1. Freeze feature definitions, numeric conventions, statuses and the proposed baseline preset. Create independent calculation fixtures first.
2. Implement pure window/smoother primitives and numerical features. Verify seeds, masks and units before integration.
3. Build the C02 prefix adapter, strict aggregation and decision API; establish historical/incremental parity and same-ms causality.
4. Add gap/revision reconstruction, checkpoints and immutable feature storage. Verify crash/restart and repair semantics.
5. Add optional quote/session diagnostics and CLI inspection/run commands. Test source-dependent readiness without penalizing unrelated features.
6. Run C01/C02 regressions, C03 acceptance tests, a bounded performance/memory characterization and a small live-input comparison through the same evaluator. Publish actual results.

Suggested CLI surface, **not available yet**:

```text
python -m tradee features list
python -m tradee features explain rsi14
python -m tradee features run DATASET_HASH --config configs/c03_baseline.json
python -m tradee features snapshot FEATURE_SNAPSHOT_HASH
```

The run configuration separates the dataset's pre-roll interval from the requested output interval. Commands explain missingness, readiness and provenance rather than just printing indicator numbers.

## 10. Research evidence and TBot review

The accompanying formula spec cites primary implementations and provider documentation. They establish definitions and compatibility choices, not predictive success. TBot's `backend/app/core/indicators.py` provides a useful checklist, but inspection found:

- EMA and MACD docstrings promise masked warm-up output that their unmasked EWM calls do not provide.
- RSI gain/loss preprocessing turns the first unavailable difference into zero; `min_periods` does not fix the resulting non-SMA initialization. The zero-loss branch also makes a flat series 100 and can expose values early.
- ATR uses a first-row high–low value and an EWM seed, rather than the specified prior-close true-range/SMA seed.
- Bollinger uses pandas' default sample standard deviation. That is a different convention from our explicit population standard deviation, not evidence that every sample-based band is inherently invalid.

Reuse ideas and tests, not those numerical implementations unchanged. Do not infer that these findings explain TBot's trading results; that would require separate strategy evaluation.

## 11. Review decisions and definition of done

Recommended choices awaiting review:

- The 14-output baseline, with RSI included and Bollinger/shape/quote outputs optional; MACD/ADX deferred.
- SMA-seeded EMA/Wilder smoothing; flat RSI=50; population standard deviation; past-only shock/location/relative-volume baselines.
- Complete finalized UTC bars, strict gap resets and availability-prefix revisions.
- Explicit recursive stabilization gating (`1e-6` seed coefficient), with its longer pre-roll cost.
- Standard-library first implementation, separate immutable feature store and one batch/incremental evaluator.

Done means all agreed formulas/edge cases pass independent references, batch and incremental evaluations agree, later data cannot rewrite prior decisions, all readiness/lineage is inspectable, restart is reproducible and the existing regression suite still passes. Report measured runtime/storage limits rather than claim full-exchange scalability.

An ablation report measuring feature value after costs requires C08/C09/C11/C12 and outcomes that do not exist yet. C03's deliverable is the reproducible feature infrastructure and a predeclared ablation protocol, **not a fabricated predictive-performance report**. That downstream research obligation remains open even after engineering acceptance.
