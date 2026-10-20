# C12 verification

Verified in the `tradee` Conda environment (Python 3.13.15), 19 October 2026. Production code remains standard library only. No Binance account keys, network capture, exchange orders or Telegram messages are used by these checks.

## Automated coverage

C12 adds **64 tests** across the following files:

| File | Tests | Evidence |
| --- | --- | --- |
| `tests/test_c12_contracts.py` | 11 | Deep freezing, round trips, strict fields/types, ordered knowledge windows, inner isolation, disjoint outer ownership, source hashes, references, budgets and resolvable uncertainty tails |
| `tests/test_c12_statistics.py` | 14 | Literal utility, abstentions versus unknown selected outcomes, duplicate protection, joint cross-asset blocks, negative/degenerate/sparse evidence, concentration/leave-group checks, label span/work bounds, rational tail probabilities and retained empty edges of declared windows |
| `tests/test_c12_persistence.py` | 14 | Idempotence, cumulative family budget/history, holdout reservation, no resealing/development overlap, atomic write failure/retry, crashed-running-job recovery, hash corruption/deleted-job detection, own database/path checks, size bounds, concurrent runner exclusion and consistent audit/job inspection during a real concurrent write |
| `tests/test_c12_cli.py` | 4 | Commands, JSON output, pending/error exit codes, missing evidence and path separation |
| `tests/test_c12_isolation.py` | 2 | Close inner scores remain distinct under a low-precision caller context; a changed C11 producer cannot cross the train/test boundary |
| `tests/test_c12_engine.py` | 16 | Real C11 training labels and frozen C10 evaluation; nested selection precedes outer scoring; holdout run manifests are untouched during development; fixed final model, frozen stress admission, retry after source/holdout/release failure, uninspected versus contaminated holdouts, negative/unknown final labels, insufficient inner evidence, explicit stress/neighborhood gates and exact purge boundaries |
| `tests/test_c12_evidence_identity.py` | 2 | Actual C11 reports with the same run ID but different outcome bytes cannot substitute for the pinned source; report hashes change experiment identity before scoring |
| `tests/test_c12_e2e.py` | 1 | Raw C01/C02 ingestion through actual features/candidates/fills/funding/outcomes and C11/C10/C12 CLI, durable failure recovery, later evaluation and release |

**Full suite: 566 tests passed in 306.250 seconds**, including all 64 C12 tests. Command: `TRADEE_C12_E2E_OUTPUT=data/c12_verification/e2e_v2 conda run --no-capture-output -n tradee python -m unittest discover -s tests -q`. The negative raw-input E2E was also run separately and passed. Both final runs use the exact production digest below.

## Retained raw-input E2E

```sh
conda activate tradee
python -m scripts.verify_c12 --output data/c12_checks/demo1
python -m scripts.verify_c12 --output data/c12_checks/negative1 --negative-holdout
python -m unittest discover -s tests -q
```

Every demo requires a fresh directory. The negative demo should exit successfully with `passed: true` and a **rejected research decision**; its strategy is deliberately losing in the held-out period. Ordinary `research open-holdout`/`decision` commands return exit 2 for that rejection, as recorded by the script.

Both modes use 48 development opportunities, two earlier-inner/outer chronological folds (eight outer candidates each), final earlier selection/training, and twelve separately pinned final opportunities. The predeclared alternatives are C10 admission buffers of 0 and 0.1 R, plus doubled-fee stress for each. The strategy, indicators, candidates, execution fees/fills, funding coverage, exact ledgers, model fits and later predictions all come from production implementations; labels are not assigned by the test.

The fixture explicitly overrides C10/C12 evidence thresholds to six mature outcomes/six occupied bins or spans, uses four-minute bins and 200 bootstrap replicates, and declares a four-variant family budget. It uses synthetic Binance-shaped prices/rules, historical receipt clocks, a one-minute/two-bar long-only breakout, quantity 1, zero manual delay, 25bps spread gate, assumed fees and an explicitly empty synthetic settlement calendar. These overrides test orchestration; they cannot establish a real-market edge or justify those thresholds in live research.

Each run performs **22 actual CLI processes**, including premature holdout refusal, SQL-trigger publication failure, immutable retry, trial ledger and audit inspection, baseline-preserving fee stress, neighborhood checks and a one-time logged final access. Raw receipt JSONL, metadata, scenario/cost/calendar/config JSON, C01/C02/C11/C12 stores, working experiment JSON, job artifacts, full reports and command logs remain in the output directory.

Final production code digest: `8028c453d94ad892057e9c087974b04cc6c1e53e15c01338dae1e11e8d2c671d` (all `tradee/**/*.py`; Git commits and documentation changes do not change this digest).

Positive final E2E retained at [e2e_report.json](../../../data/c12_verification/e2e_v2/e2e_report.json), with [command log](../../../data/c12_verification/e2e_v2/e2e_commands.json) and [working manifest](../../../data/c12_verification/e2e_v2/experiment.json):

- Experiment `2aef6190049b5587e07d9ce73931f945598e2a808442518d790cd2e9d3aceb11`.
- Sixteen outer and twelve final eligible mature outcomes; utility `2.455942622951 R/candidate` in both periods.
- Status `research_candidate`, `ready: true`, `live_approved: false`.
- 22 durable jobs and 52 audit events; frozen release `c04c40a2f68e44a2a8a7f921484a0106a02c498fd4dced3872497f7f0effe27f`.

Negative final E2E retained at [e2e_report.json](../../../data/c12_verification/negative_v2/e2e_report.json), with [command log](../../../data/c12_verification/negative_v2/e2e_commands.json) and [working manifest](../../../data/c12_verification/negative_v2/experiment.json):

- Experiment `2ccc1e952376287c34f7ca43ae635c305eaf620e4aacd3f338131c8feff04e39`.
- Earlier outer utility: `2.455942622951 R/candidate`; negative final utility: `-2.459631147541 R/candidate`.
- Frozen winner: `range_buffer` (lexical tie-break on identical inner utility); it is not replaced after the loss.
- Final status `rejected`, `ready: false`, `live_approved: false`.
- 22 durable jobs and 52 audit events, retaining failed/retried publication and one final-window access.
- Frozen rejection/release digest `7f6ee10c96fdf0149789fb131bbba7c896e705d634ac5cf24254e496fa68ea68`.

The two final experiments have different content-qualified identities and holdout outcomes but exactly the same frozen model, `8571e6ab50ff3a17574cd778634db9b71eb49e00ae8bc3db3308fddf9726d7f4`. Held-out economic labels therefore do not change training or the selected policy. A direct cross-store regression additionally refuses a substituted report with the same local run ID.

Ignored data directories are retained locally and are not Git source artifacts. The automated E2E normally uses a temporary directory; setting `TRADEE_C12_E2E_OUTPUT` to a fresh path retains its full output.

## Meaning and limits

Functional verification establishes reproducible chronological model inputs, selection, conservative coverage/unknown handling and durable research state. It does not establish future profitability, valid stationarity/block length, complete historic trial disclosure, calibrated probabilities, continuous data quality, real manual fills/funding, or untouched real-market evidence. Existing saved Binance candle research is already inspected development data, with unresolved historical funding; it is not relabeled as a fresh holdout.

Within development, source integrity checks can read full pinned artifact inventories; C10 strictly filters model labels at the declared knowledge cutoff. C12 does not open separate holdout sources until the logged access. Direct C11/raw-file/SQL access and human prior knowledge remain outside this gate. Historical modeled fit publication is not actual live availability.

All releases remain research-only with `live_approved: false`. C13 shared-capital/risk simulation, C14 live/Telegram operations and C15 forward reconciliation remain required. Broader operational, statistical, prospective custody and integration work is listed in [COMPONENT_UPGRADES.md](../../platform/COMPONENT_UPGRADES.md).
