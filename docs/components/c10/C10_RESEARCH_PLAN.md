# C10 expectancy and uncertainty research decisions

Authorized 19 October 2026 under the component workflow: implement, robustly test, exercise E2E, document future work and commit in phases. This component estimates earlier outcomes of comparable setups. It does not certify an edge, tune a strategy or authorize trading. C12 remains the next component for chronological experiment control.

## Dependencies and consumers

| Component | C10 receives | Boundary / consumer |
| --- | --- | --- |
| C03 | Frozen candidate-time feature artifacts, definition hashes and readiness | Validate causal context and pin feature semantics; no future MFE/MAE or fitted feature transform enters inference |
| C07 | Execution/delay/liquidity gates, fee evidence and size assumptions | Match cost protocols; changing fees, delay or size needs a compatible separately fitted model |
| C08 | Strategy definition/hash, direction, timeframe and candidate evidence | Each hypothesis stays separate; family names alone are insufficient compatibility |
| C09 | Exact fill-price net P&L, risk, funding, mature labels and recognition times | Reconcile net and R; target-before-stop is not positive net P&L |
| C11 | Immutable run manifests, full candidate inventory, feature joins and outcome revisions | Revision-aware causal training and later diagnostic evaluation; optional inference injection remains C11/C13 integration |
| C04/C06 optional context | Future regime/positioning covariates; C06 settled funding already reaches labels through C09 | Additional conditioning requires sufficient earlier evidence and C12 validation |
| C12 | Future caller: fit windows, frozen settings, folds, purging and experiment registry | Receives pinned snapshots, frozen models, estimates and later scoring artifacts; owns selection and promotion |
| C13/C14 | Future consumers: portfolio/admission and live Telegram pipeline | Receive applicable estimates/uncertainty/abstention; release approval and capital selection are separate |
| C15 | Future consumer: predicted versus realized forward evidence | Receives causal predictions, coverage, scoring/reliability and estimator identity |

## Estimand and cohorts

The initial estimand is **mean net R conditional on simulated fill and usable mature evidence**, under the declared strategy, exit policy and execution/funding assumptions. Unfilled setups are not zero-R trades. Unknown funding, ambiguous paths and pending/open outcomes are not losses or zero returns. Fill rate and maturity coverage therefore accompany every estimate. This is not unconditional expectancy per alert or portfolio return.

A mandatory compatibility protocol freezes the complete C08 strategy, C09 policy, base quantity, C07 fee/execution configuration, C06 funding policy, C08 eligibility/detection configuration, data availability mode and C03 feature-definition hashes. Within each protocol, default cohorts are **direction × intraday/swing horizon**, pooled across observed symbols. Optional symbol conditioning is explicit. There are no automatic fine-grained intersections, fallback pooling or shrinkage. A symbol with no mature support abstains.

Producer implementations cannot be pooled under one protocol when their C11 code hashes differ. Inference matches frozen semantic definitions and assumptions; C12 must still validate implementation/release compatibility. This reference implementation does not infer that two different code releases are equivalent merely because a feature/family name matches.

## Causal selection and windows

`TrainingWindow(start_ms,end_ms,cutoff_ms)` means candidate detections in `[start,end)`, with `start < end <= cutoff`. A separate cutoff allows labels to mature after the last training candidate. Only the last outcome revision **observed strictly before cutoff** is considered; a mature revision additionally needs `outcome_known_ms < cutoff`. Net/risk arithmetic, ledger identity, source candidate and feature prefix are checked. A later correction replaces the target; a later revocation excludes it. The final C11 trade table is never used as a historical label table.

Preserve every selected candidate's status and provenance, including unresolved/unfilled cases. Source decision windows must cover the full declared training interval for every protocol. The check covers declared C11 decision-window scope: gaps between source scopes cannot be filled with empty bins. It does not certify continuous market-feed coverage inside a source. Internal missing observations can still affect the observed candidate process; C02/C11 quality evidence and C12 missingness/selection controls are required before market-performance claims. Bootstrap empty bins describe the supplied candidate inventory, not proof that the market offered no setup. Overlapping decision windows from different runs under the same protocol are rejected, so rerun/vintage copies cannot inflate evidence. Repeated identical run hashes are deduplicated; disjoint chronological windows can be combined. C12 owns sealed holdouts, global candidate/label overlap rules, embargoes and trial accounting.

## Statistics and uncertainty

Compute exact sums with the shared Decimal400 policy; C09 net R and public diagnostic ratios use 12 decimals. Report mean net USDT/R, empirical positive-net fraction, positive/negative payoff means, nearest-rank R quantiles, lower-tail mean, exposure overlap and coverage. Empirical positive-net frequency is a descriptive baseline, not a calibrated candidate probability.

Bootstrap on **regular time bins anchored at the declared training start**, not an IID sequence of trades. Store each bin's `(sum net R, count, positive count)`, including known empty bins. Draw fixed-length circular blocks of adjacent bins until the original calendar span is covered; truncate the last draw. Resample all contemporaneous symbols together and use the same seeded index draws across ready cohorts. Each replicate estimates `sum R / count`, rather than an equal-weight mean of bin means. Report central percentile bounds for the conditional mean. The fixed block construction and percentile rule are versioned and independently tested.

Default gates are 30 mature trades, 20 occupied base bins, 10 occupied nonoverlapping resampling spans, at least 80% maturity among candidates not explicitly unfilled, and at least 50% fill coverage. Default bins are one day, block length three bins, 2,000 replicates and 95% central bounds. These are explicit engineering safeguards, **not validated sample-size guarantees**. Occupied spans are not a claim of independent observations. Blocks must be shorter than the training span and at least as long as the longest observed label interval. Sparse, degenerate, excessively empty or over-budget resampling abstains. An unobserved positive/nonpositive class yields no frequency confidence interval; it is not assigned zero uncertainty.

[ARCH's official time-series bootstrap documentation](https://bashtage.github.io/arch/bootstrap/timeseries-bootstraps.html) distinguishes circular fixed blocks from stationary and nonwrapping moving blocks. We choose the circular form to retain boundary sampling symmetry; stationarity and stable short-range dependence remain assumptions. [SciPy's official bootstrap documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html) explains percentile construction and warns about degenerate bootstrap distributions. These references inform our transparent standard-library implementation; no ARCH/SciPy dependency or BCa-equivalence claim is introduced. Checked 19 October 2026.

Bootstrap intervals cannot account for unseen regimes, arbitrary heavy tails, omitted costs or inspected strategy variants. Block length must be predeclared and later tested for sensitivity in C12. Confidence bounds are not posterior probabilities that an edge is real.

## Frozen inference and later scoring

Fits produce immutable artifacts. Publication records actual completion time by default; retrospective research must explicitly request modeled availability. A model cannot be published before its cutoff. Inference requires model availability, strictly earlier training cutoff, age within the declared limit measured from that cutoff, compatible assumptions, stable usable features, a currently available/unexpired candidate, cohort/symbol support and no reuse of a training candidate. Unsupported/sparse contexts abstain rather than borrowing a better-looking group. A usable estimate is distinct from eligibility: the initial research gate requires the lower mean-R bound to exceed a predeclared nonnegative buffer.

Later evaluation first constructs prediction requests using candidate/feature/policy evidence and the frozen estimator, then joins later outcome revisions. Report all versus estimated/eligible/mature coverage, prediction error, empirical-frequency Brier score and reliability bins, plus clearly descriptive retained/baseline mean R. No label-dependent refitting occurs. [Scikit-learn's official calibration guidance](https://scikit-learn.org/stable/modules/calibration.html) explains that Brier score mixes reliability, resolution and outcome uncertainty; a good Brier score alone does not certify calibration. Checked 19 October 2026. No calibrated classifier is claimed here.

## Acceptance and explicit remaining work

Literal statistics/bootstrap fixtures; contemporaneous resampling and trade weighting; maturity/cutoff and revision/revocation tests; source overlap/coverage controls; frozen estimate invariance to future labels; incompatible/stale/sparse abstention; exact ledger joins; atomic model publication/retry and idempotence; raw-input E2E with default thresholds on separate earlier/later periods; and an honest saved-public insufficient-evidence check.

The software can measure later predictions and admission coverage. **Evidence that an admission policy improves later real outcomes is still a research gate**, requiring C12 experiments and C13 capital-aware validation. Predictive regression/classifiers, calibrated probabilities, shrinkage, adaptive context, advanced uncertainty, large-history scale and live release integration remain in [COMPONENT_UPGRADES.md](../../platform/COMPONENT_UPGRADES.md). Functional synthetic results do not satisfy those empirical gates.
