# C06 funding accounting

Implemented scope authorized 13 October 2026: exact funding accounting for Binance crypto USDT perpetual futures, observed next-settlement estimates, explicit coverage and boundary policies, immutable reports, checkpoints, CLI and E2E tests. C06 consumes C02 data bound to C01 identities. C07 consumes estimates, C09 owns position state and booking, and C11 consumes funding outcomes in historical simulation. Optional derivatives predictors are tracked in [COMPONENT_UPGRADES.md](../../platform/COMPONENT_UPGRADES.md#c06-funding-and-derivatives-context).

## Formula and provider evidence

For linear USDT exposure, the unrounded cash flow received by the position is:

`cashflow_USDT = -side_sign × base_quantity × settlement_mark_price × settled_funding_rate`

`side_sign` is +1 for long and −1 for short. Rate is a fraction, so `0.0001` means 0.01%. Positive output is received; negative output is paid. Quantity is the base-asset quantity in the instrument's quoted units, not margin or a leverage multiplier. A `1000...` instrument uses its own exchange quantity and price units. Use the mark associated with that settlement, not entry, index or contract-candle price. Do not multiply the supplied settled rate by the funding interval again.

Binance documents position value times funding rate, variable funding intervals and a 15-second deviation in actual transaction timing. C06's symmetric ±15-second ambiguity guard is our conservative modeling choice; it is not an exchange ordering guarantee. [Binance funding explanation](https://www.binance.com/en/support/faq/detail/360033525031), checked 13 October 2026.

Funding history supplies `fundingTime`, `fundingRate` and the associated `markPrice`. The funding-info endpoint describes interval/cap adjustments; current information is not historical calendar evidence. C02 already normalizes funding history. [Official REST market-data reference](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#get-funding-rate-history).

Mark updates supply mark/index prices, the published funding rate and next funding timestamp. C06 treats this observation as an estimate for that next timestamp, never as a settled charge. [Official mark-stream reference](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market#mark-price-stream).

C06 deliberately consumes published inputs rather than reconstructing funding from premium samples/caps whose historical rules and coverage are unavailable. That extension needs its own data/evidence contract.

## Files and dependencies

| File | Responsibility | Dependencies and consumers |
| --- | --- | --- |
| `tradee/c06/contracts.py` | Frozen quantity timelines, settlement calendars, config and exact cash-flow arithmetic | Standard library, C01/C02 validation; supplied to future C07/C09/C11 |
| `tradee/c06/engine.py` | Exact replay prefix, latest settlement revisions/mark context, coverage, deterministic reports and checkpoints | Contracts and C02 event schema; no exchange connection |
| `tradee/c06/store.py` | Separate SQLite schema, immutable manifests/reports, atomic checkpoint and resume | Engine, C02 replay and C01 metadata evidence |
| `tradee/c06/cli.py` | Explain, run, report, manifest and summary | Store and explicit JSON input files |
| `configs/c06_funding.json` | Strict boundary policy, 15000ms guard and 5000ms mark freshness | Pinned in every run manifest |
| `scripts/verify_c06.py` | Offline raw-import-to-report E2E with reviewable artifacts | Real C01/C02/C03/C06 CLI processes |
| `scripts/verify_c06_live.py` | Opt-in public funding/mark capture and saved replay check | Existing public C01/C02 adapters; synthetic exposure only |
| `tests/test_c06_math.py` | Independent numeric, sign, precision and schema expectations | Pure contracts |
| `tests/test_c06_engine.py` | Prefix, estimates, calendars, boundaries, corrections and restore | Engine |
| `tests/test_c06_persistence.py` | C02 integration, rollback, idempotency, immutable sources and corruption | Actual isolated C01/C02/C06 stores |
| `tests/test_c06_cli.py` | CLI error/schema and explain behavior | Public command entry point |
| `tests/test_c06_e2e.py` | Automated current-foundation E2E | Separate actual CLI processes, no internal mocks |

## Exact numeric and identity contract

Input prices, quantities and rates use validated decimal strings or integers, never binary floats. Arithmetic uses a local Decimal precision of 400 with traps for rounding/inexact results; it does not inherit a caller's low-precision context. Outputs are canonical decimal strings. No epsilon, clipping, per-settlement currency rounding, interest annualization or leverage factor is introduced. True zero serializes as `"0"`; unresolved amounts are JSON null.

The store verifies C01 evidence for crypto USDT perpetual identities and the metadata attached to funding/mark observations. Public source metadata observed today does not prove historical rule validity. Unsupported products, ambiguous identity and mismatched metadata fail closed. C06 does not currently reconcile account income or assert exact wallet debits/credits.

## Position quantities and settlement boundaries

`PositionTimeline` has a stable position ID, full instrument ID, symbol, fixed side, and strictly ordered quantity changes. A change declares the resulting base quantity, not a fill delta. Zero means closed/flat. Initial state before the first change is zero; a change before the dataset start supports a carried position. Quantity changes must actually alter exposure and cannot share a timestamp.

C09 will generate these records from its shared lifecycle. For now callers supply historical exposure evidence or explicit synthetic scenarios. The full timeline is an accounting input, not an automatically generated trade or source of predictive features.

- **Strict, default:** any quantity change within inclusive ±`boundary_guard_ms` of a settlement makes that cash flow `boundary_ambiguous`, with null amount. Strict guard cannot be below 15000ms. This includes opens, partial changes and closes.
- **Nominal, explicit:** use post-change quantity at the settlement timestamp: an entry at that time is exposed and an exit at that time is flat. This is a documented simulation convention for sensitivity checks, not reconciliation with actual exchange ordering.

A quantity change can lie just after nominal settlement and still cause strict ambiguity. Accounting can inspect the supplied full exposure timeline; estimate calculation uses only quantity at its decision time and assumes it persists unchanged through the next funding. Future quantity changes do not alter that estimate.

## Coverage and calendars

C06 never assumes every instrument settles every eight hours. Actual settlement records retain their timestamps, including irregular changes. A `SettlementCalendar` declares the expected timestamps over an explicit `[start_ms,end_ms)` interval and names its evidence or operator assumption.

A complete total requires a calendar covering the report window. Completion is labeled **`complete_under_declared_calendar`**, conditional on that evidence. The calendar is not automatically certified by C06, and observed timestamps alone cannot prove that nothing is missing.

| Situation | Report behavior |
| --- | --- |
| No calendar or incomplete calendar range | `unknown_schedule`; known subtotal retained, total null |
| Observed settlement absent from a covering calendar | `schedule_conflict`; total null |
| Expected settlement with nonzero exposure but no available record | `missing_settlement`; total null |
| Quantity ambiguous near settlement | `boundary_ambiguous`; amount/total null |
| Unambiguously flat at an expected settlement | `not_exposed`; amount zero without requiring a rate |
| Available record with zero rate | Valid zero charge, distinct from missing information |
| All calendar checks/amounts resolved | Complete total and ready report under the declared calendar |

Reports include only economic settlement times in `[dataset.start_ms, min(dataset.end_ms, evaluation_as_of_ms+1))`. An evaluation at an exact settlement millisecond can include it if the record is already available in that prefix. Expected later times do not create a premature missing-data error. Reports describe this window, not automatically the entire lifetime of an open position.

## Information availability and corrections

C06 requires a pinned **recorded** C02 dataset and consumes `(available_ms,event_id)` order. C02's modeled mode remains candle-only. Historical funding downloaded today can be used as later outcome evidence, but cannot become a forecast known before download. Settlement economic time and source availability/recognition are separate report fields.

`push(event)` ingests one normalized observation. `context(position, when)` estimates the next known funding only from the newest event-time mark already in the prefix. Its event age must be strictly less than `max_mark_age_ms`, and `next_funding_ms` must be strictly after `when`. Missing, stale and expired estimates produce null amounts. Estimates remain separate from settled cash flows and cannot add another booked charge.

The engine refuses backward/future-prefix evaluation and events beyond its pinned decision horizon. Same-millisecond event IDs preserve the exact known prefix. Older late mark observations cannot refresh a newer mark. Only one newest mark per instrument is retained; funding records retain the latest available revision per instrument/timestamp.

Each cash flow has a stable `cashflow_key` from position/instrument/settlement identity and a `revision_hash` for its current exposure/source/amount. Reevaluation time does not change that revision hash. Corrections replace the current amount in a newly materialized report; prior immutable reports remain available. A C09 ledger must reconcile the old amount to the new one by replacement/delta, never book a second full charge. C06 produces records; C09 owns that ledger transaction.

## Persistence and operation

C06 uses its own database (`data/c06.sqlite3`, application/schema identifier C06/1). Run manifests pin dataset/source vintage, exposure timelines, calendar evidence, config, formula/sign convention, Python version, source-tree hash and decision horizon. Reports include prefix cursor/hash and settlement provenance. Checkpoints retain latest funding/mark evidence, cursor, prefix hash, event count and evaluation clock. Restore verifies compatibility and reconstructs state without pickle.

Each checkpoint and corresponding report commit atomically. Repeating a completed run resumes the pinned cursor and does not duplicate artifacts. An injected SQL write failure rolls back both. Config, dataset, positions, calendar, decision time or production code changes create another run. Report computation wall time is SQLite operational metadata, excluded from deterministic hashes.

CLI examples, from the repository root in `tradee`:

```sh
python -m tradee funding explain
python -m tradee --db data/c01.sqlite3 funding \
  --market-db data/c02.sqlite3 --funding-db data/c06.sqlite3 \
  run DATASET_HASH --positions positions.json --calendar calendar.json \
  --config configs/c06_funding.json
python -m tradee funding summary RUN_HASH
python -m tradee funding manifest RUN_HASH
python -m tradee funding report REPORT_HASH
```

`--market-db`/`--funding-db` precede the action; use the same funding path when inspecting a nondefault store. Optional `--as-of` is a timezone-aware ISO timestamp, bounded by the pinned dataset cutoff; default is that cutoff. `--batch-size` controls checkpoint frequency.

Exit 0 means a successful command and, for `run`, a ready funding report. Exit 2 means the report was saved with unresolved coverage/cash flows; inspect its statuses. Exit 1 means invalid input or operational failure. No secret file, account access, Binance connection or actual orders are required by the funding CLI.

### Input schemas

Positions file:

```json
{
  "schema_version": 1,
  "positions": [{
    "position_id": "paper-trade-1",
    "instrument_id": "REPLACE_WITH_FULL_C01_INSTRUMENT_ID",
    "symbol": "BTCUSDT",
    "side": "long",
    "changes": [
      {"at_ms": 1788220860000, "quantity": "2"},
      {"at_ms": 1788227940000, "quantity": "1"},
      {"at_ms": 1788235140000, "quantity": "0"}
    ]
  }]
}
```

Calendar file for a synthetic five-hour window, with intentionally variable intervals:

```json
{
  "schema_version": 1,
  "calendars": [{
    "instrument_id": "REPLACE_WITH_SAME_FULL_C01_INSTRUMENT_ID",
    "symbol": "BTCUSDT",
    "start_ms": 1788220800000,
    "end_ms": 1788238800000,
    "settlement_times_ms": [1788224400000, 1788228000000, 1788235200000],
    "evidence": "operator_assumption:synthetic-example-only"
  }]
}
```

These are synthetic exposure/calendar examples, not Binance schedule claims or trade recommendations. The E2E demo below generates files with real fixture-derived identity bindings, so they can be run without editing placeholders.

## E2E and manual acceptance

```sh
conda run -n tradee python -m unittest tests.test_c06_e2e -v
conda run -n tradee python -m scripts.verify_c06 --output data/c06_checks/demo1
```

Use a fresh output directory. The second command leaves SQLite databases, raw fixture files, positions/calendars, a command log and `e2e_report.json` for manual review. Without `--output`, the demo runs in a temporary directory and cleans up.

The test runs the real CLI in separate processes: import C01 metadata; import C02 raw candles/funding/mark messages; pin datasets; produce C03 features; inject a real SQLite failure after the first funding batch commits; recover in a new CLI process; compute reports; rerun; import a correction; prove the original pinned result is unchanged. It also checks unknown calendars, missing expected settlements and settlement-adjacent entry ambiguity. Internal components are not mocked. Candle feature replay is explicitly modeled; funding evidence remains recorded. No source receipt times are backdated. The fault test is a statement failure, not a physical disk or power-loss test.

For the hand-calculated fixture:

- Long: 2 units at mark 100/rate +0.001 pays 0.20; later 1 unit at mark 120/rate −0.002 receives 0.24; closed before the last settlement. Net funding **+0.04 USDT**.
- Short: 3 units held across both nonzero settlements receives 0.30 then pays 0.72. Net funding **−0.42 USDT**.
- A later first-rate correction to +0.0015 changes totals to **−0.06** and **−0.27**, while the old dataset/reports keep their original values.

Manual review: read `e2e_report.json`; use its report/run hashes with `funding report/manifest`; inspect each quantity, source, signed amount and coverage status; rerun a listed completed funding command and confirm unchanged hashes/counts; inspect the missing/boundary reports and confirm null totals. This is current-foundation E2E through C06. Strategy detection, executable fills/P&L and Telegram still require C07–C15.

Opt-in external smoke:

```sh
python -m scripts.verify_c06_live --output data/c06_checks/public1
python -m scripts.verify_c06_live --replay --output data/c06_checks/public1
```

The first command uses public C01/C02 adapters to capture three recent funding records and a mark update, with synthetic 0.001-unit exposure. It requires the existing optional live dependency and network access. The second replays that saved capture offline. Neither accesses an account or places an order. Actual run results and remaining limitations are in [C06_VERIFICATION.md](C06_VERIFICATION.md).
