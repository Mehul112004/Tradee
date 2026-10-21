# Tradee dashboard: local operation

Implemented 21 October 2026. Run everything from the repository root unless a command says otherwise. The dashboard is an interface to the existing C01–C15 core; its availability does not certify a strategy's profitability.

## Repository layout

```text
Tradee/
  backend/
    tradee_web/          FastAPI, read adapters, projections, operator jobs/runners
    tests/              API, source-integrity and operation tests
    requirements.lock   resolved Python web/test runtime
  frontend/
    src/                React + TypeScript screens and charts
    e2e/                Playwright tests against an actual API and worker
    package-lock.json   exact JavaScript dependency graph
  tradee/               shared existing trading core (source hash preserved)
  tests/                existing trading-core tests
  docs/                 categorized plans, component reports and runbooks
  scripts/serve_dashboard_e2e.py
  data/                 ignored local databases and verification outputs
```

Keeping `tradee/` in place preserves imports, existing CLI workflows and frozen research provenance. New backend web code stays in `backend/`; the React application stays in the sibling `frontend/`. Neither contains a second implementation of trading formulas.

## Install and open

Prerequisites: the dedicated `tradee` Conda environment, Python 3.13, Node **20.19+** (or a Vite-supported newer release), npm. The checked environment used Python 3.13.15, Node 20.19.5 and npm 10.8.2 on macOS arm64.

```sh
conda activate tradee
python -m pip install -r backend/requirements.lock
npm ci --prefix frontend
npm run build --prefix frontend
python -m backend.tradee_web
```

Open **http://127.0.0.1:8787**. The server binds loopback only and serves `frontend/dist/`, including direct links to client routes. API schema: `/api/openapi.json`. No database credentials or Binance keys are needed to view existing local artifacts or acquire public market data.

The default **Local recording** profile points at `data/c01.sqlite3` through `data/c15.sqlite3`. Empty sources stay empty: visiting a page does not create a registry, migrate a source or run a strategy. If retained verification artifacts exist, choose **Verification · synthetic** in the workspace selector. Those mechanically generated prices are engineering test evidence.

A separate development terminal can run `npm run dev --prefix frontend`. Vite listens on 127.0.0.1:5173 and proxies `/api` to 8787. Use the built same-origin server for acceptance checks.

## Source profiles

Copy `backend/profiles.example.json` to an ignored local configuration file. `root`, `state_path` and each optional `files` override resolve from the process working directory; absolute paths also work. Each component gets a distinct database. The UI state database must be separate from every source. Never point a profile at an untrusted database without reviewing its provenance.

```sh
python -m backend.tradee_web --config data/dashboard-profiles.json
python -m backend.tradee_web.worker --config data/dashboard-profiles.json
```

Use **the same configuration** in the API and worker. Paths are server-controlled and never accepted from a browser command. A single worker owns a given web-state file. Custom ports are useful for viewers; browser mutation origins are intentionally restricted to the shipped local origins. Change deployment configuration deliberately if introducing another origin; do not expose this local service remotely.

## Viewer and operator modes

Viewer mode is the default. To enable explicit operator requests, set `TRADEE_WEB_OPERATOR_TOKEN` in the repository-root `.env` or exported API process environment before starting it, using a long random value from your password manager. Exported values take precedence. Paste that same value into **Settings → Operator token**. It stays in browser memory and clears on reload; it is never returned by the API, placed in a URL or saved in browser storage. Do not commit it to a source/profile file. See [environment setup](../operations/ENVIRONMENT.md) for shared CLI/API/worker loading rules.

Start the separate durable worker to execute queued operations:

```sh
conda activate tradee
python -m backend.tradee_web.worker
```

Operations shows its heartbeat and queue. HTTP 202 means **queued**, not completed. The worker runs one heavy operation at a time in a separate subprocess, with a two-hour execution budget. Pending work can be cancelled. A running core publication cannot be safely cancelled halfway through a transaction. If the worker exits before acknowledging a request, restart it: the request becomes **interrupted**, rather than silently executing again. Inspect the domain audit before deliberately creating a new request.

Retries with the same idempotency key/body return the original request, including after completion. Reusing a key for another body is rejected. Pause/resume use the core's atomic revision-and-audit-head checks. Other controls check those values before delegating to the core's durable ownership/reconciliation rules. Avoid concurrent uncoordinated CLI controls while operating the same deployment from the UI.

## Data and research workflow

1. **Data Quality** shows instrument versions, datasets, UTC-day minute coverage, gaps/revisions and collector receipts. It does not infer complete trades/quotes from an absence of events.
2. **Operations → Research & data jobs** provides reviewed core-contract JSON documents. Templates prefill current session/hash references where available; validate and review all values before submission. Supported work includes registry refresh, bounded public REST backfill, immutable dataset snapshot, C03 materialization, C11 simulation, C13 replay, C12 registration/development/holdout, session/monitor creation, paper tick, C15 observation/replay and controls.
3. Data ranges are capped at 31 days per acquisition/snapshot job. Backfill requires a registered supported instrument. Inspect its source receipt before using the new dataset.
4. A **feature** job takes a dataset hash plus the existing C03 `FeatureConfig`. Warm-up/stability rules are unchanged. Markets chooses one materialized run, exposes its manifest, and renders only valid stable overlays. `feature_run` in the API can pin a C03 materialization or C11 feature inventory. A reconstruction is labelled separately from an original decision snapshot.
5. **Research** exposes frozen experiments, chronology, development evidence, selected utility/intervals, independent runs, model cohorts and any stored later-period scoring artifacts. Final holdout outcomes are denied on charts, runs, models and artifact paths until a deliberate audited C12 opening. Its command requires the exact text `OPEN <experiment hash>` and a reason. Overlapping raw-data windows and alternative strategy hashes are conservatively protected too.
6. **Signals** preserves capital rejections, expiry/lifecycle and delivery state. Select a row for original feature/expectancy/execution evidence and actual OHLCV context. CSV and JSON exports are redacted; financial strings remain exact in evidence.
7. **Portfolio** shows C13 shared paper equity/cash/risk, funded trades, drawdown and mature-R distribution. C11 independent PnL is never turned into wallet equity or annualized returns.
8. **Forward Review** selects immutable C15 report vintages, separate independent/funded maturity, fixed review evidence and paper telemetry. Missing/degenerate bounds remain unavailable.

Public streaming acquisition remains an independently owned **core collector**, not a browser WebSocket connection:

```sh
python -m tradee refresh
python -m tradee data --market-db data/c02.sqlite3 collect --symbols BTCUSDT,ETHUSDT --streams candle,trade,quote,mark
```

Run that foreground collector in its own terminal; Ctrl+C stops collection. Its database must match the selected profile. See [core CLI usage](../getting-started/README.md) for metadata/fee/calendar assumptions and strategy contracts, and [Telegram operations](../operations/TELEGRAM.md) for credentials and a real delivery smoke test.

## Session creation and owned paper runners

The session job calls **C14 create → C15 register**, checks that a retried monitor matches the deployment/policy, and returns `runner_started=false`. Explicitly queue **start runner** only after reviewing the frozen session, current source age, monitor and revision/audit head. It never sends a Telegram message or places an exchange order.

The owned runner is a separate bounded process, protected by a durable reservation and OS file lock. It waits for a future start without prematurely observing or pausing, respects source-settlement delay, continues the outcome tail after candidate detection ends, ticks the core paper runtime and observes the linked C15 monitor. It stops at the cycle/duration limit, requested stop or completed tail. C15 pause application remains a separate explicit audited action.

- **Pause/resume** controls notification admission; paper outcome processing can continue.
- **Stop runner** requests a stop after the current atomic operation and halts future paper ticks.
- **Stop collector** uses Ctrl+C in the independently owned collector terminal.
- **Recover runner** can release a stale reservation only after proving that the process lock is free. It does not start a replacement or resume anything automatically. A starting reservation has a 15-second ownership-handshake grace period.
- **Recover delivery claims** and **reconcile delivery** delegate to C14. Ambiguous Telegram acceptance requires `sent`/`not_sent` evidence and an appropriate message ID; the dashboard offers no resend action. Acceptance is not an actual user fill.

An API/worker restart does not silently start collectors, runners or notifications. An explicitly started runner can outlive the API/worker: use its stop action before planned shutdown. Its reservation and heartbeat remain inspectable after restart. This baseline uses POSIX file locks (macOS/Linux); Windows ownership requires a separate adapter.

## Cursor, synchronization and persistence

Workspace, session, timezone, market dataset/symbol/timeframe and knowledge cursor are bookmarkable URL state. The cursor is **epoch milliseconds** and uses both event and actual recording clocks for C14. The replay controller steps/plays recorded cycle vintages at 1×/2×/4×; its speed is unrelated to modeled execution delay. Only clock-navigation metadata can list later cycle cursors; future cycle payloads/outcomes remain filtered.

Markets honors the availability cutoff; Signals/Portfolio use the selected recorded cycle. C15 filters report/history by its observed clock. Research/Data archives require explicitly leaving the session cursor because their own pinned artifact/dataset vintages have different scopes. Controls are disabled in a historical view. Chart time axes are explicitly **UTC**; table times use the selected timezone.

SSE carries durable **invalidation IDs**, not replacement market/domain events. Changes trigger re-reading verified source snapshots, including full journals; quote ticks never overwrite closed bars. Reconnect uses event IDs, a 10,001-event retention window and an explicit resync when the cursor is outside retention. File/WAL revisions are checked every three seconds, with 30-second query polling as a fallback. This is recorded-source freshness, not a direct browser-to-Binance feed or a claim of continuous 4 Hz delivery. “Service connected” and market source age are separate.

## Shutdown, backup and restore

1. Stop owned paper runners explicitly; confirm `stopped`. Finish/inspect running jobs and cancel unwanted queued jobs.
2. Stop the collector, worker and API in their own terminals with Ctrl+C. Do not delete lock files to take over a live process.
3. Back up **every configured domain DB plus the web-state DB**, profile config and frozen calendar/config files. Use SQLite's backup API while a source is live, or copy only after all owners stop. Copying just the main file of an active WAL database is not a complete backup.
4. Restore into a **new directory**, configure a separate web-state/profile, start the API in viewer mode and inspect artifact hashes, balances, session revisions and journals first. Leave the worker stopped until old queued requests and interrupted operations have been reviewed; a restored queue is executable state.
5. Do not restore over an active recording or automatically merge independently advanced stores. Coordinate all source owners and keep the original recovery copy.

Automated tests verify isolated SQLite backups and readonly source behavior; production backup recovery, disk exhaustion, continuous network faults and multi-host supervision remain operational validation work.

## Tests

```sh
conda activate tradee
python -m unittest discover -s tests
python -m unittest backend.tests.test_dashboard -v
npm test --prefix frontend
npm run build --prefix frontend
npm exec --prefix frontend -- playwright install chromium
npm run test:e2e --prefix frontend
```

Playwright uses `python` from the active environment. Set `TRADEE_PYTHON` to an absolute interpreter path if needed. Its local server on port 8790 creates current-source synthetic C01–C15 artifacts, copies SQLite databases, starts a real disposable API and owned worker, and removes its temporary stores on shutdown. No real Telegram service or exchange orders are involved. Screenshots/traces land in ignored `frontend/test-results/`.

See [implementation and acceptance status](DASHBOARD_IMPLEMENTATION.md) for the chart matrix, measured checks and explicitly unfinished richer interactions.
