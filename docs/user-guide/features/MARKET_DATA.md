# Historical market data, snapshots and quality

**Location:** Data quality; Operations → Research & data jobs → backfill / dataset snapshot. **Access:** viewer for inspection; operator plus worker for UI writes. **Prerequisites:** [registered instruments](INSTRUMENT_REGISTRY.md) and an intentional date range.

Collection appends observations. A **dataset snapshot** freezes a symbol/range/type/knowledge selection for reproducible features and research. New observations do not silently change an existing dataset hash.

## Backfill and freeze

The following is a small candle-only example, using actual ISO UTC timestamps. It contacts public Binance REST endpoints and writes the default C02 store:

```sh
conda activate tradee
python -m tradee refresh
python -m tradee data backfill BTCUSDT \
  --start 2026-10-01T00:00:00Z --end 2026-10-02T00:00:00Z
python -m tradee data snapshot --symbols BTCUSDT --kinds candle \
  --start 2026-10-01T00:00:00Z --end 2026-10-02T00:00:00Z
```

Copy `dataset_hash` from the snapshot output, then replace `DATASET_HASH` below:

```sh
python -m tradee data dataset DATASET_HASH
python -m tradee data quality DATASET_HASH
python -m tradee data bars DATASET_HASH --minutes 15
```

Historical REST receipt occurs **now**. This example is suitable for learning data/quality commands; it does not certify past availability, past instrument rules or a full historical execution/funding path. A candle-only dataset cannot establish recorded quote fills or trade-trigger coverage.

## Other inputs and controls

`backfill --kind funding` and `--kind open_interest` request their supported REST histories. The archive workflow uses `data archive SYMBOL YYYY-MM-DD` or a supported month and verifies its checksum. Recorded trades/quotes/marks come from [live collection](LIVE_COLLECTION.md), not fabricated historical quote reconstruction. Use `python -m tradee data --help` for import/repair options.

For a recorded execution dataset, declare the needed kinds explicitly, e.g. `--kinds candle,quote,mark,trade,funding`. Selection is not proof those observations exist. Review its quality/coverage and independently declared funding calendars before claiming net outcomes.

The dashboard backfill/snapshot range is capped at **31 days per job**. Dates in UI JSON use epoch milliseconds; CLI `--start`/`--end` use timezone-aware ISO strings. A wider history requires deliberate bounded jobs and later validated selection.

## Read Data quality

Choose a dataset, inspect finalized/missing UTC-day minute counts, gaps, revisions, recent collector receipts and the pinned contract. A green candle coverage cell does not prove complete quotes/trades or continuously observed metadata. A provisional candle is not a finalized decision bar.

If no datasets appear, create a snapshot after acquisition and confirm the workspace paths. If quality is unready, inspect missing evidence; do not replace unknown rows with zeroes.

Related: [charts](MARKETS_AND_CHARTS.md), [features](FEATURE_ENGINE.md), [C02 operation](../../components/c02/C02_IMPLEMENTATION.md).
