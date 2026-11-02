# C05 price-structure prerequisites

Implemented 1 November 2026 as prerequisites for the three proposed pilot families. C05 supplies causal price references and descriptive relationships. Sweep/rejection/retest triggers, confluence, entries, stops, targets, level ranking and trade invalidation remain for the next pass.

## Scope and contracts

`StructureEngine` uses C02 observations and C03 complete-bar aggregation. It emits immutable `LevelSnapshot` records when an available complete configured candle changes. `StructureConfig` versions the construction settings:

| Family | Definition and availability |
| --- | --- |
| Previous day high/low | Entire completed UTC day before the target bar's exclusive end; every constituent minute required. At midnight close the just-completed day becomes the previous day. |
| Previous week high/low | Entire completed Monday 00:00–Monday 00:00 UTC week before target end; every constituent minute required. |
| Prior range high/low | Extremes of N contiguous prior output-timeframe bars, excluding current; default N=20. |
| Confirmed swing high/low | Strict extremum against all configured left/right neighbors; default 2 left and 2 right. Ties excluded; confirmation window must be contiguous. |

Period references use C02 minutes independently of output timeframe. Missing constituent minutes suppress that family with `anchor_incomplete`; startup fragments never become complete days. Levels remain separate by instrument, source timeframe and kind. Up to 20 recent confirmed pivots per side are retained. Pivots remain historical references after price crosses them; future policy decides which are tradable. There is no proximity merging or hidden “key level” selection.

Each level has stable `level_id`, `revision_hash`, exact decimal `price`, source span/digest, anchor, market-time `confirmed_ms` and source-availability `known_ms`. Swings become confirmed at the rightmost required bar's exclusive end, and knowledge also waits for the latest available source in the whole window. A correction creates a new current version and may remove/reclassify a pivot; prior snapshots remain unchanged. Recorded corrections cannot backdate knowledge. Modeled availability remains labeled as an assumption.

## Relationships and readiness

Relationships report exact close/high/low comparisons, signed price distance, optional ATR14-normalized distance and the previous contiguous bar's close relation. Intrabar touch/high/low/previous-close observations are null unless the current level version was known by current bar open. Newly confirmed pivots and just-completed day levels cannot retrospectively authorize touches during their confirmation candles.

`distance_atr14_status` and `atr14_stable` remain independent of level existence. Zero/missing ATR does not produce a fabricated normalized distance. No touch tolerance, rejection threshold, sweep classification or retest state machine is implied. Candle levels do not establish actual stops or institutional intent.

`ready` means the target is fresh and at least one reference exists. **It does not certify every requested family or strategy eligibility.** Consumers must check family `coverage`, timing and required normalization. Period anchors explicitly use `target_end_ms`; late historical downloads remain `stale_input` rather than current observations.

## Operation and integration

```sh
python -m tradee structure explain
python -m tradee structure run DATASET_HASH --config configs/c05_observations.json
python -m tradee structure summary RUN_HASH
python -m tradee structure records RUN_HASH --limit 20
python -m tradee structure snapshot SNAPSHOT_HASH
python -m tradee structure manifest RUN_HASH
python -m tradee structure lineage LINEAGE_HASH
```

Global `--db` precedes `structure`; `--market-db` and `--observation-db` precede its subcommand. Default output is `data/c05.sqlite3`. C03/C04/C05 database identities are distinct. Optional config output limits retain earlier warm-up history. Pagination uses `--after-sequence` and returned `next_sequence`.

Historical/live callers share `StructureEngine.advance(event)`. Snapshots embed C03 evidence and pin the C02 prefix. Output/lineage/checkpoint transactions commit together; restart follows replay order without duplicate records. Completed replay is not proof of complete market coverage.

The existing analysis-session level adapter now calls the same `reference_levels` helper, preserving its display subset and labels. It retains recorded source availability as `known_ms`; native history without an availability field uses modeled close-time availability. Its supplied prefix is selected by the live feed's knowledge cutoff. Exploratory display does not acquire canonical materialized-run provenance. No pilot strategy is registered in C08 or analysis sessions; C09/C11/C14 trading policies are unchanged. Strategy integration is the next pass.

No predictive C06, account access or orders are added. Existing funding accounting remains available. Multi-year performance and predictive usefulness require separate measurement. See [verification](C05_VERIFICATION.md) and [C04](../c04/C04_IMPLEMENTATION.md).

The next detector pass must preserve the existing quick Watch live / Scan history entry point. Its data preparation, saved observations and notification lifecycle are documented in [Quick analysis flow](../../dashboard/ANALYSIS_FLOW.md), including the required native-history/C02 bridge and the distinction from frozen research/paper releases.
