# Tradee dashboard — product and interaction plan

Planning date: **21 October 2026**. Status: **proposed for review; no frontend, API, dependency, configuration or trading-engine implementation is authorized by this document**. The user requested a detailed UI/dashboard plan with charts, informed by TBot, with no code changes yet.

Read this document first. Continue with [chart specifications](DASHBOARD_CHARTS.md), [service/data contracts](DASHBOARD_SERVICE_PLAN.md), then [delivery phases and acceptance](DASHBOARD_DELIVERY_PLAN.md). Together these define one planned product, not four separate projects.

## 1. Product direction

Build a personal research and paper-operations workstation for Binance USDT perpetual futures, supporting intraday and swing workflows. The user should be able to answer:

1. Is the data/runtime healthy, current and actually running?
2. What setups were detected, admitted or rejected, and why?
3. What did the frozen strategy know when it decided?
4. What is the shared paper book's exposure, cash, equity and risk?
5. Does the strategy have credible after-cost research evidence, with what limitations?
6. Are forward outcomes and delivery/cost assumptions diverging from research?
7. What changed, what needs attention, and what evidence supports the next action?

The first complete UI should make **all implemented mandatory components usable through their workflows**, while preserving the current paper-only boundaries. A frontend cannot supply missing live-trading approval, actual fills, a new indicator engine or valid statistical evidence by drawing a chart.

### What “better than TBot” means

| Improvement | Observable outcome |
| --- | --- |
| Connected investigation | Signal → synchronized chart → decision gates → paper ledger → delivery → forward review, without repeatedly reselecting context |
| Real price context | Trade inspection uses actual pinned OHLCV, never an entry/exit-point line presented as market history |
| Honest freshness | Browser connection, Binance recording, paper computation, metadata, funding and delivery each have distinct status/age |
| Explainable acceptance/rejection | Exact frozen rule, observed value, threshold, missing evidence and source artifact are inspectable |
| Research discipline | Development, validation, locked/opened holdout and forward windows stay visually and behaviorally distinct |
| Financial meaning | Shared-wallet equity is distinct from independent-signal PnL; unavailable metrics remain unavailable |
| Durable investigation | Expired, rejected, suppressed, revised and ambiguous records remain searchable; refresh/reconnect does not lose them |
| Pleasant daily use | Restrained dark design, fast symbol switching, saved layouts, linked selection, useful keyboard access and responsive detail views |

## 2. TBot review and reuse decisions

This is a **source-level review**, not a browser usability audit or a claim that every observed code path was reproduced at runtime. TBot was read only; it was not modified or started.

| Reviewed source in sibling TBot | Existing strength | Tradee decision |
| --- | --- | --- |
| `frontend/src/App.tsx` | Sidebar, responsive navigation, dedicated chart/feed/backtest/data pages | Keep recognizable navigation; group around daily workflows and add a persistent context/status header |
| `pages/Charts/Charts.tsx`, `CandleChart.tsx`, `ChartControls.tsx` | Candles, volume, OHLCV crosshair, EMA toggles, zones, pivots, reset/follow controls | Keep a strong chart workspace; default to C03/C08-supported measurements and explicit as-of/source context |
| `pages/Charts/useChartData.ts` | Parallel loading, loading/error handling, live updates and aborted-result guard | Specify cancellable requests, stale-response prevention, per-resource failure states and stable viewport behavior |
| `pages/SignalFeed/SignalFeed.tsx` | Watching/confirmed/rejected tabs, sessions, setup cards and live events | Retain the workflow, but use Tradee's actual lifecycle and separate delivery state; preserve historical rows |
| `hooks/useSSE.ts` | Shared SSE transport pattern and reconnect indicator | Use one tested event registry, resumable IDs, bounded reconnect and snapshot recovery |
| `pages/Backtest/Backtest.tsx`, `MetricsSummary.tsx`, `EquityCurve.tsx`, `TradeLog.tsx` | Config/result separation, summary/equity/chart/log tabs | Retain these affordances; add research provenance, costs, coverage, independence and capital context |
| `pages/Backtest/TradeChart.tsx` | Trade markers and chart inspection | The reviewed implementation constructs a line from trade entry/exit points; Tradee must fetch the actual market interval for price context |
| `pages/BacktestAnalyser/*` | Multi-run comparison, drill-down and heatmaps | Use registered artifacts and comparable cohorts; imported external files remain isolated and clearly unverified |
| `pages/HistoricalData/*` | Dataset browsing and import workflows | Add availability-time coverage, revisions, mark/quote/funding quality and reproducible dataset selection |

Specific source observations informing the plan:

- TBot's feed handles `signal_confirmed`, while the reviewed SSE hook's event list does not subscribe to that event name. Tradee needs an exhaustive server/client event-contract test.
- The feed removes expired cards after a timeout and clears session-associated cards when a session stops. Tradee should retain them as history, with explicit active/archive filtering.
- The reviewed chart hook can update the last historical candle's close/high/low from a generic price event. Tradee must distinguish an independently displayed live quote from an exchange-identified, provisional candle update.
- TBot's summary colors win rate at 50% and shows several metrics numerically by default. Tradee should not imply profitability from win rate alone, or replace absent Sharpe/calibration evidence with a number.
- S/R, SMC/FVG/order-block and pivot displays are useful inspiration, but Tradee C04/C05 are not implemented. They are not baseline chart capabilities merely because TBot has controls for them.

Reuse interaction ideas and the financial-chart library choice where appropriate. Do not copy TBot's strategy formulas, API payloads, confidence scores, assumptions or runtime behavior wholesale.

## 3. Navigation and context

### Primary navigation

| Area | Proposed route | Main task | Component dependencies |
| --- | --- | --- | --- |
| Overview | `/overview` | Daily operating summary and next investigation | C01/C02/C13/C14/C15 |
| Markets | `/markets/:instrumentId` | Inspect price, features and decision context | C01/C02/C03/C07/C08/C09 |
| Signals | `/signals` and `/signals/:signalId` | Follow candidate/paper lifecycle and reasons | C08/C09/C10/C13/C14/C15 |
| Portfolio | `/portfolio/:sessionId` | Inspect shared paper wallet, positions and risk | C09/C13/C14 |
| Research | `/research` with runs/experiments/models subsections | Backtests, walk-forward, comparisons and frozen releases | C03/C06–C13 |
| Forward Review | `/forward/:monitorId` | Compare forward evidence, reviews and incidents | C14/C15 plus C10–C13 lineage |
| Data | `/data` with datasets/instruments subsections | Validate inputs, coverage and instrument rules | C01/C02/C03/C06 |
| Operations | `/operations` with sessions/delivery/jobs/audit | Runtime setup, recovery, controlled actions and workload | C12–C15 plus new UI service/job infrastructure |

Settings, shortcuts/help and the artifact inspector are utility destinations, not additional primary work areas. C01–C15 identifiers appear in provenance/help, not as fifteen competing menu items.

### Persistent context header

Every screen shows the current workspace/source profile, **SHADOW / PAPER TEST / HISTORICAL RESEARCH** scope, selected session or run, local clock/timezone, evidence cutoff, and compact health indicators. The UI cannot select an unsupported live mode.

Common controls: instrument, strategy family, horizon, timeframe, date range and session/run selector. Enable only controls meaningful to the current page. Changing a display filter never edits a strategy or triggers a new experiment.

Use UTC instants and UTC candle boundaries internally. Default display to the user's Asia/Kolkata timezone with an obvious UTC toggle. Tooltips show both local and UTC time. Daily research partitions remain those declared by the producer; changing display timezone does not regroup research evidence silently.

**Follow latest** and **Pinned evidence** are explicit, mutually understandable states. A pinned research/report page never starts drifting to new data. Opening a signal carries its instrument, timeframe, policy and evidence IDs into the chart. Back/forward navigation restores context.

### Shared evidence drawer

An always-consistent right drawer opens from a signal, plot point, metric, rejection reason or artifact badge. Tabs:

1. **Explanation:** plain-language decision and relevant values.
2. **Timeline:** detection, source availability, admission, publication, delivery and outcome knowledge.
3. **Economics:** fill basis, fees, funding, net outcome and uncertainty/unknowns.
4. **Rules:** immutable configuration and comparison against observed values.
5. **Evidence:** readable source/run/model/dataset references with copy/full-record actions.

Human-friendly labels appear first. Hashes, raw JSON and schema details are available on demand. Large records use paginated sections; the browser does not download an entire audit database to show one explanation.

## 4. Visual design system

Design a calm, dense workstation rather than a wall of glowing KPI tiles.

| Element | Proposed specification |
| --- | --- |
| Theme | Dark default; a properly tested light theme follows the same semantic tokens |
| Base palette | Background `#0B1018`, panel `#121A26`, border `#2A3648`, main text `#EDF2F7`, secondary text `#A8B4C5` |
| Semantic accents | Information blue `#69AEFF`; healthy teal `#2DD4BF`; caution amber `#F7BA50`; failure red `#FF7584`; positive money `#4CD6A4` |
| Direction versus outcome | Long/short use distinct labelled blue/orange markers; profit/loss use signed money and separate semantics. Direction is not a profit prediction |
| Typography | System sans, 14–15px body, 12–13px secondary labels, 20–24px page titles; tabular numerals and monospace only for dense values/IDs |
| Spacing | 4px base scale; 16–24px page padding; 8–12px component gaps; consistent panel headings |
| Tables | Sticky headers, adjustable columns, 32–40px desktop rows, row expansion, explicit units and sticky identifying columns |
| Status | Text + icon + color; unknown uses neutral/hatching, not a successful green or a zero |
| Motion | Small transition/focus changes only; no flashing PnL, jumping rows or constant pulsing; respect reduced motion |

These are design targets; color contrast is validated during implementation rather than assumed from hex values. Aim for [WCAG 2.2 AA](https://www.w3.org/TR/WCAG22/): keyboard navigation, visible/unobscured focus, appropriate contrast, labelled controls, chart alternatives and non-color status communication. Use generous approximately 44px primary touch targets where practical, while permitting accessible desktop density.

Desktop reference layouts: 1440×900 and 1920×1080. Sidebar approximately 224px, top context approximately 56px, optional evidence drawer 360–420px. At narrower widths, the drawer becomes a full detail route and side tools collapse. At 390px mobile width, prioritize health, signals, positions and incident reading; chart navigation still works and secondary tables can scroll. Every core task has a non-hover path.

## 5. Screen specifications

### 5.1 Overview — the daily starting point

**Question:** what is happening and what deserves attention?

Top: scope/session selector and freshness strip. Four primary summaries: paper equity/cash context, open risk versus configured limit, candidate/admission coverage, and unresolved operational issues. Each includes its source time and navigates to detail.

Main grid:

- Large shared-wallet equity/drawdown panel for the selected C13/C14 book.
- Latest candidates/signals table with strategy, age, lifecycle, expectancy availability and rejection/delivery status.
- Compact market watchlist: last supported price basis, spread, quote/mark age, candle completeness, and data readiness.
- Attention queue: failed/ambiguous delivery, stale recording, unresolved outcomes, evidence verification failure, approaching resource limit and due/insufficient reviews.
- Small research/forward evidence summary: last frozen experiment, last forward review, maturity coverage and outstanding gates.

The attention queue sorts operational severity and time; it is not an invented composite “strategy confidence” score. No wallet data produces a useful setup/empty state, not a zero-equity dashboard. Independent C11 PnL cannot occupy the paper-equity card.

```text
┌──────────────┬─────────────────────────────────────────────────────────────────┐
│ Tradee       │ PAPER TEST · session A · Follow latest · IST/UTC · health       │
│              ├─────────────────────────────────────────────────────────────────┤
│ Overview     │ Equity / cash    Open risk / limit    Admissions    Attention   │
│ Markets      ├──────────────────────────────────┬──────────────────────────────┤
│ Signals      │ Shared-wallet equity             │ Attention and next action    │
│ Portfolio    │ Linked drawdown                  │ Data / delivery / reviews    │
│ Research     ├──────────────────────────────────┼──────────────────────────────┤
│ Forward      │ Latest setups / paper signals    │ Market watchlist             │
│ Data         │ Select row → explanation/chart   │ Price basis + freshness      │
│ Operations   └──────────────────────────────────┴──────────────────────────────┤
│ Settings     │ Selected evidence context / last update / stream status        │
└──────────────┴─────────────────────────────────────────────────────────────────┘
```

This is a layout wireframe, not a mock run or fake performance data.

### 5.2 Markets — the primary chart workspace

**Question:** what does the market and the actual strategy context look like?

Three regions: collapsible watchlist on the left, dominant chart stack in the center, inspector on the right. Toolbar: symbol/contract, timeframe, source/view mode, range, overlays, compare, replay, reset and follow-latest. A bottom tab region hosts recent signals, feature values and source quality.

Default chart: closed OHLC candles + volume, an explicitly provisional current bar only when supported, and the selected strategy's actual levels/EMA20/EMA50. Default lower pane is one relevant diagnostic, selectable between RSI14, ATR14/fraction, spread/age or participation. More panes are optional; do not show every indicator at once.

Baseline timeframe controls: **1m, 15m, 1h, 4h, 1d**, matching the current C03 catalog. Hide/disable unavailable combinations with a reason. TBot's 5m/30m choices require a separately defined backend extension.

Core interactions:

- Zoom/pan, price-scale reset, jump to date, follow latest, maximize chart and synchronized crosshair.
- Strategy/paper markers: detected setup, admission/rejection, stop/target/partial policy levels, actual simulated fills and exit reasons.
- Select a marker → evidence drawer and highlighted table row; select a signal/trade → chart centered on its interval with pre-roll and outcome tail.
- Overlay visibility, pane height and layout are view preferences. Editing a frozen strategy from a chart is unavailable; “Use as a new research configuration” creates an explicit draft later.
- Single chart first, linked two-chart layout next (for example 15m execution / 4h context); four-chart layout only after performance acceptance.
- Distinct latest-market and decision-as-of contexts. A generic quote updates a quote label/price line, not a closed historical OHLC bar.

Indicator inspector shows formula/version, value, units, stable/warming-up/missing/gap status, bar count and availability. A visually smooth line is not proof of valid feature evidence. No S/R, FVG/order-block, depth heatmap or predictive regime badge appears as an implemented Tradee strategy input.

```text
┌─────────────┬─────────────────────────────────────────────────────────────────────┐
│ Main nav    │ BTCUSDT contract · 15m · Decision as-of · range · overlays · replay │
│             ├──────────────┬─────────────────────────────────────┬────────────────┤
│             │ Watchlist    │ Price / actual candles             │ Selected setup │
│             │ BTC, ETH     │ EMA or frozen range / policy levels│ Admission gates│
│             │ basis + age  │ Exact simulated fill/exit markers  │ Costs / risk   │
│             │              ├─────────────────────────────────────┤ Evidence tabs  │
│             │              │ Volume + one chosen lower pane     │                │
│             │              ├─────────────────────────────────────┴────────────────┤
│             │              │ Replay cursor · cutoff · availability / publication │
│             ├──────────────┴──────────────────────────────────────────────────────┤
│             │ Signals / Features / Quality — selected row linked to chart        │
└─────────────┴─────────────────────────────────────────────────────────────────────┘
```

### 5.3 Signals — durable setup and outcome investigation

**Question:** why was this opportunity selected, rejected or left unresolved?

Use the actual C14 lifecycle: detected, suppressed, expired, paper-open, paper-closed, paper-unresolved. Show delivery separately: pending, retry-wait, in-flight, sent, ambiguous, resolved-sent, failed, expired or suppressed. “Paper admitted” never implies “Telegram delivered”; “sent” never implies a user fill.

Default table columns: detected time, instrument, side, family/horizon, timeframe, lifecycle, admission/rejection reason, conditional mean net R/availability, maturity, delivery, age. Optional columns: quantity, first simulated fill, net USDT/R, revision, publication delay. Use stable row identities, cursor pagination, filters and saved views. Retain expired/suppressed/rejected history, with an explicit active/archive filter.

Signal detail is a route as well as a drawer:

- Pinned candle chart with policy levels, fills and exact context.
- Decision checklist grouped by data, instrument, features, C10 estimate, C07 execution and C13 capacity/risk.
- Forecast card with sample coverage, mean versus uncertainty interval, model availability and limitations. No invented confidence percentage.
- C09 ledger: entry/exit fees, fill-price PnL, signed settled funding, net subtotal versus fully known net.
- Chronology showing market time, availability, logical decision cutoff, actual audit recording, HTTP attempt, acceptance assertion and outcome knowledge.
- Delivery audit and version/revision history, with changed fields and links to previous immutable snapshots.
- “View independent shadow outcome” for a rejected opportunity; never attach that result to the funded wallet.

Signals without admissions or mature outcomes still have meaningful detail and missing-value explanations. If a filter changes, totals explicitly identify the filtered denominator.

### 5.4 Portfolio — one shared paper book

**Question:** what is the portfolio carrying and what limits affect the next setup?

Header: session, paper-account basis, cash, marked equity, exposure/risk as-of and missing marks/funding. Main panels: linked equity/drawdown, open positions, concentration/risk utilization and allocation history.

Positions table: instrument, side, strategy/horizon, quantity, actual simulated entry, stop/targets, available mark and its age, realized ledger subtotal, unrealized mark PnL, settled funding status, and net/valuation readiness. No authenticated Binance balance, liquidation price or manual close control is fabricated.

Risk details show exact configured limits for per-trade, aggregate/group/horizon risk, gross notional, collateral, beta/stress proxies and drawdown, where supplied by C13. Units and assumptions appear next to the values. The allocation timeline explains admitted and competing rejected size options at the same evaluation point.

A displayed paper-equity curve is C13 evidence, not the sum of C11 independent returns. Unknown valuations break the curve and mark gaps. Pausing notifications does not flatten positions or stop paper outcome measurement; the UI explains this at the pause control.

### 5.5 Research — one workspace with three connected sections

#### Runs and backtests

Master/detail run browser: completed/failed-evidence status, producer/model/policy, source window/as-of, scenario, cost assumptions, maturity/coverage and creation/job status. Filter by registered strategy/horizon and source profile; compare only after compatibility checks.

Run detail tabs: Summary, Price/Trades, PnL/Equity, Costs/Funding, Coverage, Configuration, Evidence. C11 shows **independent-scenario PnL diagnostics**; C13 shows **funded portfolio equity/returns**. No generic equity label masks this distinction.

Backtest draft workflow: choose pinned dataset → known strategy family and quantity/policy → fees/execution/delay/funding evidence → warm-up/decision/tail windows → preflight coverage/work estimate → review exact configuration → queue job. A completed report is immutable. Changes create another run; performance-driven variants must be accounted for in C12.

Compare workspace: up to four compatible runs, aligned declared windows, explicit cost/quantity/model differences, linked time ranges, and trade drill-down. Descriptive per-asset/side/month breakdowns are marked exploratory. External JSON import is a later optional isolated viewer, not an automatic route to experiment evidence or a release.

#### Experiments and walk-forward

List registered C12 families/trials, protocol state, development progress, job budget and holdout state. Detail shows chronological train/inner/outer/purge/embargo/outcome-tail windows, counted variants/stresses, fold evidence, decision reasons and release lineage.

The final holdout is a **real access-control/workflow state**. No default chart, comparison, search preview, browser prefetch, export or arbitrary-artifact route exposes its restricted results before the required C12 access operation. Opening it shows the exact scope, reason and irreversibility of exposure; the backend records the action. It is not merely blurred UI content.

Parameter heatmaps are available only from registered evaluated variants in permitted development evidence. Clicking a profitable cell changes selection for inspection, not a frozen protocol. Turning it into another candidate records a new draft/trial through the proper workflow. Do not silently optimize on opened final evidence.

#### Models, hypotheses and releases

Read-only baseline registry for C08 strategies, C09 policies, C10 models, C12 decisions and C13 compatibility receipts. Show model availability, cohort coverage, mean/uncertainty, eligibility and version changes. A recipe being compatible is not promotion approval.

The UI can help clone a configuration into a **new draft** and later run approved research operations. It cannot edit an active frozen model/session or provide a “go live” shortcut. C04/C05/extra C06 predictors remain tracked prospects.

```text
┌─────────────┬───────────────────────────────────────────────────────────────────┐
│ Main nav    │ Research · experiment / run · permitted window · evidence state   │
│             ├───────────────┬───────────────────────────────────────────────────┤
│             │ Runs / folds  │ Summary | Trades | Costs | Coverage | Evidence    │
│             │ Filter/status ├───────────────────────────────────────────────────┤
│             │ Compare pins  │ Train / validation / purge / tail ownership      │
│             │               │ Locked holdout: metadata only until opened       │
│             │               ├──────────────────────────┬────────────────────────┤
│             │               │ Correct PnL/equity curve │ Coverage and intervals │
│             │               ├──────────────────────────┴────────────────────────┤
│             │               │ Trade / variant table → chart + evidence drawer  │
└─────────────┴───────────────┴───────────────────────────────────────────────────┘
```

### 5.6 Forward Review — research assumptions versus observed paper evidence

**Question:** are the deployment's assumptions and operational behavior holding up?

Monitor selector with policy, deployment, original registration and source-verification state. Tabs: Outcomes, Reviews, Costs/Delivery, Revisions, Replay, Research Export.

- Separate admitted-paper and independent-shadow populations, with mature/pending/unfilled/unresolved coverage and denominator badges.
- Frozen C10 prediction versus matured paper net R; residual distribution and chronological outcome context labelled descriptive between fixed looks.
- Scheduled C15 reviews show paired mean-net-R/residual intervals, family alpha, declared looks, blocks, evidence minima, reasons for abstention and triggered pause rules. Missing intervals are not drawn as zero-width confidence bands.
- Operational, integrity and statistical incidents are distinct lanes. Show first occurrence/current state, associated report, requested pause, applied pause receipt and any later explicit operator resume.
- Costs panel contrasts C07 assumptions with recorded **paper** fees/funding and C14 timing. Unknown real-user slippage/receipt is labelled unavailable. An entry next-settlement forecast is not compared as if it predicted whole-hold funding.
- Replay panel displays pinned raw-prefix/C11/C13 checks and links the mismatch to evidence. Export preserves report/version/track identity and does not retrain anything.

Historical-versus-forward comparisons require a displayed compatibility checklist. Different cohorts, source fidelity, capital policy or fee/delay assumptions remain side-by-side descriptions until a valid matched comparison exists. No unregistered confidence interval on improvement is invented in the browser.

### 5.7 Data — know what evidence is usable

Dataset list/detail: source, recorded/modeled availability basis, instrument identities, time range, as-of, streams, event count, revisions, coverage/gaps and verification. Calendar heatmaps are drill-down tools, not proof that all live event streams have a fixed sampling cadence.

Instrument detail exposes current/historical C01 eligibility, metadata freshness and exact trading filters. A stable instrument ID is the key; a reused ticker must not merge different contracts.

Feature inspection displays C03 definition/readiness/stabilization and lineage. Funding inspection distinguishes observed projections, explicit calendar assumptions, settled receipts and missing settlements. Missing data can explain a blocked run or signal through the same evidence drawer.

Data acquisition/import/repair is a later controlled job workflow with range validation, source/provenance disclosure and progress. Browsing a page does not auto-collect data, create a new dataset or recompute a multi-year feature history.

### 5.8 Operations — sessions, delivery, jobs and audit

**Sessions:** inspect frozen C14 spec, producer compatibility, expiry/tail, source cutoff, cycle latency, budget and paused/fault state. New-session wizard ultimately validates C12 release/C13 compatibility, source/calendar/fee/risk scope and monitor policy; creates deployment, registers C15 **before the first tick**, then starts the separately supervised runner only by explicit action. A future session can be configured before start.

**Delivery:** per-signal outbox and full attempt history, queue age, TTL/lease, throttles, accepted IDs, ambiguity and reconciliation proof. An expired or ambiguous record is never converted into a generic “retry now” button.

**Jobs:** queued/running/completed/failed/interrupted/cancel-requested, validated phase progress, bounded logs and output artifacts. No made-up progress percentage or ETA. Closing the browser does not terminate or duplicate a job.

**Audit:** filter by domain, actor/request, object and time; readable change summary with exact evidence links. UI notes/acknowledgments are kept separately from domain events and never rewrite history.

**Operator actions, after the control phase is approved:** C14 pause/resume, C15 apply-current-pause-request, recover elapsed leases, explicit ambiguous-delivery reconciliation, registered research job submission, deliberate holdout access and lifecycle-safe job interruption. Controls show target scope, expected revision/audit head and consequence. Invalid/stale actions return a conflict and refresh; they do not silently retry.

There is no exchange order form, leverage slider, unsupported live activation, arbitrary strategy-code runner or “pause = close positions” behavior. Telegram connectivity/send controls, if later exposed, require a dedicated test destination and explicit per-action authorization; opening a page never sends anything.

## 6. Shared interaction rules

### Loading, stale and unavailable states

Distinguish initial loading, valid empty set, filtered-to-zero, insufficient history, warming-up, known zero, missing/unknown, stale, disconnected, permission denied, locked evidence, integrity failure and incompatible producer. Use inline recovery actions with a reason. A failed optional overlay must not blank a valid price chart.

On refresh, retain a correctly labelled last-known snapshot while loading newer data. On symbol/run changes, prevent old responses or subscriptions from appearing under the new header. Reconnect reconciles from the durable cursor and a fresh snapshot when necessary; it does not append duplicate signals.

### Metrics and formatting

Money/quantities remain exact decimal strings in transport; display rounding is reversible through tooltips/exports. Show USDT rather than suggesting authenticated USD holdings. Counts/coverage accompany rate and expectancy displays. Conditional mean, empirical win frequency, confidence interval and prediction interval are different concepts.

Sharpe, Sortino, annualized return, liquidation values, real account balances and calibrated win probability remain unavailable when their backend contract is absent. In particular, current C13 explicitly returns null Sharpe/annualized return. Undefined profit factor stays explained/undefined rather than becoming a fake large finite number. Win rate is descriptive, without a universal 50%-means-good color threshold.

### Selection, sharing and personalization

Page filters, selected run/row, viewport and pinned context belong in deep-linkable URL state where appropriate. Display preferences and saved layouts belong in local/user UI storage, versioned separately from immutable strategies. Never put tokens, private proof text or secrets into URLs or local storage.

Shortcuts: command/search palette, instrument jump, follow latest, reset chart, open selected evidence and navigate table rows. Pause/resume/holdout access cannot be triggered by an unconfirmed global shortcut. Search respects evidence access rules.

Exports: source-qualified JSON/CSV and chart PNG with mode, units, time basis, evidence cutoff and source reference. Use formula-injection-safe CSV output and clearly disclose any sampling. Screenshots/exports omit secrets and mask destinations by default.

## 7. Scope decisions for review

Recommended defaults: local single-user web application; dark desktop-first workstation; eight workflow areas; Lightweight Charts for market charts; ECharts for research/operational plots; Python API over the current core; read-only real-artifact slice first, then controlled operations. This is a recommendation, not an implementation approval.

The complete initial target includes charts, signal/portfolio investigation, research and forward evidence, data quality, operations and browser E2E. First milestones intentionally expose a smaller useful slice; [the phase plan](DASHBOARD_DELIVERY_PLAN.md) makes completion dependencies explicit. Deferred items remain visible, not silently omitted.

Before implementation, review the navigation/screen scope, dark-layout direction, proposed stack, controlled-action boundary and phase order. Exact dependency versions, performance limits and detailed wireframes are validated in the first implementation phase. No package is installed and no source/runtime change is made by this planning task.
