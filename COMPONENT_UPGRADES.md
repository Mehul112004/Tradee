# Component implementation and future upgrades

Updated 19 October 2026. Tradee implements each component's agreed initial scope, verifies that scope, and extends it when its dependencies and evidence are available. C01, C02 and C03 are complete within their documented initial scope; C06 adds funding accounting, C07 adds market execution/costs, C08 adds two independent setup families, and C09 adds shared paper trade lifecycles/accounting. Some broader functionality and operational validation remain outstanding. The tables below make those gaps explicit for all fifteen components.

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
| C08 | Independent 15m range-breakout and EMA recovery setups, full inventories and causal restart | Implemented two-family scope | C09 paper lifecycle now wired; C11/C12 after-cost evidence, more horizons/context and scale remain |
| C09 | Independent paper lifecycle, fixed/partial/time/invalidation exits, exact ledger and maturity/unresolved outcomes | Implemented initial scope | C11 historical wiring complete; real-data controlled experiments, finer path/execution, external action journaling and account effects remain |
| C10 | Causal cohort fits, time-block uncertainty, frozen inference, coverage/abstention and later scoring | Implemented cohort baseline | representative real-data C12 validation, predictive/calibrated extensions, C11/C13/C14 deployment integration and scale |
| C11 | Independent historical simulation, causal revisions, reconciled ledgers, regular P&L and cost/delay sensitivity | Implemented independent scope | C10/C13 injection, finite-capital equity/risk, representative real-data controlled experiments and scale/fidelity upgrades |
| C12 | Nested chronological selection, purging, independent-signal evidence, trial/job registry and controlled holdout/release | Implemented research baseline | Representative untouched market validation, C13 portfolio integration, stronger prospective custody, scale/UI and conditional diagnostics |
| C13 | Portfolio and alert selection | Required next | Shared capital/risk constraints and combined-policy validation |
| C14 | Live orchestration and Telegram | Required next | Persistent runtime, eligibility, delivery lifecycle and live E2E |
| C15 | Forward measurement and monitoring | Required next | Signal-to-outcome tracking, reconciliation and degradation rules |

C11 independent historical simulation, C10 causal cohort expectancy and C12 walk-forward/experiment control are implemented. The next component is C13 portfolio risk and alert selection. C04/C05 and predictive C06 additions remain optional. Historical candidate-to-outcome workflow testing is now available in C11; Telegram workflow testing arrives at C14 and the complete forward feedback loop at C15. These milestones do not imply an existing dashboard or automated exchange orders.

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
| C02-U08 | Portable content-qualified dataset identities and cross-store export/merge | Required when moving/combining independent stores | Current dataset manifests qualify event IDs inside their originating store; equal IDs/times can name different bytes in another store. C12 now mitigates outcome-source substitution with mandatory C11 report hashes. A future C02 format/migration must bind event contents or an immutable store namespace and verify replay equivalence across exports |

Process supervision and an unattended deployment belong to C14/shared operations; the current C02 collector runs in the foreground. Trade/quote history is not certified gap-free, and current quotes cannot repair missing historical quotes.

## C03 Feature engine

Implemented evidence: [C03 formula contract](C03_FEATURE_SPEC.md), [C03 verification](C03_VERIFICATION.md).

| ID | Remaining work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C03-U01 | Incremental numerical caches, efficient lineage/checkpoints and long-history throughput | Validation outstanding; priority before large C11 runs | Representative datasets; exact prefix/correction/restart parity preserved. Immutable record digests are now cached after the C11 public-replay bottleneck; current feature reference reconstruction can still accumulate quadratic work |
| C03-U02 | MACD, ADX, Supertrend, stochastic RSI and Keltner channels | Conditional feature extensions | Freeze formulas/seeds/zeros first; independent fixtures and later C12 ablation justify use |
| C03-U03 | OBV/CVD, depth/order-flow, volume profiles and swing-anchored VWAP | Conditional extensions | C02 evidence continuity and, where needed, C05 anchors; no fabricated tick/depth coverage |
| C03-U04 | Derivatives, cross-asset/context and fitted ML transforms | Conditional extensions | C04/C06 and C12 fold-controlled fitting; transforms preserve availability and fit boundaries |
| C03-U05 | Predictive feature-family ablation after costs | Validation outstanding | C07/C08/C09/C11/C12; compare matched opportunities, costs, sample loss and uncertainty on later data |

The current 45 named definitions and parameterized simple returns are implemented, including C08-required `ema20_prior`/`ema50_prior`. Adding more indicators does not substitute for C03-U01 or predictive evidence. Default daily EMA50 readiness needs 396 contiguous daily bars; a one-day benchmark does not validate that workload.

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

Implemented now: signed exact funding arithmetic for identified USDT perpetual exposure, partial-exit quantity inputs, observed next-settlement estimates, strict/nominal boundary policies, explicit calendar checks, corrections without duplicate full charges, immutable recorded-prefix reports, atomic checkpoints, CLI and current-foundation E2E tests. C09 now owns paper position state and keyed ledger booking; C06 outputs are accounting evidence/scenarios, not confirmed account transactions.

| ID | Remaining work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C06-U01 | Automatically acquired, audited funding calendars and interval/cap history | Deferred data upgrade; important before broad C11 experiments | C02-U04; detect missing settlements across interval changes. Current totals are conditional on a caller-declared calendar, never certified complete from observed records alone |
| C06-U02 | Live position/fill evidence and one-time ledger reconciliation | Paper lifecycle implemented in C09; live/account wiring outstanding | C07/C09/C11/C14; C09 supplies resulting paper quantities and replaces funding revisions once; actual fill/income reconciliation remains separate |
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
| C07-U06 | Shared lifecycle, realized fills and ledger/account constraints | Independent paper lifecycle/ledger implemented in C09; shared account constraints outstanding | C11/C13/C14; C09 books admitted paper fills/fees/funding once and rechecks pending setup; shared capital/liquidity and actual account constraints remain |
| C07-U07 | Representative throughput, storage retention and unattended recovery | Operational validation outstanding | C02/C03/C14; benchmark history/universe sizes and cold restarts, migration/backup and physical failure recovery beyond statement rollback |

## C08 Candidate generation

Implemented evidence: [C08 research definitions](C08_RESEARCH_PLAN.md), [contracts and boundaries](C08_IMPLEMENTATION.md), [verification](C08_VERIFICATION.md).

The user explicitly expanded the initial scope to **both range breakout and trend continuation** on 16 October 2026. Implemented now: separate hypothesis/spec hashes and 15m presets, strict prior-range/recovery predicates, shared C03 indicators and lagged EMA readiness, observed metadata timelines or labeled research assumptions, complete per-direction diagnostics/coverage, revision-only recorded corrections, immutable artifacts, atomic restart, CLI pagination/inspection and two-family E2E. No strategy has performance-based approval.

| ID | Work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C08-U01 | Explicit strategy triggers, candidate snapshots and rejection reasons | Implemented for two initial families | C01/C03; independent formulas and long/short fixtures, full opportunities, causal metadata/revisions and CLI-process recovery E2E |
| C08-U02 | Further strategy families and separate swing horizon | Deferred beyond the two user-authorized initial families | C09/C11/C12 first; record every hypothesis/variant and validate intraday/swing separately. General timeframe configuration is not evidence that another horizon has been validated |
| C08-U03 | Market-state, levels and positioning inputs | Conditional extension | C04/C05/C06 predictors; added value survives costs and opportunity loss |
| C08-U04 | Executable action-time thesis checks, lifecycle and cost/outcome validation | C09 paper lifecycle and pending-thesis checks implemented; performance validation outstanding | C07/C06/C11/C12; fixed/partial/time policies and keyed charges are available, while active-thesis correction handling and independent after-cost family/baseline experiments remain |
| C08-U05 | Multi-year/universe throughput, incremental state and storage retention | Operational validation outstanding | C02/C03/C11/C14; current reference engine retains/reconstructs history, so benchmark realistic lengths and restart/backup behavior before broad experiments |
| C08-U06 | Complete trials, fit/holdout isolation and promotion registry | C12 research baseline implemented; empirical strategy validation outstanding | C12 now counts source-qualified trials and records isolated fitting/holdout decisions; C08 definitions/inventories supply evidence. Representative strategy experiments and C13/C14/C15 gates still precede live alerts |

## C09 Trade policy and outcomes

Implemented evidence: [C09 research decisions](C09_RESEARCH_PLAN.md), [contracts and ownership](C09_IMPLEMENTATION.md), [verification](C09_VERIFICATION.md).

Implemented now: exact C08 source-prefix activation, pending thesis/expiry checks, C07 market entry/reduce-only exit attempts, fixed reference stop/target, optional partials, delayed/time/explicit invalidation exits, conserved quantity timelines, one-time fees, C06 keyed funding replacement, sampled excursions, separate target-first/net-profit labels, outcome revisions/knowledge times, unresolved data tails, atomic restart and connected CLI E2E. Candle path/ordering and unavailable funding remain explicit rather than invented.

| ID | Work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C09-U01 | Entry/exit/expiry lifecycle, ambiguity rules, fills, quantity state and cost/funding ledger | Implemented initial independent-paper scope | C01/C06/C07/C08; independent long/short, gap, partial/time/invalidation/blocked exits, exact fees/funding and restart E2E |
| C09-U02 | Outcome labels, maturity, excursions and unresolved tails | Implemented initial evidence contract; downstream validation required | Policy-specific gross/net R, event versus profit labels, stable outcome-revision recognition time, sampled excursions and null unresolved labels; C11/C12 must respect availability and unresolved counts |
| C09-U03 | More exit policies, trailing stops and finer intrabar resolution | Conditional extension | Event-order evidence from C02/C07; changed policy gets new labels and a new C12 trial |
| C09-U04 | Margin, leverage, liquidation and actual account lifecycle | Conditional product/account extension | Compatible C01/C07/C13 models; leverage results require validated margin/liquidation semantics |
| C09-U05 | Full strategy simulation, finite-capital admission and research outcomes | C11/C12 independent research wiring implemented; C13 integration remains | Both C08 families replay to conserved inventories with cost attribution and C12 controlled research; representative real-data validation and funded capital/exposure constraints remain |
| C09-U06 | Durable external action journal and richer setup invalidation/correction policy | Forward-runtime extension | C14/C15; journal operator cancels and timer events, replay every action, define active-position response to thesis/source revisions and emergency exits without silently bypassing rule gates |
| C09-U07 | Continuous path certification, historical funding/rule coverage and account reconciliation | Data/fidelity upgrade | C01/C02/C06/C07; current excursions are sampled, bar-range conflicts remain unresolved, close-trigger fills are coarse and modeled funding stays null |
| C09-U08 | Large-history throughput, retained attempt/checkpoint size, migration/backup and physical recovery | Operational validation outstanding | C03/C11/C14; benchmark realistic histories/universe and compact durable evidence only after measured need |

## C10 Expectancy and uncertainty

Implemented evidence: [research decisions](C10_RESEARCH_PLAN.md), [implementation and limitations](C10_IMPLEMENTATION.md), [verification](C10_VERIFICATION.md).

| ID | Work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C10-U01 | Simple cohort estimates, sample/coverage status and uncertainty | Implemented statistical baseline; real-data policy-value evidence outstanding | Strict C11 revision selection, ledger/feature joins, full coverage, frozen protocol cohorts, synchronized circular time-block uncertainty, publication/inference and later evaluation; raw-input E2E and honest public-data abstention |
| C10-U02 | Predictive/calibrated probability, payoff and quantile models | Conditional extension | C12 isolated fitting/calibration and sufficient samples; calibration and policy value both evaluated |
| C10-U03 | Conditional context/positioning, shrinkage and admission policies | Basic lower-bound research gate implemented; contextual/pooling extensions conditional | C04/C06/C12/C13; current sparse cohorts abstain with no fallback. Fit shrinkage/context only with enough earlier evidence and report retained volume/dependence |
| C10-U04 | Empirical sample/gating thresholds, block-length sensitivity, heavy-tail/nonstationary robustness and uncertainty coverage | Required C12 validation; methods extensions conditional | Defaults are engineering safeguards, not power/coverage guarantees. Validate source-feed continuity/selection bias, block assumptions, unseen-outcome risk, abstention and complete admission policy on untouched later data without selecting favorable variants |
| C10-U05 | C11/C13 inference injection, release compatibility, live publication/refresh/revocation and monitoring | Required downstream integration | Estimator API is frozen; C12 records compatible research-only releases, C13 adds shared capital and C14/C15 own runtime/outbox/monitoring. Current later evaluation is not a capital-constrained policy backtest |
| C10-U06 | Incremental/out-of-core fitting, source/protocol adapters, provenance policy, migrations/backups and representative multi-year benchmarks | Operational/data validation outstanding | Current source validation loads artifacts and fixed cohort bootstrap in memory with explicit budgets; no silent truncation or automatic producer-version mixing |

## C11 Historical simulator

Implemented evidence: [research decisions](C11_RESEARCH_PLAN.md), [implementation and boundaries](C11_IMPLEMENTATION.md), [verification](C11_VERIFICATION.md).

| ID | Work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C11-U01 | Historical clock, independent candidate replay, fills, funding and reconciled trade ledgers | Implemented independent baseline | C01/C02/C03/C06/C07/C08/C09; both-family E2E, exact timers/windows, full inventories, causal outcome revisions, golden quantities/gross/fees/net and atomic publication/retry |
| C11-U02 | Frozen C10 inference and C13 finite-capital portfolio simulation | C10 API implemented; combined replay/portfolio injection remains required | C10/C13, injected state and C12 orchestration; simultaneous positions/capital and attribution reconcile |
| C11-U03 | Mark-to-market equity, regular risk metrics, tails and intraday/swing attribution | Independent regular P&L/coverage, dollar drawdown, tails and horizon attribution implemented; funded equity/returns await C13 | Fresh mark or declared bar proxy; null missing marks/funding, unresolved counts and no portfolio Sharpe/ROI. Capital/margin model required before portfolio equity or percentage/annualized risk metrics |
| C11-U04 | Higher execution fidelity and large-universe run performance | Conditional fidelity/scale upgrade | C02-U01/U02, C03-U01 and C07; reproducible stress/ambiguity results and measured resource limits |
| C11-U05 | Mid-run simulation checkpoints, out-of-core artifact/position execution, migrations, backup/recovery and multi-year benchmarks | Operational/scale validation outstanding | Current completed runs publish atomically and restart both passes on interruption; explicit budgets fail without truncation. Preserve exact source/clock/revision parity when adding resumable bounded-memory execution |
| C11-U06 | Uncertainty, sealed holdouts, cross-fold ownership, overlapping labels and complete experiment/trial registry | C10/C12 independent-signal integration implemented; empirical/portfolio validation outstanding | Revision-aware fits, chronological isolation, purging and research release records now exist; representative real-data evidence and C13 shared-capital evaluation remain |

## C12 Research validation and registry

Implemented 19 October 2026: frozen run/report-content/code/runtime experiments, earlier-only nested selection (or explicit fixed rules), label-aware pre-test purging, half-open outer ownership, actual C10/C11 integration, joint time-block independent-signal utility, family tail allocation, stress/neighborhood/leave-group diagnostics, durable trial/job/audit accounting, one-way holdout access and immutable research release/rejection records. See [research](C12_RESEARCH_PLAN.md), [operation](C12_IMPLEMENTATION.md), [verification](C12_VERIFICATION.md). All releases keep `live_approved: false`.

| ID | Work | Type | Dependencies and completion gate |
| --- | --- | --- | --- |
| C12-U01 | Frozen experiment contracts, trial registry, chronological folds, purging, holdout and research decisions | Implemented baseline; representative market validation outstanding | Actual C10 fits/evaluations over pinned C11 sources; attested inspection history, reliable real feed/cost/funding evidence and adequate dependence spans remain prerequisites. Counts/disclosures do not reconstruct missing old TBot trial records |
| C12-U02 | Nested predeclared estimator/strategy selection and resumable jobs | Implemented bounded orchestration; operational scale upgrades outstanding | Completed jobs stay immutable, failed/running jobs retry under the same source/runtime; 32 variants/20 folds/20 inner folds, 1,000 jobs, 50 MB per artifact and explicit bootstrap budgets. Distributed scheduling, Windows locking, mid-job checkpoints, migrations and backup/recovery remain future work |
| C12-U03 | Dependence uncertainty, cross-asset/time sensitivity, adverse fee/delay stress and neighborhood checks | Implemented signal-level evidence; specialized diagnostics conditional | Joint calendar blocks, approximate family tail allocation, attribution and leave-group diagnostics implemented. User must predeclare actual variants/block sensitivity/ablations; automatic grids, full refit/reselection uncertainty, richer selection tests and DSR/PBO await defensible assumptions and C13 regular funded returns. No DSR/Sharpe on irregular trade R |
| C12-U04 | Frozen release registry, monitored replacement and experiment UI | Research release/rejection manifests implemented; downstream integration/UI outstanding | Frozen policy/model/protocol/evidence hashes exist now; actual C13/C14 promotion, prospective re-fit availability, C15 replacement/degradation workflows, signed artifacts and richer UI remain. New design means a new counted experiment with untouched final evidence |
| C12-U05 | Prospective unknown-data attachment and stronger holdout custody | Conditional operational extension | Baseline pins already generated, uninspected C11 run hashes; registration does not yet accept unknown future run hashes with a controlled later attachment. API access cannot prevent C11/raw-file inspection or dishonest disclosures; controlled collection/access and cross-registry history import are needed for stronger custody |
| C12-U06 | Full portfolio-policy walk-forward evaluation and learned calibration/search | Required when those capabilities are added | C13 shared-capital runner must supply causal admission and regular equity; any learned transform/calibrator/search needs inner-only fitting and complete expanded trial accounting. Current C10 broad-cohort inference is not a calibrated classifier |

Previously inspected/TBot data remains development data. Synthetic tests exercise positive, negative and unknown-outcome research decisions without establishing a real-market edge. C12 does not bypass the remaining C13/C14/C15 or market-data/cost-validation gates.

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
