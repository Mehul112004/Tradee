# C13 verification

Verified in the dedicated `tradee` Conda environment, Python 3.13.15, 20 October 2026. Production remains standard library only. Tests use no Binance credentials, network capture, orders or Telegram messages.

## Automated coverage

C13 adds **70 tests**, including the raw production E2E:

| File | Tests | Evidence |
| --- | --- | --- |
| `tests/test_c13_contracts.py` | 9 | Frozen exact inputs, strict numbers/types/identity/clocks, explicit coverage, unsupported leverage/modes, finite expiry and replay configuration |
| `tests/test_c13_risk.py` | 11 | Hand-calculated long/short equity/reserves, missing/stale/future evidence, unknown funding/orders, expiry, pending fees, drawdown, group/beta/horizon overlap without hedge credit and decimal-context isolation |
| `tests/test_c13_allocation.py` | 15 | Shared finite cash and literal tested sizes, deterministic order/precision, horizon conflicts, slots, every independent limit, missing execution/marks, exact protocol and expectancy-buffer abstention, seen IDs, invalid fill/fee/hash/clock, work bounds and empty batches |
| `tests/test_c13_replay.py` | 13 | Exact funded cash/net, admitted-only ledgers, no future labels in allocation, repeatability/single-use runner, changed C02 content/order, pinned C11 reports, model publication/duplication, resource bounds, unknown funding, losing later paths, real settlement corrections, open tails/stale terminal marks and regular missing-value returns |
| `tests/test_c13_persistence.py` | 12 | Own DB identity, atomic publication/rollback/retry, pre-publication wallet/metric reconciliation, corrupt/missing events, artifact kinds, durable CAS reservations without cash debits, interleaving account update, failed batch rollback, source clocks, hash-linked journals and corrupt retry indexes |
| `tests/test_c13_research.py` | 4 | Counted frozen portfolio recipes, family budgets, strict recipe fields and no portfolio reads before logged holdout access and refusal of a cherry-picked holdout source subset |
| `tests/test_c13_cli.py` | 5 | Offline explain, snapshot create/read/CAS update, JSON errors, malformed inputs and path isolation |
| `tests/test_c13_e2e.py` | 1 | Raw C01/C02 to real C03/C08/C07/C06/C09/C11/C10/C12/C13 CLI, simultaneous capacity, frozen release compatibility, source corruption on cached receipt, failure recovery and persistent local proposals |

**Full suite: 636 tests passed in 410.310 seconds**, including all 70 C13 tests. Command: `TRADEE_C13_E2E_OUTPUT=data/c13_verification/e2e_v3 conda run --no-capture-output -n tradee python -u -m unittest discover -s tests -v`. The complete log is retained locally at `/tmp/tradee-c13-verified-suite.log`.

## Reproduce and inspect manually

```sh
conda activate tradee
python -m unittest discover -s tests -q
python -m scripts.verify_c13 --output data/c13_checks/demo1
```

Each demo requires a fresh directory. It retains two assets' raw Binance-shaped receipt JSONL, observed metadata, exact strategy/size/cost/funding/risk/config JSON, separate C01/C02/C10/C11/C12/C13 stores, experiment/release model, standalone offers/snapshot, full funded report, E2E summary and all actual CLI commands.

The fixture runs production ingestion/features/setup generation/execution/funding/outcomes and estimates actual earlier C11 labels. It uses 12 four-minute development cycles, two earlier fixed-rule outer windows (three test cycles each), and three separate final cycles. Six asset-level candidates compete through eighteen executable size/horizon options in the multi-size replay. The policy is frozen before final access; intraday quantity 1 and 0.5 compete with a duplicate swing policy and with one another for one wallet.

Literal accounting checks: initial equity **320 USDT**; single-size funded baseline admits three positions and ends at **328.489**; exact-size ladder admits six positions and ends at **332.7335**, net **12.7335**. Per unit, the actual entry fill is 102.2, exits are 104.8/105.8, and round-trip fees are 0.1035/0.104, so three-cycle unit net is `2.4965 + 3.496 + 2.4965 = 8.489`. The extra admitted half-size has its own actual C11/C07 path/model protocol; it is not a scaled invented outcome. These are expected mechanical fixture results, not evidence that size search improves a real strategy.

A dedicated actual-C11 settlement/correction test adds a 0.001 rate during each trade and corrects it to 0.002 after closing. Shared funding becomes **−0.918**, terminal cash **331.8155**, net **11.8155**. Replacement is keyed; adding both the original and revised cashflow would fail this literal result. Negative later-price paths still admit contemporaneously eligible setups and report losses. Open tails remain open; stale terminal marks keep final equity unknown.

The E2E injects a SQLite publication failure and verifies no partial artifacts remain. It tests deterministic replay retry, atomic account reservation/retry, stale expected-hash rejection and explicit reconciliation. Reservations leave wallet cash unchanged. It also registers a counted capital recipe, refuses premature holdout access, validates an exact frozen C12 single-model release, detects a corrupted funded report even with a cached compatibility receipt, and refuses an undeclared initial-capital recipe. The receipt always keeps `promotion_authorized: false` and `live_approved: false`.

Assumptions are explicit: synthetic recorded prices/metadata/receipt clocks; one-minute/two-bar long range breakout; quantities 1/0.5; zero manual delay; 25bps spread gate; assumed fees; empty synthetic settlement calendars in the main E2E; full-collateral paper proxy; six-span C10/three-span C12 engineering gates, four-minute bins and 200 bootstrap draws. C12 stress/neighborhood requirements are explicitly disabled only for this small integration fixture; existing C12 tests retain their default robustness tests. No untouched real-market validation, liquidation fidelity, statistical portfolio promotion, live operational readiness or Telegram receipt is established.

Production code digest (all `tradee/**/*.py`): `88e6320b8700642822e7511699c7e35392ee8232e876acbdb0b4878dc6b3524d`. Documentation and local Git commits do not change this digest.

Ignored data directories are local retained evidence, not committed source artifacts. Set `TRADEE_C13_E2E_OUTPUT` to a fresh directory when running the full suite to retain its connected E2E instead of deleting a temporary directory.


## Retained final evidence

The final E2E performed **32 real CLI processes**, with `passed: true`. Inspect [E2E summary](../../../data/c13_verification/e2e_v3/e2e_report.json), [command log](../../../data/c13_verification/e2e_v3/e2e_commands.json), [full funded report](../../../data/c13_verification/e2e_v3/funded_report.json), [frozen experiment](../../../data/c13_verification/e2e_v3/experiment.json), [raw development receipts](../../../data/c13_verification/e2e_v3/development_receipts.jsonl) and [raw final receipts](../../../data/c13_verification/e2e_v3/holdout_receipts.jsonl).

- Experiment: `1508f3d88d53b4f526a259e32856dd074d3b5250e6bb90f5f23f73fdadbb80c9`.
- Single-size baseline: `f2c1e691d32a25807c9a89ffcab69ea07445338fac5ad221c1ae23e33835b0d9`; net 8.489 USDT, three admitted positions.
- Size-ladder portfolio: `d3c44573f909f1ce98691f4d2e521643c5be9023a7034de681ec1da9906b1115`; net 12.7335 USDT, six admitted positions, thirteen regular equity observations, terminal gross exposure zero.
- Funded report: `21100d3963ccedc19e230bb18edb92be1f9029ec1163061e6b5531c10ad2e1b3`.
- Frozen C12 release: `26526134f8ebc2c35446a7b58d39e6d83e36322b707604061b37fa0a24c3cff0`; compatibility ready, portfolio promotion and live approval false.
- Local allocation artifact: `cc31149ea192fda6ba78f62a6f0d9c82330fdc4a85113d619b5f0566dfffb919`.

Read the retained result without regenerating data:

```sh
python -m tradee portfolio --portfolio-db data/c13_verification/e2e_v3/c13.sqlite3 \
  summary d3c44573f909f1ce98691f4d2e521643c5be9023a7034de681ec1da9906b1115
```
