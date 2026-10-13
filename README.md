# Tradee

Component-based crypto signal research. **C01 is implemented:** instrument identity, trading rules and metadata history. Subsequent components add market data, features, strategies, backtests and Telegram delivery.

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
