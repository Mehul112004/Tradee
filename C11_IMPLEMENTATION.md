# C11 implementation and operator contract

C11 runs frozen independent C08 candidate scenarios through shared C09 lifecycles, C07 execution and C06 funding. [Research decisions](C11_RESEARCH_PLAN.md) define dependencies, formulas and limits; [verification](C11_VERIFICATION.md) records evidence.

## Files and responsibilities

| File | Main contents | Depends on / used by |
| --- | --- | --- |
| `tradee/c11/contracts.py` | Strict immutable `Scenario`, `SimulationConfig`, record contracts; names, size, strategy/policy versions, window and resource budgets | C08/C09 contracts; engine, store, CLI and future C12 callers |
| `tradee/c11/engine.py` | `Simulator`, immutable `SimulationResult`, two replay passes, exact deadline clock, full candidate/feature/lineage inventory, lifecycle integration, causal revisions and regular samples | C01–03/C06–09; C11 store, tests, C10/C12/C15 consumers |
| `tradee/c11/analysis.py` | Quantity and monetary reconciliation, shortfall attribution, mature-only statistics, stratified summaries, fresh mark valuation and regular P&L drawdown | C06/C07 numeric contracts and C09 evidence; simulator/store/report consumers |
| `tradee/c11/store.py` | Dedicated SQLite identity/schema, one-transaction completed publication, hash checks, paged artifact reads, idempotent reuse and matched fee/execution comparison | C02 snapshots/C08 metadata capture and simulator; CLI and later research orchestrators |
| `tradee/c11/cli.py` | JSON input/output, offline explanation, run/manifest/report/summary/artifact/records/compare commands | Registered by `tradee/cli.py` |
| `configs/c11_scenarios.json` | Both 15m families, four-hour policies, explicit illustrative size | Recorded quote/contract-trade baseline; edit and freeze for each experiment |
| `configs/c11_simulation.json` | 60-second grid, 5-second valuation freshness and explicit resource budgets | Simulator configuration |
| `scripts/verify_c11.py` | Raw-import, actual-process, two-family/direction E2E with literal P&L and failure injection | Production CLI, real isolated SQLite stores |
| `scripts/verify_c11_public_replay.py` | Retained public Binance candle replay, both detectors, modeled entry/exit and unknown net labels | Existing saved C02 capture; no new network |

The shared immutable record contract in `tradee/c03/contracts.py` now caches its digest behind the existing read-only property. This avoids repeatedly hashing the full pinned Binance metadata universe; document copies remain independent and the canonical digest value is unchanged.

No new production dependency, account credential, notification or order submission is introduced. Files use the existing Python standard-library and exact Decimal400 money policy; diagnostic ratios round to 12 decimals.

## Run and inspect

Use an existing pinned recorded C02 dataset containing candles, quotes, marks and the declared trigger feed. Funding rows and independently declared calendars are needed for complete net outcomes. C01/C02/C11 paths must differ. The preset quantity is an illustrative caller-supplied base-asset amount, not capital-based sizing; exchange lot/notional/liquidity checks can reject it, especially across symbols. There is no automatic upward resizing.

```sh
conda activate tradee
python -m tradee simulate explain
python -m tradee --db data/c01.sqlite3 simulate --market-db data/c02.sqlite3 \
  --simulation-db data/c11.sqlite3 run DATASET_HASH \
  --scenarios configs/c11_scenarios.json --fees configs/c07_fee_assumptions.json \
  --calendar path/to/declared_calendar.json
python -m tradee simulate summary RUN_HASH
python -m tradee simulate manifest RUN_HASH
python -m tradee simulate report REPORT_HASH
python -m tradee simulate records RUN_HASH --kind candidate_decision --limit 100
python -m tradee simulate records RUN_HASH --kind outcome_revision --scenario range_intraday
python -m tradee simulate records RUN_HASH --kind sample
python -m tradee simulate artifact ARTIFACT_HASH
```

For custom databases, use the same `--simulation-db` for inspection. Read all pages using `has_more` and `--after-sequence NEXT_AFTER_SEQUENCE`; 100 is the default page size and 1000 the maximum. No CSV export dependency is required: CLI JSON contains complete outcomes, full ledgers and causal revision history. Artifact kinds are `candidate_decision`, `feature`, `lineage`, `lifecycle_manifest`, `transition`, `outcome_revision` and `sample`. Per-scenario samples include source cursor/hash, mark evidence and missing coverage; combined samples have null scenario and explicitly identify independent-scenario scope.

Scenario collections use `{"schema_version":1,"scenarios":[...]}`. Each item requires a unique name, a C08 strategy object, a C09 policy object and positive quantity; `horizon` is `intraday` or `swing`. To study swing, freeze a scenario with an appropriate declared holding limit (for example 48 hours), sufficient input/outcome tail and the `swing` label; the label itself does not change policy or automatically validate that horizon. The two shipped presets are engineering intraday baselines, not optimized configurations.

Optional `--candidates`, `--execution`, `--funding` and `--config` JSON files are frozen into the manifest. Candidate and execution universe/metadata policies must agree. `decision_start_ms` and `decision_end_ms` select **detection** in `[start,end)`, while earlier data remains warm-up and subsequent pinned data supplies outcomes. Default window is dataset start through `min(end_ms,as_of_ms+1)`. Samples run through `as_of_ms`; a last sample is not invented if the cutoff falls between grid points. Pending outcomes remain visible at cutoff.

Modeled C02 datasets require `market_model=modeled_bar`, `metadata_mode=research_assumption`, `bar_mark_proxy=bar_close` and explicit `bar_close`/`bar_range` policies. They cannot provide recorded quote fills or settled funding; net remains unknown. Bar-range stop/target conflicts remain unresolved. Recorded data uses recorded-quote execution and can explicitly choose the supported C09 trigger source.

## Result and label semantics

`completed` means both full source passes and atomic publication succeeded. `ready` means at least one candidate exists and every selected outcome is mature or explicitly unfilled; it does **not** mean profitable, sufficient sample size, complete continuous path, complete regular marks or out-of-sample validation. `has_mature_evidence` separately states whether any usable net outcome exists. A no-candidate run is saved with full detection coverage and `ready=false`. Gross/fees remain reported even when net is unknown. In statistics, `negative_net_usdt` is the positive magnitude of losses, used as the profit-factor denominator. Mature statistics never silently turn unresolved trades into losses or zero returns; their denominator and unresolved coverage remain explicit.

Exit status: 0 for a ready run/read command; 2 for a completed run with missing/unresolved evidence or no candidates; 1 for validation, source, budget or publication failures. Reports persist for exit 2. Failed computations/publication expose no partial run. Recover by rerunning exactly the same command; interrupted runs restart both passes. Completed runs validate saved hashes/inventory before returning the same summary.

`outcome_revision` artifacts retain an observation timestamp and full C09 evidence. A newly available funding row may revise net or revoke maturity even after an earlier usable label. Select the latest revision observable before inference, then require maturity and an `outcome_known_ms` strictly before inference. Final reports contain latest outcomes; they must not be treated as historical training tables without that revision-aware selection. Funding corrections/revocations are supported; C09 does not retrospectively re-simulate an already closed trade from later contract-path revisions. Continuous path certification and richer correction handling remain explicit C09 upgrades. Features join by their frozen snapshot hash. C12 still owns fold isolation and overlapping interval purging.

Cash accounting is fill-price gross less each actual fill fee once plus signed settled funding. Drift/spread/slippage are **attribution already inside fill prices**. Sampled unrealized P&L is gross at fresh mark, without estimated closing costs; stale/missing marks or unknown funding yield null P&L. Full dollar P&L drawdown requires complete regular samples. There is no initial capital, percentage return, annualization, Sharpe or funded equity claim.

## Sensitivity and integrity

Rerun a frozen scenario with a changed fee schedule or execution/delay assumption, then:

```sh
python -m tradee simulate compare BASELINE_RUN_HASH VARIANT_RUN_HASH
```

The comparison requires identical dataset, strategies, policies, sizes, metadata, calendars, windows, source code and other settings. It identifies changed fee/execution inputs, pairs mature candidates, reports variant-minus-baseline net difference and explicitly counts lost/gained mature evidence. Different admission from cost/delay gates must not be interpreted as a pure fee arithmetic change. This is a descriptive comparison; C12 must register all inspected variants and control selection.

The manifest pins source dataset/vintage, scenario definitions, metadata, calendars, fees, execution, numeric/runtime/code identity and child detector manifests. Complete lifecycle manifests, source-bound evidence, keyed fills/funding and causal revisions are saved as hashed artifacts. The store checks source count/prefix, selected-candidate-to-trade conservation, ledger reconciliation, artifact sequence/hash manifest and schema identity before publishing. SQLite failures roll back the entire result. Hashes detect corruption; these are not signed or authenticated audit records.

The reference implementation retains artifacts and candidate intents in memory and scans independent positions. Explicit budgets reject oversized runs; partial-run checkpoints, bounded out-of-core execution, database migrations/backups and representative multi-year throughput remain upgrades. Defaults are limits, not measured production capacity. C03's reference feature reconstruction also remains a scale constraint. Finite-capital, liquidation, trained inference and walk-forward require the later components listed in the upgrade register.
