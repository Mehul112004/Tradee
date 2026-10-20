# Dashboard API, data and runtime plan

Implementation update, **21 October 2026**: the local API is in `backend/tradee_web/`, with `frontend/` as a sibling. Concrete routes, current limits and remaining service work are recorded in [implementation status](DASHBOARD_IMPLEMENTATION.md); operation and source profiles are in [the runbook](DASHBOARD_RUNBOOK.md).

## 1. Recommended architecture

Use a local, single-user web application with three explicit responsibilities:

1. **React/TypeScript browser application:** presentation, navigation, chart interaction and view preferences.
2. **Python web adapter/service:** bounded typed read projections, evidence access policy, event delivery, authenticated command admission and UI audit.
3. **Separate worker/runner processes:** existing domain operations and collectors plus a small persistent job coordinator when that phase is approved. CPU-heavy research never executes inside an HTTP request or the browser.

Existing C01–C15 engines/stores own trading, research and monitoring truth. No duplicate browser indicator, risk, exit or bootstrap implementation. The browser never opens SQLite or connects to Binance/Telegram directly.

### Proposed stack and alternatives

| Concern | Recommendation | Reason / tradeoff |
| --- | --- | --- |
| UI | React + TypeScript + Vite, React Router | Familiar TBot stack; a local SPA needs no SEO/SSR infrastructure. We explicitly own routing/data orchestration |
| Server state | TanStack Query over a generated/validated API client | Key immutable data by source IDs; live resources by scope/revision. Avoid hand-maintaining every list in independent effects |
| View state | URL state plus small local preferences store | No large global state framework until actual interaction complexity requires it |
| Financial charts | Lightweight Charts | Price/candle/pane/marker focus; attribution included |
| Analytical plots | Modular Apache ECharts imports | Intervals, heatmaps, distributions and linked diagnostics; lazy-load nonmarket chart code |
| Components/styles | Accessible reusable primitives, CSS design tokens; Tailwind utilities optional | A consistent design system matters more than picking a theme package. Avoid multiple competing component systems |
| API | FastAPI + explicit Pydantic boundary DTOs | Python integration and OpenAPI; core dataclasses/validators remain authoritative |
| Streaming | SSE for service→browser changes; HTTP for commands | Fits mainly server-originated UI updates. Existing Binance WebSockets remain in C02 |
| Persistence | Existing separate domain SQLite DBs + new dedicated UI/job store | Preserve domain schemas. New store holds preferences, request/job audit, event cursor/index metadata—not authoritative trade results |
| Worker | One persistent local coordinator and bounded separate worker processes initially | No Redis/Celery requirement for a single host; add a distributed queue only after demonstrated need |
| Verification | Existing Python tests + API contract tests + frontend component tests + Playwright | Real browser/core E2E in addition to mocks and visual checks |

These are proposed packages, not a lockfile. At implementation, choose mutually compatible stable versions, verify Python 3.13/Node requirements and licenses, commit exact dependency locks, and record browser targets. Do not copy TBot's version ranges blindly.

Official references checked 21 October 2026: [React's build-tool guidance](https://react.dev/learn/build-a-react-app-from-scratch) describes the tradeoffs of owning an SPA stack; [Vite](https://vite.dev/guide/) documents the build/dev tool; [TanStack Query](https://tanstack.com/query/latest/docs/framework/react/overview) documents server-state caching. [FastAPI features](https://fastapi.tiangolo.com/features/) support typed/OpenAPI boundaries. Its [background-task caveat](https://fastapi.tiangolo.com/tutorial/background-tasks/#caveat) distinguishes heavy computation from small in-process tasks; the durable worker/recovery rules below are our architecture, not a guarantee supplied by the framework.

## 2. Source ownership and required adapters

| Source / existing interface | UI consumes | New work required before use |
| --- | --- | --- |
| C01 Registry universe/history/version/snapshot/health | Instrument identity, historical rules, eligibility and metadata age | Read-only discovery/list projection and precise historical binding |
| C02 dataset/replay/view/asof/quality, collector log | Candle/quote/mark/funding evidence, quality, ingestion health | Bounded instrument/time-range queries, timeframe aggregation contract, dataset catalog and quality series |
| C03 FeatureStore snapshot/manifest/summary; FeatureEngine | Original feature values/definition/readiness/lineage | Persisted feature-series lookup or explicit bounded reconstruction job; never implicit expensive GET computation |
| C06 reports/store | Funding projection, settlements, coverage and assumptions | Human-readable cash-flow/calendar projection, no horizon conflation |
| C07 execution records | Fill model, costs, freshness and rejection gates | Display DTO preserving exact quantities/prices/rates and source proof |
| C08 candidate inventory / C09 ledger/outcomes | Candidate definition, policy levels and lifecycle | Stable lookup across candidate/trade/signal identities and paginated decision timeline |
| C10 models/estimates/frozen evaluations | Conditional mean/interval, coverage and reliability/error diagnostics | Model/cohort discovery, bounded prediction/outcome joins and field-specific unavailable reasons |
| C11 SimulationStore manifest/report/records/summary | Independent historical results and regular PnL | Catalog/pagination, trade/candle links, chart-series projection and evidence compatibility view |
| C12 ResearchStore manifest/jobs/events/decision/release/ledger | Experiment ownership, trial budgets, chronological windows and holdout state | Access policy enforced before any projection/prefetch/export; permitted discovery and controlled command adapter |
| C13 PortfolioStore manifest/report/records/summary/account | Funded trades, regular equity, risk and compatibility | Position/history/risk projections and compared-run compatibility checks |
| C14 SignalStore evidence/session/signals/signal/events/status | Consistent paper snapshot, source/recording times, delivery and controls | Paged discovery/read views and scoped event projection; preserve revision/audit CAS for mutations |
| C15 MonitorStore head/events/artifact; ForwardMonitor export | Forward rows, fixed reviews, incidents, labels/revisions and replay | Monitor/report discovery, filtered populations and durable report links; no automatic research import |

**Important prerequisite:** current store constructors commonly create directories/tables or set SQLite pragmas. Calling a constructor on a GET request is not a sufficient read-only design. Implement explicit existing-store/schema checks and read-only open paths, or a carefully tested adapter, before exposing them through the web service. Missing stores appear as “not configured/no evidence”; the dashboard must not initialize an empty trading store silently.

Some catalogs/listing, ranged candles, indicator history, risk history, chart sampling, durable UI jobs and resumable UI events **do not exist as ready-made HTTP interfaces today**. They are implementation tasks, not configuration switches. Prefer new public domain read methods where needed; do not make the frontend depend on private SQL layouts or private Python methods.

## 3. Data envelopes, precision and consistent reads

### Common response metadata

Every response includes a versioned envelope with:

- API schema version, request ID, server time and resource kind.
- Core producer code/Python where relevant, API build and frontend build compatibility.
- Workspace/source profile and explicit historical/shadow/paper scope.
- Instrument/run/session/monitor identities and immutable evidence references.
- Source cutoff, actual recording/verification time, source revision/audit head, and availability basis.
- Verification, freshness, completeness and unavailable reasons, independently represented.
- Cursor pagination and series aggregation/sampling metadata when applicable.

Exact amounts, fees, prices, quantities and rates are decimal strings. Times are integer UTC milliseconds; chart-library coordinate conversion happens at the display boundary. IDs/hashes are opaque strings. Null carries a reason/status, not an invitation to substitute zero. Fractions, percentages, bps, USDT and R are explicit units.

Expose fixed vocabularies for domain state. Candidate/paper lifecycle, delivery state, monitoring decision, source quality, job state and API transport status are separate fields. New server enum values produce a safe labelled fallback and client compatibility warning, not an incorrectly green badge.

### Read consistency

- Within C14, use the consistent verified evidence/session transaction, not separate uncorrelated head/signal/outbox reads.
- Across stores there is no single magical SQLite transaction. Anchor to an immutable report/deployment and its referenced source IDs; return a **source-version vector** and explain any resources still updating.
- A page advances to a new version atomically at its chosen context boundary. Avoid a current wallet header paired with yesterday's positions, or a new candle dataset with an old feature overlay.
- Verify artifact hashes/inventories using domain contracts. Full validation can be expensive: build bounded verified projections, cache only immutable/context-qualified responses, and display when/how evidence was checked. Cache hits cannot pretend corrupted/incompatible sources remain newly verified.
- Opening raw evidence, exports and authorizing commands rechecks the relevant current integrity/ownership gates. Index/cache tables are rebuildable conveniences, not independent truth.
- Disclose stale last-known projections during revalidation. No expensive verification backlog is hidden behind a green “live” socket.

## 4. Proposed HTTP surface

Paths below are design contracts to refine against DTOs; none exist yet. Use `/api/v1`, server-side bounded filters, allowlisted sort keys and cursor pagination rather than loading complete histories.

| Group | Example reads | Purpose / constraints |
| --- | --- | --- |
| Bootstrap/context | `/bootstrap`, `/capabilities`, `/health`, `/workspaces/{id}` | Available sources, permissions, modes, versions and initial cursors; no side effects |
| Instruments | `/instruments`, `/instruments/{id}/rules`, `/instruments/{id}/history` | C01 scope and correct rule vintage |
| Market | `/market/candles`, `/market/quotes`, `/market/features` | Explicit instrument/timeframe/range/as-of or dataset; bounded series and source metadata |
| Data | `/datasets`, `/datasets/{hash}`, `/datasets/{hash}/quality` | Immutable snapshots and coverage; browse without auto-import |
| Signals | `/sessions/{id}/signals`, `/signals/{id}`, `/signals/{id}/timeline` | Filtered lifecycle and evidence; separate delivery |
| Portfolio | `/sessions/{id}/portfolio`, `/portfolio-runs/{hash}/series`, `/portfolio-runs/{hash}/allocations` | C13 book, chart samples and admitted/rejected offers |
| Simulations | `/simulation-runs`, `/simulation-runs/{hash}`, `/simulation-runs/{hash}/trades` | C11 independent evidence; underlying C12 ownership gate |
| Research | `/experiments`, `/experiments/{hash}`, `/experiments/{hash}/folds`, `/models/{hash}` | Only permitted experiment/fold/model evidence; locked metadata safe for listing |
| Forward | `/monitors`, `/monitors/{id}/reports`, `/forward-reports/{hash}`, `/forward-reports/{hash}/outcomes` | Frozen reports, track filters, maturity, revisions and reviews |
| Operations | `/sessions`, `/sessions/{id}`, `/sessions/{id}/delivery`, `/jobs`, `/audit` | Frozen state, paginated audit and runtime/job health |
| Evidence/export | `/evidence/{kind}/{hash}`, `/exports/{id}` | Strict kind/ownership authorization; bounded records/downloads, no arbitrary paths |
| Events | `/events` | One authenticated durable UI event stream with resource/context cursors |

For expensive history/chart reconstruction, return a clear `not_materialized` capability and an optional explicit job request—not a blocking GET or a surprise write.

### Proposed command surface, introduced only in the control phases

| Command | Validation / consequence |
| --- | --- |
| Create research/data/reconstruction job | Allowlisted job kind and typed inputs, validated source/config/budget, idempotency key and operator scope |
| Register experiment / open holdout | Core C12 accounting/access operation with reason and disclosure; never implemented as read convenience |
| Create C14 deployment + register C15 | Frozen source/model/recipe/spec/monitor validation and exact ordering before first tick; partial completion is inspectable/recoverable |
| Start/stop an owned runner | Coordinator ownership, existing deployment/monitor, producer compatibility and explicit bounded runtime; no duplicate process |
| Pause/resume C14 | Expected revision **and audit head**, reason, target and consequences; resume stays explicit and cannot revive stale outbox records |
| Apply C15 pause request | Current source-qualified report or recovery of the exact previously applied event; preserve cross-store recovery semantics |
| Recover delivery leases | Delegate to C14; elapsed in-flight work becomes ambiguous rather than presumed unsent |
| Reconcile ambiguity | Explicit proof, sent/not-sent decision and accepted message ID where required; never blind resend |
| Reconcile raw forward replay / export | Bounded core operation with source proof; export is not a training/promotion action |

Suggested command response: request/operation ID, accepted/rejected/conflict state, expected/actual revision, audit reference, affected target and next safe read. Use 409 for stale state, 422 for invalid domain input, 403 for permission/ownership, and structured redacted error codes. Worker acceptance (202) is not job success. A retry cannot repeat an irreversible holdout exposure or external send.

## 5. Live updates and reconnect behavior

SSE is a proposed browser transport, not a new Binance data collector. The [WHATWG server-sent-events specification](https://html.spec.whatwg.org/multipage/server-sent-events.html#server-sent-events) defines event IDs and reconnection behavior; durable retention, source-version reconciliation and idempotent reducers still require our implementation.

One browser stream owns events for the current workspace; components subscribe through a shared client. Event schema includes ID/sequence, type/version, workspace/resource identity, source revision, as-of/recorded time, immutable reference and correlation/request ID. Server and client event registries are contract-tested together.

Required event families: source/quality update, provisional/final bar, candidate/paper-cycle change, outbox/control transition, job progress/completion, forward-report publication, integrity/compatibility incident and heartbeat. Preserve source-domain IDs instead of translating everything into generic “signal confirmed”.

Sequence:

1. Fetch a versioned initial snapshot and matching event cursor through a race-safe snapshot/catch-up handshake.
2. Subscribe after that cursor. Deduplicate by event ID/resource revision.
3. Apply permitted incremental updates; invalidate/reload affected server-state queries when a complete newer snapshot is required.
4. On reconnect, resume from the last durable ID with bounded backoff/jitter; cancel old timers/connections and reject old-scope responses.
5. On retention gap, cursor mismatch, incompatible schema or overflow, send/handle an explicit resync event and refetch a consistent snapshot.
6. Display stream connectivity independently from each source's health/freshness. Age uses server clock context, not blind trust in a laptop clock.

Use bounded per-client buffers and backpressure. Quote/provisional display ticks can be coalesced; final bars, ledger/position changes, outbox results, research access and operator controls cannot disappear semantically. Background tabs reduce optional visual updates without stopping recording or losing control history. A paused/pinned replay view does not absorb latest-market events into its historical dataset.

The UI service may initially poll persisted domain heads at a bounded cadence and project changes into its durable event log. That cadence and lag are visible. Do not claim exchange-tick latency from a polled adapter. If durable event projection is not ready, start with clearly labelled polling rather than an unreliable “LIVE” animation.

## 6. Jobs and process ownership

Persist a new UI request/job record separately from existing C12 counted jobs. A convenient UI job never collapses several variants into one uncounted research trial.

State machine: queued → validating → running → succeeded / failed / interrupted, with cancel-requested as a control request and cancelled-before-start where valid. Report current named phase and completed/total work only when the producer actually exposes it. No synthetic progress percentage.

Initial bounds: one heavy research/reconstruction worker at a time on the local reference host; separate collector/paper-runner processes have protected ownership and resource limits. Configure runtime/event/byte/work budgets from the existing component contracts, plus API response/job/queue bounds. Benchmark before raising concurrency.

Idempotency key binds operator, command kind, input/config/source hashes and intended target. Conflicting bodies under the same key fail. Record every accepted command and resulting domain artifact/event reference. A crash after a domain commit but before UI acknowledgment must recover by correlation/idempotent source result, not rerun blindly.

Cancellation cannot undo consumed holdout access, old audit events or external HTTP uncertainty. Without a domain checkpoint/cooperative stop point, report interruption honestly and retain only atomically completed outputs. Do not promise resumability that C11/C12/C14 do not implement.

Development reload and opening a browser must not start collectors/runners automatically. Production process supervision, restart policy, backup/restore and ownership are separate explicit delivery tasks. A UI “stop runner” operation is distinct from pausing notifications; the latter should keep the hypothetical paper outcome measurement running.

## 7. Security and research access

Default to loopback and a single local workspace. Enforce host/origin allowlists, same-origin authenticated requests and operator authorization on the API, not only hidden buttons. Mutation requests need CSRF/replay protection as appropriate to the selected cookie/session design. No broad credentialed CORS wildcard. Remote access is a later deliberate deployment with TLS, login, roles and tested controls.

Viewer/operator scopes are capabilities: read permitted artifacts versus submit approved commands. The first phase can expose a read-only viewer; operator controls wait for their acceptance tests. A malicious page or another unauthenticated local client cannot use the browser service to send Telegram notices or open holdouts.

Keep Binance/Telegram secrets server-side, env/credential mechanism only. Never return tokens in DTOs, errors, logs, query strings, local storage, screenshots or exports. Mask destination identifiers in ordinary UI and bound/escape proof text. No arbitrary server file path, SQL, Python code or shell command is accepted from a request.

Holdout restrictions must cover list summaries, counts derived from protected results, comparisons, heatmaps, generic artifact lookup, search/autocomplete, hover prefetch, exports and worker logs. Raw public market history cannot be made intrinsically unseen; if a user inspects a reserved interval, disclose/record contamination under the research protocol rather than claiming an untouched holdout afterward. The UI improves enforcement within this application; it is not cryptographic custody over all external information.

Treat optional external file imports as untrusted data: schema/version/size validation, no embedded executable content, isolated unverified namespace, no automatic promotion or merging. CSV export protects formula-like fields; rendered logs/notes do not become HTML.

## 8. Proposed files and compatibility policy

The following tree is a proposal only; none of these directories/files are created in this task:

```text
frontend/
  package.json + lockfile + build/test configuration
  src/app/                  routes, shell, providers, errors
  src/design-system/        tokens, accessible primitives, table/status patterns
  src/api/                  generated DTO client, query keys, errors
  src/events/               shared stream, reducer, reconnect/resync
  src/charts/               wrappers, series adapters, evidence legends, exports
  src/features/             overview, markets, signals, portfolio,
                            research, forward, data, operations, settings
  src/components/evidence/  shared explanation/timeline/artifact inspector
  tests/                    component, interaction and visual tests
backend/tradee_web/
  app.py, config.py         optional API package; startup without auto runners
  dto/                     versioned boundary schemas and capabilities
  adapters/                C01–C15 read projections; no duplicate domain engine
  routes/                  read endpoints and separately authorized commands
  policy/                  source/holdout access and authorization
  events/                  durable cursor projection and SSE transport
  jobs/                    persistent requests, worker/runner ownership/recovery
  store.py                 separate UI/job metadata database
tests/web/                 contract, source-integrity, command and security tests
tests/browser/             real-service Playwright E2E and retained artifacts
configs/web.example.*      explicit local sources, limits and capabilities
```

Propose keeping presentation/API packaging separate from `tradee/`, with separately recorded API/UI build hashes. The existing `code_hash()` hashes every Python source under `tradee/`; core read-open/list/refactor changes therefore change the frozen research producer. Do not weaken or spoof that gate to ease frontend development. Core changes require current-source regression fixtures and the appropriate new research/deployment lineage. An adapter being outside that digest does not make it trustworthy automatically: its own version/schema, validation and command mapping are audited and tested.

The current project has no web dependencies; add an optional web dependency group only during an approved phase. Keep CLI-only operation available. SQLite domain schema changes are not assumed; if a needed change is unavoidable, define the migration and source compatibility before implementation.

## 9. First contract decisions to freeze

Before coding the first slice, finalize: eight-area navigation; viewer/operator boundary; configured source-profile format; a common evidence/unknown-state envelope; exact ranged-candle and feature-series semantics; snapshot/event-cursor handshake; holdout access map; producer/version policy; and reference hardware/corpus for performance targets.

Default delivery begins read-only with existing retained C14/C15 artifacts and actual pinned candles. Subsequent phases add live projections and authorized commands. Nothing in this architecture enables account orders or bypasses the existing paper-only gates.
