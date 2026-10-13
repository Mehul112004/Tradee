# Tradee

Component-based crypto signal research. **C01, C02 and C03 are implemented:** instrument metadata, market-data replay and causal mathematical features. Funding, strategies, backtests and Telegram delivery follow.

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

See [C02 implementation contracts and limits](C02_IMPLEMENTATION.md) and [C02 verification](C02_VERIFICATION.md). The full suite contains 196 passing tests, including C03. Live exchange connectivity passed on 21 September 2026; sustained recording/load remains an operational check.


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
