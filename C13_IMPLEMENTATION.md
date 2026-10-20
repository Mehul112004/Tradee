# C13 implementation and operation

Implemented 20 October 2026. Use the `tradee` Conda environment. Production remains standard library only. No new secrets or Binance account permissions are needed for offline C13.

## Files and ownership

| File | Contains | Dependencies/consumers |
| --- | --- | --- |
| `tradee/c13/contracts.py` | Frozen RiskPolicy, Position, Reservation, Mark, AccountSnapshot and exact-size Offer | C01/C02 validation, C07/C09 intents, C10 verified models; used throughout C13 and by future C14 |
| `risk.py` | Freshness, mark equity, stop reserves, collateral, group/beta/horizon limits, shocks and drawdown pause | Injected state and policy; allocator and funded replay |
| `engine.py` | Pure deterministic C10-gated ranking, size ladder, C07 rechecks and admission/exclusion artifacts | State, offers, policy, caller execution callback; local accounts and historical runner |
| `source.py` | Verified C11 inventory, first executable entries and causal outcome revisions | Pinned C11 runs/report hashes; funded runner |
| `replay.py` | Same-time scheduling, exact C02 prefix identity, frozen model bank, shared cash/positions and regular equity | C02/C07/C09/C10/C11 contracts; PortfolioStore |
| `store.py` | Own SQLite database, atomic replay publication, reconciliation checks, CAS accounts, reservations and journals | Runner/pure allocator; CLI, C12 compatibility and future operations |
| `cli.py` | Offline `portfolio` commands and bounded recorded-prefix execution callback | Existing separate C01/C02/C10/C11 stores; no collectors or exchange orders |
| `configs/c13_risk_policy.json` | Explicit default risk limits, BTC/ETH assumptions and resource limits | Pure allocator and replay |
| `configs/c13_replay.json` | Initial cash, grid, optional decision window and replay budgets | Funded replay |
| `scripts/verify_c13.py` | Raw synthetic receipt capture through production CLI to funded results and reservations | C01–C13 implemented chain; retained manual E2E artifacts |
| C12 integration | Counted recipe hashes and `research check-portfolio` compatibility receipts | Frozen release + exact C13 evidence; never authorizes promotion |

The public Python API exports `RiskPolicy`, `Position`, `Reservation`, `Mark`, `AccountSnapshot`, `Offer`, `allocate`, `ReplayConfig`, `PortfolioReplay` and `PortfolioStore` from `tradee.c13`.

## Run a funded replay

```sh
conda activate tradee
python -m tradee portfolio explain
python -m tradee portfolio replay \
  --sources path/to/source_pins.json \
  --models MODEL_HASH \
  --policy configs/c13_risk_policy.json \
  --config configs/c13_replay.json
```

`source_pins.json` is an object mapping each C11 run hash to its verified report hash. Use recorded-quote runs from the same source dataset/prefix with explicit funding evidence. A run may contain several predeclared sizes/horizons; repeated economic offers across runs fail. Every size needs a compatible model. Unsupported protocols abstain. Exact execution must remain equal to its tested C09 first fill.

Place database options after `portfolio` and before its action:

```sh
python -m tradee --db path/to/c01.sqlite3 portfolio \
  --market-db path/to/c02.sqlite3 \
  --simulation-db path/to/c11.sqlite3 \
  --estimator-db path/to/c10.sqlite3 \
  --portfolio-db path/to/c13.sqlite3 \
  replay --sources path/to/source_pins.json --models MODEL_HASH
```

All five paths must differ. Models normally come from C10. To use the exact model embedded in a frozen C12 release, export its `model` object and use `--model-files path/to/model.json` instead of `--models`. The file must pass C10's complete model verification; a summary/hash wrapper is insufficient.

`ReplayConfig` defaults to 10,000 USDT, a 60-second grid, the common source decision interval, at most 250,000 source events and 10,000 inventoried candidate size options. Policy defaults reserve 0.5% per trade, 2% total stop risk, 1.5% group/horizon risk, 50% gross/group/absolute-beta notional, 60% collateral, 10% joint stress loss/drawdown and four slots. They are explicit engineering defaults, not recommended live account settings or optimized research results. Review/freeze all settings before inspecting performance.

There is no leverage above 1, automatic quantity rounding, outcome scaling, opportunistic model fallback or terminal force-close. Stale/unknown evidence suppresses risk. A complete zero-admission run remains unready; positive net is not required for a mechanically complete funded report. `ready` describes usable engineering outcomes, not profitability or live approval.

## Inspect results

```sh
python -m tradee portfolio summary RUN_HASH
python -m tradee portfolio manifest RUN_HASH
python -m tradee portfolio report REPORT_HASH
python -m tradee portfolio records RUN_HASH
python -m tradee portfolio artifact ARTIFACT_HASH
```

The summary includes return/drawdown/coverage and report identity. The full report includes accepted source keys, exact C09 states and ledgers, terminal positions/cash/risk, source identity and limitations. Records contain allocation batches, book revisions, regular samples, source-level suppressions and margin-proxy breaches. Each allocation retains all offers, C10 predictions/abstentions, C07 evidence, exact ranking score, risk measures and reasons.

Metrics use cash plus gross marked PnL. Reserved closing fees affect admission/stress, not an invented already-paid wallet debit. Drawdown/returns use the declared regular grid and can miss between-grid movement. Unknown equity breaks adjacent returns and makes complete grid drawdown null; the available-sample drawdown lower bound stays diagnostic. `annualized_return` and `sharpe` are null.

## Persistent local proposals

`account-create NAME --snapshot FILE`, `account NAME`, `account-update NAME --expected SNAPSHOT_HASH --snapshot FILE`, and `allocate NAME --expected SNAPSHOT_HASH --offers FILE --dataset DATASET_HASH --at-ms TIMESTAMP --policy FILE` operate only on injected paper/user snapshots.

A snapshot contains cash, peak equity, complete positions/reservations, marks with provenance/availability, seen candidate IDs and explicit funding/open-order coverage flags. Offers are a JSON array of `{request, model}` objects: each request is a valid C10 EstimateRequest and each model the full verified publication. The allocator replays the recorded C02 prefix for fresh C07 evidence. It has explicit event/work budgets and rejects unavailable stores or colliding paths.

The returned `allocation_hash` identifies proposed TradeIntents and capacity reservations. An atomic successful batch advances account revision without spending cash or recording a fill. The caller must reconcile actual paper positions/fills/external state through an explicit expected-hash update. CAS conflict means refresh state and recompute; do not overwrite. Identical request retries return the original artifact even after later account changes. Local account data is caller-supplied evidence, not independently authenticated Binance state. C14 must own fill/delivery reconciliation and recheck freshness before acting.

## C12 compatibility boundary

Before registering an experiment, hash `{policy: POLICY_DOCUMENT, config: REPLAY_CONFIG_DOCUMENT}` with Tradee's canonical `fingerprint` and include it in `portfolio_recipe_hashes`. Reserve one family trial slot per recipe in addition to estimator/strategy variants and historical trials. Changing initial cash, thresholds, sampling or decision window changes the recipe.

After a passing development run and explicitly logged `open-holdout`, replay that frozen release's single model/source/window and run:

```sh
python -m tradee research check-portfolio EXPERIMENT_HASH \
  --portfolio-db path/to/c13.sqlite3 --run PORTFOLIO_RUN_HASH
```

The receipt requires compatible recipe, sources/content, producer/runtime, final model, complete labels before the test cutoff and positive funded net. It never reselects or rewrites the release. It is **compatibility only**, always `promotion_authorized: false`, `live_approved: false`. C12 multi-release composition, nested capital-policy evaluation and dependence-aware funded inference remain required upgrades. A multi-size engineering demo has its own frozen bank and does not inherit the baseline release's compatibility receipt.

## Recovery and limits

C13 schema v1 uses its own application ID and database. Replay manifest/report/all event artifacts publish in one transaction after wallet/metrics reconciliation; injected SQL failures leave no partial publication. A retry validates source content, then reuses the completed immutable result. There is no mid-run replay checkpoint. Accounts use independent hash-linked revisions and transactions; concurrent updates fail CAS. These hashes detect accidental corruption, not hostile database rewriting or dishonest snapshot inputs.

Back up with SQLite's backup API or stop writers. Distributed scheduling, migrations, bulk streaming/pagination, account authentication, tiered exchange margin/liquidation, live delivery and empirical profitability validation remain in [the upgrade register](COMPONENT_UPGRADES.md). Neither the CLI nor any C13 API sends orders or Telegram messages.
