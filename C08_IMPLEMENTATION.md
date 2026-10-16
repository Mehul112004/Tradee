# C08 candidate generation

Implemented scope authorized 16 October 2026: independent **prior-range breakout** and **EMA pullback continuation** families, both with 15-minute presets. C08 emits immutable setup candidates and retains evaluations for every configured direction at every available completed-bar update, including warmup, rejection and revision diagnostics. [Research definitions](C08_RESEARCH_PLAN.md) give the rationale, alternatives and source evidence; [verification](C08_VERIFICATION.md) records executed checks.

## Component dependencies and files

C08 consumes C01 eligibility/version history, C02's pinned event stream and C03's shared aggregation/indicators. Its core has no network or database connection. C09 will consume setups and define executable trade rules; C11/C14 will drive this same engine with historical/live events. C12 owns trials and promotion. C07 fill/cost modeling and C06 funding are downstream through C09, rather than invented inside setup detection.

| File | Major responsibilities |
| --- | --- |
| `tradee/c08/contracts.py` | `StrategySpec`, `CandidateConfig`, validated immutable `CandidateSpec`, generic immutable `CandidateRecord`; versioned hypothesis rationale and alternatives |
| `tradee/c08/strategy.py` | Strict exact-decimal range breakouts; explicit C03 float64 trend/recovery comparisons |
| `tradee/c08/metadata.py` | Pinned C01 observation timeline/version checks; observed eligibility versus labeled current-metadata assumptions |
| `tradee/c08/engine.py` | Incremental C03 child engine, readiness/timing/context gates, two-direction diagnostics, stable opportunity IDs, cooldown and checkpoints |
| `tradee/c08/store.py` | Separate C08 SQLite schema, feature/lineage evidence, atomic inventory/checkpoint writes, completed-prefix and count integrity, pagination and resume |
| `tradee/c08/cli.py` | Offline strategy catalog/explanation, run and artifact inspection commands |
| `configs/c08_range_breakout.json` | Initial 15m prior-20-bar range strategy |
| `configs/c08_trend_continuation.json` | Initial 15m EMA20/50 pullback/recovery strategy |
| `configs/c08_candidates.json` | Observed metadata, BTC/ETH eligibility, one-minute detection and 30-minute metadata age budgets |
| `configs/c08_modeled_candidates.json` | Explicit current-metadata assumption for historical research |
| `scripts/verify_c08.py` | Actual-process two-family E2E with raw inputs, independent trigger expectations and fault recovery |
| `scripts/verify_c08_live.py` | Opt-in public REST/WebSocket capture; recorded and modeled parity/saved replay for both families |

## Exact family rules

For bar index `t` and range lookback `N=20`:

```text
upper[t] = max(high[t-N], ..., high[t-1])
lower[t] = min(low[t-N], ..., low[t-1])
long  = close[t] > upper[t]
short = close[t] < lower[t]
```

All `N+1` bars must be present and contiguous. The current high/low is excluded. Equality and wick-only touch do not trigger. Range prices/comparisons remain exact decimal strings; current close is the reference price, not a promised entry fill. Repeated breakouts are independent opportunities; position conflicts belong to later components.

For EMA pullback continuation:

```text
EMA_n seed = mean(first n contiguous closes)
EMA_n[t] = EMA_n[t-1] + (2/(n+1)) × (close[t] − EMA_n[t-1])
long  = EMA20[t] > EMA50[t]
        and close[t-1] <= EMA20[t-1]
        and close[t] > EMA20[t]
short = EMA20[t] < EMA50[t]
        and close[t-1] >= EMA20[t-1]
        and close[t] < EMA20[t]
```

C03 supplies current and one-bar-prior EMA20/50 from the current known prefix. The added reusable feature IDs are `ema20_prior` and `ema50_prior`, with minimum 21/51 bars. Their lag adds one bar to seed stability: the default `ema50_prior` is stable after **397 contiguous bars**, under the existing seed-weight threshold `1e-6`. A gap resets C03's contiguous recursive segment. Nominal EMA validity alone cannot authorize a trend candidate.

EMA analytical values/comparisons use C03 float64 conventions. Thresholds serialize as round-trip decimal strings; the source reference close stays exact. Distinct source closes that collapse under float conversion cause a numeric rejection rather than a fabricated crossing. The EMA50 requirement at the previous bar is a readiness policy; the trigger itself uses the current fast/slow relationship and the previous EMA20 recovery boundary.

Both strategies attach C03 `log_return_1` and `atr14` context. Range requires valid/stable `log_return_1`; trend requires all four EMA measurements. Optional ATR/return diagnostics do not add undisclosed filters. No fitted coefficients, volatility/volume thresholds or regime conditions are applied.

## Timing and eligibility

Detection occurs at the C03 snapshot's logical evaluation time after a finalized candle completes/updates the target bucket. This is a replay information-availability convention, not a measurement of CPU/Telegram/human latency. C07/C14 own action delay.

- `detected_ms >= target_end_ms` and the feature cursor must exactly match the current prefix.
- Both presets fix `expires_ms = target_end_ms + 300000`; expiry is exclusive. Late receipt does not extend it.
- Default detection lag is strictly less than 60000ms. A fully completed input replay can legitimately emit no candidates.
- Default metadata age is strictly less than 1800000ms. The allowlist, identity, scope, status, supported metadata and reported onboarding are checked separately from the trigger.
- Default strategy cooldown is zero. If configured, only emitted candidates consume it, independently per instrument and direction. The next candidate's target-bar separation must be at least `cooldown_bars × timeframe`.

Each decision includes rule checks, reasons, `triggered` (or null when context is unavailable), `context_ready`, feature/metadata hashes and source prefix. A trigger can be true while eligibility or timing rejects it. Status is `emitted`, `rejected`, `not_triggered` or `revision_only`; only emitted records contain a candidate.

`context_ready` describes required context/eligibility/timing before cooldown/revision suppression. It is not a profitability score or execution approval. Inventory scope follows configured directions and dataset symbols; it does not imply discovery of every tradable instrument.

## Metadata history, gaps and revisions

Observed mode freezes C01 universe snapshots at dataset start and each accepted observation time through the dataset cutoff, plus all referenced versions. Each decision selects its latest already-known snapshot and independently checks exact age. Status changes or missing-latest-response states cannot be filled from a future snapshot. A snapshot rejected at capture remains conservatively rejected until new metadata evidence arrives; crossing a source-reported onboarding timestamp alone does not promote that frozen state.

Research-assumption mode pins the latest C01 snapshot by the dataset cutoff and labels that assumption in every record/candidate. It can support a historical experiment without asserting that today's rules were known then. Reported onboarding still applies. Historical verified metadata coverage remains future data work.

Partial candles cannot complete a strategy bar. Missing minute constituents prevent aggregation; gaps inside the trigger/EMA window suppress detection until sufficient contiguous context recovers. Summary coverage reports the expected complete buckets through `min(dataset.end, dataset.cutoff)`, represented buckets, missing counts and a bounded sample. A consumed dataset is not automatically a complete market history. For a late-filled older bucket, C03 may reevaluate the latest target; coverage does not fabricate a decision for that missed historical bucket.

Recorded corrections produce new `revision_only` diagnostics and update later-bar context. They cannot create a second candidate at an old target or rewrite earlier serialized decisions/cooldowns. C09 must separately decide how new facts affect an active trade.

C02 **modeled** datasets select the latest finalized source vintage at their cutoff and assume a configured close-time availability. A new modeled vintage can therefore produce different hypothetical prior decisions. This is distinct from receiving a late correction in recorded replay; the original pinned dataset/inventory remains immutable in both cases.

## Candidate and artifact contracts

A candidate contains:

- Stable `candidate_id`/opportunity key from strategy hash, full instrument identity, timeframe, target bar and direction; hypotheses never share identity.
- Family/strategy version identity, symbol, long/short side, target open/end, detection and exclusive expiry.
- Exact source reference price, trigger level, context start/end and either prior high/low boundaries or previous/current EMA context.
- Actual C03 snapshot hash, metadata snapshot hash, full input cursor/prefix hash and recorded/modeled/metadata evidence labels.

A candidate contains no stop, target, quantity, leverage, success probability or expected return. `CandidateSpec.from_dict` validates its schema, identity, chronology and directional predicate and preserves defensive immutability. Source hashes provide integrity, not authentication for arbitrary externally authored JSON.

Every direction/bar evaluation is a separate immutable `CandidateRecord`, even when no candidate exists. It includes an ordered per-run sequence and reasons. Corrected diagnostics share the opportunity key with the original target/direction; each evaluation hash identifies its precise prefix/result. The complete inventory supports later gate/cost/opportunity-loss analysis.

Each run manifest pins the full strategy definition/rationale/alternative, strategy hash, eligibility config, C02 vintage, C01 snapshots/versions, C03 feature manifest and definition hashes, production source-tree hash, Python version and timing/numeric policies. Changing a family, parameter, config, metadata evidence, dataset or code creates a new run. C08's definition catalog is not the C12 experiment/trial registry.

## Persistence and CLI

The separate database defaults to `data/c08.sqlite3`, application C08/schema 1. Evaluation/feature/lineage writes and corresponding checkpoint commit atomically. Checkpoints preserve C03 canonical source/replay state, opportunity/emission counts and per-direction cooldown state. Restore checks compatibility, counters and retained context. Completed status requires every pinned input to have been consumed; saved inventory counts must match the checkpoint. Computation wall time is operational metadata outside deterministic record hashes.

```sh
conda activate tradee
python -m tradee candidates list
python -m tradee candidates explain prior_range_breakout
python -m tradee candidates explain ema_pullback_continuation
python -m tradee --db data/c01.sqlite3 candidates \
  --market-db data/c02.sqlite3 --candidate-db data/c08.sqlite3 \
  run DATASET_HASH --strategy configs/c08_range_breakout.json \
  --config configs/c08_candidates.json
python -m tradee --db data/c01.sqlite3 candidates \
  --market-db data/c02.sqlite3 --candidate-db data/c08.sqlite3 \
  run DATASET_HASH --strategy configs/c08_trend_continuation.json \
  --config configs/c08_candidates.json
```

Run each family separately so its source/config/inventory is explicit. For an explicitly modeled historical dataset, select `configs/c08_modeled_candidates.json` if current metadata is a research assumption. This policy does not silently change C02 availability mode.

```sh
python -m tradee candidates summary RUN_HASH
python -m tradee candidates manifest RUN_HASH
python -m tradee candidates records RUN_HASH --status emitted --limit 100
python -m tradee candidates records RUN_HASH --after-sequence 100 --limit 100
python -m tradee candidates evaluation EVALUATION_HASH
python -m tradee candidates feature SNAPSHOT_HASH
python -m tradee candidates lineage LINEAGE_HASH
```

Use `--candidate-db` before the action when inspecting a nondefault database. Inventory pages are ordered by per-run sequence, maximum 1000 records per page; use returned `next_sequence` until a page is empty. A feature command returns a complete C03 artifact suitable for downstream same-dataset joins. Follow lineage parent hashes to inspect contributing sources.

Exit **0** means a valid command/replay, including normal zero-candidate runs; inspect `completed`, status/reason counts and coverage. Exit **1** means invalid input or operational failure. There is no performance-based success code. No credentials are required by C08.

## E2E and manual review

```sh
conda run -n tradee python -m unittest tests.test_c08_e2e -v
conda run -n tradee python -m scripts.verify_c08 --output data/c08_checks/demo1
```

Use a fresh output directory; omitting output uses temporary artifacts. The actual CLI imports synthetic BTC/ETH mirror paths, with 404 fifteen-minute bars per symbol, and runs both families. Each family retains **1616 direction/bar evaluations**. Expected range candidates occur at bars 402/403 (BTC long/short; ETH short/long). Expected trend candidates occur at bar 401 (BTC long, ETH short). Warmup/nontrigger/rejection records remain inspectable. A real SQLite statement failure after the first committed prefix is recovered by a new CLI process; reruns preserve hashes/counts.

The demo also checks C03 prefix/lineage inspection, inventory pagination, current metadata exclusion from observed historical decisions, recorded revision-only handling, different modeled source vintages and immutable original candidates. Raw inputs, configs, command log, SQLite databases and `e2e_report.json` remain for review. Compare the exact candidate bars/directions/prices, inspect all rejected/warmup opportunities and repeat a completed command. No strategy outcome or trading ledger is produced yet.

```sh
conda run -n tradee python -m scripts.verify_c08_live --output data/c08_checks/public1
conda run -n tradee python -m scripts.verify_c08_live --replay --output data/c08_checks/public1
```

The optional capture uses public Binance metadata, enough minute history for 400 completed 15m bars, and three candle WebSocket messages. Both families compare direct evaluation with persisted replay in recorded and explicitly modeled modes. Current-metadata assumptions stay labeled; no candidate count is interpreted as an edge. Avoid editing production source during a verification run; use saved replay after code changes. [Verification](C08_VERIFICATION.md) contains actual results and [the upgrade register](COMPONENT_UPGRADES.md#c08-candidate-generation) tracks additional families/horizons, context filters, scale, live invalidation and downstream cost/outcome validation.
