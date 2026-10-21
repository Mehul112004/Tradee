# Testing and troubleshooting

Run from the repository root in the `tradee` Conda environment. Tests below use local scripted/fixture inputs unless a section explicitly says **real external request**. They do not establish profitable strategies.

## Choose a check

| Check | What it verifies | External delivery/data |
| --- | --- | --- |
| Configuration/Telegram unit tests | Precedence, destination checks, redaction and scripted transport behavior | No real message |
| Full Python suite | Core, backend and real CLI-process integration/E2E against isolated stores | Scripted external seams |
| Frontend unit/build | UI/API helpers and compiled production assets | No real message |
| Browser E2E | Chromium against actual temporary API, worker and synthetic current-source evidence | No real message or orders |
| Provider connectivity | Actual Binance adapters, REST/archive/WebSockets and TLS, temporary stores | Real public network requests |
| Telegram diagnostic | Actual bot/destination connectivity | One real test message |

```sh
conda activate tradee
python -m unittest tests.test_environment tests.test_c14_telegram tests.test_c14_cli backend.tests.test_environment -v
PYTHON_DOTENV_DISABLED=1 python -m unittest discover -v
npm test --prefix frontend
npm run build --prefix frontend
```

For browser E2E, keep port **8790** free; its test server creates/disposes its own API/worker and does not reuse your running dashboard:

```sh
npm exec --prefix frontend -- playwright install chromium
npm run test:e2e --prefix frontend
```

Playwright uses `python` from the active environment; `TRADEE_PYTHON` can explicitly name that interpreter. Screenshots/traces are retained on failure under ignored frontend test-output directories. Tests can take several minutes due to actual research/replay work. A manually navigable generated example is covered by [Synthetic demo](SYNTHETIC_DEMO.md).

For actual public Binance connectivity use `python -m tradee.check_connectivity`. For actual Telegram delivery use [the explicit Telegram command](TELEGRAM.md). These are separate tests; do not interpret mocked HTTP acceptance as real delivery.

## Common symptoms

| Symptom | Check / action |
| --- | --- |
| `npm run dev` fails at the root | Use `npm run dev --prefix frontend`, or run inside `frontend/` |
| UI shell opens but API requests fail | Start Python API on 8787; Vite only serves frontend/proxies requests |
| Port already in use | Use the existing intended service or stop its owner; do not start duplicate APIs/Vite instances |
| Built page missing or stale | Run `npm run build --prefix frontend`; development changes are served by Vite at 5173 |
| Local recording is empty | Acquire data and create snapshots/research/session artifacts, or use the synthetic demo; GET requests do not fill stores |
| Job stays queued | Start one worker and verify matching API/worker profile/state paths and heartbeat |
| Operator button disabled / unauthorized | Set nonempty backend token, restart API, paste matching token in Settings, leave historical cursor and review required confirmation/reason |
| Empty/invalid job template | Fill actual hashes and full component JSON contracts; empty objects are not a runnable experiment |
| Revision/audit conflict | Refresh the current session and reassess the command; do not force old state |
| Service connected but old price | Check collector, source age and pinned dataset range; API connection is not a Binance recording guarantee |
| Missing indicators | Materialize compatible features/timeframe with sufficient finalized warm-up; inspect validity/stability |
| `ready=false` or CLI exit 2 | Read evidence reasons; a completed result can correctly be insufficient, rejected or unresolved |
| Research result locked | Check final holdout status; do not open final evidence just to bypass a lock |
| Frozen producer/runtime changed | Create a compatible new counted release; do not rewrite historical hashes |
| Telegram accepted but no phone alert | Notifications are silent; inspect the exact chat/test ID and receipt |
| Telegram timed out / unknown outcome | Inspect the chat before another test; follow durable reconciliation for strategy notices |
| Source corrupt/unsupported schema | Stop relevant writes, preserve the evidence and inspect integrity/schema; do not auto-migrate or delete it to hide the error |

For permission/certificate failures, repair filesystem ownership/trusted CA configuration. Do not disable TLS or delete active locks as a recovery shortcut. Record the selected workspace, full artifact identity, timestamp and reason code when investigating; redact token/destination details before sharing logs.

Related: [run commands](../START_HERE.md), [backup/recovery](BACKUP_AND_SHUTDOWN.md), [measured dashboard acceptance](../../dashboard/DASHBOARD_IMPLEMENTATION.md).
