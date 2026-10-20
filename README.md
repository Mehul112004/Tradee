# Tradee

Component-based crypto signal research. **The agreed mandatory baselines C01–C03 and C06–C15 are available:** instrument metadata, recorded market data/replay, causal features, funding, execution/costs, two setup families, shared paper lifecycles, historical simulation, frozen expectancy, chronological research controls and shared-capital equity replay. C14 adds bounded paper orchestration/durable Telegram test notifications; C15 adds prospective paper/shadow outcomes, delivery/cost measurement, raw replay, fixed statistical reviews and audited pause requests. Actionable live promotion remains gated.

## Development environment

Use the dedicated Conda environment for this project:

```sh
conda activate tradee
python -m unittest discover -v
python -m tradee.check_connectivity
```

To recreate it on another machine, run `conda env create -f environment.yml` from this directory. The specification installs Python 3.13 and this project in editable mode with its live WebSocket dependency. It is an environment specification, not an exact dependency lockfile.

Without activating your shell, use `conda run -n tradee python -m unittest discover -v`. Project work should use this environment rather than the base Conda environment or system Python.

## Run C01

Python 3.11+ is required. C01 uses the Python standard library; no runtime packages or exchange keys are needed. Run from the repository root:

```sh
python3 -m tradee refresh
python3 -m tradee universe --members-only --save
python3 -m tradee health
```

`refresh` fetches Binance USDⓈ-M exchange information. All returned metadata is retained for audit; live universe eligibility requires crypto (`COIN`), perpetual, USDT quote and margin, `TRADING` status, valid supported metadata, freshness and membership in the explicit allowlist. The default enabled list is BTCUSDT and ETHUSDT.

TLS verification stays enabled. On macOS the provider also loads `/etc/ssl/cert.pem` when available; an explicit `SSL_CERT_FILE` takes precedence. On other hosts with a custom trust chain, supply a trusted CA bundle through that variable. Certificate failures stop automatic polling rather than triggering insecure retries.

Override the universe and run periodic refreshes:

```sh
python3 -m tradee --enabled BTCUSDT,ETHUSDT,SOLUSDT universe --members-only
python3 -m tradee watch --interval-seconds 900
```

The watcher refreshes immediately, then every 15 minutes by default. Ctrl-C stops it. Long `Retry-After` delays are respected; bans and permanent HTTP errors stop the watcher. No daemon is installed automatically. Metadata becomes stale at 30 minutes by default, configurable through `--max-age-seconds`. This is an observation-based policy: polling cannot guarantee that Binance has not changed a rule since the last response.

Global arguments such as `--db`, `--enabled` and `--max-age-seconds` go **before** the subcommand. Configuration is explicit per invocation; saved universe snapshots retain the exact policy used. `watch` only collects metadata; a later live runner must supply its intended policy when evaluating eligibility.

## Inspect history and reproduce decisions

```sh
python3 -m tradee history BTCUSDT
python3 -m tradee universe --as-of 2026-09-14T00:00:00Z --save
python3 -m tradee version VERSION_HASH
python3 -m tradee snapshot SNAPSHOT_HASH
```

Replace hash placeholders with values from actual output. An as-of time must include a timezone and cannot be in the future. A query before the first observation returns unknown metadata. The as-of command evaluates the **supplied policy** using observations available then; it does not claim that this policy was in use historically. Retrieve a saved snapshot to reproduce an actual recorded policy decision.

`version` exposes normalized metadata, original filter values and exact decimal constraint strings. The Python `Registry` methods are the integration API for later components; this version does not expose an HTTP server. Each decision includes its metadata version, observation time, source and exclusion/unknown reasons.

## Persistence and integrity

The default database is `data/c01.sqlite3`, excluded from Git. SQLite schema v1 holds raw observations (including rejected payloads when available), content-addressed semantic metadata versions, observation membership and saved universe snapshots. Refresh writes are atomic and universe reads use a consistent transaction. Unchanged observations advance freshness without creating another semantic version. The application only appends history; this is not a tamper-proof archive against direct database edits.

Back up the database using SQLite's backup API or stop writers before copying it. Unsupported schema versions fail explicitly; a future PostgreSQL migration can preserve the registry API and record contracts. SQLite is sufficient for the initial single-host metadata workload and does not determine storage for all later components.

- A missing symbol retains its old record, is marked missing and does not acquire a fabricated delisting date. Other valid records from the response can still refresh. Completeness of a syntactically valid provider response cannot be proven by C01.
- Invalid envelopes and duplicate symbols reject the refresh atomically. Malformed rules or unknown filter types quarantine the affected contract.
- Identity changes quarantine the symbol, including a later reversion. A reviewed identity-reconciliation workflow is deferred; C01 does not automatically stitch relistings or renames together.
- Current rules are never backfilled as verified historical rules. `effective_from_ms` remains unknown. Source-reported onboarding dates are not complete historical status evidence.
- Existing positions must continue to be monitored by later components even when C01 disallows new entries.
- Account fee tiers, execution rounding policy, margin/liquidation modelling, and funding calculations belong to later components. C01 exposes the provider constraints rather than claiming an order is guaranteed executable.

## Offline development and verification

```sh
python3 -m tradee --db /tmp/tradee-fixture.sqlite3 import tests/fixtures/exchange_info.json
python3 -m tradee --db /tmp/tradee-fixture.sqlite3 universe --members-only
python3 -m unittest discover -v
```

The fixture is a small public Binance response captured during development, not a permanent statement of current trading rules. `import` records receipt now and identifies its file source. Use a separate database for fixtures; imports are trusted developer inputs, not a production authenticity check. No historical effective dates are inferred from a fixture.

Exit codes: 0 for successful commands (including a universe report containing unknown/ineligible records), 1 for errors, 2 for `health` when not all enabled instruments are eligible, 130 for interruption. `health.ready` concerns enabled new-entry eligibility, not the completeness of the entire discovered catalog.

## Planning documents

See [C01 verification](C01_VERIFICATION.md) for measured results, including the completed live TLS-path recheck, and its scope limits.

- [Platform overview](PLATFORM_PLAN.md): scope and agreed implementation order.
- [Component research](COMPONENT_RESEARCH.md): responsibilities, dependencies and evidence.
- [C01 plan](C01_RESEARCH_PLAN.md): C01 decisions, scope and implementation status.
- [Review template](COMPONENT_REVIEW_TEMPLATE.md): future component research.


### C01 regression tests

Run `python3 -m unittest discover -v` for the full offline suite. C01 contributes 80 tests covering validation, historical consistency, database rollback, immutable snapshots, transport failure handling and CLI polling. Tests use temporary databases and mocked transport; they do not contact Binance or alter the runtime database. See [C01_VERIFICATION.md](C01_VERIFICATION.md) for the test map, fixes and verification limits.


## Run C02

C02 uses C01 metadata and its own database (`data/c02.sqlite3`). Offline/REST/archive operations use the standard library. For live WebSockets, install the optional transport:

```sh
python3 -m pip install -e '.[live]'
python3 -m tradee refresh
python3 -m tradee data backfill BTCUSDT --start 2026-09-01T00:00:00Z --end 2026-09-02T00:00:00Z
python3 -m tradee data archive BTCUSDT 2026-08
python3 -m tradee data collect --symbols BTCUSDT,ETHUSDT --streams candle,trade,quote,mark
```

`collect` runs in the foreground until Ctrl-C. It starts separate routed connections as needed and repairs recent candle gaps. The default stream is `candle`; request the others explicitly. No exchange credentials are required. This records data only; it does not issue orders or signals.

Backfill derivatives through `--kind funding` or `--kind open_interest`. Binance endpoint retention limits still apply; a successful request does not establish complete historical coverage. Use `data repair SYMBOL --start … --end …` to revisit a range. Backfill resumes its exact range's saved checkpoint; repair bypasses that cursor.

Pin a historical candle dataset with an explicit availability assumption:

```sh
python3 -m tradee data snapshot --symbols BTCUSDT --start 2026-09-01T00:00:00Z --end 2026-09-02T00:00:00Z --mode modeled --delay-ms 1000
python3 -m tradee data dataset DATASET_HASH
python3 -m tradee data quality DATASET_HASH --as-of 2026-09-02T00:00:01Z
python3 -m tradee data replay DATASET_HASH
python3 -m tradee data bars DATASET_HASH --minutes 15
```

Replace `DATASET_HASH` with the snapshot result. The example's one-second delay is a declared research assumption, **not a measured Binance latency**. Omit `--mode modeled --delay-ms …` for recorded availability. Downloaded historical candles then become available only when actually ingested. Saved datasets are immutable; create a new one to include later repairs.

Replay emits JSON lines in availability order, including revisions and partial updates for recorded datasets. `--as-of` bounds replay/view availability; `--after-id` resumes after a particular event within that saved ordering. `bars` emits only complete finalized aggregates. `quality` exits 2 when the requested candle window is incomplete or stale, and 0 when complete/fresh. This is data readiness, not strategy or trade readiness.

Offline imports are also available:

```sh
python3 -m tradee data import-rest BTCUSDT candles.json
python3 -m tradee data import-ws recorded-messages.jsonl
python3 -m tradee data import-archive BTCUSDT BTCUSDT-1m-2026-08.zip BTCUSDT-1m-2026-08.zip.CHECKSUM
```

Local imports record receipt **now**; JSONL files cannot claim original live receipt times. Use a separate database for fixtures: `python3 -m tradee --db /tmp/c01.sqlite3 data --market-db /tmp/c02.sqlite3 …`. Global C01 arguments go before `data`; `--market-db` goes before its action.

See [C02 implementation contracts and limits](C02_IMPLEMENTATION.md) and [C02 verification](C02_VERIFICATION.md). The full suite now contains 404 passing tests, including C03, C06, C07 and C08. Live exchange connectivity passed on 21 September 2026; sustained recording/load remains an operational check.


## Check Binance connectivity

No Binance API key, secret or `.env` file is needed for the C01/C02 public data feeds. From this repository, run:

```sh
python3 -m tradee.check_connectivity
```

If WebSocket dependencies are missing, first run `python3 -m pip install -e '.[live]'` in your Python environment. The command checks live exchange metadata, three recent closed BTCUSDT candles, funding, open interest, a recent daily archive and its checksum, and both WebSocket routes (candles/trades/mark updates and quotes). It uses the actual adapters with TLS verification, writes only to temporary databases, closes connections and removes those databases afterward. No credentials or account endpoints are used.

Each check emits JSON with `passed: true` or an error. The final line must show `"passed": true`; exit code 0 means all seven checks passed, and 1 means at least one failed or dependent checks were skipped. This is a brief connectivity/ingestion check, not a sustained-uptime test. Running within a sandbox may require network permission.

All seven checks passed locally on 21 September 2026, without credentials.


## C03 feature engine

- [Research and implementation plan](C03_RESEARCH_PLAN.md): dependencies, consumers, baseline feature set, files and build order.
- [Mathematical specification](C03_FEATURE_SPEC.md): formulas, periods, initialization, units, missingness and optional/deferred indicators.
- [Validation plan](C03_VALIDATION_PLAN.md): independent examples, causality, batch/stream parity, recovery and later ablation research.

C03 v1 is implemented. It provides 14 baseline outputs and optional raw indicators, Bollinger bands, candle geometry, session VWAP and top-of-book diagnostics. Features use finalized C02 replay prefixes, explicit UTC boundaries, strict gaps and versioned formula conventions. [Verification and limits](C03_VERIFICATION.md) includes the independent numerical checks and public Binance replay comparison.

From the repository root, use the dedicated environment:

```sh
conda activate tradee
python -m tradee features list
python -m tradee features explain ema20_distance_atr14
python -m unittest discover -s tests -q
```

First create a pinned C02 dataset using the commands above. Substitute its actual hash for `DATASET_HASH`:

```sh
python -m tradee --db data/c01.sqlite3 features \
  --market-db data/c02.sqlite3 --feature-db data/c03.sqlite3 \
  run DATASET_HASH --config configs/c03_baseline.json
python -m tradee features summary RUN_HASH
python -m tradee features manifest RUN_HASH
python -m tradee features snapshot SNAPSHOT_HASH
python -m tradee features lineage LINEAGE_HASH
```

Use `--feature-db` before each action when inspecting a nondefault database. `run` returns the run hash, snapshot counts and latest snapshot hashes. Repeating the same pinned run resumes its atomic checkpoint and does not duplicate outputs. Code, configuration or dataset changes create a different run. A successful command exits 0 even when snapshots are not ready; inspect `ready` and each value's `status`/`stable` fields. Invalid commands/configurations exit 1 with a JSON error.

The baseline uses 15m, 1h, 4h and 1d bars. `1m` is also supported for diagnostics. EMA50 seed stabilization needs **396 contiguous bars at the chosen timeframe**, including 396 days for daily readiness. Keep pre-roll inside the pinned dataset; optional `run --start ISO_TIME --end ISO_TIME` restricts outputs without discarding earlier warm-up inputs. Bounds are timezone-aware and end-exclusive. Missing input and undefined denominators produce JSON nulls with reasons, never invented zero values.

For historical downloads, use an explicitly **modeled** C02 candle dataset with the intended close-to-availability delay. A **recorded** dataset preserves download receipt time; it cannot pretend historical candles were observed live. The configuration separately pins `processing_delay_ms` for assumed feature-processing latency. Actual computation timestamps live outside deterministic snapshot hashes.

An optional quote diagnostic need not block candle readiness: list all desired outputs in `features`, and only mandatory outputs in `required_features`. Quote freshness defaults to strictly less than five seconds. Session VWAP requires every minute from UTC midnight. Quote-only evaluations use the Python API; automatic `run` decisions are triggered by completed requested candle buckets and revisions.

```python
from tradee.c03 import FeatureConfig, FeatureEngine

engine = FeatureEngine(market.dataset(dataset_hash), FeatureConfig())
for event in market.replay(dataset_hash):
    for snapshot in engine.advance(event):
        consume(snapshot.document())  # later strategy/runtime integration
# Explicit context evaluation uses the same current prefix:
# engine.evaluate(instrument_id, "4h", decision_ms)
```

`market`, `dataset_hash`, and `consume` above are caller-provided. `push` ingests without automatic decisions, `evaluate` evaluates that prefix, and `advance` combines ingestion with candle-triggered decisions. C03 opens no Binance connection itself. Prior snapshots remain immutable after a correction; revised evaluations carry `trigger="revision"`.

Opt-in checks (use a fresh benchmark directory):

```sh
python -m scripts.verify_c03 --output data/c03_checks/benchmark_run1
python -m scripts.verify_c03 --live --output data/c03_checks/public_session
python -m scripts.verify_c03 --replay --output data/c03_checks/public_session
```

Only `--live` connects to public Binance endpoints; it captures up to 75 seconds of WebSocket data and requires the existing live dependency. No keys or orders are used. `--replay` rechecks that saved capture offline. This v1 retains candle history and reconstructs derived state, so multi-year/many-symbol throughput needs further optimization and validation. Strategy rules, net-expectancy evaluation and Telegram delivery belong to later components.

## C06 funding accounting

C06 calculates exact signed USDT funding cash flows from settled C02 records and a caller-supplied position quantity timeline. It supports partial quantity changes, estimates the next funding from an available mark observation, preserves later corrections as new reports, and resumes atomic checkpoints. [C06 implementation](C06_IMPLEMENTATION.md) documents schemas, formulas and ownership; [verification](C06_VERIFICATION.md) records actual results.

```sh
conda activate tradee
python -m tradee funding explain
python -m tradee --db data/c01.sqlite3 funding \
  --market-db data/c02.sqlite3 --funding-db data/c06.sqlite3 \
  run DATASET_HASH --positions positions.json --calendar calendar.json
python -m tradee funding summary RUN_HASH
python -m tradee funding report REPORT_HASH
```

The dataset must be recorded and include the relevant funding/mark observations. An explicit settlement calendar is required for a complete total; the result is conditional on its evidence. Missing calendar/rates or ambiguous exposure produce null totals and exit code 2 for `run`. Default strict policy flags quantity changes within ±15 seconds of nominal settlement. Exact unrounded cash flows are calculations for supplied exposure, not reconciliation with actual account transactions. C09 will own executable position state and booking.

Run the current-foundation E2E and retain a manual demo:

```sh
python -m unittest tests.test_c06_e2e -v
python -m scripts.verify_c06 --output data/c06_checks/demo1
```

Use a fresh output directory. The demo runs **26 actual CLI processes/commands** through C01/C02/C03/C06, including recovery in a new process after an injected SQLite write failure. It checks hand-calculated amounts and error scenarios, and leaves databases, raw inputs, positions/calendars, a command log and `e2e_report.json`. It uses synthetic scenarios with no network, orders or credentials. Inspect a demo report with:

```sh
python -m tradee funding --funding-db data/c06_checks/demo1/c06.sqlite3 report REPORT_HASH
```

Get the hash from that demo's `e2e_report.json`. Complete trading and Telegram E2E follow the [platform milestones](PLATFORM_PLAN.md#end-to-end-testing-milestones--agreed-requirement-added-13-october-2026).

The optional public check captures funding records and a mark update, then compares saved replay at its input availability time:

```sh
python -m scripts.verify_c06_live --output data/c06_checks/public1
python -m scripts.verify_c06_live --replay --output data/c06_checks/public1
```

Only the first command needs public Binance connectivity and the existing live dependency. It uses synthetic exposure, not account access or trading.

## Component scope and upgrades

[COMPONENT_UPGRADES.md](COMPONENT_UPGRADES.md) is the maintained register for **all fifteen components**. It distinguishes implemented scope, required unbuilt baseline work, deferred/conditional extensions, validation gaps, dependencies and completion gates. Update it after every component implementation. C06 predictive premium/OI/liquidation work and automated calendar acquisition are recorded there; C07 market execution/cost scope is now implemented; C08 now provides range-breakout and trend-continuation candidates; C09 trade lifecycle, C11 historical simulation/attribution and C10 cohort expectancy are implemented; C12 research control is next.


## C07 execution and tradability

C07 checks proposed market entries/exits against observed rules, fresh quotes/marks, spread, quantity/liquidity budgets, manual delay, expiry and optional required C03 readiness. It returns paper fill prices, explicit taker fees, drift/spread/slippage attribution, cost bps/R and separate next-funding estimates from C06. [Implementation contracts](C07_IMPLEMENTATION.md) and [verification](C07_VERIFICATION.md) document assumptions, formulas and limits.

```sh
conda activate tradee
python -m tradee execution explain
python -m tradee --db data/c01.sqlite3 execution \
  --market-db data/c02.sqlite3 --execution-db data/c07.sqlite3 \
  run DATASET_HASH --intents intents.json --fees configs/c07_fee_assumptions.json \
  --config configs/c07_execution.json --features features.json
```

The intent/feature schemas are in the implementation document. Required C03 artifacts must come from the same pinned dataset. Fee rates are explicit illustrative assumptions, not verified account tiers. The quote preset waits 30 seconds after detection by default. Historical candles need the explicit `c07_modeled_bar.json` preset, which labels synthetic spread, volume/mark proxies and current-metadata assumptions; it does not supply an exact intrabar fill or historical funding forecast.

Exit 0 means all scenarios admitted under the declared model; exit 2 saves rejected scenarios with reasons and null fills; exit 1 means invalid input or operational failure. Admission does not certify a profitable setup. Use `execution report REPORT_HASH`, `manifest RUN_HASH` or `summary RUN_HASH`, with `--execution-db` before the action when inspecting a nondefault database.

Run the connected E2E and retain artifacts for manual review:

```sh
conda run -n tradee python -m unittest tests.test_c07_e2e -v
conda run -n tradee python -m scripts.verify_c07 --output data/c07_checks/demo1
```

Use a fresh output directory. The demo runs 27 real CLI commands/processes through C01/C02/C03/C06/C07, verifies independent buy/sell price/fee/funding amounts, recovers from a failed database write in another process, and exercises delay, expiry, quantity, passive-order, spread and coarse-bar cases. Read `e2e_report.json` and `e2e_commands.json`; inspect reports and repeat a completed command to check unchanged hashes/counts. All prices/exposures/rules are synthetic, with actual import receipt times and no network, orders or Telegram.

The full offline suite has **404 passing tests**, including **58 C07 tests** and **52 C08 tests**. An opt-in public metadata/quote/mark capture also passed direct-versus-persisted replay checks; see verification for exact results. Passive/partial fills, calibrated cost/delay distributions, account reconciliation and richer historical coverage remain in the upgrade register. C08 candidate generation is now implemented; complete trade-ledger E2E arrives at C11 and Telegram E2E at C14.


## C08 range breakout and trend continuation

C08 implements two separate 15m hypothesis families. Range breakout requires a close strictly outside the previous 20 bars' high/low range. Trend continuation requires EMA20/EMA50 direction plus recovery across EMA20 after the prior close was on the pullback side. Shorts use the reverse rules. Each family has independent versions, runs and opportunity inventories. [Research definitions](C08_RESEARCH_PLAN.md), [implementation contracts](C08_IMPLEMENTATION.md) and [verification](C08_VERIFICATION.md) describe formulas, dependencies and results.

```sh
conda activate tradee
python -m tradee candidates list
python -m tradee candidates explain prior_range_breakout
python -m tradee candidates explain ema_pullback_continuation
python -m tradee --db data/c01.sqlite3 candidates \
  --market-db data/c02.sqlite3 --candidate-db data/c08.sqlite3 \
  run DATASET_HASH --strategy configs/c08_range_breakout.json \
  --config configs/c08_candidates.json
```

Run the second family with `configs/c08_trend_continuation.json`. For explicitly modeled historical candles using current metadata as an assumption, choose `configs/c08_modeled_candidates.json`. Observed mode keeps actual metadata/receipt timing. Both presets use a five-minute exclusive entry window and a separate one-minute detection-lag budget. Trend readiness needs 397 contiguous bars because both current and lagged EMA50 must be stabilized.

Inspect `candidates summary RUN_HASH`, `manifest RUN_HASH`, `records RUN_HASH --status emitted`, `evaluation EVALUATION_HASH` and `feature SNAPSHOT_HASH`. Database options precede the action. Paginate all opportunities with `--limit`/`--after-sequence`; warmup, nontrigger, suppression and revision records remain available. Successful zero-candidate runs exit 0; inspect completion, coverage and reasons. A candidate has no invented stops, targets, quantity, probability or proven expectancy.

```sh
conda run -n tradee python -m unittest tests.test_c08_e2e -v
conda run -n tradee python -m scripts.verify_c08 --output data/c08_checks/demo1
```

Use a fresh directory. The E2E imports raw synthetic BTC/ETH paths, processes both default 15m families through real C03 calculations, retains 1616 direction/bar evaluations per family, detects independently expected long/short setups, and recovers in a new process after a failed database write. Raw inputs, bound candidates, SQLite state, command log and `e2e_report.json` remain for manual review. The full suite has **404 passing tests**, including **52 C08 tests**.

C09 now supplies executable paper entry/exit policy, position quantities and one-time fee/funding booking. Full strategy backtests still require C11; walk-forward evidence and promotion require C12. [COMPONENT_UPGRADES.md](COMPONENT_UPGRADES.md) tracks remaining families/horizons, context filters and operational work.


## C09 paper trade lifecycle and outcomes

C09 connects evidence-bound C08 candidates to C07 market fills and C06 settled-funding accounting. It owns fixed stops/targets, optional partial exits, time/invalidation closes, remaining quantities and exact keyed ledgers. Both stop/target event labels and after-cost profit labels remain explicit; unknown funding and incomplete paths produce unresolved labels. [Research decisions](C09_RESEARCH_PLAN.md), [contracts](C09_IMPLEMENTATION.md) and [verification](C09_VERIFICATION.md) document the implementation.

Default policy: 1% reference-price stop, 2R reference target, four-hour hold and contract-trade triggers. These are unoptimized engineering assumptions. Entry retains C07's manual-delay model; exit delay is separately explicit. Candle-only research can select close-only or range triggers, but C07 supplies only an explicitly modeled close execution. A stop/target conflict in one range bar stays unresolved rather than inventing intrabar ordering or a fill price.

```sh
conda activate tradee
python -m tradee lifecycle explain
python -m tradee --db data/c01.sqlite3 lifecycle \
  --market-db data/c02.sqlite3 --lifecycle-db data/c09.sqlite3 \
  run DATASET_HASH --intents intents.json --fees configs/c07_fee_assumptions.json \
  --execution configs/c07_execution.json --funding configs/c06_funding.json \
  --calendar calendar.json
```

Each intent contains the complete emitted candidate, its actual C03 feature artifact, quantity and policy; use the implementation document or generated E2E inputs for the schema. All evidence must share the pinned dataset. Funding calendars remain declared evidence/assumptions. A published next-funding estimate is never booked as settled cash flow.

Inspect `lifecycle summary RUN_HASH`, `manifest RUN_HASH`, `report REPORT_HASH` and `transition TRANSITION_HASH`, with `--lifecycle-db` before the action for nondefault stores. Exit 0 means ready outcomes/valid unfilled cases, 2 means saved unresolved outcomes, and 1 means invalid input or operational failure. Replay completion does not imply every trade has a mature outcome.

```sh
conda run -n tradee python -m unittest tests.test_c09_e2e -v
conda run -n tradee python -m scripts.verify_c09 --output data/c09_checks/demo1
```

Use a fresh directory. The connected E2E runs 22 actual CLI commands through raw imports, real C08/C03 candidates, C07 fills, C06 coverage and C09 outcomes, including recovery after a failed write. Exact synthetic nets are **2.4965 USDT long** and **2.5035 USDT short**, under explicitly overridden zero manual delay, 25bps spread budget and empty synthetic settlement calendars. Raw inputs, configs, SQLite state, `e2e_report.json` and command log remain for manual inspection. At C09 completion, the suite had **404 passing tests**, including **54 C09 tests**; current full-suite results are recorded in [C12 verification](C12_VERIFICATION.md).

The optional [public replay script](scripts/verify_c09_public_replay.py) reuses the retained C08 Binance candle capture and checks direct/persisted lifecycle parity under explicit modeled assumptions. It makes no fresh live-feed or profitability claim. **C11 historical simulation is now implemented**; C10 now provides cohort expectancy from causally available matured outcomes. [The upgrade register](COMPONENT_UPGRADES.md) tracks research, execution/account fidelity and operational work.


## C11 historical simulation and attribution

[Research and component map](C11_RESEARCH_PLAN.md), [implementation and CLI](C11_IMPLEMENTATION.md), [verification](C11_VERIFICATION.md). C11 drives the actual C08/C03 → C07/C06/C09 pipeline for both strategy families, with complete detection inventories, exact deadline ticks, independent trade ledgers, causal outcome revisions, regular marked P&L and matched fee/delay sensitivity.

```sh
conda activate tradee
python -m tradee simulate explain
python -m tradee simulate run DATASET_HASH --scenarios configs/c11_scenarios.json \
  --fees configs/c07_fee_assumptions.json --calendar path/to/declared_calendar.json
python -m tradee simulate summary RUN_HASH
python -m tradee simulate report REPORT_HASH
python -m tradee simulate records RUN_HASH --kind outcome_revision
python -m tradee simulate compare BASELINE_RUN_HASH VARIANT_RUN_HASH
python -m scripts.verify_c11 --output data/c11_checks/demo1
```

The demo requires a fresh directory and runs actual CLI processes from raw imports to both families' BTC long/ETH short outcomes, SQL failure/retry, fee sensitivity, unknown funding, manual delay and immutable reruns. Inputs, database state, command log and `e2e_report.json` remain for manual inspection. Exact fixture nets are **3.456 USDT long** and **4.4445 USDT short per family**, using size 1, explicit synthetic rules, zero manual delay, a 25bps spread gate and empty synthetic settlement calendars. These are engineering fixtures, not evidence of profitability.

Run all tests with `conda run -n tradee python -m unittest discover -s tests -q`. Optional saved public replay: `python -m scripts.verify_c11_public_replay --source data/c08_verification/public1 --output data/c11_checks/public1`. It reuses real Binance candles with explicit modeled assumptions; funding/net remain null.

A completed run can contain unresolved outcomes and exit 2 while retaining its report. Earlier data supplies warm-up; half-open detection windows and the pinned tail define which outcomes are measured. Completed runs publish atomically; interrupted runs restart deterministically. Independent scenarios do not share capital/liquidity and their P&L is not portfolio return/Sharpe. C10 now consumes revision-aware matured evidence; C12 now adds walk-forward isolation and experiment control; C13 enables funded portfolio simulation. Remaining scope stays in the upgrade register.


## C10 cohort expectancy and uncertainty

[Research decisions](C10_RESEARCH_PLAN.md), [implementation and commands](C10_IMPLEMENTATION.md), [verification](C10_VERIFICATION.md). C10 trains from the last C11 outcome revision actually knowable before a cutoff, keeps unresolved/unfilled coverage, matches strategy/policy/cost/feature protocols and estimates broad cohorts with synchronized circular time-block uncertainty. Sparse, stale, incompatible or degenerate evidence abstains.

```sh
conda activate tradee
python -m tradee expectancy explain
python -m tradee expectancy fit --runs C11_RUN_HASH --window path/to/training_window.json
python -m tradee expectancy summary MODEL_HASH
python -m tradee expectancy estimate MODEL_HASH --request path/to/candidate_request.json
python -m tradee expectancy evaluate MODEL_HASH --runs LATER_C11_RUN_HASH --window path/to/later_window.json
python -m scripts.verify_c10 --output data/c10_checks/demo1
```

Use a fresh demo directory. The E2E demo ingests raw Binance-shaped data through production APIs with explicitly injected synthetic receipt clocks, generates 36 genuine simulated trading outcomes across 36 days, fits the default 30-trade/20-bin/10-span C10 gates and scores four separate later candidates through real CLI processes. Inputs, database state, publication-failure recovery evidence, requests and reports remain for manual review. It uses synthetic prices/rules, size 1, zero manual entry delay, assumed fees and empty synthetic funding calendars; it is not a market-profitability experiment.

Training windows contain `start_ms`, exclusive detection `end_ms` and later knowledge `cutoff_ms`. Publication uses actual completion time unless historical research explicitly supplies `--modeled-available-ms`. Frozen inference never reads a candidate's later outcome. Mean net R is conditional on fill and mature evidence; empirical win frequency is not a calibrated probability. `ready` means usable evidence, while `eligible` separately checks a predeclared lower-bound buffer. Neither grants release/trading approval.

The saved-public check, `python -m scripts.verify_c10_public_evidence --source data/c11_verification/public1 --output data/c10_checks/public1`, confirms that modeled candle outcomes with unknown funding cannot become training labels. No new network or credentials are required. **C12 walk-forward and experiment control is now implemented**; [the upgrade register](COMPONENT_UPGRADES.md) tracks real-data validation, optional predictive/calibrated models and later C11/C13/C14 integration.


## C12 walk-forward and experiment control

At the C12 checkpoint, **566 tests passed**, including 64 dedicated C12 tests and its raw-input E2E. See the C13 verification below for the current suite.

[Research and dependency map](C12_RESEARCH_PLAN.md), [implementation and commands](C12_IMPLEMENTATION.md), [verification](C12_VERIFICATION.md). C12 freezes all variants and trial budgets, selects only inside earlier chronological history, purges boundary labels, and evaluates later windows with the frozen C10 model. It checks neighboring parameters and adverse costs, retains failed/rejected trials, and logs final holdout access before reading it.

```sh
conda activate tradee
python -m tradee research explain
python -m tradee research register --manifest path/to/experiment.json
python -m tradee research run EXPERIMENT_HASH
python -m tradee research jobs EXPERIMENT_HASH
python -m tradee research ledger FAMILY_NAME
python -m tradee research open-holdout EXPERIMENT_HASH --reason 'Final policy frozen; first inspection'
python -m tradee research release EXPERIMENT_HASH
python -m scripts.verify_c12 --output data/c12_checks/demo1
python -m scripts.verify_c12 --output data/c12_checks/negative1 --negative-holdout
```

Use fresh demo directories. Both demos should pass engineering verification: the negative mode must produce a research rejection. The connected E2E ingests raw synthetic Binance-shaped inputs through production APIs, generates actual C11 outcomes, runs nested selection across two outer windows, verifies fee/parameter robustness, injects an atomic-write failure and retries, then explicitly opens the sealed final window. Raw receipts, configs, stores, experiment JSON and reports remain for manual inspection. The fixture uses six-outcome/six-span thresholds, four-minute bins, 200 bootstrap draws, zero manual delay, assumed fees and empty synthetic funding calendars; it makes no real-market profitability claim.

The example [experiment JSON](configs/c12_experiment.example.json) deliberately contains unusable placeholder hashes and an unattested development-only holdout. Prepare separate pinned single-protocol C11 sources and honest research-history disclosures before registering a real experiment. Final access is an application-level research control and cannot prevent inspection of raw files outside C12. All frozen releases say `live_approved: false`; C13 shared portfolio risk and funded replay are now implemented. C14’s shadow/paper baseline is now implemented; next is **C15 forward measurement**. Deferred scope is recorded in [the upgrade register](COMPONENT_UPGRADES.md).


## C13 shared portfolio risk and funded replay

At the C13 checkpoint, **636 tests passed**, including 70 dedicated C13 tests and its raw-input E2E. See C14 verification for the current suite.

[Research and formulas](C13_RESEARCH_PLAN.md), [files, API and commands](C13_IMPLEMENTATION.md), [verification and retained E2E](C13_VERIFICATION.md). C13 shares one wallet across assets and intraday/swing strategies, admits compatible tested sizes under risk/collateral/concentration/stress limits, rechecks C07 execution, and books only admitted C09 ledger revisions. It preserves complete reasons, regular equity, exact cash/fee/funding reconciliation, and atomic persistent local reservations.

```sh
conda activate tradee
python -m tradee portfolio explain
python -m tradee portfolio replay --sources path/to/source_pins.json --models MODEL_HASH
python -m tradee portfolio summary RUN_HASH
python -m tradee portfolio report REPORT_HASH
python -m scripts.verify_c13 --output data/c13_checks/demo1
```

`source_pins.json` maps C11 run hashes to report hashes. Each predeclared quantity requires its own compatible C10 estimate; outcomes are never rescaled. Models and sources must be frozen before the test window. The funded runner requires recorded quotes/marks and explicit funding evidence. Defaults are explicit research settings, not validated live account recommendations.

The demo needs a fresh directory and retains raw Binance-shaped BTC/ETH receipts, configs, C01/C02/C10/C11/C12/C13 databases, reports and command logs. It exercises actual production components, simultaneous capital competition, the size ladder, horizon conflicts, later funding/fee accounting, atomic failure/retry and local account CAS. Its synthetic assumptions and reduced research gates establish engineering correctness only.

C13 supports a conservative fully collateralized `leverage: 1` paper proxy. Exchange maintenance tiers/liquidation, live account synchronization and delivery remain upgrades. A counted predeclared capital recipe can receive a C12 `check-portfolio` **compatibility receipt** after logged holdout access; it does not grant portfolio promotion or statistical outperformance evidence. Full nested portfolio-policy inference remains a required gate. All artifacts retain `live_approved: false`. C14’s paper baseline is now implemented. Complete the remaining research/timing/forward/operational gates before actionable trading signals.


## C14 shadow/paper runtime and Telegram

At C14 completion, 717 tests passed, including 81 dedicated C14 tests and its raw-input E2E. Current C15 verification is linked below.

[Research and dependencies](C14_RESEARCH_PLAN.md), [operation and manual Telegram test](C14_IMPLEMENTATION.md), [verification](C14_VERIFICATION.md). C14 consumes a frozen C12/C13 research release, replays the actual recorded production pipeline, and commits its paper book, signal lifecycle and outbox atomically. It rechecks current features/execution/expectancy/risk, retains timeout/crash ambiguity, persists throttles and supports pause/resume/recovery.

```sh
conda activate tradee
python -m tradee signals explain
python -m scripts.verify_c14 --output data/c14_checks/demo1
```

The demo requires a fresh directory and sends no external messages. It retains a real synthetic research release, separate prospective raw BTC/ETH receipts, all databases, paper outcomes, scripted wire messages and delivery audit. The default mode is `shadow`. To manually test real Telegram connectivity, follow the explicit token/test-chat procedure in [C14 operation](C14_IMPLEMENTATION.md#optional-real-telegram-connectivity-smoke); no token is stored in the repository or database.

The optional `paper_test` mode reports **evaluated paper fills**, clearly labelled `NO TRADE INSTRUCTION`. It is not a pre-entry trading alert or a user-fill record. `live` mode remains unavailable. C15 monitoring is now implemented; representative forward evidence, full portfolio-policy validation, validated actionable/manual-entry timing and real-load operational acceptance remain required. Full-prefix rebuilding has explicit resource limits and is not an unlimited 24/7 feed-throughput claim. Deferred work is tracked in [the upgrade register](COMPONENT_UPGRADES.md).

## C15 prospective forward measurement and monitoring

**787 project tests pass, including 70 C15 tests and the complete raw-input E2E.**

[Research and formulas](C15_RESEARCH_PLAN.md), [operation and manual checks](C15_IMPLEMENTATION.md), [verification](C15_VERIFICATION.md). Register frozen monitoring rules before the first C14 cycle. C15 retains admitted funded-paper outcomes and capital-rejected independent shadow outcomes separately, validates label revisions/maturity/money, records paper fees and delivery delays, and reconstructs pinned raw inputs through C11/C13. Scheduled calendar-block reviews assess mean net R and forecast deterioration with a declared family budget and explicit insufficient-evidence states.

```sh
conda activate tradee
python -m tradee monitor explain
python -m scripts.verify_c15 --output data/c15_checks/demo1
```

The fresh-directory demo exercises the complete synthetic C01→C15 workflow through mature outcomes and raw replay, with scripted Telegram acceptance and zero external messages. For real recording, create the C14 session, then `monitor create NAME --session SESSION --policy path/to/policy.json` **before** starting C14 ticks. `monitor watch NAME` retains evidence and requests; `--apply-pauses` explicitly applies local C14 pauses under the frozen rules. It never resumes, sends messages, retrains or places orders. Historical reports and matured exports remain versioned.

The agreed mandatory component sequence is complete within the documented scope. Next is representative recorded-market strategy/forward validation and the remaining research, timing, account and operational gates. Actual fills, a dashboard, advanced drift/replacement and cross-session inference are explicit future work; the default inference settings and short synthetic fixture do not establish profitable setups.
