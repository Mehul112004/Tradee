# Component implementation and future upgrades

Updated 13 October 2026. Tradee implements each component's agreed initial scope, verifies that scope, and extends it when its dependencies and evidence are available. C01, C02 and C03 are complete within their documented initial scope; C06 adds funding-accounting scope and C07 adds market execution/cost scope. Some broader functionality and operational validation remain outstanding. The tables below make those gaps explicit for all fifteen components.

This register consolidates the currently identified work in [the platform plan](PLATFORM_PLAN.md), [component research](COMPONENT_RESEARCH.md) and component verification reports. It is a maintained backlog, not a promise to implement every possible indicator or predictive model. New prospects belong here when identified; unnecessary extensions can be rejected with a recorded reason.

## Status definitions and maintenance

- **Implemented:** code exists and its stated tests pass. Scope and deployment limitations still apply.
- **Required next:** baseline functionality belonging to an unbuilt component; it is not an optional upgrade.
- **Deferred extension:** functionality deliberately excluded from the agreed initial scope.
- **Validation outstanding:** code or a design exists, but the stated operational, scale or predictive evidence has not been established.
- **Conditional:** implement only if a strategy, dataset, deployment or measured bottleneck justifies it.

Each backlog entry has an ID, purpose, dependencies and a completion gate. After every component implementation, update its status and evidence link here, add newly discovered gaps, and record completed/rejected entries rather than silently deleting them. Priority follows the build order unless a completion gate explicitly blocks earlier work. No automated recurring task is implied.

## Component status overview

| Component | Current scope | Status | Most important remaining work |
| --- | --- | --- | --- |
| C01 | Binance contract identity, rules, metadata history and explicit universe | Implemented | Historical metadata evidence and broader universe selection |
| C02 | Public archive/REST acquisition, foreground live recorder, immutable datasets and replay | Implemented | Scale, tick/depth coverage and additional source adapters |
| C03 | Shared causal mathematical features, optional diagnostics, persistence and CLI | Implemented | Long-history performance and separately justified feature extensions |
| C04 | Market-state interpretation and filters | Deferred optional component | Establish added value against the baseline strategy |
| C05 | Causal price levels and structure | Deferred optional component | Define levels and demonstrate added value |
| C06 | Exact funding cash flows, observed estimates, coverage/boundary statuses, durable reports and E2E | Implemented funding scope | Audited calendar acquisition, account reconciliation and predictive derivatives extensions |
| C07 | Market scenarios, exact fees/costs, rule/readiness/delay gates, durable replay and E2E | Implemented market scope | Passive/partial fills, empirical calibration, historical fidelity and account integration |
| C08 | Candidate generation | Required next | One precisely specified strategy and complete candidate inventory |
| C09 | Shared trade lifecycle and outcomes | Required next | Entries/exits, actual quantity timelines, ledger booking and labels |
| C10 | Expectancy and uncertainty | Required next after C11 | Estimates from earlier matured outcomes and uncertainty |
| C11 | Historical simulator | Required next after C09 | First complete trading E2E workflow and reconciled ledgers |
| C12 | Research validation and registry | Required next | Walk-forward orchestration, isolation, trial accounting and promotion |
| C13 | Portfolio and alert selection | Required next | Shared capital/risk constraints and combined-policy validation |
| C14 | Live orchestration and Telegram | Required next | Persistent runtime, eligibility, delivery lifecycle and live E2E |
| C15 | Forward measurement and monitoring | Required next | Signal-to-outcome tracking, reconciliation and degradation rules |

The next component after C07 is C08 candidate generation. C04/C05 and predictive C06 additions remain optional. Full historical workflow testing arrives at C11, Telegram workflow testing at C14 and the complete forward feedback loop at C15. These milestones do not imply an existing dashboard or automated exchange orders.

## C01 Instrument and universe registry

Implemented evidence: [C01 research and scope](C01_RESEARCH_PLAN.md), [C01 verification](C01_VERIFICATION.md).

| ID | Remaining work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C01-U01 | Historical listing/delisting, rule changes and metadata effective times | Deferred extension; research validity limitation | C02 historical evidence sources and C12 experiment manifests; replay past eligibility without substituting today's metadata |
| C01-U02 | Liquidity-based universe snapshots, broader scanning and survivorship controls | Conditional extension | C02 liquidity/coverage artifacts; historical membership is available at each decision and exclusion reasons persist |
| C01-U03 | Reviewed identity reconciliation for ticker changes/relistings | Deferred extension | Auditable provider evidence; conflicts remain quarantined until reconciled, with no silent stitching |
| C01-U04 | Additional providers/products and margin/leverage/risk metadata | Conditional extension | Product-specific contracts and C07/C09/C13 models; unsupported products fail closed |
| C01-U05 | HTTP/operator interface and coordinated refresh deployment | Conditional interface; validation outstanding | Shared UI/runtime work; freshness, restart and multi-process behavior verified. Existing foreground watcher is already available |

## C02 Market data and replay

Implemented evidence: [C02 implementation and limits](C02_IMPLEMENTATION.md), [C02 verification](C02_VERIFICATION.md).

| ID | Remaining work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C02-U01 | Streaming dataset manifests, partitioning and storage suitable for large tick archives | Conditional scale upgrade | Representative history/symbol load measurements; bounded memory, restart and input hashes remain reproducible |
| C02-U02 | Local order-book reconstruction, sequence validation and trade-ID repair | Deferred extension | New source adapters and C07 execution requirements; continuity/resynchronization is demonstrated before depth-based fills are used |
| C02-U03 | Historical quote/trade/mark/premium coverage, audited OI and additional derivatives sources | Deferred extension | Provider/archive evidence and C06/C07 consumers; gaps and source vintages remain explicit |
| C02-U04 | Funding interval/cap configuration observations and historical calendar evidence | Required for automated calendar upgrade | C06-U01; persist observations/revisions without assigning current intervals to the past |
| C02-U05 | Liquidation and scheduled-event/calendar feeds | Conditional extension | C04/C06 hypotheses and provider semantics; snapshot limitations and schedule revisions are preserved |
| C02-U06 | Shared IP rate limiting, archive retries and repair beyond the automatic 24-hour window | Conditional operational upgrade | Multi-collector/load needs; outages resume without losing known gaps or falsely claiming completeness |
| C02-U07 | Sustained recording, reconnect/load exercises and backup/restore drills | Validation outstanding | C14 deployment/runtime; durable recovery is verified over representative outages and volumes |

Process supervision and an unattended deployment belong to C14/shared operations; the current C02 collector runs in the foreground. Trade/quote history is not certified gap-free, and current quotes cannot repair missing historical quotes.

## C03 Feature engine

Implemented evidence: [C03 formula contract](C03_FEATURE_SPEC.md), [C03 verification](C03_VERIFICATION.md).

| ID | Remaining work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C03-U01 | Incremental numerical caches, efficient lineage/checkpoints and long-history throughput | Validation outstanding; priority before large C11 runs | Representative datasets; exact prefix/correction/restart parity preserved. Current reference reconstruction can accumulate quadratic work |
| C03-U02 | MACD, ADX, Supertrend, stochastic RSI and Keltner channels | Conditional feature extensions | Freeze formulas/seeds/zeros first; independent fixtures and later C12 ablation justify use |
| C03-U03 | OBV/CVD, depth/order-flow, volume profiles and swing-anchored VWAP | Conditional extensions | C02 evidence continuity and, where needed, C05 anchors; no fabricated tick/depth coverage |
| C03-U04 | Derivatives, cross-asset/context and fitted ML transforms | Conditional extensions | C04/C06 and C12 fold-controlled fitting; transforms preserve availability and fit boundaries |
| C03-U05 | Predictive feature-family ablation after costs | Validation outstanding | C07/C08/C09/C11/C12; compare matched opportunities, costs, sample loss and uncertainty on later data |

The current 43 named definitions and parameterized simple returns are implemented. Adding more indicators does not substitute for C03-U01 or predictive evidence. Default daily EMA50 readiness needs 396 contiguous daily bars; a one-day benchmark does not validate that workload.

## C04 Market state

This optional component has no implementation yet. C02 and C03 supply measurements; C08 and C10 can consume its outputs.

| ID | Remaining work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C04-U01 | Continuous trend, volatility, liquidity, broad-market and time context | Deferred component scope | Baseline C08/C11/C12 first; quantify improvement and lost opportunities under matched coverage |
| C04-U02 | Scheduled-event proximity and revision-aware event context | Conditional extension | C02-U05; event schedules and timezone conversions are available at each decision |
| C04-U03 | Simple regimes, learned filtered state probabilities and state uncertainty | Conditional extension | C12 fitting isolation; no future-smoothed labels or unrecorded threshold tuning |

## C05 Price structure

This optional component has no implementation yet. It supplies level snapshots to C08/C09 when a strategy requires them.

| ID | Remaining work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C05-U01 | Completed-period highs/lows, ranges and confirmed pivots | Deferred component scope | C02/C03 and strategy requirement; explicit confirmation lag, immutable availability and baseline comparison |
| C05-U02 | Level merging, aging, touches, invalidation and normalized distances | Conditional extension | C05-U01; deterministic snapshots and measured incremental value |
| C05-U03 | Zones, order blocks, fair-value gaps, BOS/CHOCH and sweeps | Conditional hypothesis extensions | Exact causal definitions and C12 trials; compare against simple range/ATR methods |

## C06 Funding and derivatives context

Implemented funding evidence: [C06 contracts and boundaries](C06_IMPLEMENTATION.md), [C06 verification](C06_VERIFICATION.md).

Implemented now: signed exact funding arithmetic for identified USDT perpetual exposure, partial-exit quantity inputs, observed next-settlement estimates, strict/nominal boundary policies, explicit calendar checks, corrections without duplicate full charges, immutable recorded-prefix reports, atomic checkpoints, CLI and current-foundation E2E tests. C09 will own executable position state and actual booking; C06 outputs are accounting evidence/scenarios, not confirmed account transactions.

| ID | Remaining work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C06-U01 | Automatically acquired, audited funding calendars and interval/cap history | Deferred data upgrade; important before broad C11 experiments | C02-U04; detect missing settlements across interval changes. Current totals are conditional on a caller-declared calendar, never certified complete from observed records alone |
| C06-U02 | Live position/fill evidence and one-time ledger reconciliation | Required downstream wiring | C07/C09/C11/C14; quantity at settlement comes from the shared lifecycle and corrections are booked as replacements/deltas |
| C06-U03 | Account income reconciliation, currency rounding and settlement-time ambiguity resolution | Conditional account extension | Explicit user authorization for account access and authenticated records; reconcile modeled versus actual amounts without claiming public data proves wallet charges |
| C06-U04 | Premium/basis features and historical derivatives summaries | Deferred predictive extension | C02-U03, C03 and C12; normalize units, distinguish forecasts/settlements and test added value |
| C06-U05 | Open-interest changes, positioning interpretation and coverage audits | Deferred predictive extension | Audited OI history, C02/C12; distinguish base units/notional and measure matched-coverage performance |
| C06-U06 | Liquidation snapshot interpretation and optional positioning filters | Conditional predictive extension | C02-U05 and C12; provider snapshots cannot be represented as complete liquidation volume |
| C06-U07 | Funding forecasting models, multi-settlement scenarios and uncertainty | Conditional extension | Earlier known estimates, C07/C11/C12; no use of eventual settlement rates as earlier predictions |
| C06-U08 | Other settlement currencies, inverse products and account/margin effects | Outside current agreed product scope | New C01 product contracts and C07/C09/C13 accounting; no reuse of linear USDT formula for inverse products |

The default boundary guard flags quantity changes within inclusive ±15 seconds of nominal settlement; it is a conservative modeling policy. Actual transaction ordering requires account evidence. A nominal policy can be selected explicitly for sensitivity tests. Missing/ambiguous amounts remain null; the known subtotal is not a complete trade outcome.

## C07 Execution and tradability

Implemented evidence: [C07 contracts and boundaries](C07_IMPLEMENTATION.md), [verification](C07_VERIFICATION.md).

Implemented now: independent full market-fill scenarios under explicit liquidity caps, observed quote/mark freshness, exact quantity/tick/fee arithmetic, drift/spread/slippage attribution, manual action delay/expiry, required C03 artifact joins, separate next-funding estimates, immutable reports, atomic restart, CLI, connected E2E and public-source replay. Historical candle execution is an explicit coarse model with labeled metadata/mark assumptions; no exact intrabar price or historical funding forecast is invented.

| ID | Work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C07-U01 | Fee assumptions, market fills, spread/slippage, freshness and manual-action delay | Implemented initial scope | C01/C02/C03/C06; independent amounts, feature/funding integration, 58 new tests, CLI-process E2E and public-source parity; admission is model-conditional |
| C07-U02 | Passive/partial fills, synchronized depth and size-dependent impact | Conditional fidelity upgrade | C02-U02 and forward observations; do not award a fill or maker fee merely from a bar touch |
| C07-U03 | Empirical human/delivery delay and cost calibration | Validation outstanding after implementation | C14/C15; compare estimates with recorded execution/delay and stress adverse scenarios |
| C07-U04 | Venue-specific execution and account-specific fee tiers | Conditional extension | Explicit sources/account scope and C01 product support; preserve policy versions and avoid double-counted costs |
| C07-U05 | Verified historical metadata, quote/mark/depth coverage and multi-settlement funding projections | Data/fidelity upgrade before broad cost claims | C01-U01/C02-U03/C06-U07; current-metadata and bar-close mark proxies stay explicit research assumptions; no exact intrabar or full-horizon funding claim |
| C07-U06 | Shared lifecycle, realized fills and ledger/account constraints | Required downstream wiring | C09/C11/C13/C14; book fills/fees/funding once, reconcile revisions, consume shared capital/liquidity, validate strategy again at action time; test complete trade outcomes |
| C07-U07 | Representative throughput, storage retention and unattended recovery | Operational validation outstanding | C02/C03/C14; benchmark history/universe sizes and cold restarts, migration/backup and physical failure recovery beyond statement rollback |

## C08 Candidate generation

| ID | Work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C08-U01 | One explicit strategy, triggers, candidate snapshots and rejection reasons | Required baseline | C01/C03 and reviewed C09/C12 concepts; deterministic causal candidate E2E |
| C08-U02 | Additional strategy families and second trading horizon | Conditional extension | First complete C11/C12 pipeline; record every hypothesis/variant and evaluate intraday/swing separately |
| C08-U03 | Market-state, levels and positioning inputs | Conditional extension | C04/C05/C06 predictors; added value survives costs and opportunity loss |

## C09 Trade policy and outcomes

| ID | Work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C09-U01 | Entry/exit/expiry lifecycle, ambiguity rules, fills, quantity state and cost/funding ledger | Required baseline | C01/C06/C07/C08; independent long/short, gap, partial/time-exit and one-time funding booking cases |
| C09-U02 | Outcome labels, maturity, excursions and unresolved tails | Required baseline | C11/C12 interfaces; labels match the exact executable policy and unavailable outcomes remain explicit |
| C09-U03 | More exit policies, trailing stops and finer intrabar resolution | Conditional extension | Event-order evidence from C02/C07; changed policy gets new labels and a new C12 trial |
| C09-U04 | Margin, leverage, liquidation and actual account lifecycle | Conditional product/account extension | Compatible C01/C07/C13 models; leverage results require validated margin/liquidation semantics |

## C10 Expectancy and uncertainty

| ID | Work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C10-U01 | Simple cohort estimates, sample/coverage status and uncertainty | Required baseline after C11 | Earlier matured C09/C11 outcomes and C07 costs; frozen estimator evaluated on later observations |
| C10-U02 | Predictive/calibrated probability, payoff and quantile models | Conditional extension | C12 isolated fitting/calibration and sufficient samples; calibration and policy value both evaluated |
| C10-U03 | Conditional context/positioning and conservative admission policies | Conditional extension | C04/C06 and C13 policy tests; uncertainty assumptions and retained signal volume reported |

## C11 Historical simulator

| ID | Work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C11-U01 | Historical clock, independent candidate replay, fills, funding and reconciled trade ledgers | Required baseline | C01/C02/C03/C06/C07/C08/C09; first complete historical trading E2E and golden ledger totals |
| C11-U02 | Frozen C10 inference and C13 finite-capital portfolio simulation | Required later integration | C10/C13, injected state and C12 orchestration; simultaneous positions/capital and attribution reconcile |
| C11-U03 | Mark-to-market equity, regular risk metrics, tails and intraday/swing attribution | Required research reporting | Shared lifecycle and sufficiently complete mark/fill evidence; report unresolved outcomes and holdings |
| C11-U04 | Higher execution fidelity and large-universe run performance | Conditional fidelity/scale upgrade | C02-U01/U02, C03-U01 and C07; reproducible stress/ambiguity results and measured resource limits |

## C12 Research validation and registry

| ID | Work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C12-U01 | Frozen experiment contracts, trial registry, folds, purging, holdout and promotion | Required baseline | C09/C10/C11; fit boundaries, overlapping labels and reproducible later-data evaluation verified |
| C12-U02 | Nested parameter/model selection and resumable orchestration | Required where tuning is used | Complete trial accounting; failed jobs resume without changing the experiment or viewing forbidden data |
| C12-U03 | Dependence-aware uncertainty, cross-asset/time stress, ablations and selection diagnostics | Required evidence plus conditional diagnostics | Adequate outcome samples; assumptions, failed/null results and all attempted variants are retained |
| C12-U04 | Release registry, monitored replacement workflow and richer experiment UI | Baseline release records; conditional interface extension | C14/C15 and shared UI; a revised policy must pass a new declared evaluation |

Basic C09 outcome and C12 holdout/trial rules must be settled before inspecting strategy performance, even though their full code comes later. TBot-used data remains development data.

## C13 Portfolio and alert selection

| ID | Work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C13-U01 | Shared capital, risk, notional limits, admission, sizing and conflicts | Required baseline | C01/C03/C07/C09/C10; simultaneous-trade E2E and combined C11/C12 policy validation |
| C13-U02 | Correlation/beta/concentration and cross-horizon overlap | Required before broad simultaneous strategies | Representative portfolio evidence; intraday and swing exposure cannot be counted independently by default |
| C13-U03 | Adaptive allocations and more complex ranking/size policies | Conditional extension | Forward evidence and new C12 experiments; sizing changes do not establish predictive edge |

## C14 Live signals and Telegram

| ID | Work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C14-U01 | Shared live decision pipeline, approved-release checks and persistent signal/outbox state | Required baseline | C01/C02/C03/C07/C08/C09/C10/C13 and C12 release artifacts; replay/live decision parity |
| C14-U02 | Telegram format, expiry, throttling, retry and ambiguous-delivery reconciliation | Required baseline | Explicit test bot/chat configuration; deterministic delivery E2E and manual message acceptance |
| C14-U03 | Supervision, durable deployment, pause, backup/restore and measured runtime latency | Required operational validation | C02 collectors, shared storage and C15 monitoring; stale instructions remain suppressed during outages/restarts |
| C14-U04 | Dashboard/API and additional notification destinations | Conditional interface extension | Shared service design; preserve evidence IDs, access control and lifecycle semantics |
| C14-U05 | Automated order execution | Separate extension outside manual-trading scope | Explicit user request, account authorization and new execution/risk/E2E review |

## C15 Forward measurement and monitoring

| ID | Work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C15-U01 | Paper/shadow outcome tracking, measured costs/delays and replay reconciliation | Required baseline | C02/C07/C09/C10/C13/C14 and C11/C12 artifacts; complete signal-to-matured-outcome E2E |
| C15-U02 | Operational health, predeclared degradation rules and pause reasons | Required baseline | Persisted telemetry and adequate matured evidence; separate data/service failure from statistical underperformance |
| C15-U03 | Optional user-fill reconciliation and research/live comparison interface | Conditional account/interface extension | Voluntarily supplied actual fills; paper and actual user outcomes remain distinct |
| C15-U04 | Drift/calibration analysis and replacement-version experiments | Conditional analytical extension | Sufficient sequential data and C12 controls; monitoring does not silently retrain or rewrite prior decisions |

## Cross component completion gates

- Every implemented component receives unit/integration tests and the E2E workflow possible at that stage. External-service smoke is separate and opt-in. Actual manual acceptance uses fixed scenarios and visible evidence, as specified in [the E2E milestones](PLATFORM_PLAN.md#end-to-end-testing-milestones--agreed-requirement-added-13-october-2026).
- Before large backtests, resolve data/calendar coverage and characterize C03's long-history workload. Before strategy promotion, complete C12 validation. Before unattended Telegram use, complete C14 recovery/deployment and C15 monitoring prerequisites.
- Shared future work includes consistent service interfaces, migrations, redacted logs, backup/restore, operator UI, deployment configuration and measured scale. These have owners above; they are not implied capabilities of the current CLI package.
- Feature correctness, engineering reliability and positive net expectancy have separate acceptance gates. The platform can reject every strategy and still meet its engineering requirements.
