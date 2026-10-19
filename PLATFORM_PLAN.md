# Tradee platform plan

## Agreed component working order

Updated 14 September 2026. For each component: **deep research and discussion → finalize its plan → user approval → implementation and verification**. The user authorized C01 implementation with Binance; its first version is now implemented. See [README.md](/Users/artemis/Mehul/Tradee/README.md) for operation and verification.

Status updated 19 October 2026: C01, C02, C03, C06 funding, C07 execution/costs, C08 two-family candidate generation, C09 paper trade lifecycles/ledgers and C11 independent historical simulation/attribution are implemented. C11 follows the same robust-testing, E2E, documentation and commit workflow. Next is C10 expectancy from causal matured-outcome revisions, then C12 walk-forward and selection control. [COMPONENT_UPGRADES.md](COMPONENT_UPGRADES.md) tracks implemented scope, required remaining functionality and future upgrades for every component; update it with every implementation increment.

| Order | Component | Initial scope |
| --- | --- | --- |
| 1 | C01 — Instrument and universe registry | Contract identity, eligibility, trading rules and metadata history |
| 2 | C02 — Market data and replay | Audited historical/live inputs and deterministic replay |
| 3 | C03 — Feature engine | Minimal shared mathematical measurements |
| 4 | C06 — Funding fundamentals | Settlement accounting; predictive positioning features deferred |
| 5 | C07 — Execution and tradability | Fills, fees, slippage and manual-entry delay |
| 6 | C08 — Candidate generation | Independent range-breakout and trend-continuation baselines |
| 7 | C09 — Trade policy and outcomes | Shared entry/exit lifecycle and outcome definitions |
| 8 | C11 — Historical simulator | Independent candidate evaluation and verifiable ledgers first |
| 9 | C10 — Expectancy and uncertainty | Estimates from earlier matured outcome artifacts |
| 10 | C12 — Research validation | Walk-forward orchestration, trial accounting and promotion |
| 11 | C13 — Portfolio and alert selection | Shared risk limits; extend C11 with portfolio-policy evaluation |
| 12 | C14 — Live signals and Telegram | Deliver the validated policy with persistent state |
| 13 | C15 — Forward measurement | Reconcile research assumptions with live observations |

**Preparation before strategy experiments:** agree the basic C09 outcome definitions and C12 research/holdout rules before inspecting performance, even though their full implementations occur later.

**Optional extensions:** C04 market-state filters, C05 price structure and predictive C06 positioning features follow the baseline pipeline. Bring an extension forward if the chosen initial strategy explicitly requires it.

The numbers C01–C15 identify components, not build sequence. Each component initially delivers its agreed minimum scope and can be extended through later reviewed increments. The broader phases below group this work; this table is the current component working order.

Original planning draft — 6 September 2026; implementation status updated 19 October 2026. C01–C03, C06 funding, C07 execution, C08 setup detection, C09 paper outcomes and C11 independent historical simulation are implemented. Finite-capital simulation awaits C13; expectancy, walk-forward and performance validation remain downstream.

Expanded research: [Components for finding positive net expectancy setups](/Users/artemis/Mehul/Tradee/COMPONENT_RESEARCH.md), researched 9 September 2026, specifies fifteen modules, their evidence, dependencies and acceptance criteria.

The expanded specification now includes a typed dependency/consumer matrix, each component's major internal parts and output contracts, and a review-first research sequence. Use the [component review template](/Users/artemis/Mehul/Tradee/COMPONENT_REVIEW_TEMPLATE.md) for individual deep dives. Implementation will follow component research and review.

## 1. Objective and agreed scope

Build a research and live signal platform for **Binance USDT-margined perpetual futures**, supporting **intraday and swing trading**, with delivery to Telegram.

The platform must establish whether a precisely defined strategy has evidence of an edge after realistic costs, reproduce its decisions, and track how its live signals perform. Reliable software and profitable strategies are separate outcomes; the research process must be able to reject every strategy.

Proposed first-release scope:

- Personal use, with manual trade execution. Account integration and automatic orders would be a separate extension.
- BTCUSDT and ETHUSDT as a small engineering/research universe; broader liquidity-based selection follows after the pipeline works. These are scope choices, not trading recommendations.
- Intraday decisions on 15m/1h candles, with 4h context; swing decisions on 4h candles, with daily context. Each strategy declares its exact inputs and holding horizon.
- Closed-candle strategy evaluation. Live quotes support freshness, spread checks, and outcome tracking.
- Separate validation for intraday and swing strategies, plus joint risk evaluation when their signals overlap.
- Implement range-breakout and trend-continuation as separate initial hypotheses, as requested on 16 October 2026. Add a second horizon after the complete trading/validation pipeline is trustworthy.

## 2. What TBot teaches us

A targeted read of TBot's documentation and relevant backtest/research code found useful foundations: closed-candle enforcement, next-open simulation, fixed detection-time levels, conservative stop/target conflict handling, experiment manifests, anchored walk-forward folds, and an explicit final holdout.

The initial TBot review referenced `docs/backtesting.md` and `docs/walk-forward-signal-validation-plan.md` and identified the limits below. Those two document paths are absent from the current TBot checkout, so they are retained here as historical references rather than active links:

- Historical costs use an all-in basis-point assumption, without separate funding, spread, fee, and size-dependent impact accounting.
- Walk-forward validation is narrowly scoped to one frozen strategy/symbol/timeframe; rolling selection and portfolio evaluation are deferred.
- Raw strategy confidence is used for simultaneous-signal selection without cross-strategy calibration.
- Some live paths differ: the README describes LLM-reviewed setups and a separate live-candle EMA alert path.
- Runtime stream/session recovery is incomplete according to the README.

These observations define requirements for Tradee. They do not prove the cause of poor returns. No old strategy has been rerun or statistically audited in this review. The new codebase should preserve useful specifications and regression scenarios while independently verifying the implementation.

**Prior research still counts:** data repeatedly inspected or used to tune TBot is development data for Tradee too. Starting a new repository does not create a fresh holdout.

## 3. Decisions and practical prerequisites

| Decision/input | Proposed starting point or requirement |
| --- | --- |
| Market and pace | Confirmed: USDT perpetual futures; intraday and swing |
| Initial universe | Proposed: BTCUSDT and ETHUSDT; explicitly record survivor-selection limitations |
| Historical coverage | Target several years spanning varied conditions, ideally 3–5 where available; audit actual coverage before setting fold dates |
| Execution assumptions | Manual entry; declare market/limit entry, user delay, signal lifetime, stop trigger source, and missed-entry rules |
| Research risk policy | Choose model account equity, per-trade loss budget, total concurrent risk, notional/margin caps, and tolerated drawdown before performance-based promotion |
| Strategy lifecycle | Fixed rules first; bounded tuning only within chronological development windows |
| Hosting | Always-on host with working Binance and Telegram connectivity, stable clock, persistent storage, backups, and restart supervision |
| Secrets | Telegram bot token and destination chat ID, supplied only when notification integration starts; keep secrets outside source control |
| Exchange access | Verify public market-data access from the intended host; signal-only market-data collection should not require trading permissions |
| Operational budget | Agree monthly hosting/storage budget and retention policy after a representative ingestion benchmark |
| Product scope | Assume one user and a private dashboard; multiple users require separate authentication, subscriptions, and tenant isolation design |

A provisional candle-based development host can start around 4 CPU cores and 8–16 GB RAM. This is a sizing assumption to benchmark, not a capacity promise. Tick retention and parallel experiments can increase disk and memory needs substantially. A GPU is not a prerequisite for the proposed rules-based scope.

## 4. Platform components

```text
Binance archives + REST + WebSockets
                 |
        ingestion and integrity checks
                 |
       versioned canonical market data
                 |
          common feature/strategy core
             /                  \
 historical event replay     live event processing
           |                       |
 backtests + walk-forward     evidence + risk policy
           |                       |
     strategy registry ------> approved signal lifecycle
                                   |
                         durable Telegram delivery
                                   |
                         paper outcomes + monitoring
```

Use one modular Python codebase with independently supervised collector, live runner, research worker, API, and notification worker processes. Heavy backtests must not block market ingestion. Persist checkpoints so a web-server restart cannot silently remove active monitoring.

Proposed stack: Python for features, simulations, and services; NumPy/pandas for initial calculations; PostgreSQL for operational state; Parquet for immutable research datasets; DuckDB for querying those datasets; FastAPI for the API; React/TypeScript for a small dashboard. Start with a database-backed job queue and delivery outbox. Introduce additional infrastructure only when measured load requires it. DuckDB supports direct Parquet querying; see its [Parquet documentation](https://duckdb.org/docs/stable/data/parquet/overview). Deployment must account for restarts, replication, and worker memory, as described in [FastAPI deployment concepts](https://fastapi.tiangolo.com/deployment/concepts/).

The key design choice is the shared, deterministic strategy core. API and frontend choices do not establish a trading edge.

## 5. Historical and live data

Minimum datasets:

| Dataset | Purpose |
| --- | --- |
| Contract OHLCV, initially 1m plus derived higher intervals | Feature calculation and finer-resolution outcome replay |
| Live best bid/ask and trades where needed | Spread measurement, entry-delay observations, and forward outcome tracking |
| Historical funding events and rates | Cash flows for positions held through settlement |
| Mark/index prices as required | Funding valuation and declared trigger/margin semantics |
| Instrument metadata | Contract identity, listing/delisting times, status, tick size, quantity step, and notional rules |
| Raw ingestion records and provenance | Debugging, replay, revisions, and dataset reconstruction |

Binance provides daily/monthly public data archives and checksum files. Use them for bulk history, REST for recent data and gap repair, and WebSockets for ongoing updates. Validate schema and timestamp units per dataset instead of assuming all Binance data is identical. See [Binance public data](https://github.com/binance/binance-public-data). Funding history contains settlement timestamps and associated mark-price information; use actual events rather than a hard-coded funding interval. See [Binance futures market data](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data).

Canonical records need exchange, product, symbol, event time, receive time, availability time where known, interval, candle finality, source, and revision/version. Historical OHLCV cannot recover original network arrival times; declare an availability-delay model for archive replay and measure actual delays going forward.

Required integrity controls:

- UTC and explicit timestamp units; unique event/candle keys and deterministic ordering.
- Reject invalid OHLC envelopes and non-finite prices; report missing, duplicated, stale, or inconsistent data.
- Never silently fill missing market candles into tradable observations. Repair from a verified source or quarantine the affected span.
- Derive a higher-timeframe bar only from complete finalized component bars. Use it only after it is available; define deterministic handling of simultaneous closes.
- Record dataset fingerprints and source checksums. Corrections create new versions instead of changing old experiment inputs.
- Buffer during bootstrap/reconnect, backfill from the last durable checkpoint, deduplicate overlap, verify continuity, then resume signal eligibility.
- Handle heartbeat timeouts, connection rotation, subscription limits, rate limits, reconnect backoff, and schema changes. Keep adapter behavior aligned with current [Binance futures stream documentation](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/public).

Do not assume historical quote or full order-book data exists for the desired period. Any strategy needing unavailable inputs remains untestable until suitable data is acquired or recorded. One-minute OHLCV improves resolution but still does not reveal the complete price path.

## 6. Mathematical features and strategy contracts

Start with a small, transparent feature set:

- Log return: `log(close[t] / close[t-1])`.
- Rolling realized volatility from past returns; ATR for price-range normalization.
- Trend features: moving-average distance/slope and breakout range, normalized by volatility where appropriate.
- Mean-reversion features: a rolling z-score using past-window mean and standard deviation.
- Volume and liquidity filters; funding context only with point-in-time availability.

These are candidate measurements, not proven predictors. A hypothesis might be that a volatility-normalized breakout has positive net expectancy in a predeclared trend regime. Test a small number of economically motivated ideas and measure whether each extra filter improves unseen results.

Every strategy must declare:

1. Hypothesis, market scope, timeframes, and data requirements.
2. Warm-up, feature availability, parameters, and code version.
3. Entry conditions/order type, entry validity period, stop, target, and maximum holding time.
4. Exit precedence, partial exits if any, and invalidation rules.
5. Eligibility filters and machine-readable reasons for a signal or no signal.
6. State transitions and checkpoint format.

Strategies consume time-bounded inputs through the common core. They must not read unrestricted future data or call external services during evaluation. Historical prefixes and event-by-event replay must produce equivalent decisions. Pivots requiring later confirmation become available only at confirmation time.

Defer LLM verdicts, elaborate pattern libraries, and automated parameter searches until deterministic baselines have credible evidence. If a score is introduced, call it a rule score until separate unseen-data calibration supports a probability interpretation.

## 7. Proper backtesting

Maintain two distinct evaluation tracks:

| Track | Question | Outputs |
| --- | --- | --- |
| Independent candidates | Does the detector identify useful opportunities? | Net expectancy in R, hit rate, payoff distribution, adverse/favorable excursion, duration, skips, uncertainty |
| Executable paper policy | What happens with finite capital and simultaneous opportunities? | Mark-to-market equity, drawdown, net returns, exposure, turnover, margin use, risk-adjusted returns |

Independent overlapping opportunities cannot be compounded into an account equity curve. The paper policy must model shared capital across symbols, intraday/swing overlap, deterministic selection, and correlated exposure limits.

The simulator must account for:

- A decision using only information available at that instant; no same-close fill based on an already inspected close.
- Next available executable price plus latency. A next-bar-open model is a baseline; Telegram/manual execution also needs delayed-entry scenarios.
- Entry and exit fees with declared maker/taker assumptions, spread/slippage without double-counting, and funding cash flows.
- Quantity rounding, minimum size/notional, leverage/margin constraints, and liquidity/participation assumptions.
- Mark-price versus contract-price triggers; leverage experiments require margin and liquidation handling before their account results are valid.
- Unfilled/expired limit entries; a candle touching a limit is not evidence of queue execution.
- Gaps through stops, missed entries, stop and target reached in the same bar, and end-of-data unresolved trades.
- Conservative stop-first treatment for unresolved intrabar conflicts, with finer replay where available; report ambiguous cases and sensitivity.
- Immutable detection-time levels and explicit target/partial-exit semantics.

Reports must separate gross result, each cost component, and net result. Define one R as the declared initial price-risk budget and include costs in realized net R. Report trade count, sample duration, expectancy with uncertainty, profit factor, drawdown and recovery duration, turnover, exposure, and worst fold. Calculate Sharpe/Sortino from a declared regular mark-to-market return series, not irregular per-trade outcomes.

Compare against no-trade and simple strategy baselines under compatible exposure/cost assumptions. Use buy-and-hold as contextual market exposure, clearly labelled if its risk differs.

## 8. Walk-forward and research discipline

Walk-forward simulates what could have been selected using earlier information and then tests that selection on the next unseen period.

1. Register the hypothesis and every material attempted variant, including failed experiments.
2. Reserve a final chronological holdout. Previously inspected TBot periods cannot be claimed as untouched.
3. Define outer development/test folds, cost scenarios, metrics, and promotion criteria before looking at outcomes.
4. For frozen strategies, evaluate the fixed specification on successive unseen windows. For tuned strategies, use an inner chronological train/validation split inside each outer development window.
5. Fit normalization, regime thresholds, feature selection, and parameters only on permitted earlier data; freeze them for the next outer test window.
6. Purge training labels whose outcome intervals cross a test boundary. Derive separation from actual holding/label horizons and apply an embargo where the split design requires it. Warm-up can use earlier history without scoring it.
7. Join non-overlapping outer test results in chronological order. Specify how positions crossing fold boundaries are owned, carried, or closed and how parameter changes affect existing positions; never count a trade twice.
8. Review stability, parameter neighborhoods, cost/delay stress, and concentration by asset, direction, regime, and time.
9. Reveal the final holdout once after the experiment is frozen. Changes inspired by it require fresh future evaluation.
10. Run forward paper validation using the actual live ingestion and alert paths.

An illustrative intraday design might use 12 months of development followed by 2 months of testing, advancing 2 months each fold. Swing strategies may need longer windows to accumulate observations. Exact dates and sizes depend on clean coverage, label horizons, and expected signal counts, not which split produces the best return. Reserve a later final holdout and sufficient outcome-resolution data.

Use block-based uncertainty estimation that preserves time dependence and joint cross-asset behavior. Keep a trial ledger and account for selection across variants; multiple-testing adjustment cannot rescue unrestricted experimentation. The risk from selecting the best of many backtests is documented in [The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

Promotion should produce **eligible for paper validation**, **insufficient evidence**, or **rejected**, with reasons. Predeclare required net expectancy, uncertainty tolerance, drawdown limits, fold/regime coverage, and stress tolerances. No universal win-rate or trade-count threshold establishes an edge. Sparse swing results may require months of additional observation.

## 9. Live signals and Telegram

Each candidate stores its strategy/data versions, inputs, rule decisions, signal time, entry/stop/target/expiry, evidence status, and reasons for admission or rejection. Keep rejected candidates too, so filtering can be evaluated without selection bias.

Proposed lifecycle: detected → eligible or suppressed → pending entry → entered in paper model or expired/cancelled → closed in paper model. Telegram delivery status is tracked separately from trading state. A modelled entry is not confirmation that the user traded.

Each Telegram signal should include symbol and product, long/short, intraday/swing label, timeframe, timestamp/age, entry rule or range, stop, targets, expiry, invalidation, brief deterministic rationale, and a link/ID for its evidence record. Display validation sample and status rather than unsupported confidence percentages.

Persist signals and delivery jobs atomically in a durable outbox. Use stable IDs, retries with backoff, delivery logs, throttling, and recovery after restart. Telegram retries can be ambiguous after a timeout; document possible duplicate delivery rather than promising exactly-once messages. Drop expired entry alerts rather than flooding the chat after an outage. Respect [Telegram's documented messaging limits](https://core.telegram.org/bots/faq#my-bot-is-hitting-limits-how-do-i-avoid-this).

Track detection-to-send latency, Telegram acceptance, paper entry delay, and optional user-recorded fills separately. Telegram API acceptance does not prove the user received/read the message. Signal quality, simulated tradability, and actual user P&L must remain distinguishable.

## 10. Reliability and verification

Essential controls: persistent checkpoints, process supervision, database migrations, backup/restore verification, private dashboard access, secret redaction, structured logs, and resumable research jobs with code/data/environment fingerprints.

Monitor feed freshness, gaps, reconnects, processing lag, strategy exceptions, queue age, delivery failures, observed spread/funding, and rolling paper performance. Suppress affected signals on stale or invalid data; allow an explicit operator pause. Detect degradation using predeclared monitoring rules, rather than repeatedly retuning on recent losses.

Meaningful acceptance checks:

- Small manually calculated trade cases for long/short P&L, funding, fees, gaps, partial exits, and ambiguity rules.
- Prefix-causality and higher-timeframe availability checks.
- Historical replay versus recorded live decisions for identical available inputs.
- Duplicate, out-of-order, missing-event, reconnect, restart, and queue-timeout recovery scenarios.
- Portfolio accounting with simultaneous trades, open P&L, capital constraints, and cross-horizon conflicts.
- Fold/holdout isolation, fitting boundaries, trade ownership, and reproducible runs.

### End-to-end testing milestones — agreed requirement added 13 October 2026

E2E verification is a completion requirement alongside unit and integration tests. Build and test complete workflows as their dependencies become available; a full-platform E2E suite is possible programmatically, with separate manual acceptance of the actual user experience.

| Available after | Workflow the user can exercise | Scope of acceptance |
| --- | --- | --- |
| C03 — available now | Market observations → persisted replay → features and readiness | Existing recorded Binance capture/replay smoke covers this foundation; C03 itself supplies measurements without setup/outcome logic |
| C06 — available now | Raw metadata/candles/funding/mark imports → replay/features → exact funding reports | Automated current-foundation E2E uses 26 actual CLI commands, fixed expected amounts and recovery after a failed write; preserves old reports after corrections and flags missing/ambiguous funding |
| C07 — available now | Raw candles/quotes/marks → same-dataset C03 readiness → C06 estimate → C07 paper fills/costs/rejections | 27 actual CLI commands, independent costs, persisted restart/idempotency, immutable revisions and explicit coarse-bar limitations |
| C08 — available now | Raw candles → shared C03 indicators → two independent 15m candidate inventories | Actual-process E2E detects expected long/short range/recovery setups, retains all direction/bar diagnostics and checks fault recovery, coverage, metadata availability and correction vintages; no backtest ledger yet |
| C09 — available now | Bound C08 candidates → C07 entries/exits → quantities/fees/C06 funding → independent trade outcomes | Actual CLI E2E verifies exact long/short net ledgers, failed-write recovery, null unknown funding and delayed-entry suppression; unit/integration cover partial/time/gap/ambiguous exits and funding revisions |
| C11 | Dataset → features → candidates → entry/fills → fees/funding → exits → net outcome ledger/report | First complete historical trading workflow, using C06/C07/C08/C09 and the same shared rules as later live operation |
| C12, then C13 integration | Earlier-data fitting/selection → frozen later-period evaluation → reports; then finite-capital combined-policy evaluation | Test fold isolation and experiment reproducibility; rerun C12 validation after adding C13 portfolio admission/risk rules |
| C14 | Live/replayed feed → decision gates → persisted signal/outbox → Telegram test delivery | Full alert flow, expiry, restart, freshness, delivery failure and retry behavior; actual Telegram use is an explicit opt-in test |
| C15 | Signal → forward paper lifecycle → matured outcome → monitoring/reconciliation | Complete signal-to-outcome feedback loop, including pause reasons and historical/live comparison |

**Automated deterministic E2E:** invoke the public runner/CLI against isolated databases, a frozen configuration and controlled raw market observations. Exercise the real parsing, feature, strategy, execution, lifecycle and persistence code available at that milestone. Replace external network services with controllable boundary adapters, rather than mocking each internal component. A replayed sequence should deliberately trigger known setup, suppression, entry, exit and cost cases, with enough pre-roll for its declared features. Assert expected decisions, state transitions, timestamps, signed cash flows and final ledger totals against independent expectations. Exit status alone is insufficient.

Include missing/partial/duplicate/late observations, stale context, gaps, process restart, failed database writes, simultaneous candidates and notification failures. Check stable internal signal identities and recovery; delivery timeouts can remain ambiguous and may cause duplicate external messages, so verify the declared reconciliation policy rather than promise exactly-once delivery. Keep research/data/code/config hashes and logs with each test run. No external API keys or outbound notifications are required in ordinary CI.

**External-service smoke:** keep a separate opt-in check of public Binance connectivity and a dedicated Telegram test destination once C14 exists. Use deterministic replay to guarantee a test setup instead of waiting indefinitely for a natural live opportunity. Tag test messages clearly and isolate test state. A separate bounded live session checks actual feed ingestion and timing. An HTTP/API success is evidence of service acceptance; the user manually verifies visibility and message usability.

**Manual acceptance:** provide a repeatable operator checklist using the same fixed scenarios and expected results. Before C14, the user can inspect CLI reports and trade ledgers, verify setup timestamps and costs, and interrupt/restart a run. At C14/C15, verify the actual test message, entry/stop/target/expiry presentation, traceable evidence ID, paper lifecycle and recovery after a controlled interruption. This checklist is usable through CLI/Telegram; a dashboard is a separate interface milestone.

All E2E test outcomes concern functional correctness and recovery. Strategy promotion additionally requires C12 evidence from unseen data. Before larger C11 experiments, characterize C03 with representative history lengths and symbol counts; its current one-day benchmark does not establish multi-year throughput. Concrete runner commands and automated E2E cases will be delivered with each corresponding component, not represented as already implemented here.

## 11. Build sequence and completion gates

| Phase | Deliverable | Completion gate |
| --- | --- | --- |
| 0 — Research specification | Scope, hypotheses, data contract, timing/execution policy, risk policy, experiment schema | Definitions are explicit enough to calculate a sample trade and identify permitted data |
| 1 — Data foundation | Archive import, REST repair, WebSocket recorder, canonical store, coverage report | Audited history and demonstrated reconnect/restart recovery; no silent gaps |
| 2 — Common core and simulator | Features, one baseline strategy, event replay, cost/funding ledger, two evaluation tracks | Hand-calculated cases and causal/parity checks pass |
| 3 — Validation | Frozen and nested walk-forward workflows, trial registry, sealed holdout, reports | Reproducible later-data results and explainable evidence decisions |
| 4 — Forward paper and Telegram | Persistent live runner, paper policy, durable alerts, outcome journal | Reliable lifecycle under outages and measured delivery/execution-delay assumptions |
| 5 — Dashboard and broader research | Data health, signal evidence, fold reports, experiment comparison; second horizon and portfolio policy | User can audit any signal and both horizons can be evaluated jointly |

Start recording live data during Phase 1 while historical tooling is developed. The platform can be considered functionally complete even if all strategies are rejected; those strategies remain in research. Engineering milestones can be scheduled, but evidence accumulation depends on signal frequency and observed market conditions.

The immediate implementation milestone is an audited data pipeline and one completely specified strategy replay with a trade-by-trade cost ledger. That establishes a trustworthy basis for subsequent strategy research and Telegram delivery.

## Implementation status — 19 October 2026

C01, the initial C02 data/replay increment, C03 features, C06 funding accounting, C07 paper market execution/costs and C08 two-family setup detection and C09 independent paper trade lifecycle/accounting are implemented. See [C02 contracts](C02_IMPLEMENTATION.md), [C03 verification](C03_VERIFICATION.md), [C06 contracts](C06_IMPLEMENTATION.md), [C06 verification](C06_VERIFICATION.md), [C07 contracts](C07_IMPLEMENTATION.md), [C07 verification](C07_VERIFICATION.md), [C08 contracts](C08_IMPLEMENTATION.md) and [C08 verification](C08_VERIFICATION.md), [C09 contracts](C09_IMPLEMENTATION.md) and [C09 verification](C09_VERIFICATION.md). The full offline suite has 404 passing tests, including 54 C09 tests and actual-process E2E. Public C06 funding/mark, C07 quote/mark and C08 candle capture plus saved replay checks passed. C09 also passed saved public-candle replay under modeled assumptions. Next is C11 historical simulation, then C10 expectancy. Sustained recording, large-universe load validation and all deferred prospects remain tracked in [COMPONENT_UPGRADES.md](COMPONENT_UPGRADES.md).

## C03 implementation package — 21 September 2026

References: [C03 architecture and dependencies](C03_RESEARCH_PLAN.md), [exact feature formulas and indicator conventions](C03_FEATURE_SPEC.md), [validation specification](C03_VALIDATION_PLAN.md), and [completed verification and limits](C03_VERIFICATION.md). C03 provides 14 baseline outputs, 45 named definitions (including the C08-required one-bar-prior EMAs) plus parameterized simple returns, explicit availability/warm-up policies, optional diagnostics, atomic checkpoints and an inspection/run CLI. It supplies measurements to later components; strategy expectancy and Telegram signals remain downstream work.
