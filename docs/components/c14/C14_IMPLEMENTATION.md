# C14 implementation and operation

Implemented 20 October 2026. Use the dedicated `tradee` Conda environment. Production stays standard library only; the existing C02 WebSocket collector uses the project's optional live dependency.

## Files and interfaces

| File | Contains | Dependencies and consumers |
| --- | --- | --- |
| `tradee/c14/contracts.py` | Strict RuntimeConfig, SessionSpec and redacted DeliveryResult | CLI, release loader, runtime/store/dispatcher |
| `release.py` | Frozen C12 research + C13 recipe/source/model/runtime checks; prospective scope | C11/C12/C13 evidence; creates a paper deployment |
| `pipeline.py` | Bounded C02 prefix replay through production C11/C13, feed health, signal phases and current send checks | C01–C13 shared implementations; publishes to C14 |
| `store.py` | Own SQLite schema, deployment/cycle/signal/outbox state, CAS, atomic publication, corruption checks and audit | Runtime, dispatcher, CLI and C15 |
| `delivery.py` | Durable leases, rate limits, HTTP result transitions, recovery and explicit reconciliation | Injected preflight/transport; never guesses ambiguous acceptance |
| `telegram.py` | Fixed-host TLS `sendMessage`, bounded response validation and redacted failure classification | Explicit token/destination; no account or strategy changes |
| `message.py` | Plain bounded paper-fill notice, evidence IDs, planned levels, costs and absolute expiry | Frozen signal + fresh guard |
| `cli.py` | `signals` commands, foreground watcher and explicit standalone connectivity diagnostic | Existing stores and runtime; actual sending requires `--send-paper` |
| `configs/c14_runtime.json` | Default shadow-mode bounds and timing | RuntimeConfig reference |
| `configs/c14_session.example.json` | Example minute-aligned session/warm-up/tail | Template; replace dates and inspect resource needs before creating a deployment |
| `scripts/verify_c14.py` | Actual research release plus raw prospective feed → paper signals/outbox/recovery/close | Production pipeline, scripted Telegram network seam; retained E2E artifacts |

Public Python exports: `RuntimeConfig`, `SessionSpec`, `DeliveryResult`, `load_release`, `SignalStore`, `SignalRuntime`, `Dispatcher`, `TelegramTransport`.

## Offline end-to-end verification

```sh
conda activate tradee
python -m tradee signals explain
python -m scripts.verify_c14 --output data/c14_checks/demo1
```

Use a fresh output directory. The script reads no credentials and sends no external messages. It first runs the real C13 research E2E to generate a current-source C12 release and compatible funded policy, then ingests a separate prospective BTC/ETH feed and exercises C14 through real CLI processes. It records raw receipts, all six databases, deployment/config/calendar JSON, paper books, audit events, outbox states, scripted wire messages and command logs. See [verification](C14_VERIFICATION.md) for literal expected results.

The nested `research/` directory holds C01/C02/C10/C11/C12/C13 evidence; `c14.sqlite3` holds only the prospective C14 state. Demo bot/chat IDs are synthetic placeholders. They cannot be retargeted by supplying a different bot token.

## Create a frozen paper deployment

Prepare a passing current-source C12 `research_candidate` and its C13 compatibility run. C14 does not promote those artifacts to actionable live authority. Supply a session JSON based on the example, plus explicit settlement-calendar JSON. Empty/missing calendars remain unknown funding; they do not silently become zero funding. Example calendars in tests are explicitly synthetic operator assumptions.

```sh
python -m tradee signals create \
  --spec path/to/session.json \
  --experiment EXPERIMENT_HASH \
  --portfolio-run COMPATIBLE_C13_RUN_HASH \
  --calendar path/to/settlement_calendars.json
```

Database options go after `signals` and before its action:

```sh
python -m tradee --db path/to/c01.sqlite3 signals \
  --market-db path/to/c02.sqlite3 \
  --simulation-db path/to/c11.sqlite3 \
  --research-db path/to/c12.sqlite3 \
  --portfolio-db path/to/c13.sqlite3 \
  --signal-db path/to/c14.sqlite3 \
  create --spec path/to/session.json --experiment EXPERIMENT_HASH \
  --portfolio-run COMPATIBLE_C13_RUN_HASH --calendar path/to/calendars.json
```

All six paths must differ. The C11/C13 stores must contain the frozen historical evidence; C14 appends immutable prospective analysis there and commits its publication/outbox atomically in C14. For isolated operations, use consistent SQLite backups of the complete evidence bundle, not empty replacement stores.

A session declares name, minute-aligned warm-up/start/end/tail and runtime configuration. Decisions belong to `[start,end)`; monitoring continues through the tail without forced closes. Tail must cover maximum holding, exit wait and an observation allowance. The session begins strictly after final research evidence. Defaults are shadow mode, 250ms source settling, 10-second notice life, 5-second cycle/analysis freshness, 3-second HTTP timeout, 15-second lease, three attempts, 3.5-second chat and 100ms bot spacing. These are engineering settings requiring host/load validation.

The deployment pins one research model/scenario, its exact quantity/costs/timing/features, one C13 risk/capital recipe, calendars, source digest and Python runtime. Changing the frozen name's deployment fails; create a new clearly identified deployment for a changed configuration. Distinct deployments have separate hypothetical wallets and cannot be combined as one user's account without validated composition.

## Record and watch the feed

C14 consumes existing recorded stores. In separate foreground processes, use the existing collectors:

```sh
python -m tradee watch
python -m tradee data collect --symbols BTCUSDT,ETHUSDT --streams candle,quote,mark,trade
python -m tradee signals watch SESSION_NAME --interval-seconds 1
```

C01 refresh and C02 collection/repair remain independent processes. Prepare causal candle warm-up with the existing C02 backfill commands and record actual settlement evidence promptly through C02's funding path. A mark's projected next funding rate is not a settled funding receipt. Unknown/stale feed, metadata, model or paper risk suppresses notices. Follow the configuration of the actual frozen release; the example symbols are not a universe override.

`watch` emits JSON health lines and a final stop result. It supports `--max-cycles N` for a bounded foreground run. Without `--send-paper`, it never constructs a Telegram sender. It does not install supervision, a daemon or an automation. An expired session/tail stops; unresolved positions remain visible rather than receiving invented liquidation/exit fills.

Each tick rebuilds the full bounded prefix. This baseline has explicit event/candidate/artifact/cycle/byte/session limits, not an out-of-core or incremental execution claim. A full-rate Binance quote/trade capture can reach those bounds quickly. Warm-up collection design, realistic throughput/latency and storage/recovery benchmarks are required before unattended operation; a synthetic demo does not establish that capacity.

For deterministic replay/manual inspection:

```sh
python -m tradee signals tick SESSION_NAME --at-ms SOURCE_CUTOFF_MS
python -m tradee signals status SESSION_NAME
python -m tradee signals session SESSION_NAME
python -m tradee signals list SESSION_NAME
python -m tradee signals signal SIGNAL_ID
python -m tradee signals events SESSION_NAME
python -m tradee signals artifact ARTIFACT_HASH
```

`status` exits 2 if unready, 0 if healthy. Read/observation commands report completed operations even when their paper book has unresolved outcomes; inspect `health`, `fault` and delivery states. Bad input/incompatible evidence exits 1. A source watermark or past paper admission change stops publication and requires reconciliation; silently rebuilding a different past is forbidden.

## Optional real Telegram connectivity smoke

See [Telegram credentials and delivery testing](../../operations/TELEGRAM.md) for the credential variable names, TBot configuration location and a complete secure terminal example.

This is separate from the automated E2E and strategy deployment. Use a dedicated test bot/chat. Supply the token through the environment; it is never stored in a config or database. On macOS zsh, secure input can be entered without including the token in the command history:

```sh
read -s 'TRADEE_TELEGRAM_BOT_TOKEN?Telegram test bot token: '
export TRADEE_TELEGRAM_BOT_TOKEN
python -m tradee signals telegram-test \
  --bot-id NUMERIC_BOT_ID --chat-id NUMERIC_TEST_CHAT_ID \
  --test-id manual_smoke_1 --send-paper
```

The bot ID is the numeric prefix of its token. The destination must be a numeric private/group/channel ID; usernames are deliberately unsupported in this baseline. The command makes **one** explicit HTTP attempt with a fixed connectivity-only message and returns a redacted result/message ID. It has no strategy, account, durable outbox or automatic retry. Exit 2 means no confirmed acceptance. If the result is ambiguous, inspect the test chat before considering another explicit attempt. API acceptance does not prove visibility: manually verify the exact test ID and `NO TRADE INSTRUCTION` text.

The automated tests do not run this real-network command. They validate it with an injected sender and validate the production HTTPS transport with scripted response objects.

## Paper-fill notifications

To test the durable strategy notification path, prepare a new session with `runtime.mode: paper_test` and explicit numeric `bot_id`/`chat_id`, preserving the validated research policy. Then, with the matching token in the environment:

```sh
python -m tradee signals watch SESSION_NAME --interval-seconds 1 --send-paper
```

`signals send SESSION_NAME --send-paper` performs one fresh tick/eligible dispatch attempt. Paper-test notices report evaluated paper fills, planned levels, exact size, conditional expectancy, entry-leg costs, funding, expiry and stable evidence IDs. They are **not** pre-entry trade instructions, user-fill records or live promotion. The current tested manual delay ends at the evaluated paper fill; adding another human delay would require another validated protocol.

Before each HTTP attempt, C14 rechecks current C03/C07/C10 context and C13 risk, rejects changed tested price/quantity/fees, and expires old notices. A new position/thesis-affecting source event requires another tick. Throttle/retry waits are persisted timestamps, not blocking sleeps. Telegram requests use plain text, verified TLS, no redirects or paid broadcasts, bounded reads and no generic HTTP retry. Exceptions are redacted to fixed reason codes.

## Pause and reconcile

```sh
python -m tradee signals pause SESSION_NAME --reason 'Operator maintenance'
python -m tradee signals resume SESSION_NAME --reason 'Recovery checked'
python -m tradee signals recover SESSION_NAME
python -m tradee signals reconcile SIGNAL_ID --decision sent \
  --message-id TELEGRAM_MESSAGE_ID --evidence 'Verified exact signal ID in the configured test chat'
```

Pause suppresses queued notices and stops new dispatch. It does not unwind the paper-policy benchmark, cancel a message already in flight, close a position or disable source recording. Resume allows future opportunities and does not revive old notices.

The outbox claim commits before network I/O. A crash or timeout can therefore leave acceptance unknown; an expired lease becomes `ambiguous` and is never automatically retried. Only explicit reconciliation can resolve it. `--decision not_sent --evidence 'Definitive non-acceptance evidence'` may schedule another attempt only before expiry and within budget. A missing UI message alone may be inconclusive; leave uncertainty ambiguous. Manual assertions are recorded as assertions, not authenticated Telegram history.

A late confirmed response remains recorded even after expiry; the audit says it was late. Positive Telegram acceptance never establishes a user fill or becomes a second paper-account debit.

## Storage, telemetry and operational boundaries

C14 SQLite schema v1 has an application ID, content-addressed artifacts, frozen deployments, current paper heads, signal/outbox indexes, throttle timestamps and a hash-linked journal. Readers verify source/head/signal/delivery relationships; corrupt indexes fail closed. Cycles and outbox publication are transactional; a failed receipt commit leaves the already-claimed attempt unknown for recovery. Actual threads/process restarts are covered by tests.

Audit records separate the logical/source operation time from actual recording time. Cycle analysis duration, send attempts, HTTP elapsed time, acceptance IDs and late receipts support later C15 reconciliation. Processing duration currently measures analysis before final C14 publication; use audit/source/attempt clocks for complete latency analysis. A server may accept a request after a timeout/deadline, so remote exactly-once delivery is not promised.

Use SQLite backup APIs or stop writers before copying. Source evidence and live state must remain mutually consistent. No migration, distributed scheduling, automatic backup/restore service, authenticated user fills or production approval authority is installed. [C15 forward monitoring](../c15/C15_IMPLEMENTATION.md) is now implemented and must be registered before the first cycle. Full portfolio-policy inference, pre-entry actionable timing and representative forward/deployment acceptance remain explicit [upgrade gates](../../platform/COMPONENT_UPGRADES.md).
