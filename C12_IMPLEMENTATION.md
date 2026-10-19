# C12 implementation and operation

C12 implements frozen experiments, nested chronological estimator selection, explicit label purging, independent-signal uncertainty/robustness diagnostics, a complete newly declared variant ledger, resumable jobs, controlled final-window access and immutable research release records.

## Files and responsibilities

| File | Main contents | Depends on / used by |
| --- | --- | --- |
| `tradee/c12/contracts.py` | `Split`, `Fold`, `Variant`, `EvidencePolicy`, `Experiment`; deep freezing, chronological ownership, source separation, references, budgets and exact tail resolution | C10 contracts; engine/store/CLI |
| `tradee/c12/engine.py` | Revision-aware source selection, purged snapshots, fits, inner selection, frozen outer/final evaluation, adverse stress and neighborhood orchestration | C10/C11; store |
| `tradee/c12/statistics.py` | Selected net-R utility, synchronized calendar blocks, family tail allocation, unknown/degenerate gates, attribution and leave-group diagnostics | Exact C07 arithmetic/C10 block sampler; engine |
| `tradee/c12/store.py` | C12 SQLite database, family reservations, immutable artifacts, jobs, retry journal, kernel runner lock, one-way holdout access, decisions and releases | Contracts/engine; CLI and Python callers |
| `tradee/c12/cli.py` | `research` commands, strict JSON inputs, path isolation and inspection | Store; top-level CLI |
| `scripts/verify_c12.py` | Raw Binance-shaped synthetic receipt inputs through actual C01–C12 implementations and CLI processes | Production components; E2E test/manual verification |
| `configs/c12_experiment.example.json` | Annotated-by-field synthetic experiment shape with deliberately unusable source hashes | Replace only with honestly sourced, predeclared evidence |

## Workflow

Use the `tradee` Conda environment. No new packages, account credentials, network access or Telegram settings are needed for C12 or its offline E2E.

```sh
conda activate tradee
python -m tradee research explain
python -m tradee research register --manifest path/to/experiment.json
python -m tradee research manifest EXPERIMENT_HASH
python -m tradee research run EXPERIMENT_HASH
python -m tradee research jobs EXPERIMENT_HASH
python -m tradee research events EXPERIMENT_HASH
python -m tradee research ledger FAMILY_NAME
python -m tradee research decision EXPERIMENT_HASH
```

Prepare immutable C11 simulations first, with separate single-protocol baseline/neighbor/stress runs and separate uninspected final-period runs. The example run and report hashes are placeholders; running the verification script writes a complete working manifest with actual hashes. The experiment-level `source_report_hashes` map must bind every referenced C11 run ID to its `report_hash` from C11 output. Run IDs alone can collide across independent stores that reuse local event IDs; content hashes prevent a different database from silently replacing registered evidence. Prepare holdout references through a blinded process and do not inspect its performance while collecting hashes. C12 validates development content before cached reuse and holdout content after logged access.

Include all inspected/TBot history in the disclosure and historical count; counts alone cannot reconstruct missing old trial records. Preserve the historical record outside the registry when available. Do not describe already inspected data as untouched.

`Split.train` and `Split.test` use C10 windows: `start_ms`, exclusive detection `end_ms`, and knowledge `cutoff_ms`. Training cutoff must be no later than test start. Test cutoff permits a fixed outcome maturation tail. Every inner test must be wholly inside the enclosing training history, with its labels known by the outer training cutoff. Multiple inner and outer test windows are disjoint within their respective tier. One base variant may omit inner selection; two or more require it in every outer and final fold.

C10 freshness gates still apply: its default model age is seven days from the training cutoff. C12 fits once per declared outer/final split. Use an appropriate predeclared fold/refit cadence, or explicitly justify a different estimator age before registration; a long test does not silently refresh its model or ignore stale abstentions.

Each variant provides name, hypothesis, rationale, parameter description, estimator settings, pinned development/holdout run lists, and optional `stress_of` or `neighbor_of`. Actual frozen C11 protocols define what ran; descriptive parameter labels cannot change execution. C12 refuses multiple protocols within a variant, incompatible test protocols or changing C11 producer implementations. Development C11 data must not include sealed-period decisions or later revision tails.

Base variants compete on passing inner evidence and maximum selected net R per candidate, with lexical tie-breaking. Neighborhood evaluation follows the durable outer selection and never reselects. The neighborhood relationship is explicitly declared; parameter distance is not inferred. For a matched parameter comparison, use identical underlying datasets/scope; a changed data/universe variant is an ablation, not evidence isolating a parameter effect. Stress uses precisely the same datasets and frozen baseline predictions; fees/delays/impact may only increase in the supported fields. Changing strategy, exit policy, quantity, funding semantics or evidence timing is another hypothesis, not a cost stress.

The default evidence policy requires 30 candidates, 20 eligible mature labels, 10 occupied nonoverlapping blocks, at least 80% estimated coverage, no unknown selected outcomes, a strictly positive family-adjusted lower bound, passing stress and neighboring parameter evidence, and positive leave-period/asset-out diagnostics. Default blocks are 3 daily bins with 2,000 replicates and alpha 0.05. The resampling grid retains full predeclared decision windows, including empty leading/trailing bins; inter-window time gaps carry no invented candidates or returns. These are conservative engineering defaults to freeze/review before real research; they are not an empirical guarantee. Increase draws before registration if the family budget makes the tail unresolvable. Disabling a stress/neighborhood gate is an explicit recorded policy choice, not evidence that robustness was checked.

After reviewing passing development evidence, the operator explicitly opens the final window:

```sh
python -m tradee research open-holdout EXPERIMENT_HASH --reason 'Final policy frozen; first authorized inspection'
python -m tradee research release EXPERIMENT_HASH
python -m tradee research decision EXPERIMENT_HASH
python -m tradee research artifact ARTIFACT_HASH
```

No confirmation UI or external publication occurs. This command itself is the intentional access action. It logs the frozen development hash, final winner/model and attestation before reading results. Retrying resumes that same policy; an unfavorable result remains rejected. `holdout_status: development_only` permits disclosed diagnostic evaluation but cannot yield a passing research release. Holdout reservations apply globally by time in the registry, conservatively across this project's crypto universe; they cannot be erased by renaming a family.

`release` returns the frozen model, policy/protocol identity, evidence hashes, code/runtime and remaining gates. All releases have `live_approved: false`. A historical modeled publication timestamp is a research clock and does not make this model fresh for live use. Refit/replacement and live admission require downstream controlled integration.

Exit codes: 0 for successful inspection/registration or passing validation; 2 for a completed unready/rejected validation or incomplete/pending decision; 1 for malformed inputs, missing/corrupt evidence or execution failure. An unready research result is persisted, not deleted. `release` is an inspection command and exits 0 even for a frozen rejected release; read its `ready`/`research_status` fields.

## Persistence, recovery and boundaries

The separate C12 SQLite database contains `families`, `experiments`, `artifacts`, `jobs`, `events` and `holdouts`. Experiment registration and family/holdout reservation are atomic. Job completion and its hash-chained event publish in one transaction. Failed publication leaves no partial artifact; attempts/errors remain visible. Cached completed jobs and their audit hashes are checked before reuse. Audit and job indexes are read in one SQLite snapshot, so inspection during a concurrent commit cannot create a false corruption report. A process crash releases the kernel lock and leaves its running job resumable without replacing completed selections.

One runner per database is enforced with the standard-library POSIX `fcntl` lock (macOS/Linux). SQLite is persistent, with a distinct application ID; C01/C11/C12 paths must differ. Remote/multi-host scheduling, Windows locks, schema migration and backup operations are separate extensions. Bounds: 32 variants, 20 outer folds, 20 inner folds each, 100 sources per variant, 1,000 durable jobs, 50 MB per artifact, and explicit time-bin/bootstrap budgets. Exceeding a bound fails rather than truncates evidence.

Code/runtime changes prohibit resuming that registered experiment; preserve its artifacts and register a new counted experiment with untouched final evidence. This is deliberate reproducibility behavior, including source changes outside C12. A working tree may contain old C11 producer artifacts, but a fitted/tested protocol cannot pool or cross different producer implementations.

C12 does not reconstruct unknown historical TBot trials, prevent direct SQL/raw-file access, automatically discover strategies or parameter neighborhoods, calibrate a classifier, prove continuous feed quality, simulate shared capital/liquidation, compute DSR/PBO, deploy a policy, or send signals. Exact remaining work is recorded in [COMPONENT_UPGRADES.md](COMPONENT_UPGRADES.md).

## Manual E2E

```sh
python -m scripts.verify_c12 --output data/c12_checks/demo1
python -m scripts.verify_c12 --output data/c12_checks/negative1 --negative-holdout
python -m unittest discover -s tests -q
```

Use fresh output directories. Both E2E modes should report `passed: true`: the negative mode verifies a correct research rejection. The script retains raw receipts, metadata, calendars, scenarios, fee/execution configs, source databases, full experiment JSON, all immutable jobs, audit events and `e2e_report.json`/`e2e_commands.json`. It uses reduced six-outcome/six-span thresholds, 4-minute bins and 200 bootstrap draws for speed. These overrides, synthetic receipt clocks, zero manual delay, assumed fees and empty settlement calendars are disclosed explicitly. Baseline positive utility is the hand-checked `2.455942622951 R/candidate`; it is a synthetic engineering result.

To inspect a demo store manually, take `EXPERIMENT_HASH` from its report and use its paths:

```sh
python -m tradee --db data/c12_checks/demo1/c01.sqlite3 research \
  --simulation-db data/c12_checks/demo1/c11.sqlite3 \
  --research-db data/c12_checks/demo1/c12.sqlite3 decision EXPERIMENT_HASH
```

Replace `decision` with `jobs`, `events`, `manifest` or `release` for the corresponding saved evidence.
