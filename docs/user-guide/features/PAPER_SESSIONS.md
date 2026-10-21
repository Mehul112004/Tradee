# Paper sessions and owned runners

**Location:** Operations → Session controls / Research & data jobs / Process ownership. **Access:** operator plus worker for UI actions. **Prerequisites:** a current-source compatible C12/C13 research release, captured source data, a reviewed C14 session specification and a prospective C15 monitor policy.

A **session** is a frozen bounded deployment definition. A **runner** repeatedly advances its recorded-prefix paper processing. A **collector** records market data. A **worker** executes dashboard jobs. None of these is interchangeable.

## Create, then explicitly start

1. Review the release/model/portfolio compatibility and source/Python version. Old frozen releases do not become current by editing their hashes.
2. Prepare actual future session bounds, preceding warm-up and an outcome tail. [Session example](../../../configs/c14_session.example.json) and [runtime example](../../../configs/c14_runtime.json) are schemas/settings to review; do not reuse illustrative historical times.
3. Prepare the C15 review policy **before the first cycle**, with appropriate future absolute review deadlines.
4. In **Research & data jobs**, submit **create session** with the exact experiment, portfolio run, spec, monitor name/policy and required calendars. Inspect its receipt: `runner_started=false` is intentional.
5. Start [collection](LIVE_COLLECTION.md) independently. Submit **start runner** with that session/monitor, a reason, fresh revision/audit head and explicit interval/cycle bound. Inspect Process ownership and session cycles.

The owned runner waits for a future session start, respects source-settlement delay, continues the outcome tail and observes its linked C15 monitor. It stops at its bound, requested stop or completed tail. The dashboard runner does **not** dispatch Telegram messages or place exchange orders.

## Modes and controls

| Mode/control | Effect |
| --- | --- |
| `shadow` | No configured Telegram destination |
| `paper_test` | Frozen numeric bot/chat required; real delivery still requires explicit CLI opt-in |
| Pause / resume | Controls admission/notification processing according to C14 rules; paper outcome tracking may continue |
| Stop runner | Requests a stop after the current atomic operation, preventing further runner ticks |
| Recover runner | Releases a stale reservation only after ownership checks; does not start/resume a replacement |
| Stop collector | Ctrl+C in its separate terminal; unrelated to pause/stop runner |

Controls require the **current** view, operator authorization, confirmation/reason and current revision/audit head. A conflict means refresh and reassess; it is not permission to force overwrite. Do not run a separate CLI watch against a session already owned by a dashboard runner.

## Direct CLI alternative

For a deliberately CLI-owned deployment, create and register it using [C14/C15 operation](../../components/c14/C14_IMPLEMENTATION.md), then run the following command shape:

```sh
conda activate tradee
python -m tradee signals watch SESSION_NAME --interval-seconds 1 --max-cycles 3600
```

Register/observe its monitor as described in [Forward review](FORWARD_REVIEW.md). Omitting `--send-paper` does not send Telegram, even if `.env` contains a token. For real strategy-path notifications use the separate [Telegram guide](TELEGRAM.md) and a reviewed `paper_test` session.

## Stop/recover safely

An owned runner can outlive the API/worker. Closing the browser or restarting the API does not stop it. Request stop and verify its state before planned shutdown; do not delete a lock file to take over an active process. If ownership is stale, use recovery only after checking its receipt/heartbeat and process state. POSIX ownership currently targets macOS/Linux.

Related: [operator jobs](OPERATOR_JOBS.md), [forward review](FORWARD_REVIEW.md), [shutdown](BACKUP_AND_SHUTDOWN.md).
