# Statistical expectancy

**Location:** Research → Expectancy models; original predictions in Signals. **Prerequisites:** verified C11 runs with eligible net outcome evidence and an explicitly declared chronological training window. C10 is a statistical cohort estimator; no Groq/LLM or learned confirmation model is implemented.

## Fit and inspect

Create `path/to/window.json` with `start_ms`, `end_ms` and `cutoff_ms` satisfying `start < end <= cutoff`. These are epoch milliseconds selecting decisions and the knowledge cutoff; do not use the final outcomes of trades that were not knowable by the cutoff.

```sh
conda activate tradee
python -m tradee expectancy explain
python -m tradee expectancy fit --runs RUN_HASH \
  --window path/to/window.json --config configs/c10_estimator.json
python -m tradee expectancy summary MODEL_HASH
python -m tradee expectancy model MODEL_HASH
```

Replace hashes with actual C11/C10 outputs. A model may have several protocol-specific cohorts. Model fields, sources, publication time, training cutoff and limits are retained. For inference/evaluation request schemas, see [the C10 implementation guide](../../components/c10/C10_IMPLEMENTATION.md).

The dashboard reads stored models. It does not have a standalone “fit C10 model” job or a model-editing form; use the CLI or [C12's controlled research orchestration](WALK_FORWARD_RESEARCH.md).

## What the numbers mean

C10 groups compatible historical outcomes into the predeclared side/horizon and optional symbol cohorts. It estimates conditional mean **net R** and uncertainty using time-block resampling. R is an outcome normalized by its recorded initial risk, not a fixed USDT amount or a guaranteed payoff.

- **Ready/estimated:** this cohort estimate is applicable to compatible inputs.
- **Eligible:** the separately checked lower confidence bound exceeds the declared buffer and required evidence gates pass.
- **Abstained/insufficient:** no supported estimate/admission from those inputs. Sparse, unseen, incompatible, expired or unavailable evidence is not replaced by an unqualified fallback.

A positive mean with a nonpositive/insufficient lower bound need not be eligible. Empirical positive-net frequency is not an independently calibrated probability of winning the next trade. Read confidence settings from the frozen model; a chart or badge is not a calibration certificate.

## Configuration and issues

[c10_estimator.json](../../../configs/c10_estimator.json) controls cohorts, sample/coverage minima, calendar bins/blocks, bootstrap draws/confidence, age and lower-bound buffer. Do not lower minima just to make a demonstration admit trades and then treat that result as real-market validation.

If a model abstains, inspect the specific cohort/protocol, outcome maturity, funding completeness, training cutoff, model age and input definition hashes. Republishing an old fit does not refresh its training evidence. Standalone evaluation is descriptive; capital-aware strategy validation remains a separate workflow.

Related: [backtesting](BACKTESTING.md), [research](WALK_FORWARD_RESEARCH.md), [portfolio](PORTFOLIO.md), [future model extensions](../../platform/COMPONENT_UPGRADES.md).
