# C14 verification

Verified in the `tradee` Conda environment, Python 3.13.15, 20 October 2026. Production uses the standard library. No token was read for external use, and no actual Telegram messages or exchange orders were sent by verification.

## Automated coverage

C14 adds **81 tests**:

| File | Tests | Evidence |
| --- | --- | --- |
| `tests/test_c14_contracts.py` | 5 | Frozen runtime/session round trips, shadow default, explicit numeric destinations, unsupported live mode, strict types, time/resource/throttle bounds and confirmed-message receipts |
| `tests/test_c14_telegram.py` | 9 | Fixed TLS host, exact plain-text/chat/message receipt, credentials/bot matching and redaction, explicit 429, permanent rejections, uncertain server/redirect responses, malformed/oversize bodies, proven connect failures versus unknown timeout, HTTP error-body parsing and bounded input |
| `tests/test_c14_store.py` | 16 | Idempotent deployment/tick, persistent reopen, atomic paper/signal/outbox rollback, CAS and clocks, missed/closed/unhealthy suppression, measured latency, pause/resume, later new opportunities, shadow without outbox, immutable past fills, index/artifact/audit corruption, resource limits and status |
| `tests/test_c14_delivery.py` | 19 | Persistent acceptance without duplicates, 429/backoff/throttle, expiry, timeout/crash ambiguity, leased concurrency, control interleaving, claim/receipt transaction failures, late acceptance, guard redaction/defer/rejection, manual reconciliation, bot mismatch, message content and a real concurrent worker thread |
| `tests/test_c14_cli.py` | 9 | Offline explain, readiness/error codes, local inspection, pause/recover, path isolation, invalid inputs, one-shot connectivity diagnostic with injected transport and no accidental network on missing credentials |
| `tests/test_c14_pipeline.py` | 15 | Actual production paper/funded parity, reopen/retry, current-vintage C03/C07 context without changing candidate proof, closed watermarks, code/clock changes, stale marks/expiry, trigger trade defer, benign active-feed continuity, mark-trigger/peak-path safety, changed economics, downtime catch-up, unknown funding, event budgets and session/tail scope |
| `tests/test_c14_release.py` | 7 | Actual frozen C12/C13 gate, no final-test reuse as prospective history, tail/calendar constraints, runtime changes, corrupt training reports and explicit missing funding evidence |
| `tests/test_c14_e2e.py` | 1 | Raw current-source C01–C13 research gate plus prospective C02→paper signals/outbox→scripted Telegram, retry/restart/reconcile/pause and exact closed book |

**Full suite: 717 tests passed in 465.807 seconds**, including all 81 C14 tests. Final command: `TRADEE_C13_E2E_OUTPUT=data/c14_verification/c13_regression_v2 TRADEE_C14_E2E_OUTPUT=data/c14_verification/e2e_v2 conda run --no-capture-output -n tradee python -u -m unittest discover -s tests -v`. The complete log remains at `/tmp/tradee-c14-final-suite.log`.

## Reproduction and retained evidence

```sh
conda activate tradee
python -m unittest discover -s tests -q
python -m scripts.verify_c14 --output data/c14_checks/demo1
```

Use a fresh demo directory. The automated E2E scripts their external HTTP seam and explicitly removes `TRADEE_TELEGRAM_BOT_TOKEN` from CLI subprocesses, even if the developer has configured one. The production Telegram transport is separately exercised with scripted HTTPS responses, not replaced in its parsing/classification tests.

The C14 E2E runs **23 real C14 CLI processes**, after **32 real C13/C12 prerequisite CLI processes**. It generates actual earlier features/candidates/executions/funding/outcomes, fits a frozen estimator, obtains a counted C12 recipe compatibility release, then records a separate later raw BTC/ETH stream. No strategy labels are hand-assigned by the integration fixture.

It demonstrates:

1. Two detected candidates have no notice before tested paper execution. At first execution, one asset fits the shared 320 USDT wallet and the other is suppressed.
2. Entry fee is booked once: first paper cash **319.9489**. A repeated tick does not create another signal/outbox debit.
3. An explicit 429 response schedules retry; the persisted chat interval still blocks an earlier attempt.
4. The next attempt times out ambiguously. It is not automatically resent. A recorded operator assertion resolves acceptance without changing paper cash.
5. Another paper entry loses its worker after durable claim. Reopening the store and recovering the elapsed lease retains ambiguity. Definitive non-acceptance after expiry cannot revive the notice.
6. Pause suppresses a later pending notice; resume does not recreate it. The independent hypothetical paper benchmark continues tracking the frozen policy.
7. All three admitted paper positions close through the real C09 path. Terminal cash is **328.489**, terminal positions empty, matching the single-size funded baseline's **8.489 USDT** net after costs.
8. Every scripted notice is bounded plain text with `NO TRADE INSTRUCTION`, absolute expiry and a stable signal ID. No real bot/chat receives it.

Unit failure injection verifies that no HTTP starts before a committed claim; a failed post-HTTP receipt write leaves an in-flight attempt recoverable as ambiguous. A real threaded second worker cannot claim the same attempt. A valid late response is retained even if another worker has already recovered the lease. Mutable signal/delivery indexes cannot silently contradict the current cycle or audit records.

Pipeline regressions append raw new quotes/trades and reconstruct the actual C03/C07 current snapshot. They distinguish a changed quote/entry price from a position-affecting prefix needing a new tick. Benign in-range trades and unchanged marks permit fresh checks under an active feed; trigger crossings, changed exposed-mark paths and their possible intermediate equity peaks require complete paper replay. The original C10 candidate's feature proof remains unchanged. Isolated test copies deliberately remove only later synthetic observations before appending alternate paths, because C02 correctly clamps availability behind its latest recorded clock. Database copies use SQLite backup and close their handles.

## Scope of this evidence

The prior research fixture uses synthetic recorded Binance-shaped prices/rules, one-minute/two-bar long range breakout, quantity 1, assumed fees, zero manual delay and explicitly empty funding calendars. Its C10/C12 evidence gates are reduced engineering thresholds and bootstrap draws, with C12 fee/neighborhood gates disabled for that small fixture; the independent full C12 suite retains its robustness checks. The prospective session uses a 30-second analysis/cycle freshness allowance for the fixture, zero source-settle delay, a 10-second notice life, fake numeric bot/chat IDs and scripted responses. Production defaults are documented separately.

These tests establish paper orchestration and delivery-state semantics. They do not establish real-market expectancy, a valid actionable entry-delay protocol, actual Telegram visibility, user fills, exchange liquidation fidelity, representative full-rate throughput or production deployment readiness. Full-prefix rebuilding is bounded and can hit resource limits on active feeds. Full portfolio-policy inference and C15/operational acceptance remain required.

For an actual service smoke, follow [the opt-in manual procedure](C14_IMPLEMENTATION.md#optional-real-telegram-connectivity-smoke). It performs one fixed connectivity-only request with an explicitly configured test destination; it is not silently run by the test suite. Human visibility remains a separate acceptance step.

Final production digest (all `tradee/**/*.py`): `297085717ab185bcc65416954a21bb3b1f7da6aa148aded47e3893bd7f3114b4`. Documentation and Git commits do not change it.

Set `TRADEE_C14_E2E_OUTPUT` to a fresh path to retain the connected C14 E2E during the full suite. `TRADEE_C13_E2E_OUTPUT` separately retains the standalone C13 regression. Retained data directories are local ignored evidence, not committed source artifacts.


## Manual acceptance checklist

| Step | Expected result |
| --- | --- |
| Run the fresh offline demo | `passed: true`; 23 C14 CLI operations after 32 prerequisite research operations |
| Inspect `scripted_telegram.json` | Two scripted attempts with one stable first-signal ID, clear paper label, fill/stop/target and absolute expiry; no bot token |
| Inspect the final outbox | Exactly three admitted-entry deliveries: `resolved_sent`, `expired`, `suppressed`; no pending retry recreated on resume |
| Inspect the paper book | Cash 328.489 USDT, no remaining positions; six asset-level candidates retain their admitted/suppressed history |
| Inspect recovery/audit | Three claimed attempts, explicit 429, ambiguity, lease recovery and operator assertions; no automatic unknown-outcome resend |
| Stop the synthetic feed | Health/status can be unready because quotes/marks are stale; the completed paper result stays inspectable |
| Optional dedicated real-bot smoke | Run only the explicit connectivity command, verify the exact test ID in the test chat and retain its message ID; never infer a user trade |

The offline demo's historical source clocks are intentionally simulated. For inspection use `session`, `list`, `signal`, `events` and the JSON report; a wall-clock `status` of a finished historical fixture should be stale. A green paper pipeline does not erase individual failed delivery records: inspect outbox state/reason counts and the audit too.


## Final retained artifacts

Inspect [E2E result](data/c14_verification/e2e_v2/e2e_report.json), [C14 command log](data/c14_verification/e2e_v2/e2e_commands.json), [prospective raw receipts](data/c14_verification/e2e_v2/live_receipts.jsonl), [scripted Telegram bodies](data/c14_verification/e2e_v2/scripted_telegram.json), [frozen session](data/c14_verification/e2e_v2/session.json) and [prerequisite research E2E](data/c14_verification/e2e_v2/research/e2e_report.json). The standalone [C13 regression](data/c14_verification/c13_regression_v2/e2e_report.json) also passed under the same production digest.

- Deployment: `f0c6a308629292f55583026fd23ea9d3147c881c096c7fbedcccb4f3902889fe`.
- Final cycle: `eaecad73fe1034b24b2db63900d7abd3f57a8497ab250e072da1e411b55019a8`.
- Paper book: cash **328.489 USDT**, zero remaining positions.
- Final admitted-entry delivery states: one each `resolved_sent`, `expired`, `suppressed`.
- Actual external messages: **zero**. Scripted attempts and explicit synthetic reconciliation remain distinguishable in the audit.

Inspect the retained lifecycle without regenerating it:

```sh
python -m tradee signals --signal-db data/c14_verification/e2e_v2/c14.sqlite3 list paper_demo
python -m tradee signals --signal-db data/c14_verification/e2e_v2/c14.sqlite3 events paper_demo
```
