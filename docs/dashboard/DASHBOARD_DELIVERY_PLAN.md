# Dashboard implementation order, verification and completion gates

Implementation update, **21 October 2026**: the user approved development. The working dashboard covers all eight areas and controlled local operation. [Phase-by-phase delivery and remaining targets](DASHBOARD_IMPLEMENTATION.md) distinguish the shipped baseline from the larger D0–D8 specification below.

Read with [product/screens](DASHBOARD_PLAN.md), [charts](DASHBOARD_CHARTS.md) and [service/data contracts](DASHBOARD_SERVICE_PLAN.md).

## 1. Working rules

- Deliver useful vertical slices against real domain evidence, rather than build all visual pages against fabricated success data and connect them afterward.
- For each phase: confirm its contract/scope → implement → meaningful unit/API/browser tests → manual visual review → update docs/prospects → local phased commit. Existing core tests remain required when their producers/read semantics change.
- Fixtures may be synthetic but must retain their source/mode identity and call the actual core path where claimed. No external Telegram message/order is part of automated UI verification.
- Treat a backend prerequisite as a named task. Do not silently recreate its math or lifecycle logic in React.
- Do not add rough calendar estimates before contract and performance spikes. Dependencies and completion gates are more useful than unsupported dates.

## 2. Implementation sequence

| Phase | Depends on | Deliverable | Charts / workflows | Exit gate |
| --- | --- | --- | --- | --- |
| D0 — Contract and design freeze | Approved planning direction | Detailed desktop/mobile wireframes, exact DTO/capability boundaries, read-only DB approach, stack/lock decisions, reference data/benchmarks | One signal-to-chart-to-evidence walkthrough, empty/unknown/stale states | Screen/contract review complete; no unresolved source/holdout/precision ambiguity |
| D1 — Read-only shell and real evidence | D0 | Optional Python API, source-profile bootstrap, auth/read boundary, discovery, app shell, shared evidence drawer and status system | Overview basics, real C14 session/signal list and C15 report list | Real retained artifacts load in browser; missing/foreign/corrupt DB states are honest; GET has no domain writes |
| D2 — Market charts and signal investigation | D1; C01/C02/C03 ranged projections | Actual candles/volume, valid feature/strategy overlays, selected signal/trade route, linked table/marker and strict time context | CH01–CH05, initial CH23; Markets + Signals | Real raw-input trade opens correct OHLCV and original levels; gaps/provisional/revision/as-of cases pass browser E2E |
| D3 — Portfolio and economics | D2; C13 sample/risk projections | Shared-wallet equity/drawdown, positions, allocation reasons, costs/funding and evidence drill-down | CH06–CH10, CH22/CH23 | Cash/net/fees/funding agree with producer; no independent PnL presented as capital equity |
| D4 — Research and walk-forward read workspace | D1–D3; C10–C13 projections and holdout authorization | Run browser/detail/compare, fold timeline, cohort/model/release registry, counted variant/stress views | CH11–CH16, bounded CH24 | Locked/opened holdout behavior enforced across API/search/export/chart; metric/interval semantics remain exact |
| D5 — Live browser synchronization | D1–D4; durable event/cursor service | Resumable SSE or explicit polling-first fallback, resource-version reducers, live forming data and freshness | CH04/CH05/CH19–CH21 update behavior | Reconnect/gap/duplicate/stale-response/clock-skew tests pass; pinned historical views remain pinned |
| D6 — Forward review and data quality | D3–D5; C15 + C02 quality/revision projections | Full forward outcomes/reviews/replay/export, coverage/calendar and instrument/feature/funding inspection | CH17–CH24; Forward + Data | Mature/revoked/unknown tracks and fixed-look insufficiency render correctly; source-qualified export and replay links work |
| D7 — Controlled operations and durable jobs | D1–D6; operator auth/idempotency/job coordinator | Research/data/reconstruction jobs, deliberate holdout action, session/monitor wizard, pause/resume/recover/reconcile | Operations workflows and progress/audit | Stale/CAS, crash-gap, duplicate-click, interruption, holdout exposure and unauthorized-action E2E pass |
| D8 — Polish, resilience and local-release acceptance | D0–D7 | Responsive layouts, saved views, keyboard/accessibility, exports, two-chart workspace, operational docs/performance/backup drills | All baseline screens/charts | Automated + manual acceptance complete on declared machine/corpus; remaining limitations recorded |

This order deliberately exposes the platform early. **After D2**, the user can manually inspect actual Tradee signals on real candle charts. **After D3**, the shared paper-book economics are visible. **After D4**, existing backtests/walk-forward evidence is reviewable. **After D6**, all mandatory component outputs are covered read-only. **After D7/D8**, the planned initial dashboard includes controlled operation and release-quality interaction.

D5 may be split into an early minimal signal-change subscription after D2 and the full durable synchronization acceptance after D4, if this helps manual use. Its recovery/causal guarantees are not optional simply because the first transport looks live.

## 3. Phase detail and likely files

### D0 — Make decisions concrete

Approve the Overview, chart workspace, signal detail, research detail and Forward Review reference layouts at 1440×900 and 390px. Define palette/type/spacing/status tokens and chart-table alternatives. Freeze read envelopes, IDs, units, null reasons, source-vector semantics, supported timeframes and the first chart-range query.

Choose exact compatible versions only now; confirm chart attribution and local browser/Node/Python support. Decide whether read-only domain openers require a core change and therefore new producer fixtures. Establish the initial fixture corpus from C14/C15 retained artifacts plus explicit gaps, incomplete/late data and locked-holdout scenarios.

Planned artifacts: finalized UI wireframes/design tokens, endpoint schemas/capability matrix, benchmark profile and approval notes. These may remain documentation before any application bootstrap.

### D1 — Useful read-only application

Create the proposed optional `backend/tradee_web/` adapter package and `frontend/` shell only after approval. Implement configured source profiles, strict existing-store checks, typed DTOs, source discovery, stable errors and API authorization. Show Overview, Signals, basic Operations state and C15 report selection using real artifacts.

Do not start collectors, run the engine, initialize missing domain stores or make Telegram requests on application startup. Shared evidence navigation should already work. Show unavailable screens/routes with their phase/source requirements rather than decorative fake statistics.

### D2 — Financial chart foundation

Implement the authoritative range/OHLC aggregation contract, revision/finality metadata, C03 feature-series access and chart primitives. Cover original candidate levels, entry/exit/partial markers, volume and optional EMA/ATR/RSI panes. Add one deep-linked real signal/trade view and the three view modes.

Use the actual C03 warm-up/stability policy. If a requested series was not recorded/materialized, present that fact; an explicit reconstruction job can be added in D7. Preserve viewport/selection and reject late responses after symbol/context changes. A live quote line remains separate from completed OHLCV.

### D3 — Book and execution explanations

Add C13 regular samples, exact risk/position/allocation DTOs and C07/C09 ledger projections. Implement linked equity/drawdown, risk-versus-limit display and cost/funding bridge. Reuse the same evidence drawer and unknown-value patterns.

Validate the existing synthetic funded example against its **320 → 328.489 USDT**, **8.489 USDT net**, three-admitted/six-independent outcome fixture, while clearly labelling synthetic paper scope. These are engineering assertions, not expected investment results. Open or unresolved positions require separate cases.

### D4 — Research completeness and access

Add C11/C13 run discovery, semantic comparison rules, C12 chronological window/trial views and C10 model/evaluation displays. Incompatible comparisons are blocked or kept as explicitly unmatched descriptions. Implement real server-side ownership restrictions for protected results before adding generic artifact/search/export convenience.

No new strategy builder is needed to view existing research. The first registry is inspect/clone-to-draft; submission waits for D7. Do not infer unsupported Sharpe, probability calibration, full portfolio promotion or significance of a slice from a pretty chart.

### D5 — Synchronization that survives real use

Add a shared stream registry, initial snapshot/cursor handshake, durable replay/resync, bounded queues, per-resource revisions and source freshness. Test event completeness across server/client types. A single tab/route unmount cancels its work without leaking timers/subscriptions. Page refresh and disconnection retain record identity/history.

Benchmark an active but bounded recorded fixture; do not claim 24/7 Binance throughput from a small sample. Domain collector/runtime scaling limits still apply. If the service polls persisted heads, the refresh cadence is displayed accurately.

### D6 — Forward and input evidence

Implement C15 tracks, original forecasts, actual recording-time gates, maturity/revision history, scheduled intervals, incident/pause receipt and raw replay checks. Keep complete-cohort and insufficient-evidence states visible. Data views show which source gap/rule/funding uncertainty affects a selected signal/run.

Forward JSON/CSV export retains report/version/track identity. It does not import into C10 training or C12's holdout. Historical/forward comparison declares matching assumptions and abstains from unsupported significance claims.

### D7 — Deliberate controls

Introduce the persistent UI command/job journal, separate bounded worker and runner ownership. Add allowed actions incrementally: domain pause/request application and recovery first; then explicit resume/reconciliation; then data/research jobs and session creation/start. Every action has permission, typed input, expected state and idempotency/correlation.

Session setup must preserve the ordering C14 create → C15 register → explicit runner start. Future-start sessions show awaiting status without an early spurious pause. An interrupted wizard exposes its completed immutable steps for recovery.

Opening a holdout and reconciliation of a potentially accepted Telegram request are consequential actions with clear evidence/confirmation. Ordinary navigation and reversible display edits need no approval ceremony. A collector stop, runner stop and notification pause are separate actions with different consequences.

### D8 — Finish the product

Finalize keyboard/focus behavior, responsive layouts, load/error handling, view persistence, export masking, chart attributions, accessible tables and contrast checks. Add linked two-chart layouts only after the one-chart fixture passes resource tests. Document local startup/shutdown, independent process roles, source configuration, recovery, backup/restore and the manual acceptance run.

Keep a local-first deployment initially. A hosted multi-user platform, real account integration or automated trading is a separate review, not a hidden final step.

## 4. Automated verification plan

### Domain/API contracts

Test exact Decimal transport/formatting, UTC/timezone boundaries, opaque identity mapping, actual supported timeframes, schema/enum evolution, stable cursor pagination and deterministic filter/sort semantics. Verify missing stores are not created by reads, wrong SQLite application IDs fail, and cross-store source vectors never imply atomicity that does not exist.

Exercise corrupt/incomplete inventory, incompatible producer, stale/unready source, unavailable feature history, C03 unstable/gapped segments, late candle/settlement revisions and C15 label revocation. Hash or access-policy errors must not become an empty successful report.

### Frontend component/interaction

Test shared status/null/units components, table keyboard and filter behavior, every loading/error/locked state, form validation, chart selection deep links and stale-response cancellation. Test price/mark/provisional/closed-bar distinctions and exact tooltip values. Snapshot tests support visual regression; they are not proof of financial correctness.

### Browser E2E against real services

Use [Playwright](https://playwright.dev/docs/intro) with the real web service and real synthetic domain stores. Keep transport mocks only at external boundaries. Browser assertions read the same authoritative artifacts as the Python fixture. Retain screenshots/traces/logs and the source/build IDs on failure.

| ID | Scenario | Required result |
| --- | --- | --- |
| UI-E01 | Open empty/missing-source workspace | Honest setup state; no implicit DB creation, network collection or zero-PnL success |
| UI-E02 | Load raw C01–C15 fixture | Correct workspace/mode/source identity; C14/C15 reports discoverable |
| UI-E03 | Select an admitted signal | Correct instrument/timeframe and actual OHLCV; original levels and fill markers; exact ledger/evidence links |
| UI-E04 | Inspect capital-rejected candidate | Rejection reasons and independent outcome visible; funded wallet unaffected |
| UI-E05 | Advance decision-as-of cursor | No future feature, publication, delivery or matured outcome; revealing full tail switches mode explicitly |
| UI-E06 | Generic quote after a closed candle | Quote updates its own line/label; closed OHLCV remains unchanged |
| UI-E07 | Gapped or revised bar/unknown funding | Gaps/unresolved states persist; no fabricated smooth line, zero funding or win classification |
| UI-E08 | Portfolio/net reconciliation | Source cash/equity/fees/funding/net match exact producer values; independent rows never summed into wallet |
| UI-E09 | Switch symbol/run during slow request | Old response/event cannot paint the new context; selection and cleanup correct |
| UI-E10 | Disconnect/reconnect, duplicates and cursor gap | Bounded reconnect, no duplicate rows/lost controls, explicit snapshot resync, stale source badge independent of socket |
| UI-E11 | Locked final holdout | API, chart, preview, search, comparison and export all refuse protected evidence; explicit allowed access is audited |
| UI-E12 | Research compatibility and undefined metric | Invalid overlay rejected; null Sharpe/ratio/calibration stays explained; counts/populations accurate |
| UI-E13 | C15 insufficient/degraded/revoked evidence | Exact fixed-review state/reasons; old report unchanged; mature exports exclude revoked/unknown labels |
| UI-E14 | C15 pause + crashed acknowledgment | Exact existing C14 pause recovered, pending notices suppressed, paper book continues, no auto-resume/duplicate pause |
| UI-E15 | Delivery ambiguity/lease expiry | Cannot blind resend; state/proof/ID requirements preserved; acceptance never becomes a user fill |
| UI-E16 | Duplicate click/stale action/two clients | Idempotent result or explicit CAS conflict; no duplicate process/job/holdout operation |
| UI-E17 | Worker interruption/browser refresh | Job persists, partial outputs honest, completed domain artifacts retained, no fake resumability |
| UI-E18 | Unauthorized/malicious requests and exports | Operator gates, origin/CSRF, path/code limits, escaped content and secret masking hold |
| UI-E19 | Keyboard/mobile/reduced-motion | Core investigation and approved actions remain usable; focus/labels/tables/controls accessible |
| UI-E20 | Large bounded history and two charts | Reference performance/retention targets met, no resource leaks, sampling disclosed and metrics unchanged |

Browser E2E begins at D1 with UI-E01/UI-E02 and grows with each slice. Do not defer the first browser test until D8. Automated tests never contact real Telegram or submit exchange orders.

## 5. Manual acceptance script

On the declared desktop and mobile widths:

1. Open the local workspace; identify mode, clock, source freshness and any missing input without reading raw JSON.
2. Select BTC/ETH and supported timeframes; pan/zoom, toggle one feature, inspect warm-up/gaps and switch price basis. Confirm a live quote is not a final candle.
3. Open a candidate from the feed, inspect its exact chart/decision/cost/risk path, and move to a rejected opportunity without losing context.
4. Step the original decision view to entry and then outcome knowledge; confirm future information is initially hidden and retrospective mode is obvious.
5. Inspect paper cash/equity/open risk and trace a fee/funding amount to the ledger. Locate unresolved quantities/marks when present.
6. Open a backtest and walk-forward experiment; identify independent versus capital results, source window, sample coverage, frozen protocol and holdout access state.
7. Compare compatible runs and try an incompatible comparison; inspect a development heatmap without accidentally modifying/consuming an experiment.
8. Review a C15 insufficient-evidence report, its recorded publication times, a label revision and the raw replay receipt. Export one pinned track-qualified dataset.
9. Disconnect/reconnect the service in a test workspace; confirm stale indicators, state recovery, historical rows and unchanged pinned charts.
10. In an isolated paper session, exercise authorized pause/recover/reconcile/resume and verify the audit consequences. Notification pause must not pretend to close paper positions.
11. Navigate core tasks with keyboard only, use compact/mobile layout and inspect chart data through its accessible table.
12. Confirm no real credentials leak through developer-visible errors, exports, URLs or logs, and that no page load sends a notification or starts a process.

Record issues against page/chart/API/phase IDs and retain screenshots plus the exact fixture/build identity. A visual sign-off is separate from mathematical and domain-test acceptance.

## 6. Performance and operational acceptance

Targets are provisional until D0 establishes the machine/corpus. Suggested initial budgets: useful cached page content within roughly two seconds locally; lightweight list/filter interactions typically under 200ms after data is loaded; tail visual updates coalesced around 4Hz where appropriate; paginated default 50–100 table rows and bounded requests; one heavy job at a time. These are proposed goals, not measurements or domain timing promises.

Measure cold/warm API latency, source verification backlog, chart mount/update/zoom cost, tab memory over repeated navigation, event reconnect/resync time, file/DB growth and worker interference with paper-loop deadlines. Expose lag rather than disabling verification to make a latency target look good.

Release acceptance requires: all contracted screens/states covered, core tests appropriate to any source changes passing, real-service browser E2E passing, manual visual/accessibility review, no unintended domain writes/external sends, producer/schema compatibility documented, and explicit remaining throughput/backup/supervision limits.

## 7. Deferred extensions and review decisions

| Extension | Why deferred / completion gate |
| --- | --- |
| Arbitrary S/R, SMC/FVG/order blocks, new indicators/timeframes | Needs authoritative C03/C04/C05 definitions, causal data, tests and incremental value; a toggle is insufficient |
| Order book depth heatmap, footprint, trade delta/order flow | Current top-of-book/aggregate trade data is not full depth; requires recording/reconstruction/sequence coverage and validated projections |
| Actual account/fill reconciliation and order execution | Separate authenticated account contracts, permissions, risk/E2E and explicit request; no frontend shortcut |
| Advanced drift/calibration and automatic replacement | C15/C12 research extension, adequate prospective data, counted experiments; current reviews never retrain automatically |
| Multi-session/model statistical aggregation | Explicit ownership, aligned cohorts and a shared sequential/trial budget; cannot reset an alarm by combining charts |
| Arbitrary dashboard builder/four-chart grids | Finish curated useful workflows and benchmark two charts before expanding complexity |
| External backtest JSON analyser | Optional TBot-like convenience after strict schema, origin, isolation and unverified-evidence labels |
| Cloud/multi-user/RBAC/remote notifications | Authentication/TLS/deployment/tenant/source isolation and incident policy; not required for the first local product |
| Native mobile app or desktop packaging | Responsive browser first; package only if a measured workflow need remains |
| Browser push/audio and custom price alerts | Explicit opt-in/destination/lifecycle policy, no unsolicited permissions; not trading-engine evidence |
| Full strategy visual builder | First expose immutable existing recipes and audited clone-to-draft; arbitrary execution creates an unreviewed engine |

Current implementation and next acceptance work are tracked in [DASHBOARD_IMPLEMENTATION.md](DASHBOARD_IMPLEMENTATION.md). Use that status alongside these original target phases; do not treat the historical approval gate as a request for renewed permission.
