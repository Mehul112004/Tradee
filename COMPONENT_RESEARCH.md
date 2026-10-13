# Components for finding positive net expectancy setups

Research and proposed specification — 9 September 2026.

Status: C01 is implemented; remaining components follow the agreed working order.

Scope: Binance USDT-margined perpetual futures; intraday and swing; Telegram signals for manual execution. This extends [the platform plan](/Users/artemis/Mehul/Tradee/PLATFORM_PLAN.md). It does not report a completed empirical test of any Tradee strategy.

## 1. What the platform must estimate

A useful setup is a fully specified trading policy with a positive estimated mean outcome after costs, adequate supporting evidence, acceptable downside, and an entry the user can realistically obtain. Directional accuracy and target-to-stop distance alone do not answer that question.

For market state x and a specified policy a:

`net expectancy(x, a) = E[gross trading P&L − fees − execution friction + signed funding cash flow | information available now, a]`

Compute the complete outcome distribution, including stops, targets, time exits, partial exits, gaps and missed entries. Report both quote-currency outcomes and net R, where one R is the initial declared price-risk budget. If executable prices already include spread/slippage, do not subtract them a second time.

For a simplified two-outcome trade with gross win W, gross loss L, win probability p and fixed average cost C, all measured in R:

`E_net = p × W − (1 − p) × L − C`

`break-even p = (L + C) / (W + L)`

Illustration, not an estimated strategy: with p = 45%, W = 1.8R, L = 1R and C = 0.12R, expectancy is +0.14R and break-even probability is 40%. If cost rises to 0.60R, expectancy becomes −0.34R. A 12-basis-point round-trip cost is 0.12R against a 100-basis-point stop, but 0.60R against a 20-basis-point stop. In a real strategy changing the stop also changes probabilities and outcomes; those must be re-estimated.

For limit entries, estimate fill probability and outcomes conditional on filling. Under zero P&L for unfilled signals, expected net R per candidate is fill probability times expected net R conditional on fill. Passive fills can be adversely selected; filled trades are not a random sample of opportunities. Also measure missed opportunities and time/capital reserved by orders.

An estimated confidence interval for mean expectancy describes estimation uncertainty. It is not a prediction interval for the next trade, and neither guarantees future performance.

## 2. What published evidence supports—and what still needs testing

| Evidence | Finding relevant to design | Limit of transfer to Tradee |
| --- | --- | --- |
| Liu and Tsyvinski, *Risks and Returns of Cryptocurrency* | Historical crypto momentum and attention effects motivate simple momentum baselines | Earlier assets/sample/horizons do not establish a current Binance perpetual edge. [Paper](https://www.nber.org/papers/w24877) |
| Wen et al., *Intraday return predictability…* (2022) | The accessible abstract reports both momentum and reversal, varying with jumps, liquidity and events | Reviewed publisher abstract, not full methods; no direct reproduction or endorsement of its trading results. [Publisher](https://www.sciencedirect.com/science/article/pii/S1062940822000833) |
| *On the Performance of Lagged Momentum and Reversal Strategies…* (September 2026) | The indexed publisher summary reports asset-dependent results and no rejection after a test accounting for 300 searched combinations | Reviewed accessible publisher summary only. Its illustrative costs exclude funding and other execution frictions; this is counterevidence to assuming simple historical patterns are readily tradable. [Publisher](https://www.mdpi.com/1911-8074/19/9/692) |
| Liu, Tsyvinski and Wu, *Common Risk Factors in Cryptocurrency* | Market, size and momentum factors motivate common-exposure attribution | Different coins need not supply independent opportunities. Findings are historical, not a fixed correlation model. [Paper](https://www.nber.org/papers/w25882) |
| Schmeling, Schrimpf and Todorov, *Crypto Carry* | Futures/spot pricing reflects leveraged demand and constrained arbitrage | Dated-futures carry is not identical to perpetual funding; high funding alone does not establish a profitable short. The BIS landing-page summary and indexed October 2025 revision differ; no numeric effect size is transferred here. [BIS](https://www.bis.org/publications/working-paper-1087-crypto-carry) |
| Cont, Kukanov and Stoikov, *The Price Impact of Order Book Events* | Order-flow imbalance relates to short-interval price changes and depth | Equity microstructure evidence, largely contemporaneous; it does not prove predictive crypto returns after manual delay. [Paper](https://arxiv.org/abs/1011.6402) |
| Cont, Cucuringu and Zhang, *Cross-Impact…* | Lagged order flow can have short-lived predictive content in the studied equity data | Horizon mismatch is material for Telegram execution. [Paper](https://arxiv.org/abs/2112.13213) |
| Bailey et al.; Bailey and López de Prado | Strategy selection can inflate backtest performance; DSR addresses selection and non-normality | Diagnostics depend on assumptions and trial records. They do not establish future profitability. [PBO](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf), [DSR](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) |

The component design below is an engineering/research recommendation inferred from these findings and the product's constraints. No cited paper proves that a particular Tradee component will increase returns. We must measure its incremental value on our own permitted data.

## 3. Component map

These are logical modules, not a requirement for fifteen microservices. One modular application with isolated background workers is sufficient initially.

| ID | Component | Main output | Role and priority |
| --- | --- | --- | --- |
| C01 | Instrument and universe registry | Eligible contracts as of a timestamp | Mandatory validity foundation |
| C02 | Point-in-time data and replay | Audited, time-bounded market observations | Mandatory validity foundation |
| C03 | Feature engine | Versioned measurements with availability times | Mandatory; start small |
| C04 | Market-state context | Volatility, trend, liquidity and event context | Basic context first; routing is experimental |
| C05 | Price structure and levels | Causally available pivots, ranges and levels | Optional predictive/geometry features |
| C06 | Derivatives and positioning context | Funding, premium, open-interest changes, observed liquidations | Funding accounting mandatory; predictive filters experimental |
| C07 | Execution and tradability | Fill/delay scenarios and net cost estimates | Mandatory for net expectancy |
| C08 | Candidate generation | Explicit, versioned setup hypotheses | Mandatory; few strategy families |
| C09 | Trade policy and outcome labels | Executable entry/exit contract and resolved outcomes | Mandatory target definition |
| C10 | Conditional expectancy and uncertainty | Estimated net outcome distribution and evidence status | Mandatory; simple cohorts first |
| C11 | Historical simulator | Candidate and finite-capital policy results | Mandatory measurement foundation |
| C12 | Research validation and registry | Frozen experiment, unseen results, promotion decision | Mandatory evidence control |
| C13 | Portfolio and alert selection | Admitted setups under shared risk constraints | Mandatory before simultaneous live strategies |
| C14 | Live decision and Telegram lifecycle | Timely signals with immutable evidence | Mandatory operational delivery |
| C15 | Forward measurement and degradation monitoring | Research/live reconciliation and pause reasons | Mandatory ongoing verification |

### 3.1 Dependency notation and scope

Each relationship is written **provider → consumer**. The tables list direct relationships; dependencies inherited through another component are not repeated everywhere.

| Type | Meaning | Implementation implication |
| --- | --- | --- |
| D | Required data or shared logic | Needed for the component's declared first-release scope, although an interface/fixture may support isolated development |
| O | Optional feature or policy | Enable only when the chosen experiment needs it; once enabled, its declared inputs must be available or the run fails explicitly |
| A | Versioned artifact | Read completed datasets, fitted models or approval records; do not synchronously invoke the producing process |
| R | Research orchestration | C12 starts a run or fitting job through an interface; this is not a reverse library import |
| F | Later feedback or control | A dated snapshot, a subsequent research input, or an operational pause; not same-decision future information |

“Used by” is the exact reverse of “depends on” below, with the same relationship type. D covers both data contracts and reusable logic, not necessarily a network service. Artifacts required for live eligibility remain mandatory even though they are marked A rather than D. External APIs, databases, clocks and user settings are prerequisites outside this component graph.

### 3.2 Direct dependency and consumer matrix

| Component | Depends on / receives from | Used by / supplies to |
| --- | --- | --- |
| [C01](#c01--instrument-and-universe-registry) — Instrument and universe registry | F: [C02](#c02--point-in-time-market-data-and-deterministic-replay) | D: [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C07](#c07--execution-costs-and-tradability), [C08](#c08--candidate-generation-and-hypothesis-registry), [C09](#c09--trade-policy-and-outcome-labelling), [C11](#c11--historical-simulation-and-attribution), [C12](#c12--walk-forward-selection-control-and-experiment-registry), [C13](#c13--portfolio-risk-and-alert-selection), [C14](#c14--live-decision-and-telegram-lifecycle) |
| [C02](#c02--point-in-time-market-data-and-deterministic-replay) — Point-in-time data and replay | D: [C01](#c01--instrument-and-universe-registry) | D: [C03](#c03--feature-engine), [C04](#c04--market-state-context), [C05](#c05--price-structure-supportresistance-and-level-construction), [C06](#c06--derivatives-and-positioning-context), [C07](#c07--execution-costs-and-tradability), [C11](#c11--historical-simulation-and-attribution), [C12](#c12--walk-forward-selection-control-and-experiment-registry), [C14](#c14--live-decision-and-telegram-lifecycle), [C15](#c15--forward-measurement-and-degradation-monitoring); F: [C01](#c01--instrument-and-universe-registry) |
| [C03](#c03--feature-engine) — Feature engine | D: [C02](#c02--point-in-time-market-data-and-deterministic-replay) | D: [C04](#c04--market-state-context), [C05](#c05--price-structure-supportresistance-and-level-construction), [C07](#c07--execution-costs-and-tradability), [C08](#c08--candidate-generation-and-hypothesis-registry), [C10](#c10--conditional-net-expectancy-and-uncertainty), [C11](#c11--historical-simulation-and-attribution), [C13](#c13--portfolio-risk-and-alert-selection), [C14](#c14--live-decision-and-telegram-lifecycle); O: [C06](#c06--derivatives-and-positioning-context) |
| [C04](#c04--market-state-context) — Market-state context | D: [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C03](#c03--feature-engine) | O: [C08](#c08--candidate-generation-and-hypothesis-registry), [C10](#c10--conditional-net-expectancy-and-uncertainty) |
| [C05](#c05--price-structure-supportresistance-and-level-construction) — Price structure and levels | D: [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C03](#c03--feature-engine) | O: [C08](#c08--candidate-generation-and-hypothesis-registry), [C09](#c09--trade-policy-and-outcome-labelling) |
| [C06](#c06--derivatives-and-positioning-context) — Derivatives and positioning context | D: [C02](#c02--point-in-time-market-data-and-deterministic-replay); O: [C03](#c03--feature-engine) | D: [C07](#c07--execution-costs-and-tradability), [C09](#c09--trade-policy-and-outcome-labelling), [C11](#c11--historical-simulation-and-attribution); O: [C08](#c08--candidate-generation-and-hypothesis-registry), [C10](#c10--conditional-net-expectancy-and-uncertainty) |
| [C07](#c07--execution-costs-and-tradability) — Execution and tradability | D: [C01](#c01--instrument-and-universe-registry), [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C03](#c03--feature-engine), [C06](#c06--derivatives-and-positioning-context) | D: [C09](#c09--trade-policy-and-outcome-labelling), [C10](#c10--conditional-net-expectancy-and-uncertainty), [C11](#c11--historical-simulation-and-attribution), [C13](#c13--portfolio-risk-and-alert-selection), [C14](#c14--live-decision-and-telegram-lifecycle), [C15](#c15--forward-measurement-and-degradation-monitoring) |
| [C08](#c08--candidate-generation-and-hypothesis-registry) — Candidate generation | D: [C01](#c01--instrument-and-universe-registry), [C03](#c03--feature-engine); O: [C04](#c04--market-state-context), [C05](#c05--price-structure-supportresistance-and-level-construction), [C06](#c06--derivatives-and-positioning-context) | D: [C09](#c09--trade-policy-and-outcome-labelling), [C11](#c11--historical-simulation-and-attribution), [C14](#c14--live-decision-and-telegram-lifecycle) |
| [C09](#c09--trade-policy-and-outcome-labelling) — Trade policy and outcome labels | D: [C08](#c08--candidate-generation-and-hypothesis-registry), [C01](#c01--instrument-and-universe-registry), [C06](#c06--derivatives-and-positioning-context), [C07](#c07--execution-costs-and-tradability); O: [C05](#c05--price-structure-supportresistance-and-level-construction) | D: [C10](#c10--conditional-net-expectancy-and-uncertainty), [C11](#c11--historical-simulation-and-attribution), [C12](#c12--walk-forward-selection-control-and-experiment-registry), [C13](#c13--portfolio-risk-and-alert-selection), [C14](#c14--live-decision-and-telegram-lifecycle), [C15](#c15--forward-measurement-and-degradation-monitoring) |
| [C10](#c10--conditional-net-expectancy-and-uncertainty) — Conditional expectancy and uncertainty | D: [C03](#c03--feature-engine), [C07](#c07--execution-costs-and-tradability), [C09](#c09--trade-policy-and-outcome-labelling); O: [C04](#c04--market-state-context), [C06](#c06--derivatives-and-positioning-context); A: [C11](#c11--historical-simulation-and-attribution); R: [C12](#c12--walk-forward-selection-control-and-experiment-registry) | D: [C13](#c13--portfolio-risk-and-alert-selection), [C14](#c14--live-decision-and-telegram-lifecycle), [C15](#c15--forward-measurement-and-degradation-monitoring); O: [C11](#c11--historical-simulation-and-attribution); A: [C12](#c12--walk-forward-selection-control-and-experiment-registry) |
| [C11](#c11--historical-simulation-and-attribution) — Historical simulator | D: [C01](#c01--instrument-and-universe-registry), [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C03](#c03--feature-engine), [C06](#c06--derivatives-and-positioning-context), [C07](#c07--execution-costs-and-tradability), [C08](#c08--candidate-generation-and-hypothesis-registry), [C09](#c09--trade-policy-and-outcome-labelling); O: [C10](#c10--conditional-net-expectancy-and-uncertainty), [C13](#c13--portfolio-risk-and-alert-selection); R: [C12](#c12--walk-forward-selection-control-and-experiment-registry) | A: [C10](#c10--conditional-net-expectancy-and-uncertainty), [C12](#c12--walk-forward-selection-control-and-experiment-registry), [C15](#c15--forward-measurement-and-degradation-monitoring) |
| [C12](#c12--walk-forward-selection-control-and-experiment-registry) — Research validation and registry | D: [C01](#c01--instrument-and-universe-registry), [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C09](#c09--trade-policy-and-outcome-labelling); A: [C11](#c11--historical-simulation-and-attribution), [C10](#c10--conditional-net-expectancy-and-uncertainty); F: [C15](#c15--forward-measurement-and-degradation-monitoring) | A: [C14](#c14--live-decision-and-telegram-lifecycle), [C15](#c15--forward-measurement-and-degradation-monitoring); R: [C11](#c11--historical-simulation-and-attribution), [C10](#c10--conditional-net-expectancy-and-uncertainty) |
| [C13](#c13--portfolio-risk-and-alert-selection) — Portfolio risk and alert selection | D: [C01](#c01--instrument-and-universe-registry), [C03](#c03--feature-engine), [C07](#c07--execution-costs-and-tradability), [C09](#c09--trade-policy-and-outcome-labelling), [C10](#c10--conditional-net-expectancy-and-uncertainty) | D: [C14](#c14--live-decision-and-telegram-lifecycle), [C15](#c15--forward-measurement-and-degradation-monitoring); O: [C11](#c11--historical-simulation-and-attribution) |
| [C14](#c14--live-decision-and-telegram-lifecycle) — Live decision and Telegram lifecycle | D: [C01](#c01--instrument-and-universe-registry), [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C03](#c03--feature-engine), [C07](#c07--execution-costs-and-tradability), [C08](#c08--candidate-generation-and-hypothesis-registry), [C09](#c09--trade-policy-and-outcome-labelling), [C10](#c10--conditional-net-expectancy-and-uncertainty), [C13](#c13--portfolio-risk-and-alert-selection); A: [C12](#c12--walk-forward-selection-control-and-experiment-registry); F: [C15](#c15--forward-measurement-and-degradation-monitoring) | D: [C15](#c15--forward-measurement-and-degradation-monitoring) |
| [C15](#c15--forward-measurement-and-degradation-monitoring) — Forward measurement and degradation monitoring | D: [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C07](#c07--execution-costs-and-tradability), [C09](#c09--trade-policy-and-outcome-labelling), [C10](#c10--conditional-net-expectancy-and-uncertainty), [C13](#c13--portfolio-risk-and-alert-selection), [C14](#c14--live-decision-and-telegram-lifecycle); A: [C11](#c11--historical-simulation-and-attribution), [C12](#c12--walk-forward-selection-control-and-experiment-registry) | F: [C14](#c14--live-decision-and-telegram-lifecycle), [C12](#c12--walk-forward-selection-control-and-experiment-registry) |

### 3.3 Runtime, historical and feedback boundaries

- **Market analysis:** C01/C02 supply identity and available observations. C03 supplies common features. C04/C05/C06 add only the context declared by the selected strategy. C08 emits a candidate; C09 resolves it into the chosen trade policy. C07 assesses proposed execution, C10 estimates outcomes, and C13 admits/sizes the opportunity. C14 runs this pipeline against live events.
- **Historical research:** C11 drives the same shared logic with a historical clock. First it can produce independent outcomes using a baseline policy without C10/C13. C12 then fits C10 on permitted earlier outcomes and reruns later evaluation with a frozen estimator and selection policy. C11 must not train a model on its current test period.
- **Forward observation:** C15 reads live telemetry and uses the shared C09 policy for paper/shadow outcomes. Its matured results become inputs to a later C12 experiment. Its health decisions may pause C14 immediately under a declared rule; neither action rewrites previous decisions.
- **Universe bootstrap:** C01 starts from exchange metadata and a fixed universe. Optional liquidity-based membership later uses a completed, time-bounded C02 snapshot (F). C02 ingestion does not wait for a universe calculation that itself requires the current unfinished ingestion.
- **Paper state:** historical or live runners own the clock and persistence and inject current position/account state into C13. C13 does not call C14. C15 performs forward measurement; C14 owns delivery. Both use C09 semantics rather than separate outcome implementations.
- **Shared contracts:** neutral, versioned types carry instrument, event, candidate, trade intent, fill, outcome, model and decision records. Shared domain modules do not import C11/C12/C14 orchestration. Logical feedback therefore does not require circular code imports.

### 3.4 Cross-cutting prerequisites

All components need versioned configuration, structured errors/logs, stable IDs, UTC/availability semantics, persistence contracts, and test fixtures appropriate to their role. C02 owns raw/normalized datasets; C12 owns experiment and promotion records; C14 owns signal/delivery persistence. Other modules own their domain records and expose them through explicit interfaces. Storage technology and deployment choices remain subject to review; this map does not start implementation.

## 4. Component specifications

### C01 — Instrument and universe registry

Detailed plan and implementation decisions: [C01_RESEARCH_PLAN.md](/Users/artemis/Mehul/Tradee/C01_RESEARCH_PLAN.md). Status: first version implemented with Binance; see README.md for commands and scope.

**Depends on / receives from:** F: [C02](#c02--point-in-time-market-data-and-deterministic-replay).

**Used by / supplies to:** D: [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C07](#c07--execution-costs-and-tradability), [C08](#c08--candidate-generation-and-hypothesis-registry), [C09](#c09--trade-policy-and-outcome-labelling), [C11](#c11--historical-simulation-and-attribution), [C12](#c12--walk-forward-selection-control-and-experiment-registry), [C13](#c13--portfolio-risk-and-alert-selection), [C14](#c14--live-decision-and-telegram-lifecycle).

**Major internal parts:**

- Contract identifiers and product classification
- Versioned listing, status and trading-rule records
- Universe eligibility and historical membership snapshots
- Metadata provenance and missing-history policy
- Fixed-universe bootstrap; later liquidity-based membership

**Output contracts:** InstrumentSpec; UniverseSnapshot; metadata coverage report. Names are proposed domain records, not finalized code APIs.

**Ownership boundary:** Owns contract identity and eligibility. C02 owns market observations; exchange metadata can be bootstrapped directly before C02 exists.

**Questions for component research:** Which contracts are initially eligible? How will historical rule changes and delistings be represented?

**Purpose:** avoid attributing success to a universe selected with hindsight and avoid simulating unavailable contracts.

Store exchange/product/contract identity, quote and margin asset, listing/status history, available precision and size rules, and metadata provenance. Binance's exchange-information endpoint supplies current contract metadata; an authoritative history of every previous rule must be separately verified or labelled unavailable. [Market-data reference](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data)

Begin with a fixed BTC/ETH engineering universe. Before a broad scanner, define eligibility using trailing liquidity and age measured at the time; retain delisted assets where coverage permits. Never use today's top-volume list to claim an unbiased multi-year universe.

**Acceptance:** a simulated listing date gates participation; symbol/product keys cannot mix spot, USDT futures and coin-margined contracts. Report missing metadata assumptions and survivor-selection limitations.

### C02 — Point-in-time market data and deterministic replay

**Depends on / receives from:** D: [C01](#c01--instrument-and-universe-registry).

**Used by / supplies to:** D: [C03](#c03--feature-engine), [C04](#c04--market-state-context), [C05](#c05--price-structure-supportresistance-and-level-construction), [C06](#c06--derivatives-and-positioning-context), [C07](#c07--execution-costs-and-tradability), [C11](#c11--historical-simulation-and-attribution), [C12](#c12--walk-forward-selection-control-and-experiment-registry), [C14](#c14--live-decision-and-telegram-lifecycle), [C15](#c15--forward-measurement-and-degradation-monitoring); F: [C01](#c01--instrument-and-universe-registry).

**Major internal parts:**

- Archive, REST and WebSocket adapters; scheduled-event ingestion when enabled
- Raw storage, canonical schemas, timestamps and revision history
- Integrity checks, gap repair, deduplication and quarantine
- Finalized candle aggregation and time-bounded joins
- Reconnect/checkpoint recovery and deterministic event replay

**Output contracts:** MarketEvent; DatasetSnapshot; DataQualityReport; optional trailing-liquidity snapshot. Names are proposed domain records, not finalized code APIs.

**Ownership boundary:** Owns ingestion and chronological event delivery, including raw derivatives data. It does not calculate trading outcomes; C11 owns historical simulation.

**Questions for component research:** What data can be verified historically? What availability, finality, retention and repair policies will apply?

**Purpose:** make every past decision reconstructible from information that was available then.

Maintain raw immutable records, normalized datasets and experiment snapshots. Store event time, receipt time, availability time where known, source/schema version, finality, checksums and data revisions. Join inputs by availability, not merely matching timestamps.

Use archives for bulk ingestion, REST for repair and WebSockets for ongoing collection. Binance provides daily/monthly archives and checksum files; archive coverage must be audited per product and dataset. [Public-data repository](https://github.com/binance/binance-public-data)

Maintain one-minute contract candles for initial higher-timeframe research, plus recorded quotes/trades for execution study. Higher-timeframe bars require complete finalized constituents. Historical archives cannot reconstruct original receipt latency; use a declared historical delay model and measure real latency forward.

**Acceptance:** gaps, duplicates, invalid candles, revisions, stale inputs and unclosed bars have explicit outcomes. Replaying recorded input events reproduces live decisions. Prefix tests show future additions cannot change already-issued signals. Repairs never silently rewrite old experiments.

### C03 — Feature engine

**Depends on / receives from:** D: [C02](#c02--point-in-time-market-data-and-deterministic-replay).

**Used by / supplies to:** D: [C04](#c04--market-state-context), [C05](#c05--price-structure-supportresistance-and-level-construction), [C07](#c07--execution-costs-and-tradability), [C08](#c08--candidate-generation-and-hypothesis-registry), [C10](#c10--conditional-net-expectancy-and-uncertainty), [C11](#c11--historical-simulation-and-attribution), [C13](#c13--portfolio-risk-and-alert-selection), [C14](#c14--live-decision-and-telegram-lifecycle); O: [C06](#c06--derivatives-and-positioning-context).

**Major internal parts:**

- Feature definitions, units and dependency registry
- Returns, trend, volatility, reversion and participation calculations
- Spread/depth measurements when source data supports them
- Warm-up, missingness and numerical policies
- Batch/stream parity, feature snapshots and fitted-transform versions

**Output contracts:** FeatureSnapshot; FeatureDefinition; transform artifact. Names are proposed domain records, not finalized code APIs.

**Ownership boundary:** Owns reusable mathematical measurements. C04 owns market-state interpretation; C05 owns structural levels; C06 owns derivatives-specific interpretation.

**Questions for component research:** What is the minimal feature set? Which calculations require fitted state, and when is that state available?

**Purpose:** translate market observations into a small set of reproducible explanatory variables.

Initial families:

- Returns and trend: log returns, rolling return, normalized moving-average distance/slope.
- Volatility: realized return dispersion, ATR/price, jump size relative to previous volatility.
- Reversion: deviation from a past-window mean or explicitly anchored VWAP, with past-window scaling.
- Participation: relative volume and signed aggressive trade volume where supported.
- Liquidity: spread, visible depth and quote age.

Every feature declares units, lookback, warm-up, dependency datasets, missingness policy and availability time. Fit learned transformations only in earlier development data. Batch and streaming implementations must agree within declared numerical tolerances.

**Acceptance:** controlled calculation examples, prefix invariance, and an ablation report. Several moving-average-derived indicators are not automatically independent evidence. More features earn inclusion through later-data improvement, not visual plausibility.

### C04 — Market-state context

**Depends on / receives from:** D: [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C03](#c03--feature-engine).

**Used by / supplies to:** O: [C08](#c08--candidate-generation-and-hypothesis-registry), [C10](#c10--conditional-net-expectancy-and-uncertainty).

**Major internal parts:**

- Trend, volatility and liquidity context
- Cross-market and time-of-week context
- Scheduled-event proximity and event revisions
- Simple regime definitions; optional learned state models
- State uncertainty, model versioning and context snapshots

**Output contracts:** MarketStateSnapshot; optional fitted state model. Names are proposed domain records, not finalized code APIs.

**Ownership boundary:** Describes conditions; strategy routing belongs to the selected C08/C13 policy. Any learned state must be filtered using earlier observations.

**Questions for component research:** Which continuous measures or regimes will be used? Does context improve the base policy under matched-data evaluation?

**Purpose:** describe conditions in which a strategy may behave differently, without assuming that a regime label predicts success.

Start with continuous measures: trend strength, volatility percentile, spread/depth conditions, broad BTC/ETH movement, time-of-week, and time to known scheduled events. Persist these when the candidate is detected.

Simple regimes can summarize those measures. Learned regimes such as hidden Markov models are later experiments: use filtered state probabilities from past observations, never states smoothed using the future. Fit regime thresholds inside the development fold and handle uncertain states explicitly.

An event module can consume official [FOMC calendars](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) and [CPI schedules](https://www.bls.gov/schedule/news_release/cpi.htm). Store schedule revisions and convert time zones correctly. Scheduled-event awareness is distinct from trading on economic surprises, which requires timestamped first-release and expectation data.

**Acceptance:** compare the same base policy with and without a context gate. Report net return, expectancy, risk and lost opportunities. A filter that raises average R while removing most useful trades may not improve the policy.

### C05 — Price structure, support/resistance and level construction

**Depends on / receives from:** D: [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C03](#c03--feature-engine).

**Used by / supplies to:** O: [C08](#c08--candidate-generation-and-hypothesis-registry), [C09](#c09--trade-policy-and-outcome-labelling).

**Major internal parts:**

- Completed-period highs/lows and trailing ranges
- Confirmed pivots with explicit confirmation delay
- Level merging, aging, touches and invalidation
- Volatility-normalized distances
- Optional SMC-style definitions with immutable snapshots

**Output contracts:** LevelSnapshot; level provenance and confirmation times. Names are proposed domain records, not finalized code APIs.

**Ownership boundary:** Produces levels; C09 decides how a trade policy uses them for stops and exits. Pattern names do not imply predictive validity.

**Questions for component research:** How is each level known at the time? Which level methods justify their complexity against a simple range baseline?

**Purpose:** provide objective candidate locations and invalidation levels when the strategy needs them.

Start with previous completed-day/week high/low, trailing range boundaries, delayed-confirmation pivots, and distance to levels in volatility units. Specify pivot confirmation lag, level aging, merging, touch rules and invalidation as deterministic operations.

Treat supply/demand zones, order blocks, fair-value gaps, BOS/CHOCH and liquidity sweeps as hypotheses with exact definitions. Candle shapes cannot establish institutional intent or reveal all resting stop orders. A retrospectively beautiful level is not evidence that the live algorithm could have known it.

**Acceptance:** level snapshots do not change retroactively. Each complex level method must beat or complement a simpler range/ATR baseline on later data. The platform must work without this component if it adds no measurable value.

### C06 — Derivatives and positioning context

**Depends on / receives from:** D: [C02](#c02--point-in-time-market-data-and-deterministic-replay); O: [C03](#c03--feature-engine).

**Used by / supplies to:** D: [C07](#c07--execution-costs-and-tradability), [C09](#c09--trade-policy-and-outcome-labelling), [C11](#c11--historical-simulation-and-attribution); O: [C08](#c08--candidate-generation-and-hypothesis-registry), [C10](#c10--conditional-net-expectancy-and-uncertainty).

**Major internal parts:**

- Funding schedules, observed estimates and settlement records
- Shared signed funding cash-flow calculation
- Premium/basis features with explicit units
- Open-interest changes and coverage checks
- Liquidation-snapshot interpretation and missingness flags

**Output contracts:** FundingContext; FundingCashFlow; DerivativesSnapshot. Names are proposed domain records, not finalized code APIs.

**Ownership boundary:** C02 collects raw records. C06 computes funding amounts; C09 books each applicable amount once. C07 consumes funding forecasts for estimates, not a second realized charge.

**Questions for component research:** Which funding conventions and holding intervals apply? Which positioning features have enough trustworthy historical coverage?

**Purpose:** account for perpetual-specific cash flows and test whether derivatives state improves selection.

Separate two responsibilities: realized funding cash-flow accounting is mandatory; funding/OI/liquidation-based prediction is optional.

Potential features: current premium, known funding estimate and time to settlement, past funding distribution, changes in open interest alongside price and volume, and observed liquidation snapshots. Distinguish contract-unit OI from notional OI, which also changes with price. OI growth alone cannot tell us which side is informed; each outstanding contract has both a long and a short.

Binance currently documents only the latest month for its open-interest statistics endpoint. This is an endpoint limit, not proof that no other archive exists. Audit official archives or an independently sourced dataset before promising multi-year OI testing. The market stream publishes liquidation snapshots, including only the latest liquidation per symbol within each 1,000ms window; their sum is not a complete liquidation-volume measure. [REST documentation](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data), [stream documentation](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market)

**Acceptance:** realized funding agrees with hand-calculated long/short settlement cases. A forecast cannot use the eventual settlement rate before it was known. Predictive additions need matched-coverage ablations; missing OI history cannot be manufactured from candles.

### C07 — Execution, costs and tradability

**Depends on / receives from:** D: [C01](#c01--instrument-and-universe-registry), [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C03](#c03--feature-engine), [C06](#c06--derivatives-and-positioning-context).

**Used by / supplies to:** D: [C09](#c09--trade-policy-and-outcome-labelling), [C10](#c10--conditional-net-expectancy-and-uncertainty), [C11](#c11--historical-simulation-and-attribution), [C13](#c13--portfolio-risk-and-alert-selection), [C14](#c14--live-decision-and-telegram-lifecycle), [C15](#c15--forward-measurement-and-degradation-monitoring).

**Major internal parts:**

- Quote freshness, spread and optional synchronized depth
- Fee schedule and order-type assumptions
- Slippage/impact and size-dependent fill models
- Detection-to-entry delay and passive fill scenarios
- Cost estimates, entry-drift limits and tradability reasons

**Output contracts:** ExecutionEstimate; FillEvent; TradabilityDecision. Names are proposed domain records, not finalized code APIs.

**Ownership boundary:** Estimates costs and produces simulated fills when asked by a runner. C09 owns position/exit semantics; C13 proposes size and requests evaluation at that size.

**Questions for component research:** What entry delay and order types match manual use? How will cost assumptions and passive fills be calibrated?

**Purpose:** estimate the entry/exit the user could obtain and whether enough edge survives.

Inputs include quote age, spread, visible liquidity, intended order size, volatility, order type, and detection-to-action delay. Output fill scenarios, total cost in basis points and R, maximum acceptable entry drift, expiry and rejection reasons. Account separately for fees, spread/impact assumptions and signed funding, with no double counting.

Model delay from data arrival through computation, Telegram acceptance and human action. Measure an empirical distribution during forward operation and test adverse scenarios. Small historical OHLCV bars do not reveal an exact price 30 seconds after a signal; use trades/quotes or declare coarse replay uncertainty.

For depth features, reconstruct the local book from a buffered stream and REST snapshot, checking sequence continuity and resynchronizing after gaps, following [Binance's documented process](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly). Displayed liquidity is cancellable and is not a guaranteed fill.

**Acceptance:** compare estimated versus forward paper/recorded actual costs by volatility, size and delay. Separate market and passive-entry assumptions; do not award maker fees to every limit-price touch. If a candidate only works before a plausible manual entry, suppress it for this product.

### C08 — Candidate generation and hypothesis registry

**Depends on / receives from:** D: [C01](#c01--instrument-and-universe-registry), [C03](#c03--feature-engine); O: [C04](#c04--market-state-context), [C05](#c05--price-structure-supportresistance-and-level-construction), [C06](#c06--derivatives-and-positioning-context).

**Used by / supplies to:** D: [C09](#c09--trade-policy-and-outcome-labelling), [C11](#c11--historical-simulation-and-attribution), [C14](#c14--live-decision-and-telegram-lifecycle).

**Major internal parts:**

- Strategy definitions and hypothesis-family identifiers
- Trigger rules and declared optional inputs
- Candidate snapshots and rule-by-rule reason codes
- Deterministic state and cooldown rules where strategy-specific
- Strategy versioning and complete candidate inventory

**Output contracts:** CandidateSpec; candidate rejection/diagnostic records. Names are proposed domain records, not finalized code APIs.

**Ownership boundary:** Owns setup detection and strategy specifications. C12 owns the experiment/trial ledger; C09 owns the executable trade policy.

**Questions for component research:** Which first hypothesis will be tested? What exactly triggers a candidate and which data dependencies does it require?

**Purpose:** turn measurable conditions into falsifiable setup families.

Suggested experiments, with no profitability claim:

| Family | Initial definition to specify | Intended research horizon |
| --- | --- | --- |
| Trend continuation | Past trend plus normalized pullback/recovery trigger | Intraday and swing, separately |
| Range breakout | Break of a previously completed range with explicit entry/expiry | Intraday and swing |
| Conditional reversion | Large normalized deviation with a separately tested context condition | Initially intraday |
| Funding/positioning extension | Add one derivatives-context feature to an established baseline | Later, where historical coverage supports it |

Implement one family end to end first. Keep triggers, features, exit policy, and eligibility policy independently versioned. Save all candidates, including rejected ones, to measure what later gates remove.

**Acceptance:** write the economic rationale and alternative explanation before testing. Compare against simple market-exposure and no-trade baselines. A renamed indicator combination remains part of its original hypothesis family for trial accounting.

### C09 — Trade policy and outcome labelling

**Depends on / receives from:** D: [C08](#c08--candidate-generation-and-hypothesis-registry), [C01](#c01--instrument-and-universe-registry), [C06](#c06--derivatives-and-positioning-context), [C07](#c07--execution-costs-and-tradability); O: [C05](#c05--price-structure-supportresistance-and-level-construction).

**Used by / supplies to:** D: [C10](#c10--conditional-net-expectancy-and-uncertainty), [C11](#c11--historical-simulation-and-attribution), [C12](#c12--walk-forward-selection-control-and-experiment-registry), [C13](#c13--portfolio-risk-and-alert-selection), [C14](#c14--live-decision-and-telegram-lifecycle), [C15](#c15--forward-measurement-and-degradation-monitoring).

**Major internal parts:**

- Entry/stop/target/expiry contract validation
- Position lifecycle and exit precedence
- Partial exits, gaps and intrabar ambiguity rules
- Net/gross ledger and one-time funding booking
- Outcome labels, maturity times, excursions and unresolved states

**Output contracts:** TradeIntent; PositionState; OutcomeRecord; TradeLedger. Names are proposed domain records, not finalized code APIs.

**Ownership boundary:** A shared deterministic policy/state machine used by historical and forward runners. It consumes market/fill events; it does not fetch future data or run its own historical loop.

**Questions for component research:** Which exact outcome is being predicted? How are fills, trigger sources, expiry and ambiguous paths resolved?

**Purpose:** define exactly what the expectancy estimator is predicting.

A candidate must specify direction, decision time, permitted entry window/order, acceptable entry range, stop trigger source, target/partial-exit rules, maximum holding period and cancellation conditions. Record label start/end and when the outcome becomes known.

Resolve take-profit, stop, time exit, invalidation, unfilled and unresolved cases. Capture gross/net R, fees/funding, holding time, maximum favorable/adverse excursion and ambiguity flags. Excursions are diagnostic outcomes, not future-informed inputs for the same trade.

Do not train a target-before-stop model and present its probability as positive net P&L probability. They are different events. Changing exit rules changes labels and requires a new experiment. If a stop and target share a bar, use a declared conservative rule or verified finer replay; trailing stops require event-order fidelity.

**Acceptance:** manually verifiable long/short, gap, time-exit and partial-exit cases; unresolved data tails are flagged rather than silently counted as losses or removed without reporting.

### C10 — Conditional net expectancy and uncertainty

**Depends on / receives from:** D: [C03](#c03--feature-engine), [C07](#c07--execution-costs-and-tradability), [C09](#c09--trade-policy-and-outcome-labelling); O: [C04](#c04--market-state-context), [C06](#c06--derivatives-and-positioning-context); A: [C11](#c11--historical-simulation-and-attribution); R: [C12](#c12--walk-forward-selection-control-and-experiment-registry).

**Used by / supplies to:** D: [C13](#c13--portfolio-risk-and-alert-selection), [C14](#c14--live-decision-and-telegram-lifecycle), [C15](#c15--forward-measurement-and-degradation-monitoring); O: [C11](#c11--historical-simulation-and-attribution); A: [C12](#c12--walk-forward-selection-control-and-experiment-registry).

**Major internal parts:**

- Earlier matured-outcome selection and cohort definitions
- Mean/payoff/distribution estimation and optional shrinkage
- Uncertainty, coverage and insufficient-evidence handling
- Optional fitted prediction and probability calibration
- Frozen inference artifact and applicability checks

**Output contracts:** ExpectancyEstimate; EstimatorArtifact; calibration/coverage report. Names are proposed domain records, not finalized code APIs.

**Ownership boundary:** Training consumes an earlier outcome artifact. Inference consumes a frozen estimator, not an active backtest or current candidate's future outcome.

**Questions for component research:** How much comparable evidence is required? What estimand, pooling, uncertainty and eligibility rules are defensible?

**Purpose:** estimate outcomes for comparable setups and abstain when evidence is inadequate.

First version: a frozen strategy with broad, predeclared cohorts such as horizon and direction; estimate net outcome distributions and block-based uncertainty using only matured earlier observations. Avoid tiny intersections of symbol × regime × timeframe × pattern × funding bucket. Sparse groups should remain provisional or be pooled through an explicitly tested shrinkage model.

Later candidates include regularized outcome regression, probability-plus-payoff models, and quantile estimates. Start with simple baselines. A classifier's raw score is not a probability. Calibration should use disjoint, earlier data, followed by untouched chronological evaluation; inspect reliability plots and scoring rules together. Brier score alone does not isolate calibration. [Calibration reference](https://scikit-learn.org/stable/modules/calibration.html)

Output estimated mean net R, uncertainty, sample/coverage information, adverse outcomes, applicable cost/delay assumptions and model version. Optional conservative eligibility can require a predeclared lower confidence bound above a buffer, but that bound remains conditional on sampling/selection assumptions and is not a guarantee.

**Acceptance:** estimates computed before outer-test observations predict ordered realized net outcomes on those later observations; the complete admission policy improves the relevant objective. Evaluate retained signal volume and dependence, not only the highest-looking bucket. A basic empirically evaluated policy is sufficient; a complex predictive model is not mandatory.

### C11 — Historical simulation and attribution

**Depends on / receives from:** D: [C01](#c01--instrument-and-universe-registry), [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C03](#c03--feature-engine), [C06](#c06--derivatives-and-positioning-context), [C07](#c07--execution-costs-and-tradability), [C08](#c08--candidate-generation-and-hypothesis-registry), [C09](#c09--trade-policy-and-outcome-labelling); O: [C10](#c10--conditional-net-expectancy-and-uncertainty), [C13](#c13--portfolio-risk-and-alert-selection); R: [C12](#c12--walk-forward-selection-control-and-experiment-registry).

**Used by / supplies to:** A: [C10](#c10--conditional-net-expectancy-and-uncertainty), [C12](#c12--walk-forward-selection-control-and-experiment-registry), [C15](#c15--forward-measurement-and-degradation-monitoring).

**Major internal parts:**

- Chronological clock and event-loop orchestration
- Candidate replay and independent-outcome track
- Finite-capital replay with injected selection policy
- Execution, funding and position-ledger integration
- Result artifacts, attribution, regular equity series and diagnostics

**Output contracts:** SimulationRun; OutcomeDataset; PortfolioResult; attribution report. Names are proposed domain records, not finalized code APIs.

**Ownership boundary:** Drives shared C07/C08/C09 logic. Optional C10/C13 policies are injected; baseline runs can use no estimator and a simple fixed admission policy.

**Questions for component research:** How is simulator fidelity checked? How are concurrent trades, unresolved tails, fold boundaries and mark-to-market equity handled?

**Purpose:** provide a trustworthy measuring instrument.

Use the same causal feature, strategy and policy logic for historical replay and live decisions. Maintain independent-candidate evaluation and a separate finite-capital simulation with concurrent trades, mark-to-market equity, funding, sizing and exposure constraints.

Include execution delays, gaps, failed/partial fills where supported, notional rules and end-of-sample treatment. Leverage-dependent results require a compatible margin/liquidation model; a stop is not a guaranteed maximum loss. Mark-price risk and contract-price fills have distinct roles.

Attribute changes to candidate generation, entry delay, fee/friction, funding, exit policy and selection. Keep intraday/swing attribution alongside their combined portfolio result.

**Acceptance:** golden hand-calculated ledgers, streaming/batch parity and injected feed failures. Report ambiguity and cost sensitivity. Derive drawdown and risk-adjusted returns from regular mark-to-market equity rather than a sequence of irregular trade returns.

### C12 — Walk-forward, selection control and experiment registry

**Depends on / receives from:** D: [C01](#c01--instrument-and-universe-registry), [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C09](#c09--trade-policy-and-outcome-labelling); A: [C11](#c11--historical-simulation-and-attribution), [C10](#c10--conditional-net-expectancy-and-uncertainty); F: [C15](#c15--forward-measurement-and-degradation-monitoring).

**Used by / supplies to:** A: [C14](#c14--live-decision-and-telegram-lifecycle), [C15](#c15--forward-measurement-and-degradation-monitoring); R: [C11](#c11--historical-simulation-and-attribution), [C10](#c10--conditional-net-expectancy-and-uncertainty).

**Major internal parts:**

- Experiment manifests and complete trial-family ledger
- Chronological folds, label purging and holdout access
- Training/calibration/search orchestration
- Uncertainty, multiplicity, sensitivity and stress evaluation
- Versioned research decisions and promotion registry

**Output contracts:** ExperimentManifest; ValidationReport; ApprovalRecord; frozen release manifest. Names are proposed domain records, not finalized code APIs.

**Ownership boundary:** Owns orchestration and evidence policy. It calls runner/training interfaces and reads artifacts; shared simulation/estimation logic must not import this orchestrator.

**Questions for component research:** What are the experiment and promotion criteria? How will tuning, repeated inspection and prior TBot research be recorded?

**Purpose:** establish whether the complete process generalizes to later observations.

Freeze data versions, code, hypothesis family, scope, cost model, fold boundaries, tuning budget, objective and promotion criteria. Preserve every trial, including feature/exit/filter/universe variants and manual inspection decisions. Previously used TBot data is development data.

Use nested chronological evaluation when tuning: fit features/models on earlier training data; select/calibrate within earlier development data; freeze the decision policy; evaluate the next non-overlapping outer window. Fixed rules still need later-window evaluation but no artificial parameter fitting.

Purge observations whose label intervals overlap the test boundary; apply additional separation where warranted. A generic time-series split supports time ordering and gaps but does not understand our event-specific outcome intervals. [TimeSeriesSplit documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)

Use joint time blocks for cross-asset uncertainty, parameter-neighborhood checks, cost/delay stress, leave-period/asset-out diagnostics, and a sealed final holdout. Specify fold ownership for positions and forbid duplicate counting. Multiple-testing diagnostics such as DSR/PBO supplement the protocol; their sampling and effective-trial assumptions must be stated, and they do not replace chronological deployment simulation. [DSR paper](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf), [PBO paper](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf)

**Acceptance:** the experiment can be reconstructed, failed runs resume without changing the trial, and a rejection cannot be converted to success by silently selecting another window. Any redesign prompted by outer results is another trial; the final holdout remains separate.

### C13 — Portfolio risk and alert selection

**Depends on / receives from:** D: [C01](#c01--instrument-and-universe-registry), [C03](#c03--feature-engine), [C07](#c07--execution-costs-and-tradability), [C09](#c09--trade-policy-and-outcome-labelling), [C10](#c10--conditional-net-expectancy-and-uncertainty).

**Used by / supplies to:** D: [C14](#c14--live-decision-and-telegram-lifecycle), [C15](#c15--forward-measurement-and-degradation-monitoring); O: [C11](#c11--historical-simulation-and-attribution).

**Major internal parts:**

- Injected account/paper state and exposure accounting
- Per-trade, total-risk, notional and margin constraints
- Correlation, beta, concentration and horizon overlap
- Candidate ranking, conflicts and duplicate suppression
- Size proposal, execution recheck and admission reasons

**Output contracts:** AllocationDecision; admitted/rejected TradeIntent; risk snapshot. Names are proposed domain records, not finalized code APIs.

**Ownership boundary:** A deterministic selection policy shared by historical/live runners. It receives portfolio state from its caller; it does not depend on Telegram or own the live runner.

**Questions for component research:** Which risk limits and ranking objective apply? How are correlated intraday and swing positions admitted together?

**Purpose:** decide which individually eligible setups fit the user's combined risk budget.

Track shared capital, concurrent stop-risk, notional/margin limits, BTC/ETH beta, direction, horizon overlap, and concentration. A BTC long and several correlated altcoin longs are not independent bets. Resolve repeated and conflicting setups by a frozen rule; record every exclusion.

Rank using estimated net outcomes, downside, uncertainty, holding time and incremental exposure. Net R alone is insufficient when strategies reserve capital for very different durations. Begin with conservative fixed risk allocation; full Kelly sizing is inappropriate as a default when the underlying estimates are unstable.

Risk sizing can change drawdown and growth, but does not establish that the original predictor has an edge. Volatility scaling is itself a testable policy: published evidence exists in other asset classes, with transfer to our market unproven. [Moreira and Muir](https://www.nber.org/papers/w22208)

**Acceptance:** simultaneous-trade accounting reconciles; candidate-level benefits survive portfolio constraints; reports show total exposure and where apparent diversification disappears under joint stress.

### C14 — Live decision and Telegram lifecycle

**Depends on / receives from:** D: [C01](#c01--instrument-and-universe-registry), [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C03](#c03--feature-engine), [C07](#c07--execution-costs-and-tradability), [C08](#c08--candidate-generation-and-hypothesis-registry), [C09](#c09--trade-policy-and-outcome-labelling), [C10](#c10--conditional-net-expectancy-and-uncertainty), [C13](#c13--portfolio-risk-and-alert-selection); A: [C12](#c12--walk-forward-selection-control-and-experiment-registry); F: [C15](#c15--forward-measurement-and-degradation-monitoring).

**Used by / supplies to:** D: [C15](#c15--forward-measurement-and-degradation-monitoring).

**Major internal parts:**

- Live scheduling and shared-pipeline orchestration
- Approved-release loading and pre-send eligibility checks
- Durable signal state and atomic delivery outbox
- Formatting, retry, expiry and delivery reconciliation
- Decision/latency telemetry and paper/user-state separation

**Output contracts:** SignalRecord; DeliveryEvent; decision and lifecycle telemetry. Names are proposed domain records, not finalized code APIs.

**Ownership boundary:** Owns live orchestration and delivery. Historical simulation never calls it. C15 can request a documented pause; that control does not retrain or rewrite strategy logic.

**Questions for component research:** What makes an alert usable and when does it expire? How are restarts and ambiguous delivery outcomes handled?

**Purpose:** deliver the tested policy while its entry remains valid.

Persist the decision and delivery outbox atomically. Snapshot inputs, strategy/model/data versions, evidence status, levels, costs and expiry. Separate candidate state, paper-position state, Telegram delivery state and user-recorded trades.

Apply freshness and spread checks again before sending. Retry with stable identifiers and expiry controls; acknowledge that a timeout can leave delivery ambiguous. Retain detected, suppressed, pending, entered-in-paper, expired and closed states. Telegram acceptance is not evidence of user receipt or execution.

The message should explain the setup, usable entry conditions, invalidation, expiry and evidence limitations. “Insufficient comparable evidence” is a legitimate output. An LLM may later summarize immutable facts, but changing entry/exit/eligibility requires a separately evaluated policy.

**Acceptance:** restart/reconnect/retry scenarios do not produce stale trade instructions; identical available data yields the replayed decision, and measured latency is included in validation.

### C15 — Forward measurement and degradation monitoring

**Depends on / receives from:** D: [C02](#c02--point-in-time-market-data-and-deterministic-replay), [C07](#c07--execution-costs-and-tradability), [C09](#c09--trade-policy-and-outcome-labelling), [C10](#c10--conditional-net-expectancy-and-uncertainty), [C13](#c13--portfolio-risk-and-alert-selection), [C14](#c14--live-decision-and-telegram-lifecycle); A: [C11](#c11--historical-simulation-and-attribution), [C12](#c12--walk-forward-selection-control-and-experiment-registry).

**Used by / supplies to:** F: [C14](#c14--live-decision-and-telegram-lifecycle), [C12](#c12--walk-forward-selection-control-and-experiment-registry).

**Major internal parts:**

- Recorded-live replay and forward/shadow outcomes
- Estimated-versus-realized cost/delay/fill reconciliation
- Calibration, drift and performance review
- Operational health versus statistical evidence classification
- Pause requests, incident records and future-research datasets

**Output contracts:** ForwardReport; matured ForwardOutcomeDataset; HealthDecision; research feedback. Names are proposed domain records, not finalized code APIs.

**Ownership boundary:** Uses the shared C09 policy for paper outcomes and never changes past records. New data enters later research only after maturity and an explicit versioned evaluation.

**Questions for component research:** Which failures trigger immediate suppression? What review schedule and evidence distinguish ordinary losses from degradation?

**Purpose:** determine whether research assumptions remain representative in deployment.

Record live inputs and decisions before outcomes. Compare predicted and realized costs, delay, fill rates, funding, net outcomes and calibration; track rejected signals in a shadow evaluation too. Actual user fills, if voluntarily recorded, remain distinct from hypothetical fills and may themselves be selectively reported.

Separate operational failure from statistical underperformance: a stale feed can justify immediate suppression; a few losses do not prove an edge disappeared. Use predeclared review intervals, sufficient matured observations and dependence-aware uncertainty. Repeated significance checks need an appropriate sequential policy or multiplicity allowance.

Feature drift is a prompt to investigate; it does not by itself imply profitability drift. Adaptive uncertainty methods exist for distribution shift, but do not automatically give reliable per-trade confidence or solve changing financial dynamics. Treat them as later research. [Gibbs and Candès](https://proceedings.neurips.cc/paper/2021/hash/0d441de75945e5acbc865406fc9a2559-Abstract.html)

**Acceptance:** the dashboard can explain research/live divergence, pause affected signals, retain evidence, and validate a replacement version before promotion.

## 5. How to establish that a component adds value

For every optional predictor or filter, use this protocol:

1. State the hypothesis and expected mechanism before inspecting outcomes.
2. Freeze a base policy, eligible sample and trial budget.
3. Run base and base-plus-component on identical permitted data, costs and timestamps. If a new dataset shortens coverage, compare both on that common coverage and disclose it.
4. Select any thresholds only inside development. Evaluate outer windows with the complete selection process frozen.
5. Compare candidate expectancy and portfolio net return, drawdown, exposure, turnover, coverage and alert rate. Use paired time-block differences where appropriate.
6. Inspect stability by horizon, asset and market conditions without promoting an exploratory slice after seeing it.
7. Stress entry delay, friction, funding and nearby parameters; investigate dependence on a few trades.
8. Charge the variant to the trial ledger and validate the chosen version forward.

Do not optimize every module independently and assume their combination works. Filters interact, and successive selection changes the candidate population. Freeze and retest the assembled policy.

Record evidence as rejected, insufficient, historically supported within declared scope, or forward-supported within declared scope. A source-data integrity failure is an invalid experiment, not evidence that the strategy is unprofitable. No label should imply certainty about future trades.

## 6. Different requirements for intraday and swing

| Dimension | Intraday | Swing |
| --- | --- | --- |
| Proposed decision bars | 15m/1h | 4h/daily context |
| Execution sensitivity | Delay and friction may consume a large share of intended move | Still material; multiple funding events and gap/tail risk become more prominent |
| High-frequency inputs | Potential execution context; test whether information survives manual delay | Usually lower priority as directional predictors |
| Data resolution | Fine replay needed for entry/stop ordering | Coarse decision bars still need finer execution replay |
| Evidence accumulation | More signals can still be highly dependent | Fewer outcomes; resist excessive regime subdivision |
| Validation duration | Based on matured independent information and regime coverage | Often requires longer windows and forward observation |
| Joint operation | Must account for existing swing exposure | Must account for repeated intraday positions in the same direction |

These are design priorities, not fixed rules that determine a profitable horizon.

## 7. What to build first and what to defer

### 7.1 Review and research sequence

Research order is deliberately different from implementation order: outcome definitions and evidence requirements need to be understood before their full engines are built.

| Review stage | Components | Decision to settle |
| --- | --- | --- |
| 1 — Overall contracts | C09 and C12 concepts; all component boundaries | What counts as a setup/outcome, what constitutes usable evidence, and who owns each responsibility |
| 2 — Data foundation | C01 → C02 | Universe, historical coverage, available datasets, timing and integrity requirements |
| 3 — Measurements and perpetual costs | C03; mandatory funding subset of C06 | Minimal features, units, warm-up and settlement accounting |
| 4 — Strategy and execution | C08, C09 and C07 | First hypothesis, executable trade contract, fill/delay/cost assumptions; iterate their interfaces together |
| 5 — Evaluation and estimates | C11 → C10 → full C12 | Replay semantics, estimand, uncertainty, nested fitting, folds and promotion decisions |
| 6 — Combined risk | C13 | Risk limits, candidate ranking and intraday/swing overlap |
| 7 — Operation and feedback | C14 → C15 | Delivery lifecycle, paper-state ownership, forward measurement and pause rules |
| 8 — Optional predictive extensions | C04, C05 and predictive subset of C06 | Dataset feasibility and an incremental-value experiment for each proposed feature |

If the chosen first strategy requires an optional module, bring that module's research forward before finalizing the strategy. Optional does not mean it can be omitted from an experiment that explicitly depends on it.

### 7.2 Reusable component research record

Use [COMPONENT_REVIEW_TEMPLATE.md](/Users/artemis/Mehul/Tradee/COMPONENT_REVIEW_TEMPLATE.md) for each deep dive. Record alternatives, sources, selected definitions, incoming/outgoing contracts, unresolved questions, failure modes and acceptance examples. Keep proposed decisions distinct from reviewed decisions. Update both sides of a changed dependency and revisit affected consumers.

### 7.3 Provisional implementation sequence after review

The following is a dependency-based sequence for later implementation, not authorization to begin it now:

1. Agree neutral domain contracts and versioned configuration from the C09/C12 research; build C01, then C02.
2. Build minimal C03 and mandatory C06 funding logic; implement C07 execution primitives and C08 baseline detection, followed by the shared C09 lifecycle. Review their interfaces together, using fixtures where useful.
3. Build C11's independent-candidate replay and basic ledgers; generate earlier outcome artifacts; build C10's baseline estimator.
4. Complete C12 orchestration, fold isolation and promotion records; inject frozen C10 inference into later C11 evaluations.
5. Build C13 and integrate finite-capital policy evaluation into C11; validate the complete combined policy through C12.
6. Build C14 and C15 and perform forward paper validation. Add optional C04/C05/C06 predictors only through separately recorded experiments.

This ordering resolves the C11/C10 relationship by separating outcome generation, estimator fitting and later evaluation. C12's manifest/holdout specification must be in place before performance inspection even though the full automation is implemented later.

### 7.4 Minimum scope and deferred work

**First complete research slice:** C01/C02, a minimal C03, one C08 hypothesis, C09, realistic C07/C11, basic C10 and C12. Add C13/C14/C15 for forward paper validation. Record live data early so execution research can accumulate while the simulator is built.

**Next experiments:** simple C04 context, a second trading horizon, basic C05 levels, then C06 predictive features where historical coverage is sufficient. Validate the combined portfolio before broadening the scanner.

**Defer:** full order-book directional models, deep-learning prediction, large SMC rule libraries, sentiment/on-chain feeds, unrestricted optimization, and LLM trade verdicts. Each creates data, validation or latency burdens. None is a prerequisite for testing whether a simple strategy has positive expectancy.

Open choices needed before implementation: manual-entry delay assumptions; modeled account and risk limits; maximum signal/position duration; allowable order types; source-data retention budget; initial hypothesis; and a record of which historical periods have already influenced prior research. Numeric promotion criteria should be declared after coverage/sample planning and before performance inspection.

The recommended first deliverable is a report that follows one complete setup from available data through candidate detection, fill/exit simulation, costs, uncertainty and an unseen-data decision. That makes every later component accountable for an observable improvement.

## 8. Research limitations

This is a source-informed architecture and research design, not a systematic meta-analysis or a measured claim about Binance profitability. Primary exchange documentation, original research abstracts/papers and official statistical documentation were prioritized. Some publisher full texts were unavailable; their accessible summaries are identified above. Exchange documentation was checked on the research date and should be rechecked at implementation. Data coverage, strategy results, actual fee tier and manual execution behavior remain unmeasured.
