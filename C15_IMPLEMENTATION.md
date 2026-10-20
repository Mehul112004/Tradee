# C15 implementation and operation

Use the `tradee` Conda environment. C15 adds no dependency or credential. Its watcher reads local recorded evidence and may apply local C14 pause controls; it never sends a message or places a trade.

## Files and data ownership

| File | Contents |
| --- | --- |
| `tradee/c15/contracts.py` | Frozen review schedule, maturity/health rules, inference settings and resource bounds |
| `source.py` | C11/C13/C14 receipt verification, C09 label validation, cost/fee reconciliation and separate track summaries |
| `statistics.py` | Scheduled paired net-R/forecast-residual calendar-block intervals and evidence abstention |
| `store.py` | Separate SQLite application/schema, content hashes, transactional reports, journal, CAS and pause receipts |
| `engine.py` | Prospective registration, revision-aware observation/export, health classification and recoverable pause application |
| `reconcile.py` | Pinned C02 raw replay through actual C11/C13 production logic; manifest/report hash checks |
| `cli.py` | Explain, create, observe/watch, inspect, export, reconcile and explicit pause commands |
| `configs/c15_monitor.example.json` | Example rule settings and **illustrative historical review timestamps to replace** |
| `scripts/verify_c15.py` | Fresh-directory synthetic raw-input E2E, staged live receipts, all production stores, scripted Telegram and command logs |

`data/c15.sqlite3` owns immutable `forward_monitor`, `forward_report`, replay-reconciliation and pause-receipt artifacts. Its journal and indexed observations publish atomically. Prior reports are readable after source-code changes; operational observation/replay requires the exact frozen producer/runtime. Adding C15 changes the repository-wide production digest, so retained C14 releases from earlier code remain historical evidence and require new current-source counted research/deployment before operational reuse.

## Automated full workflow test

```sh
conda activate tradee
python -m tradee monitor explain
python -m scripts.verify_c15 --output data/c15_checks/demo1
```

The output directory must be fresh. The script generates raw synthetic BTC/ETH market/metadata receipts, executes C01–C13 research, creates a frozen C14 deployment, registers C15 before any cycle, and stages detection→paper admission→delivery acceptance→operational pause→paper closure→mature measurement→raw replay. Each C14/C15 child executes the real CLI main with a test-harness wall clock matching the historical synthetic receipts; no production clock bypass is added. It keeps both capital-admitted and rejected independent outcomes, immutable earlier reports, a matured export, all databases and CLI command logs. No token is read and no external message is sent. The small inference minima and synthetic funding calendar are test fixtures, not approved real-market settings.

## Real recorded-feed sequence

First prepare a **current-source** frozen C12/C13-compatible shadow or paper-test C14 deployment using [C14 operation](C14_IMPLEMENTATION.md). Start C01 metadata observation and C02 recording as documented there. Before its first `signals tick/watch`, replace the example's review times with absolute UTC millisecond deadlines after the session start, choose rules for the declared horizon, and register:

```sh
python -m tradee monitor create forward1 --session SESSION --policy path/to/frozen_monitor_policy.json
python -m tradee signals watch SESSION --interval-seconds 1
```

Run the monitor in a separate terminal:

```sh
python -m tradee monitor watch forward1 --interval-seconds 5
```

Observation alone saves requests. To authorize automatic **local pauses under the already frozen rules**, add `--apply-pauses` to `monitor watch` or `monitor observe`. No automatic resume exists. Keep the C14 runner and data recorder running to measure the hypothetical policy after notifications stop.

```sh
python -m tradee monitor observe forward1
python -m tradee monitor status forward1
python -m tradee monitor events forward1
python -m tradee monitor artifact REPORT_HASH
python -m tradee monitor apply-pause forward1 --report REPORT_HASH
python -m tradee monitor reconcile forward1 --report REPORT_HASH
python -m tradee monitor export forward1 --report REPORT_HASH
```

Read commands and export need only the C15 store. `status` returns the frozen definition and latest report; assess `report.ready`, its three health categories, `already_paused`, review evidence and delivery counts. `observe`/`reconcile` exit 2 on unready/failed evidence, 1 on invalid inputs, and 0 on success. `watch` emits compact JSON per observation and its stop summary. Ctrl-C retains all committed artifacts. `--at-ms` is intended for controlled replay/testing; normal operation uses wall-clock time.

Defaults use `data/c01.sqlite3`, `c02.sqlite3`, `c11.sqlite3`, `c13.sqlite3`, `c14.sqlite3`, `c15.sqlite3`. Custom paths go **before the action**, for example `python -m tradee --db path/c01.sqlite3 monitor --market-db path/c02.sqlite3 --simulation-db path/c11.sqlite3 --portfolio-db path/c13.sqlite3 --signal-db path/c14.sqlite3 --monitor-db path/c15.sqlite3 observe forward1`. All stores must differ.

## Report interpretation and manual checks

Each row has a stable signal/track identity, source cycle, current revision, original decision/forecast, actual admission audit-recording timestamp, first-decision provenance, label availability, mature/pending/unfilled/unresolved status, costs and exact outcome money. Slow or catch-up admissions recorded at/after outcome knowledge remain diagnostic and cannot enter inference. A fixed review also excludes cycles first published after its deadline despite an earlier source cutoff. Independent labels do not share capital. Mature-label sums exclude unknown/open labels; C13's wallet remains authoritative for total cash, equity and open mark PnL. Never sum independent and portfolio rows together.

Inspect an admission report before a trade closes: its new outcome must be pending and absent from export. After a later C14 close and the strict maturity lag, inspect a new report: net must equal gross minus fees plus settled funding, and entry fee difference must reconcile. Reopen the old report hash: it must still show its earlier pending state. Inspect the rejected candidate's independent outcome separately.

To exercise a local pause manually in an isolated paper deployment, stop new C14 ticks long enough to exceed the frozen active-session freshness bound, then run `monitor observe --apply-pauses`. Verify the pause journal and suppressed pending outbox in C14. Restart ticks/recording; the paper outcome book continues and notification pause remains. Resolve the cause and use C14's explicit operator `resume` only when justified. Retrying an already applied C15 request recovers its original receipt rather than overriding that later resume.

Run `monitor reconcile` on an observed report: all raw-prefix, C11 manifest/report and C13 manifest/report checks must pass. This uses the **pinned original dataset**, not a newly collected vintage. A mismatch/unverifiable replay is retained, and the next observation requests an integrity pause. Same-model replay proves reproducibility, not cost realism against actual fills.

## Resource and research gates

The baseline revalidates bounded historical inventories and stores full report vintages. Source cycles, observations, report bytes, event/candidate/artifact limits and bootstrap work are capped; no silent truncation occurs. Defaults cap C15 at 10,000 source cycles and 10,000 observations, 50 MB per report, 10,000 bins and two million bin×replicate work. Benchmark real feed/storage/latency before unattended operation. No supervisor or new daemon is installed.

Default statistical settings require 30 matured admitted trades and four occupied nonoverlapping 24-hour blocks. A short C14 session will normally produce insufficient evidence; choose a prospectively justified longer bounded session or implement the separately reviewed multi-session extension. A block shorter than a swing label also abstains. Review failure to detect degradation is never release authority. The export is a versioned future-research input, not a C10 training loader or a new C12 untouched holdout.

Actual-user fills/latency, authenticated balances, automated execution, a dashboard, conditional drift/calibration methods, multi-session inference and replacement experiments remain explicit upgrades in [the register](COMPONENT_UPGRADES.md). C14's evaluated-paper-fill notices remain `NO TRADE INSTRUCTION`; `live_approved` and `promotion_authorized` stay false.
