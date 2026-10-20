# Dashboard implementation and acceptance

**21 October 2026 — working local dashboard implemented.** The original dashboard documents remain the larger product/design specification. This file records the shipped behavior and the remaining interactions precisely; it does not assert that every D8 target has passed production acceptance. Startup, process ownership, recovery and source configuration are in [DASHBOARD_RUNBOOK.md](DASHBOARD_RUNBOOK.md).

## Architecture and delivered scope

The user-approved layout is one repository with sibling **`backend/` and `frontend/`**. Existing shared domain code remains in `tradee/`, keeping its producer hash unchanged:

`894c8f30c2a5290b2f59b6572496be7f816622395ade9fe0b7571b83cde590df`

Models can resolve from the C10 registry or C12’s verified frozen final-training artifact without republishing/copying a model. Explicit first backfill can initialize C02 after C01 registration; viewer requests cannot.

The Python web package and UI changes are excluded from that trading-core hash and have a separate API build hash. GET requests use existing-store adapters with SQLite `mode=ro` and `query_only`, reuse domain hash/inventory/audit verification, and never invoke initializing domain constructors. New UI command/invalidation/runner state lives in a distinct SQLite file. Core changes remain subject to new source-qualified research fixtures rather than compatibility bypasses.

| Phase | Implemented behavior | Remaining target work |
| --- | --- | --- |
| D0 | Local architecture, exact dependency locks, dark design system, semantic data/availability contracts, measured reference fixture | Broader source-volume and continuous-operation budgets |
| D1 | Profile bootstrap, honest missing/error states, Overview/Signals/source views, shared evidence disclosure, viewer/operator boundary | Field-specific generated DTO/OpenAPI schemas beyond core-validated command documents; richer universal cross-artifact navigation |
| D2 | Actual closed OHLCV/volume, one pinned C03/C11 feature source, stable overlays, original decision snapshots, frozen trade levels, rejection history, separate quote/funding context, signal-to-chart investigation | Bar-click source inspector, separately selectable indicator lower panes and every individual fill/partial/exit marker; source-event/bar replay beyond recorded C14 cycles |
| D3 | C13 paper equity/cash/drawdown, exact summaries, risk versus limits, capital rejections, stress scenarios, funded trades, mature-R distribution | Interactive allocation-contributor drilldowns and linked ledger brushing |
| D4 | C12 experiment/fold/utility evidence, conditional registered-parameter heatmap, source-qualified independent runs/comparison, C10 cohort bounds and conditional stored scoring diagnostics | More convenient guided experiment/session forms and click-to-filter scientific plots; no new statistical tests are inferred from filters |
| D5 | Durable bounded SSE invalidation/replay/resync, verified snapshot refetch, polling fallback, journal preservation, explicit service/feed distinction | Granular incremental chart patches, continuously measured live stream latency/backpressure and large-source incremental verification |
| D6 | C15 report vintages, fixed review evidence/absent bounds, separate track maturity, forecast/label diagnostics; C01 rules/C02 coverage calendar/gaps/collector receipts | Large-history retention and continuously supervised network/host incidents |
| D7 | Durable idempotent jobs, worker heartbeat/ownership, bounded subprocess work, queue cancellation/interruption, public data jobs, core-validated research documents, guarded holdout, create→monitor→explicit runner, bounded owned paper runners, pause/resume/recovery/reconciliation | Browser-managed streaming collector lifecycle, hard OS CPU/memory limits, deployment supervisor and crash/disk/backup drills under real load |
| D8 | Responsive desktop/mobile, keyboard controls and source alternatives, bookmarkable workspace/session/market/cursor state, two synchronized market time ranges, resource disposal/viewport preservation, JSON/CSV exports, actual-service browser tests and local runbook | Crosshair synchronization, per-chart PNG/CSV export, richer saved-layout presets, multi-browser/screen-reader certification and full production/real-feed acceptance |

All eight workflow areas plus Settings are usable. The broader plan's unfinished interactions are retained above and in the upgrade register; a chart's source may also be unavailable without constituting a software error.

## Chart implementation matrix

Exact strings and source receipts remain inspectable even when a chart uses numeric coordinates. Chart axes are UTC; table times use the selected timezone. Empty/insufficient/missing observations are never silently changed into zero. No chart supplies a new trading/risk/statistical decision.

| ID | Delivered view | Availability / limits |
| --- | --- | --- |
| CH01 | Actual C02 closed OHLCV, Markets and signal context | Only supported C03 intervals; complete-minute aggregation through core |
| CH02 | Matched base-asset volume pane | Same candle vintage; no synthetic zero bars |
| CH03 | Stable EMA20/50 and session VWAP when materialized; frozen recorded stop/target/partial levels in single-trade context | One manifest at a time; invalid feature points break lines; original snapshot JSON remains primary; more lower panes/markers remain |
| CH04 | Recorded quote-spread bps series, exact bid/ask/size and observed delay evidence | Book-top observations are not depth or actual fills |
| CH05 | Signal event/source-usable timeline and exact C14 recording clocks | Telegram attempt clocks only where present; richer event replay remains |
| CH06 | C13 funded equity/cash/unrealized and drawdown | Decimal display transform starts from initial capital; producer metrics remain authoritative |
| CH07 | Current gross/risk/collateral/beta/stress values versus frozen limits, stress chart | Exact policy/account inspection; richer contributing-group interactions remain |
| CH08 | C11 independent regular-sample PnL | Never account equity/percentage return |
| CH09 | Fixed-bin mature net-R distribution and underlying rows | Mature and omitted denominators shown; MFE/MAE retained as source diagnostics |
| CH10 | Core gross/fee/known-funding attribution and exact trade ledgers/cost receipts | Fees remain one expense; shortfall is never subtracted again; animated cumulative bridge remains a presentation extension |
| CH11 | Train/test fold ownership timeline and exact purge/cutoff contract | Final holdout outcomes stay gated |
| CH12 | Stored research utility and interval endpoints, fold utilities/coverage | Exact estimand disclosed; no invented per-fold bounds |
| CH13 | Registered final-selection two-parameter utility heatmap | Only when actual scored variants have two axes and unambiguous cells; fixed-hypothesis fixture correctly shows unavailable |
| CH14 | Compatible independent-run PnL comparison and contract differences | Dataset/window/cost/execution/producer/tested quantities must match for overlay; no resizing a tested execution path |
| CH15 | C10 cohort mean/bounds plus exact coverage table | Conditional mature simulated-fill estimand, no confidence score |
| CH16 | Stored C10 reliability/error diagnostics, if an evaluation artifact exists | No evaluation in the reference fixture; missing diagnostic is explicit; empirical frequency is not calibrated probability |
| CH17 | C15 fixed-review means/stored bounds and exact reasons | Insufficient reviews keep empty bounds |
| CH18 | Frozen C10 forecast versus matched mature paper net R, separated tracks | Descriptive matched comparison; no pooling/new significance |
| CH19 | Measured paper-cycle processing-ms series and delivery receipts | No invented human reaction/fill latency or promised transport SLA |
| CH20 | C02 UTC-day expected/finalized/missing-minute coverage heatmap | Candle coverage only; trade/quote completeness not inferred |
| CH21 | Recorded operational audit-state history | Browser connectivity and market age remain separate |
| CH22 | Published funding-rate series and exact forecast/settled cash-flow ledger inspection | Forecast rates, next estimates and settled USDT are kept separate; matched forecast-error chart requires matching evidence |
| CH23 | Candidate/fill/mature/unresolved coverage and independent/funded counts | Exact scope and denominators retained |
| CH24 | Curated dataset/model/deployment/simulation/portfolio/cycle lineage with copyable hashes | Accessible ordered inspector; arbitrary graph traversal and cyclic expansions remain future work |

## Service and control contracts

- Responses use `{data, meta}` with workspace, synthetic scope, recording time, core build and API build. Domain financial values remain decimal strings. Unsupported/missing/corrupt sources return structured errors; locked evidence returns 423; stale controls return 409.
- Public query groups: bootstrap/health; source/session overview; market/datasets/quality/instruments; signal/portfolio/analytics; research/runs/models; monitors; artifacts/exports; jobs/worker/runners; SSE invalidations. See `/api/openapi.json` for concrete paths and source code's `COMMAND_FIELDS` for exact operator fields.
- All mutations require the configured bearer token and permitted local origin/host. Commands reject extra fields, use bounded inputs, reuse the existing core config validators and require idempotency keys. Queued acceptance is distinct from core completion.
- Resume/pause use C14 atomic revision and audit-head comparison. Other operator actions check the selected current head before core delegation; their own claim/audit/reconciliation semantics remain intact. Uncoordinated CLI mutation races are an operational limitation; no distributed lock claim is made.
- Final evidence is protected by both registered run ownership and overlapping raw-data intervals, including generic artifact/chart/export paths. The viewer is not an adversarial custody mechanism against someone who already controls the underlying SQLite files.
- Cursor views filter C14 cycles/events using actual recording time as well as logical event time. Navigation exposes future **clock positions**, not future payloads. C15 report cursor filtering uses observed time. Research/Data archive views require leaving the session replay explicitly.
- Market requests cap visible bars at 2,000 (default 500), input replay at 250,000 events; catalog reads are bounded at 5,000 rows and response documents at 50 MB. Tables page 50 rows. This is a bounded local research corpus, not an unlimited exchange data warehouse.
- Owned runners use separate reservations/file locks and preserve future-start and outcome-tail semantics. They have no Telegram/exchange-send path. Queue work and paper runners are separate from public streaming collectors.

## Verification record

The final acceptance command outputs are retained locally under `data/dashboard_verification/` and ignored browser test outputs. The tested reference is current-source synthetic raw-input C01–C15 evidence, not hand-authored frontend mock JSON.

- **787 existing core tests passed** in 544.196 seconds; unchanged trading-core hash above.
- **44 backend tests** cover readonly byte preservation, foreign/missing/corrupt sources, dataset membership/raw integrity, causal cutoffs, locks on every evidence surface, exact paper/independent reconciliation, pagination, bearer/origin/host checks, queue idempotency/cancellation, stale controls, core execution, feature materialization, immutable snapshots, worker/runner ownership and recovery, future-start/outcome-tail lifecycle and report cursors.
- **11 frontend unit tests passed** and cover financial missing/zero/fraction formatting, timezone, query encoding, protected-source errors, envelopes, registered parameter scores and compatible-run/gap-preserving comparison.
- **10 Chromium E2E tests passed** against a real disposable API and worker: wallet reconciliation and synthetic labels, actual candles/incomplete buckets, two-chart mounting, rejected-signal detail/source snapshots/CSV, causal cursor/disabled controls, funded trades, experiment/fold/run/model inspection, immutable forward vintages, dataset quality, queued revision-checked resume through the worker, token clearing and all routes at mobile width.
- `npm run build` typechecks and builds the production bundle. Dependency audit reports no known npm vulnerabilities at verification time. This is not a general security audit or a real-feed load test.

Measured local ASGI reference timings (three requests per endpoint, Python 3.13.15/macOS arm64): market median **7.34 ms**, Overview median **22.76 ms**, session median **20.99 ms**, portfolio median **20.02 ms**, research catalog median **22.42 ms**, C11 run catalog median **121.83 ms**, forward report median **18.52 ms**. Responses ranged from 16 KB to 256 KB. These exclude browser/network/production concurrency; they establish a small-corpus baseline, not an SLA. Exact source/build-qualified measurements: `data/dashboard_verification/api_benchmark.json`.

Manual visual checks used the real local preview and browser-generated desktop/mobile screenshots. The acceptance matrix does not claim screen-reader certification, Windows ownership, months of representative forward validation, all network/disk fault drills, profitable signals or live execution approval.
