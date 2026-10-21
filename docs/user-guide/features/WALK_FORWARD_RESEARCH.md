# Walk-forward research and holdout

**Location:** Research → Experiment registry; Operations → Research & data jobs. **Access:** viewer for allowed reports; operator plus worker for UI registration/runs and final holdout opening. CLI mutations do not use the dashboard token.

C12 separates earlier fitting/selection from later evaluation, tracks counted variants and reserves final holdout access. It produces frozen research decisions rather than live-trading authorization.

## Prepare and run

Prepare C11 development/neighbor/stress runs and separately protected final-period runs. Freeze an experiment manifest with actual run **and report** hashes, chronological folds, policies, trial budget and holdout status. [The example](../../../configs/c12_experiment.example.json) contains deliberately unusable placeholder hashes; it is a schema illustration, not a ready experiment.

```sh
conda activate tradee
python -m tradee research explain
python -m tradee research register --manifest path/to/experiment.json
python -m tradee research run EXPERIMENT_HASH
python -m tradee research jobs EXPERIMENT_HASH
python -m tradee research events EXPERIMENT_HASH
python -m tradee research decision EXPERIMENT_HASH
```

Copy the actual experiment hash from registration. In the dashboard use **register experiment**, then **research run** and inspect Job history plus the Research experiment/audit view. A worker marks a request successfully executed separately from whether the research evidence passed; read the returned decision.

## Final holdout is a deliberate one-way action

Review/freeze the development choice before inspecting the final period. The dashboard **open holdout** request requires the exact `OPEN <experiment hash>` confirmation and a reason. Do not click it merely to fill an empty chart.

The corresponding CLI action, to run only when you intentionally open that final evidence, is:

```sh
python -m tradee research open-holdout EXPERIMENT_HASH \
  --reason 'Final choice frozen; intentional first inspection'
python -m tradee research release EXPERIMENT_HASH
```

The CLI command itself records the access; it does not display the dashboard's typed confirmation prompt. Opening cannot be undone by deleting/retrying a job or renaming a strategy. Unfavorable final results remain part of the decision. Access to raw files outside the controlled interface cannot be made blind by the dashboard.

## Interpret the evidence

Inspect inner selection, outer fold results, purge/embargo chronology, outcome maturity, coverage, uncertainty, stress, neighboring definitions and the variant ledger. Fit and later evaluation have different availability clocks. A completed job can correctly reject a hypothesis or remain unready.

The UI conservatively denies protected holdout outcomes in linked run/model/chart/artifact paths until the audited opening. A missing/locked result is not automatically a backend fault. Research and Data archives require leaving a session replay cursor so their own pinned vintages are clear.

Current research/portfolio compatibility receipts have `live_approved: false`; they do not supply every remaining capital-policy/promotion check. See [Portfolio](PORTFOLIO.md), [the C12 contract](../../components/c12/C12_IMPLEMENTATION.md) and [remaining work](../../platform/COMPONENT_UPGRADES.md).
