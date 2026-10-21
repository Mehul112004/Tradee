# Operator access and durable jobs

**Location:** Settings → Operator token; Operations → Research & data jobs / Job history. Operator is a local authorization capability, not another service, exchange account or LLM.

## Enable and submit

1. Choose a long random `TRADEE_WEB_OPERATOR_TOKEN` in root `.env`. Restart the API so it reads the setting. A blank value leaves operator requests disabled.
2. Start one worker for the API's web-state/profile:

```sh
conda activate tradee
python -m backend.tradee_web.worker
```

3. Enter the same token in Settings. It stays in browser memory and clears on reload; do not place it in a URL or frontend build config.
4. Choose the intended workspace and return to the **current** view. Open Operations → Research & data jobs.
5. Choose a job, review/edit its JSON template, confirm the exact command/workspace, then **Queue core job**.
6. Inspect Job history and its returned receipt, then the corresponding feature page. HTTP 202 means queued, not completed or passing research.

For example, **refresh registry** takes `{}`. It makes a real public Binance request. More complex templates contain blank arrays/objects or placeholder timestamps: these are required contract shapes, not valid automatically chosen experiments.

## Job map

| Job selection | Inputs/purpose | Guide |
| --- | --- | --- |
| refresh registry | Append current Binance contract observations | [Registry](INSTRUMENT_REGISTRY.md) |
| backfill / dataset snapshot | Actual symbols, range/type and knowledge scope | [Data](MARKET_DATA.md) |
| features | Dataset hash plus feature config | [Features](FEATURE_ENGINE.md) |
| simulation | Dataset, scenarios, fees, execution and optional funding/calendars/config | [Backtesting](BACKTESTING.md) |
| register experiment / research run | Complete manifest or registered experiment hash | [Research](WALK_FORWARD_RESEARCH.md) |
| open holdout | Experiment, reason and exact confirmation | [Research](WALK_FORWARD_RESEARCH.md) |
| portfolio | Verified source/report pins, model IDs, policy and replay config | [Portfolio](PORTFOLIO.md) |
| create session / tick | Compatible release/portfolio, reviewed session/monitor, then an explicit current tick | [Sessions](PAPER_SESSIONS.md) |
| start runner / stop runner / recover runner | Session ownership, linked monitor, bounds, reason and fresh revision/audit head | [Sessions](PAPER_SESSIONS.md) |
| forward observe / replay / apply pause | Monitor/report identity and current control context | [Forward review](FORWARD_REVIEW.md) |
| reconcile delivery | Signal, evidence-backed sent/not-sent decision, proof and required receipt fields | [Telegram](TELEGRAM.md) |

Pause/resume and delivery-claim recovery are also available in Session controls. The standalone C08 detector and standalone C10 fitting commands are CLI workflows, not separate dashboard job kinds. There is no browser send-Telegram, exchange-order or arbitrary shell-command job.

## Lifecycle and recovery

Requests move through `queued`, `running`, then `succeeded` or `failed`; interrupted work and cancelled queued work retain receipts. A succeeded request can still return a rejected/unready research result—read its domain fields. The single worker serializes work for its state file and uses a separate child process with a two-hour budget per task.

Pending requests can be cancelled. Running atomic core publication is not a safe mid-transaction cancellation target. If the worker disappears, inspect the domain audit and interrupted receipt before deliberately resubmitting. Do not assume “no acknowledgment” means “nothing committed.”

The UI tracks an idempotency key for the exact reviewed body. Repeating the same request can return its original receipt; editing it creates a distinct request. Controls also require matching session revision/audit head. On conflict refresh state and reassess instead of forcing stale input.

If a job stays queued, inspect worker heartbeat and identical API/worker `--config`. If unauthorized, check backend token availability, exported-value precedence and browser token. See [troubleshooting](TESTING_AND_TROUBLESHOOTING.md).
