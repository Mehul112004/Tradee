# Tradee: running the system

This is the short operating guide. Read it first, then use the [feature-by-feature manual](FEATURES.md) when you need a particular task. All commands run from the **Tradee repository root**. This guide describes the implemented local research/paper platform; it has no exchange-order execution or AI/LLM confirmation layer.

For the simplest workflow, start with **[Analysis sessions](features/ANALYSIS_SESSIONS.md)**: choose instruments, timeframe and strategies, then watch live or scan history. The API prepares history and supervises the existing C02 WebSocket collector for live sessions; no manually started worker/collector or research release is required. Setups are evaluated only on fully closed candles. Existing research/paper tools remain available separately.

Changing backend/core code requires a **new analysis session**, rather than regenerating a C12 release for this quick flow. A same-build server restart only requires deliberately resuming the paused session. The [analysis flow reference](../dashboard/ANALYSIS_FLOW.md) explains ownership, storage, notifications and the integration requirements for future detectors.

## 1. Install once

Prerequisites: the `tradee` Conda environment, Python 3.13 and Node 20.19+ with npm. No Docker, PostgreSQL, Redis or separate database server is required. SQLite stores component data in local `data/*.sqlite3` files.

```sh
conda activate tradee
python -m pip install -e '.[live,dashboard]'
python -m pip install -r backend/requirements.lock
npm ci --prefix frontend
```

The local root `.env` already contains the Telegram values reused from TBot. On a **fresh checkout only**, copy [`.env.example`](../../.env.example) to `.env`, populate the supported values and set file permissions with `chmod 600 .env`. Keep an existing `.env`; dependency installation does not require replacing it. See [configuration reference](CONFIGURATION_REFERENCE.md).

## 2. Choose how to open the dashboard

### Development: automatic frontend updates

Terminal 1:

```sh
conda activate tradee
python -m backend.tradee_web
```

Terminal 2:

```sh
npm run dev --prefix frontend
```

Open **http://127.0.0.1:5173**. Vite serves React and forwards API requests to Python on port 8787. `npm run dev` alone works inside `frontend/`; from the root use `--prefix frontend`. No build is needed for this development path.

### Built dashboard: one serving process

```sh
conda activate tradee
npm run build --prefix frontend
python -m backend.tradee_web
```

Open **http://127.0.0.1:8787**. Python serves the built frontend and API. Rebuild after changing frontend source. Run either this path or the development path; do not start a second API on the same port.

## 3. Choose viewer or operator access

| Access | Available actions | Setup |
| --- | --- | --- |
| Viewer | Read charts, stored results, signals, reports and exports | Start the API; no browser token needed |
| Operator | Submit supported jobs and change paper-session state | Set `TRADEE_WEB_OPERATOR_TOKEN` in root `.env`, restart the API and enter the same token in Settings |

The operator token is a local dashboard permission, separate from Telegram. The shipped value is blank. Choose a long random value when enabling operations; the browser holds it only until reload or clearing authorization. An empty backend token disables operator requests. Direct Python CLI commands use local filesystem access and do not require this dashboard token.

To execute queued dashboard jobs, start **one worker** in another terminal:

```sh
conda activate tradee
python -m backend.tradee_web.worker
```

Advanced research/paper jobs use this worker. Simple **Analysis sessions** run under the API and do not need it. You can browse without a worker. Check Operations for worker heartbeat, request state and results. See [operator jobs](features/OPERATOR_JOBS.md).

## 4. Understand the other independent choices

| Choice | Meaning |
| --- | --- |
| Development / built frontend | How the browser application is served; unrelated to permissions |
| Viewer / operator | Whether this browser can request changes; unrelated to strategy profitability |
| Local recording / synthetic workspace | Which databases are being inspected; synthetic data is an engineering demonstration |
| Shadow / paper-test session | Frozen C14 runtime mode; unrelated to whether you opened the UI with Vite |
| Current / historical cursor | Latest recorded state or an earlier knowledge view; historical views disable operator controls |

None of these choices enables live exchange trading. A ready result can still be unprofitable or unsuitable for a research release.

## 5. Choose your first task

- **Start a TBot-style analysis:** select Local recording → Analysis sessions → New analysis session, enable local controls, choose instruments/timeframe/strategies and start watching. Opt into Telegram setup observations if wanted. See [the walkthrough](features/ANALYSIS_SESSIONS.md).
- **Learn the interface with populated data:** follow the [synthetic demo](features/SYNTHETIC_DEMO.md). An empty Local recording workspace is normal on a new checkout.
- **Record actual Binance public data:** follow [live collection](features/LIVE_COLLECTION.md), then create a [dataset snapshot](features/MARKET_DATA.md). Collection does not automatically build research models or produce signals.
- **Test Telegram delivery only:** with `.env` populated, run the explicit command below. It sends one real, silent, clearly labelled test message and requires no strategy or database:

```sh
conda activate tradee
python -m tradee signals telegram-test --test-id manual_smoke_1 --send-paper
```

Look for `ready: true` and the test ID in the chat. For an ambiguous timeout, inspect the chat before another attempt. See [Telegram](features/TELEGRAM.md).

The full research sequence is **registry/data → features and candidate definitions → independent simulations → expectancy and chronological research → shared-capital replay → a frozen paper session → forward review**. Read the relevant [feature guide](FEATURES.md) at each step; this sequence is not performed automatically by opening the dashboard.

## 6. Know which processes to keep running

| Process | Needed for | Starts automatically with the dashboard? |
| --- | --- | --- |
| API, `python -m backend.tradee_web` | Every dashboard view | You start it |
| Vite, `npm run dev --prefix frontend` | Development frontend only | No |
| Analysis-session supervisor and managed C02 collectors | Historical preparation, WebSocket live/forming candles, closed-candle setups and opted-in observations | Starts subscriptions only for sessions you explicitly create/resume |
| Worker, `python -m backend.tradee_web.worker` | Queued dashboard jobs | No |
| Separately CLI-owned Binance collector | Advanced standalone recording/research/paper inputs | No; simple analysis sessions manage their own C02 subscriptions |
| Owned paper runner or explicit C14 CLI watch | Repeated paper ticks | No; creating a session does not start it |
| Explicit CLI Telegram dispatch | Advanced C14 paper-fill notifications | No; C14 dashboard runners do not send these; simple analysis observations are a separate opt-in path |

For a custom workspace configuration, pass the **same** `--config data/dashboard-profiles.json` to both API and worker. Collector/CLI database paths must also match that workspace; see [settings and workspaces](features/SETTINGS_AND_WORKSPACES.md).

## 7. Stop and troubleshoot

Stop owned paper runners first and confirm their state. Stop collectors, worker, Vite and API in their own terminals with **Ctrl+C**. A runner can outlive its API/worker; closing the browser is not a shutdown command. See [backup and shutdown](features/BACKUP_AND_SHUTDOWN.md).

If something is empty, stale, queued or unauthorized, use [testing and troubleshooting](features/TESTING_AND_TROUBLESHOOTING.md). Detailed engineering references remain available in the [main documentation index](../index.md), [dashboard runbook](../dashboard/DASHBOARD_RUNBOOK.md) and [future-upgrade register](../platform/COMPONENT_UPGRADES.md).
