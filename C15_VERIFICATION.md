# C15 verification

Verified 20 October 2026 in Conda `tradee`, Python 3.13.15. **All 787 project tests passed in 518.296 seconds**, including **70 dedicated C15 tests** and a complete raw-input C01–C15 E2E.

## Scope and coverage

| Test module | Cases | Evidence |
| --- | ---: | --- |
| `test_c15_contracts.py` | 4 | Immutable schedules, strict schema/types, bounded settings and family-tail resolution |
| `test_c15_statistics.py` | 9 | Paired net/residual intervals, fixed RNG/rational tails, negative-net and forecast rules, whole-cohort maturity, prospective decisions, overlap blocks, sparse/degenerate evidence and work bounds |
| `test_c15_store.py` | 12 | Persistent/idempotent registration/publication, one policy per deployment, concurrent CAS winner, source/review immutability, SQL rollback, artifact/index/journal corruption and pause receipts |
| `test_c15_engine.py` | 21 | Causal/pre-start registration/clocks, observation retry, operational versus statistical/integrity reasons, failed/ambiguous/elapsed/expired delivery, fixed reviews, count/byte bounds, stale pause refusal, crash-gap recovery and no auto-resume |
| `test_c15_cli.py` | 8 | Offline explain/read/export, missing/aliased stores, health exit codes, opt-in pause application and bounded watch |
| `test_c15_integration.py` | 15 | Actual production stores, exact fees/net, revisions/revocation, strict maturity lag, old exports, replay corruption, delivery-audit CAS, explicit resume preservation, precise label classification, actual recording before outcome and publication by a review deadline |
| `test_c15_e2e.py` | 1 | Full raw-input research→paper decision/delivery→pause→mature outcome→export→replay workflow |

Operational fault-injection fixtures are explicitly synthetic and do not replace the real-source integration/E2E. Revision-classification fixtures modify copies of actual C09 records; upstream C06/C09 tests cover the detailed settlement/path revision algorithms. No artificial test result is treated as market profitability evidence.

## Reproduction

```sh
conda activate tradee
python -m unittest tests.test_c15_contracts tests.test_c15_statistics tests.test_c15_store tests.test_c15_engine tests.test_c15_cli tests.test_c15_e2e tests.test_c15_integration -v
python -m scripts.verify_c15 --output data/c15_checks/demo1
```

The script needs a fresh directory. It runs **32 actual C01–C13 research CLI processes and 27 C14/C15 CLI processes**, alongside staged raw Binance-shaped prospective receipts and the production dispatcher with a scripted transport. The C14/C15 child harness executes real CLI main under a controlled test wall clock matching the fixture's historical receipts; production receives no clock-override flag. No credentials are read and no real Telegram messages or exchange orders are sent.

Expected engineering results:

- Six independent shadow outcomes, including candidates rejected by shared-capital allocation, remain separate from three funded paper trades.
- Admitted mature paper net is **8.489 USDT**; funded cash goes from **320 to 328.489 USDT**, with no final position. These synthetic amounts are fixture assertions only.
- Initial admission reports expose no future mature outcome. Earlier hashes remain pending after later labels mature. Export has nine rows distinguished by signal and track, never nine independent funded trades.
- A stale active paper cycle produces an operational pause; the hypothetical paper book continues to close normally. The delivery journal shows one scripted acceptance and two later suppressed notices. No automatic resume occurs.
- Both scheduled reviews remain **insufficient evidence**: the first lacks the declared sample/time spans; the final small fixture encounters an empty resample. Abstention is the intended result. Separate dense statistical tests exercise both degradation rules and the no-degradation branch.
- Pinned raw-prefix, C11 manifest/report and C13 manifest/report checks all pass after actual production re-execution.
- Pause receipt retry recovers the original C14 event and does not apply another pause or override a later operator resume.

## Final source and whole-project regression

Final production digest: `894c8f30c2a5290b2f59b6572496be7f816622395ade9fe0b7571b83cde590df`.

The final suite uses fresh retained evidence directories `data/c15_verification/e2e_v3` and `data/c15_verification/c14_regression_v3`, with log `/tmp/tradee-c15-final-suite-v3.log`. These generated databases/receipts are ignored local artifacts, not repository fixtures or user credentials. Earlier C14 evidence remains historical under its earlier producer digest.

```sh
TRADEE_C14_E2E_OUTPUT=data/c15_verification/c14_regression_v3 \
TRADEE_C15_E2E_OUTPUT=data/c15_verification/e2e_v3 \
conda run --no-capture-output -n tradee python -u -m unittest discover -s tests -v
git diff --check
```

Whole-project outcome: **787 tests, OK**, exit code 0. `git diff --check` also passed. The retained monitor's producer digest matches the final source digest above.

| Retained C15 evidence | Hash |
| --- | --- |
| Deployment | `a09a67c95d7c0b16aa777db5639cae1f9cef9a0f9756ae7c5b3cdfce8889f027` |
| Monitor manifest | `cd43963ca8327a3359fab62ba9202837da82c75aac93142a6114bd7b44f1f1a0` |
| Initial admission report | `8ac15434f43f60d9bc3ce0da3c1e9d59e8d55f84257bf4052509f393e53f7459` |
| Final forward report | `a2d038488f0ef1c72fe10b254603c6a733151a1002c48f536adeee8a66808389` |
| Raw replay receipt | `629c62336e6a171b22c69c9f8b9babfa9bfe812e9950e0d3282067d9668c7854` |

The separate C14 regression also passed its 23 CLI commands plus 32 prior research commands under the final source digest. Its final cycle is `127266f530ef17c9e5b526d17b0a238dc4e09e5282df29cc07b3518d92ce31f1`. The retained C15 workflow runs another 27 runtime/monitor CLI commands plus 32 research commands, with the exact results stated above. Earlier interrupted verification attempts are not final acceptance evidence.

## Limits

This verifies software accounting, causality, reproducibility, recovery and monitoring controls. It does not establish a profitable real-market strategy, empirical user execution costs, human Telegram receipt, statistical power for a short live sample, a production-scale unattended service, a dashboard or live promotion. Remaining gates and prospects are maintained in [COMPONENT_UPGRADES.md](COMPONENT_UPGRADES.md).
