# C10 implementation and operator contract

C10 provides revision-aware cohort training, time-block uncertainty, frozen inference and later diagnostic evaluation. [Research decisions](C10_RESEARCH_PLAN.md) define the estimand/dependencies; [verification](C10_VERIFICATION.md) records evidence. It uses the existing Python standard library and shared exact monetary contracts.

## Files and responsibilities

| File | Major contents | Dependencies / consumers |
| --- | --- | --- |
| `tradee/c10/contracts.py` | `TrainingWindow`, `EstimatorConfig`, validated `EstimateRequest`, compatibility protocols, cohort identities and immutable records | C03/C06–09/C11 contracts; all C10 paths and future C12/C14 callers |
| `tradee/c10/source.py` | Full pinned C11 verification, paged source reads, strict historical revision selection, feature/candidate joins, net/R checks, complete decision coverage and overlapping-vintage rejection | C11 store/C09 evidence; fit and later evaluation |
| `tradee/c10/statistics.py` | Coverage, payoff/tail statistics, synchronized circular time-block bootstrap, explicit degeneracy and resource gates | Exact Decimal sums/rounded ratios; fit artifacts |
| `tradee/c10/engine.py` | Deterministic cohort fits, availability envelope, frozen inference, freshness/compatibility checks and conservative eligibility | Snapshot/config/request; store and future injected policies |
| `tradee/c10/evaluation.py` | Prediction construction followed by later label joins, coverage, squared error, Brier/reliability and retained outcome diagnostics | Frozen model, later C11 artifacts; C12/C15 research reports |
| `tradee/c10/store.py` | Dedicated SQLite schema, atomic snapshot/fit/publication, hash verification, immutable estimates/evaluations and idempotent replay | Production CLI and future research orchestrators |
| `tradee/c10/cli.py` | `expectancy` explanation, fit, inspect, estimate and evaluate JSON commands | Registered in `tradee/cli.py` |
| `configs/c10_estimator.json` | Explicit initial cohort/gating/block/seed/freshness settings | Research fit configuration; no strategy tuning |
| `scripts/verify_c10.py` | Raw simulated-receipt data through C11, default C10 fit, real CLI publication failure/retry and later inference/scoring | Isolated C01/C02/C11/C10 stores and production logic |
| `scripts/verify_c10_public_evidence.py` | Retained public-data insufficiency check without new network | Existing modeled C11 public replay; no invented net labels |

## Fit and inspect

Use the dedicated environment and an existing completed C11 run. C01/C10/C11 paths must differ; C10 does not need exchange credentials. Prepare a window JSON using Unix milliseconds:

```json
{"start_ms":1788220800000,"end_ms":1791331200000,"cutoff_ms":1791331200001}
```

Those timestamps illustrate schema only; use your source's actual covered decision window and knowledge cutoff. `end_ms` selects detections exclusively, while the later cutoff determines which label revisions are knowable. Full declared decision-window scope is required. This is not continuous feed certification: internal candle/trade/quote gaps remain source-quality limitations for C02/C11/C12 review. Default settings require substantial recorded evidence across time; a few profitable examples are intentionally insufficient.

```sh
conda activate tradee
python -m tradee expectancy explain
python -m tradee expectancy fit --runs C11_RUN_HASH --window path/to/window.json
python -m tradee expectancy summary MODEL_HASH
python -m tradee expectancy model MODEL_HASH
python -m tradee expectancy training-snapshot SNAPSHOT_HASH
python -m tradee expectancy fitted FIT_HASH
```

For custom stores, place `--simulation-db PATH --estimator-db PATH` immediately after `expectancy`. Multiple disjoint runs can follow `--runs`. Pass `--config path/to/config.json` to freeze a different predeclared configuration. Changing cohorts, gates, blocks, confidence, buffer or cost assumptions is a new research variant that C12 must register.

Normal publication uses actual completion time. Historical evaluation requires an explicitly modeled publication clock, for example `--modeled-available-ms CUTOFF_PLUS_DELAY_MS`. It is retained in the artifact and cannot precede the fit cutoff. Repeating an identical recorded publication reuses its first available time; a different explicit modeled time creates a distinct publication of the same fit. The default model-age limit is seven days from **training cutoff**, so republishing an old fit does not make its evidence fresh.

## Estimate and evaluate

```sh
python -m tradee expectancy estimate MODEL_HASH --request path/to/request.json
python -m tradee expectancy estimate-record ESTIMATE_HASH
python -m tradee expectancy evaluate MODEL_HASH --runs LATER_C11_RUN_HASH --window path/to/later_window.json
python -m tradee expectancy evaluation EVALUATION_HASH
```

A request requires the full emitted C08 `candidate`, its complete hashed C03 `feature_snapshot`, the C11 `scenario`, `execution`, `fees`, `funding` and `candidates` configuration objects, and `evaluation_ms`. Use the generated E2E `request.json` as an executable example. The request contains no realized outcome or future excursion. Feature evidence must share the candidate prefix; required features must be valid/stable. Execution/metadata/fee/size/policy/feature definitions must match the trained protocol. Inference does not read a simulation store or fit a model.

A model may have both ready and insufficient cohorts; global `ready` means at least one cohort is usable. Each estimate checks its own cohort and symbol. `ready=true` / `status=estimated` means the conditional estimate is applicable, **not** that the trade is eligible. `eligible` separately requires a strictly positive lower confidence bound above the configured buffer. A ready negative/uncertain-edge estimate can be ineligible. Sparse/unseen/incompatible/expired/future/stale inputs abstain; no fallback cohort is silently substituted.

Evaluation decisions must follow estimator availability and fit cutoff. The estimator remains frozen; later C11 labels are joined after prediction creation and selected at the evaluation cutoff. Reports retain every prediction and unresolved label, estimated/eligible/mature counts, squared R error, empirical-frequency Brier score, reliability bins and all/matched/eligible mature mean R. Comparisons are descriptive and are not a funded policy backtest, calibration certificate, confidence interval on improvement or walk-forward release decision.

Exit codes: 0 for reads or a usable fit/estimate/evaluation; 2 for a saved artifact with insufficient/applicability evidence (or no matched mature evaluation); 1 for invalid input, incompatible source coverage, resource or persistence failure. An ineligible but applicable estimate still exits 0; inspect `eligible` and `reasons`. Failed publication rolls back the entire snapshot/fit/model transaction. A repeat command deterministically rebuilds/reuses the publication. Estimates and evaluations are content-addressed and idempotent.

## Data and numerical contracts

Train from the **latest revision observed before cutoff**, not today's final C11 outcome table. Recognition times, entry/exit intervals, ambiguity, net cash arithmetic and feature identity stay attached to training rows. Unfilled and unresolved inventory stays in coverage. A later funding correction can replace a previously mature target, and a subsequent conflict can revoke it. Different overlapping vintages under one protocol must be selected explicitly; they cannot count as additional observations.

Mean R is the average of C09's 12-decimal net-R diagnostics, each based on net fill-price P&L and actual initial risk. Gross fill prices already include shortfall; C10 never subtracts slippage again. Funding must be known under the C06 calendar contract. Calendar evidence still matters: empty schedules in synthetic tests are named assumptions, not claims that real perpetual futures have no funding.

The bootstrap stores count-weighted sums in fixed bins, including empty bins in the supplied candidate inventory. Missing observations within a declared source scope are not automatically detected or repaired by C10; data representativeness and selection bias still need C02/C11/C12 validation. All symbols in a bin move together; adjacent bins move in circular blocks with deterministic seeded draws. Bounds use nearest-rank central percentiles. Sparse/degenerate or excessively empty replicates do not produce actionable uncertainty. Positive-net frequency remains empirical; if a positive/nonpositive outcome class was never observed, frequency confidence bounds remain null rather than reporting spurious zero uncertainty. Mean-R uncertainty still depends on representative/stable data and the chosen block length.

Source runs, reports, training rows/revision references, hypothesis/cost protocols, settings, seeds, fit implementation hash and Python version are pinned. SQLite hashes detect corruption; they do not authenticate supplied market data or prove economic assumptions. Producer code hashes cannot be mixed within one training protocol. Inference's semantic-definition matching is not a substitute for later C12 release compatibility checks.

Budgets cap source runs, rows, cohorts, calendar bins and total bootstrap work; exhaustion fails rather than truncates. Large source artifacts are currently read into memory. Incremental fitting, source-version adapters, large-history benchmarks/migrations/recovery and atomic deployment/runtime integration remain documented upgrades.

## End-to-end and manual review

```sh
conda run -n tradee python -m unittest discover -s tests -q
conda run -n tradee python -m scripts.verify_c10 --output data/c10_checks/demo1
conda run -n tradee python -m scripts.verify_c10_public_evidence \
  --source data/c11_verification/public1 --output data/c10_checks/public1
```

Use a fresh directory for the E2E demo. It ingests Binance-shaped raw inputs through production APIs with explicit synthetic historical receipt clocks, produces 36 daily training outcomes through C11 from four-minute synthetic sessions separated by intentional calendar gaps, fits the **default** C10 configuration and evaluates four later outcomes through real CLI processes. Raw receipts, configs, databases, requests, command log and `e2e_report.json` remain for manual review. It also injects an SQL publication failure, checks retry/idempotence and rejects unknown-funding/incompatible-cost evidence. The public check reuses saved real Binance candles and must abstain on uncertified net outcomes.

Next is C12 walk-forward/research control. C10's predictive/calibrated models and contextual shrinkage are optional extensions; production admission, shared capital, estimator injection into C11 and live Telegram integration still require C12/C13/C14 as recorded in the upgrade register.
