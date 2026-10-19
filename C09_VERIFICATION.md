# C09 verification

Verified 19 October 2026 in the dedicated `tradee` Conda environment, Python 3.13.15 on macOS arm64. C09's agreed independent paper-trade scope is implemented: source-bound C08 activation, C07 entry/exit scenarios, fixed/partial/time/invalidation exits, quantity conservation, C06 funding reconciliation, exact ledgers, outcome availability and atomic recovery. [Contracts](C09_IMPLEMENTATION.md) and [research decisions](C09_RESEARCH_PLAN.md) define the policy and its limits.

## Offline results

```sh
conda run -n tradee python -m unittest discover -s tests -q
```

**404 tests passed in 62.763 seconds:** all 350 previous component tests plus **54 new C09 tests**. Ordinary tests use isolated databases and no external network, credentials or account access. Existing CI discovery includes them; these are local macOS/Python 3.13 results rather than a claim that remote Linux/Python 3.11 CI ran.

| Test file | Cases | Evidence |
| --- | ---: | --- |
| [test_c09_contracts.py](tests/test_c09_contracts.py) | 6 | Independent long/short/partial levels, versioned size/policy IDs, immutable evidence, exact candidate/feature prefix binding and invalid schema/product/source modes |
| [test_c09_engine.py](tests/test_c09_engine.py) | 36 | Independent gross/fees/net, stop gaps, partial-target/stop quantities, delay/expiry/thesis checks, C07 rejection and blocked-exit timeout, time/invalidation/mark/contract triggers, same-ms aggregate-trade ordering, stale/revised/gapped paths, funding schedules/revisions/partial exposure/boundaries, close-only versus ambiguous bars, unresolved tails, every restart split, ledger/schema corruption, distinct event/profit labels, stable outcome recognition and sampled excursions |
| [test_c09_persistence.py](tests/test_c09_persistence.py) | 8 | Actual C01/C02/C03/C08/C07/C06 integration, atomic SQL rollback/resume, exact persisted net ledgers, immutable vintage, corruption/aliases, missing transitions/full-input completion and deleted inventory detection |
| [test_c09_cli.py](tests/test_c09_cli.py) | 3 | Explain without database creation, JSON errors for missing/aliased sources and strict collections |
| [test_c09_e2e.py](tests/test_c09_e2e.py) | 1 | 22 actual CLI commands/processes from raw imports to C08 setups, C07 fills, C06 declared funding coverage and C09 exact outcomes, including new-process write-failure recovery and unresolved alternatives |

Literal golden monetary expectations are independent of production P&L/fee functions. Tests additionally check quantities and source/knowledge times rather than accepting exit status alone. All previously implemented component formulas/oracles still pass. Monetary arithmetic remains exact Decimal400; diagnostic ratios use explicit rounding.

## Connected E2E and manual artifacts

Retained final run:

```sh
conda run -n tradee python -m scripts.verify_c09 --output data/c09_verification/e2e_ordered
```

The demo performs **22 production CLI commands in separate processes** using real SQLite stores. It imports synthetic Binance-shaped metadata, six finalized minute candles, entry quote/mark messages and exit quote/mark/contract-trade messages. Receipts are actual import times. Real C03/C08 processing produces a BTC long and ETH short on the same pinned recorded C02 dataset. C09 then requests actual C07 paper estimates and C06 coverage on its resulting position quantities. Internal components are not mocked.

This short fixture explicitly sets zero entry delay and a 25bps spread budget, and declares an empty synthetic settlement calendar for each instrument. These are fixture assumptions, not changes to the default 30-second entry delay/20bps spread budget, account fee evidence or claims about Binance's historical funding schedule.

Independent base expectations, one base unit each:

| Item | BTC long | ETH short |
| --- | ---: | ---: |
| Candidate reference | 102 | 98 |
| Fixed stop / target | 100.98 / 104.04 | 98.98 / 96.04 |
| C07 entry / exit fills | 102.2 / 104.8 | 97.8 / 95.2 |
| Gross realized | 2.6 | 2.6 |
| Total entry + exit fee | 0.1035 | 0.0965 |
| Funding under declared empty calendar | 0 | 0 |
| Net USDT | **2.4965** | **2.5035** |
| Actual initial risk USDT | 1.22 | 1.18 |
| Net R | 2.046311475410 | 2.121610169492 |

Both trades end flat, with exactly two fill-ledger entries each, final-target-first labels and mature net-positive labels under the declared fixture assumptions. Spread/drift/slippage are already embedded in fill prices; subtracting shortfall again would fail the exact net assertions.

Verified recovery and alternative paths:

- A real SQLite trigger aborts the second report insertion after one committed prefix. The CLI exits 1; exactly one report and one checkpoint remain. A new CLI process resumes the prefix, consumes candidate/fill events and reaches the exact ledgers. This is statement-failure recovery, not a power-loss/physical-disk test.
- Repeating the completed run returns identical summary, hashes, quantities and fee totals.
- Omitting calendars leaves gross/fees known but funding/net/profit labels null. The report is saved and exits 2; closed quantity alone does not establish a mature net outcome.
- The explicit 30-second manual-delay alternative creates no early entry. The short data tail leaves both pending entries unresolved, rather than inventing an execution or loss.
- Importing later funding evidence does not rewrite the original pinned dataset/report. Funding revision replacement and nonzero partial-position cash flows additionally have direct/integration lifecycle fixtures.

Final base run: `58c10c9fb2a24db9cbe1fb3b33d43219b535c7d26d5aac75f4163f022e2dba9a`.

Final base report: `88007739b225cfe5597fc4c3a3f614ffb89a48b6ac33144ef55c0b16e9494931`.

Unknown-funding report: `5a7de609a8ea515925b998ba865f0bbb3a20a720013aa95a9a551380ecc5905b`.

Delayed-entry report: `867e71cf4d6afc309eae0a2b831dfa4ab68e1aae9bc4b66e798c799392fdef1d`.

Artifacts in `data/c09_verification/e2e_ordered/` are excluded from Git: C01/C02/C08/C09 databases, raw data, full candidate/feature/quantity/policy intents, execution/calendar config, `e2e_commands.json` and `e2e_report.json`. C03/C07/C06 run as actual shared core modules inside the connected components, rather than requiring their own standalone databases.

Inspect the retained ledger:

```sh
conda run -n tradee python -m tradee lifecycle \
  --lifecycle-db data/c09_verification/e2e_ordered/c09.sqlite3 \
  report 88007739b225cfe5597fc4c3a3f614ffb89a48b6ac33144ef55c0b16e9494931
```

Read each fixed level, quantity change, execution attempt, fill fee and source hash; verify the table above and empty-calendar assumption; inspect delayed/unknown cases; rerun the completed command from the log. Repeat the full E2E in a fresh directory. These exact synthetic trade outcomes verify software accounting, not a trading edge.

## Additional independently checked outcomes

- Long stop gap: entry 102.2, available exit fill 98.8 despite fixed stop 100.98. Gross **−3.4**, fees **0.1005**, net **−3.5005** under a declared zero-settlement calendar. No stop-level fill is invented.
- Long partial then target: initial one unit, exit 0.5 at 103.3, remaining 0.5 at 104.8. Gross **1.85**, fees **0.103125**, net **1.746875** under a zero-settlement calendar. Timeline is `1 → 0.5 → 0`.
- A settlement while only 0.5 unit remains at mark 104/rate +0.001 charges **−0.052**, giving net **1.694875** for that partial/target scenario.
- One-unit long settlement at mark 102/rate +0.001 changes base net to **2.3945**. A later rate revision to +0.002 changes it to **2.2925** with one current funding key, not a second full charge. Old serialized outcome remains unchanged.
- Missing expected settlement or a quantity change near settlement yields null total funding/net. A settlement just before entry is included in the strict timing guard.
- Mark and contract trade triggers are distinct; a trade observation cannot fire a mark-only stop. Distinct same-ms contract trades follow aggregate IDs, while a quantity-changing exit waits until a later millisecond.
- Final target reached before stop can still be net-negative under an explicit stressed fee schedule. Target-first and profitable labels are tested separately.
- A range bar touching stop and target keeps the position unresolved with no fake exit. Modeled close-only trades can produce gross/fees, but unsupported historical funding leaves net null.
- Every checkpoint split across activation, entry and exit reproduces the same final report. Altered quantity, ledger arithmetic or feature hash fails restore. Completed replay requires all pinned inputs and a complete transition inventory.

## Retained public Binance replay

C09 reused the **already captured C08 public Binance minute payloads**; no new REST/WebSocket session was performed for this check. The saved data is replayed as an explicit modeled candle dataset with assumed close-time availability, current metadata and a contract-close mark proxy. A real derived range-breakout candidate drives a synthetic **0.001-unit** lifecycle with a 15-minute holding limit and illustrative fees.

Direct incremental lifecycle, persisted replay and completed rerun matched exactly over **6013 events**. The model produced a paper entry and `time_exit`, gross **−0.0037 USDT** and fees **0.08301615 USDT**. Funding/net/net R/profitability remain **null** because this modeled dataset cannot certify historical funding. The saved run is complete while its net label is unresolved; this is the expected integration result, not a failed trade-label assertion.

- Source capture: `data/c08_verification/public1/`.
- Modeled dataset: `aaa0692b162b3018e9d41b0bfc412e121085357fe5d37ee8ff2b0a2241ffe778`.
- Public lifecycle run: `cf10e1e9e30c53b8da9f6ad726429dc2c60c9a20cb51e42e9842b289e95b1481`.
- Public lifecycle report: `aae3b75da4c4946aa6d228f0d3cf4de3b0af0008406ac5958a5dcde1e70a2a72`.
- Verified production source-tree hash, also matched by the retained E2E manifests: `fdd2665ee6df0c8be8ae69ab00de4fe91e986c6841d7b048d639956eb878bd5b`.

The output database and `public_replay.json` are in `data/c09_verification/public_replay/`. Recheck offline:

```sh
conda run -n tradee python -m scripts.verify_c09_public_replay \
  --source data/c08_verification/public1 --output data/c09_verification/public_replay
```

## Remaining gates

- C11 must drive and reconcile complete C08 candidate/trade inventories across historical experiments; C13 adds shared capital/risk/admission, and C12 measures walk-forward/holdout evidence. This component's independent trade ledgers do not establish portfolio or strategy expectancy.
- Fixed 1%/2R/four-hour policies and zero default exit delay are unoptimized conventions. Separate policy versions, stress cases and forward latency/cost measurements are required before promotion.
- Bar-range ambiguity stays unresolved; single-bar triggers use a declared delayed-close scenario, not an exact intrabar price or conservative fill bound. Finer replay, alternate exits and trailing policies remain upgrades.
- Trigger streams are sampled. Gaps/stale/revised paths suppress mature labels, and sampled excursions are not continuous-market extrema. True exchange stop/account timing remains unverified.
- Historical calendars, rule coverage and account fee/fill/income reconciliation remain evidence requirements. Known partial subtotals are not certified net P&L. Modeled funding is null.
- Operator cancellation is supported by the core API, but C14 still needs a durable external action/timer journal, automatic active-thesis/correction policy, emergency exit routing and forward replay parity.
- Multi-year/universe throughput, attempt/checkpoint retention, migrations/backups and unattended physical recovery remain operational validation. Ordinary E2E and statement rollback do not prove those properties.
- No secrets were read, account endpoints called, orders placed or Telegram messages sent. C11 historical simulation is next, then C10 expectancy from mature outcomes.

All remaining work is maintained with dependencies and completion gates in [COMPONENT_UPGRADES.md](COMPONENT_UPGRADES.md#c09-trade-policy-and-outcomes).
