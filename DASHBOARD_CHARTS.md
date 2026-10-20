# Dashboard chart and financial-display specification

Planning date: **21 October 2026**. Proposed, not implemented. Companion to [the product plan](DASHBOARD_PLAN.md), [service contracts](DASHBOARD_SERVICE_PLAN.md) and [delivery plan](DASHBOARD_DELIVERY_PLAN.md).

## 1. Shared chart contract

Every chart declares instrument/contract identity, population/track, run or session, dataset/report version, time/availability basis, units, whether values are exact or display approximations, and verification/unknown state. The context is visible near the plot and included in export metadata.

All charts provide labelled axes/legends, a useful tooltip, keyboard-accessible detail/table alternative, no-data/error explanations and a direct evidence link. Linked zoom/crosshair applies only to compatible time axes. A missing value creates a gap or unavailable region; it does not become zero or a carried-forward observation unless that specific financial contract permits it.

The browser renders authoritative series and exact summary values from the service. It does not independently recreate C03 indicators, C07 fills, C09 outcomes, C10 intervals, C12 research tests, C13 risk or C15 reviews.

## 2. Baseline chart inventory

IDs are acceptance references, not new domain components. “Projection” means new API/service work is required even when source evidence already exists.

| ID | Chart and location | Authoritative source | Axes / series | Click or selection | Important restriction / prerequisite |
| --- | --- | --- | --- | --- | --- |
| CH01 | Price candles — Markets, signal/trade detail | Pinned C02 observations, C01 precision/identity | UTC bar interval, price OHLC | Crosshair; select bar → source/feature evidence | New ranged OHLCV projection; do not substitute entry/exit-point prices |
| CH02 | Volume — lower market pane | Same C02 candle vintage as CH01 | Time, base or quote volume with explicit unit | Bar selection follows CH01 | Missing minute/bar is a gap; no synthetic zero volume |
| CH03 | Strategy and feature overlays | C03 snapshots + C08/C09 original definitions | EMA20/50, prior breakout range, policy stop/target/partial levels | Select line/marker → rule/value/timestamp | New feature-series projection; no front-end formula or future-derived level |
| CH04 | Spread, top-of-book and freshness | C02 quote/mark + C03/C07 status | Time, bps/notional/age in separate scales/panes | Select point → quote/evaluation | Top-of-book is not depth/order flow or an authenticated execution |
| CH05 | Decision / trade / delivery timeline | C08/C09/C14 journal + C15 references | Multiple event lanes with distinct clocks | Step/select event → exact decision/publication/attempt | Event time and availability/recording time cannot be collapsed |
| CH06 | Funded equity + drawdown | C13 regular samples/terminal report; selected C14 book | USDT equity; USDT/fraction drawdown | Brush interval → position/ledger window | Funded book only; preserve valuation gaps and full-resolution extrema |
| CH07 | Exposure and risk utilization | C13 inspect/allocation, frozen RiskPolicy | Exact value versus limit by symbol/group/horizon | Click utilization → contributing positions and rejected allocations | Risk/stress/beta/collateral are implemented proxies with declared assumptions |
| CH08 | Independent-scenario PnL | C11 regular_pnl/report samples | Time, independent marked PnL USDT | Linked trades and coverage | Label independent; no capital-return percentage or funded equity claim |
| CH09 | Net-R distribution and excursions | Mature C09/C11/C13 labels of selected track | Fixed bins, count and net R; MFE/MAE optional | Select bin → exact underlying rows | Mature denominator and unknown count always shown; sampled extrema only |
| CH10 | Cost attribution / ledger bridge | C07 estimates, C09 ledger, C11 attribution | Gross fill-price PnL → fees → signed funding → net | Select leg → fill/source receipt | Shortfall breakdown is separate; never subtract shortfall twice |
| CH11 | Walk-forward ownership timeline | C12 immutable protocol/jobs and C11 label windows | Train/inner/outer/purge/gap/tail intervals | Select fold → permitted evidence/config | Final holdout results gated; boundaries reflect actual protocol |
| CH12 | Fold evidence intervals | C12 stored fold/final evidence | Fold/window, producer's utility/interval and coverage | Select point → exact estimator/sample/budget | Label exact estimand; do not present every interval as mean trade R |
| CH13 | Development parameter/stress heatmap | Registered C12 variants/stresses in allowed evidence | Two declared parameters; fixed metric and scale | Cell → run/variant detail | Not an optimizer; no hidden trials or final-holdout sorting |
| CH14 | Compatible-run comparison | Pinned C11/C13/C12 artifacts | Same metric/unit/window per panel | Align range; select diverging period → trades | Reject mixing independent PnL and funded equity; no rescaled-size outcomes |
| CH15 | C10 cohort estimate / coverage | Frozen C10 model/estimate | Cohort mean and block interval, counts/time spans | Select cohort → definitions and applicability | Conditional on simulated fill/mature evidence; not confidence in next trade |
| CH16 | Reliability/error diagnostics | Existing C10 frozen_evaluation | Reliability bins with n; net-R error | Select bin → matched prediction/outcome rows | Empirical frequencies and Brier diagnostics are not certified calibration |
| CH17 | Forward fixed-review evidence | C15 immutable reviews and policy | Scheduled look, mean net R / residual, stored bounds | Review → evidence rules and pause decision | Sparse/degenerate reviews remain visibly insufficient, without drawn fake bounds |
| CH18 | Research versus forward comparison | Matched C10/C12/C13 + C15 population | Side-by-side net/cost/coverage summaries | Period/cohort → compatibility/evidence | Conditional UI projection; no automatic pooling or unregistered significance |
| CH19 | Processing and delivery latency | C14 journal/processing and C15 telemetry | Measured ms over time; descriptive histogram/quantiles | Outlier → exact attempt/cycle | Acceptance/claim time is not human reaction/fill latency; sample size required |
| CH20 | Data coverage / revision calendar | C02 pinned quality/replay; C01 metadata scope | UTC calendar buckets by symbol/stream | Bucket → gaps/revisions and affected runs | Absence of trades/quotes is not automatically a missing fixed-cadence event |
| CH21 | Operational health history | C14/C15 journal + collector telemetry | Discrete states, source ages, configured thresholds | Incident → source and available recovery action | A connected browser is not proof of a healthy market feed |
| CH22 | Funding projection and settlement | C06/C02 report/calendar + C09 cash flows | Timestamped projected rate/next estimate versus settled cash-flow events | Settlement → receipt/calendar/provenance | Explicit different units/horizons; no zero-fill for unknown funding |
| CH23 | Candidate/admission/outcome coverage | C08/C11/C13/C14/C15 inventories | Stage counts and disclosed denominator | Stage → filtered list/reasons | Distinct candidates versus size options, fills and mature outcomes |
| CH24 | Evidence lineage explorer | Curated references across C02/C03/C10–C15 | Dataset → feature → policy/model → decision → outcome | Select node → shared inspector | New bounded projection; cyclic/historical refs collapse; accessible table equivalent |

CH01–CH10 form the initial chart/operations foundation. CH11–CH18 make research and forward review complete. CH19–CH24 supply diagnostics and explainability across those screens. Implementation phases may split them, but the full target includes them subject to source availability and the explicit gates below.

## 3. Price, indicators and order-of-knowledge

### Candles and alignment

Baseline supported timeframes are exactly C03's `1m`, `15m`, `1h`, `4h`, `1d`. C02 stores one-minute candles; aggregate through the shared authoritative C03 bar semantics or a tested identical projection, with identical boundary/finality/gap rules. Do not add a second casually different aggregator in TypeScript.

- Candle identity includes instrument ID, timeframe, open/close UTC interval, source version and availability cutoff.
- A higher-timeframe completed bar requires its full permitted lower-timeframe evidence; mark incomplete/gapped intervals rather than polishing them into complete candles.
- Partial/current-bar updates are a different series state. They require the matching exchange interval and event evidence. If unavailable, show latest quote/mark as a price line and label the current candle unavailable.
- Never update an old closed bar from a generic last-price event. Corrections/revisions produce a new version or explicit revision marker.
- Base volume, quote volume and trade count have distinct units. No unexplained tick-volume proxy.
- Price precision comes from the applicable C01 rules, including historical rule vintage for historical charts. Full Decimal values remain accessible even when rendered as finite numeric coordinates.

### Features and strategy levels

Default range-breakout template: previous completed-bar range, actual breakout/detection marker, C09 policy levels and volume. Default trend-continuation template: EMA20/EMA50, recovery/detection marker, policy levels and volume. ATR14 and RSI14 are optional secondary panes; VWAP/participation/Bollinger and other existing C03 features are available through a controlled selector when the service supplies valid series.

Every feature carries value/status, stable flag, definition/version, target interval and source cutoff. Invalid/unstable regions are excluded or visibly marked. The initial chart-series job must budget enough pre-roll for the actual C03 stabilization policy; requesting 50 visible bars does not imply 50 bars is enough EMA50 history.

Frozen entry, stop, target and partial levels are read from original policy/decision artifacts. No visual dragging changes the policy. A future research scratch drawing can exist as an annotation, visually and persistently separate from tested levels.

### Price basis and execution

Provide explicit last-trade, best bid/ask, mid, mark and candle-close choices where supported. The default basis is shown in the title. A stop/target trigger basis is the C09 policy's basis, not whatever price the viewer selected. Simulated fills use exact C07/C09 price/time/quantity and distinct marker shapes; funding and partial fills are separate timeline events.

A chart cannot determine a win from wick contact if the authoritative policy marks an unresolved path. It must retain the unresolved result and let the user inspect finer evidence when available.

## 4. Replay and trade investigation

### Three clearly named view modes

| Mode | What the user can see | What it changes |
| --- | --- | --- |
| Latest market | Current permitted recorded observations, explicit provisional data and latest paper state | View only; no extra candidate/strategy execution |
| Decision as-of | Only source observations/features/decisions published/available by the selected cursor | Immutable inspection; hidden later outcomes and markers |
| Retrospective review | Complete permitted outcome tail with entry/exit/funding and revisions | Explicitly leaves the causal decision view; cannot become new untouched evidence |

The replay controller supports play/pause, speed presets, step source event/bar/decision, jump to next candidate/exit and return to the original decision cutoff. A viewer speed setting is unrelated to C07's modeled/manual delay.

Use availability order and actual audit-recording time where relevant, not just exchange event timestamps. A late or backfilled publication cannot appear at an earlier cursor. Outcome markers and net values appear only when their relevant knowledge/publication timestamps permit them.

Stored decision snapshots are preferred. If a requested feature/policy state has no persisted representation, show “not recorded for this cursor” or request an explicit bounded reconstruction job. No browser look-ahead or implicit full-history engine run fills the gap.

Selecting a trade fits actual OHLCV around pre-roll, decision/entry and outcome tail. A shaded warm-up/decision/tail ruler and vertical time markers explain context. Include deterministic previous/next trade navigation, the exact ledger, data gaps and the independent/funded track label. Trade markers can be clustered at low zoom, but the underlying table remains exact.

## 5. Financial plot rules

### Equity and drawdown

Source authoritative C13 samples. Display marked equity with cash as an optional separate line. Drawdown uses the producer's running-peak semantics, including the initial capital baseline. Unknown marks/funding create gaps and a coverage warning; do not connect across them as if known.

Display-only downsampling cannot determine max drawdown or totals. Use producer metrics and retain extrema/threshold crossings in visual sampling. Never average candlesticks or drawdowns to make a chart fit the screen. If new regularly sampled statistics are needed, they require a backend-defined metric contract.

C11's independent PnL panel has no invented initial account, leverage, portfolio percent return or annualized Sharpe. C13 supplies a shared book but currently returns null annualized return and Sharpe; they remain unavailable in the UI.

### Costs and funding

The primary ledger bridge is **gross fill-price PnL − fees + signed settled funding = net PnL**. A second panel explains delay drift + spread crossing + extra slippage/rounding = implementation shortfall. These are different views of the economics, not successive debits.

Next-settlement funding estimates have a forecast timestamp, horizon and assumption disclosure. Settled whole-hold funding has receipt/coverage state and signed cash flows. Show them separately; only a genuinely matched forecast/settlement pair can support a forecast-error display. C15's entry-paper-fee difference is a paper-accounting check, not proof that modeled slippage matches the user.

### Research inference and comparison

Reuse stored intervals/methods. C10 conditional mean R, C12 selected utility per candidate and C15 admitted mean/residual R are separate estimands. Axes, tooltips and exported metadata must name them. No generic “95% confidence” badge is allowed without the actual producer's family/look/block details.

Keep all-versus-mature and estimated/eligible/matched denominators visible. Display omitted/unresolved samples alongside distributions. C15 fixed reviews with absent bounds show reason chips and an empty interval slot; continuously updated descriptive curves never impersonate extra statistical looks.

Compare only identical defined metrics; incompatible quantities/policies/capital or data windows trigger a visible compatibility warning or disable overlay. Do not rescale a one-unit execution path to an untested quantity. Any normalization to a common base is a labelled display operation and does not supply missing capital evidence.

Exploratory filter/heatmap changes update the visible slice label and sample coverage. They do not recalculate promotion decisions, narrow original intervals on the fly or reopen a frozen final holdout silently.

## 6. Rendering, performance and accessibility

Recommended chart split: **Lightweight Charts** for candles, volume, market overlays, markers and synchronized financial panes; **Apache ECharts** for distributions, heatmaps, fold intervals, coverage, funding and diagnostics. Use a consistent wrapper for units, colors, evidence metadata, empty state, resize, export and keyboard/table alternatives.

The official [Lightweight Charts pane documentation](https://tradingview.github.io/lightweight-charts/docs/panes) supports separate/resizable panes. Its [README attribution requirements](https://raw.githubusercontent.com/tradingview/lightweight-charts/master/README.md) require the applicable notice and a TradingView link; preserve them in the designed chart/footer and recheck the exact pinned release before implementation. Do not assume the commercial TradingView Charting Library or hosted widgets are interchangeable with this library.

[Apache ECharts](https://echarts.apache.org/en/index.html) supplies suitable analytical chart types. Its [ARIA guidance](https://echarts.apache.org/handbook/en/best-practices/aria/) describes chart descriptions and pattern support; enable the supported accessibility facilities and still provide our own useful data tables/summaries. Package capability does not alone establish dashboard accessibility. Sources checked 21 October 2026; proposed versions are not installed or locked yet.

Initial performance targets, to benchmark rather than claim achieved:

- Price request defaults to 500 visible candles, caps an individual response around 2,000, and pages older intervals while preserving viewport.
- Start with one chart; target two synchronized market charts with up to four enabled overlays and two lower panes on the recorded developer reference machine.
- Bound analytical plot points, use server-side aggregation with disclosed bucket semantics, and virtualize/paginate long tables.
- Preserve current selection and visible range on incremental update. Append/update supported tail data rather than rebuilding every chart on each quote.
- Coalesce provisional quote/visual ticks at a bounded display cadence. Final bars, policy/position transitions, delivery receipts and control events are never semantically dropped.
- Dispose subscriptions, timers, ResizeObservers, chart instances and fetches on route/symbol changes; test repeated mount/unmount and reconnect.
- Annotate large gaps and missing values, use accessible patterns/shapes, support reduced motion, and provide keyboard navigation or equivalent tabular workflows.
- PNG/CSV export includes scope/cutoff/units and a sampling disclosure. A reduced plot never replaces full-resolution authoritative metrics.

Exact hardware, test corpus, response/interaction budgets and memory ceilings are frozen after the first benchmark. New chart types or unsupported features must be reviewed as extensions, not added as decorative defaults.
