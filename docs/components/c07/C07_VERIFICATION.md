# C07 verification

Verified 13 October 2026 in the dedicated `tradee` Conda environment, Python 3.13.15 on macOS arm64. C07's agreed market execution/cost scope is complete: observed rule/price/readiness/delay gates, explicit fees, conservative paper price scenarios, exact monetary attribution, separate funding projections, immutable reports and atomic replay. Broader fidelity and operational work remains in [COMPONENT_UPGRADES.md](../../platform/COMPONENT_UPGRADES.md#c07-execution-and-tradability).

## Offline checks

```sh
conda run -n tradee python -m unittest discover -s tests -q
```

**298 tests passed in 6.384 seconds:** all 240 previous C01/C02/C03/C06 tests plus **58 C07 tests**. Ordinary tests use isolated databases and no external network, secrets, account access or orders. Existing CI discovery picks up these tests; this local result does not claim remote Linux/Python 3.11 CI was executed.

| Test file | Cases | Evidence |
| --- | ---: | --- |
| [test_c07_math.py](../../../tests/test_c07_math.py) | 15 | Independent fee and two-leg P&L amounts, signs, exact common grids/floor, rational participation and non-power-of-ten ticks, local precision isolation, ratios, schemas, cost decomposition and size monotonicity |
| [test_c07_engine.py](../../../tests/test_c07_engine.py) | 30 | Independent buy/sell price/cost/funding expectations; latency, expiry, stale/missing quotes/marks, liquidity, drift/stop, quantity/min-notional/reduce-only gates, passive rejection, fee timing, required feature prefix/stability/age joins, no future artifacts, optional-feature isolation, funding boundaries, explicit bar coverage, immutable revisions, checkpoint splits and invalid states |
| [test_c07_persistence.py](../../../tests/test_c07_persistence.py) | 9 | Actual C01/C02 integration, direct/persisted parity, partial restart/idempotency, atomic SQL rollback, immutable source vintage, prior decision cutoff, changed fee manifests, corruption/aliases, backward/conflicting checkpoints and exact fractional-second metadata-age budgets |
| [test_c07_cli.py](../../../tests/test_c07_cli.py) | 3 | Explain without database creation, missing/aliased input JSON errors and strict collection schemas |
| [test_c07_e2e.py](../../../tests/test_c07_e2e.py) | 1 | 27 actual CLI commands/processes through raw data, real C03 artifacts, C06 estimates and C07 persistence; independent amounts, fault recovery and rejection/model scenarios |

The E2E case checks many behaviors despite counting as one unittest. Numeric expectations are literal independent amounts, not generated using the production pricing/cost functions. Source integrity, logical timing and restart behavior are separate assertions. Monetary calculations use exact decimal/rational arithmetic; production does not use binary floats for amounts.

## Connected E2E and manual artifacts

The final retained run:

```sh
conda run -n tradee python -m scripts.verify_c07 --output data/c07_verification/e2e_final
```

This runs production commands in separate processes and real SQLite stores. It imports synthetic current metadata and recent synthetic finalized candles/quote/mark payloads, preserving actual receipt times; pins a mixed recorded C02 dataset; computes real C03 artifacts on that dataset; requests C06 next-funding context; and produces durable C07 scenarios. A separate explicitly modeled candle dataset exercises the coarse bar preset. Internal components are not mocked. There are no account endpoints, network calls, real orders or Telegram messages in this E2E.

Verified outcomes:

- **55 C03 feature snapshots** for diagnostic 1m `log_return_1`, `vwap20`, `rsi14`. Required `log_return_1` is valid/stable and zero; latest VWAP is 100. C07 uses that actual snapshot's hash and exact source prefix.
- One-unit **buy** at reference 100 / ask 100.1 / visible size 10 produces tick-rounded price **100.2**, fee **0.0501**, execution-plus-fee cost **0.2501**, next funding **−0.1**, projected cost **0.3501 USDT**.
- One-unit **sell** at reference 100 / source bid 99.9 produces price **99.8**, fee **0.0499**, execution-plus-fee cost **0.2499**, next funding **+0.1**, projected cost **0.1499 USDT**. The modeled price includes adverse slippage/rounding.
- The quote fixture explicitly chooses zero manual delay; a separate default 30-second case rejects early evaluation without a fill.
- A real SQLite trigger aborts the second report write. Exit 1 surfaces the error and exactly one prior report/checkpoint remains. Removing the trigger and starting another CLI process resumes the persisted prefix and returns the expected final amounts. This tests statement failure, not physical disk/power-loss recovery.
- Completed rerun returns the same summary, hashes and counts.
- Off-step quantity, unsupported passive order, expired intent and wide-spread revision produce persisted rejection reports/exit 2 with null fills/costs.
- A new quote produces a new dataset; the original dataset/run/report keeps its original amounts.
- Explicit coarse-bar execution at the 30-second action boundary produces price **100.1**, fee **0.05005** and cost **0.15005**. Metadata/contract-close mark proxy and synthetic spread/volume participation are research assumptions. Funding projection remains **null**, not invented from later settled outcomes.

Final base run: `bcf5685a67b1bbabb6fd089622959adba27909a03e7ca503f9ebb37b64033d4b`.

Final base report: `81412ad588fa34b20f11577c875da1f2ada1e7cb98195638330a0810f8d6fd52`.

Artifacts are in `data/c07_verification/e2e_final/`, excluded from version control: four component databases, raw data, bound intents, feature collection, configs, command log and `e2e_report.json`. C06 is used directly for next-funding estimates rather than a separate settled-funding database; its accounting E2E remains independently covered by C06 tests.

```sh
conda run -n tradee python -m tradee execution \
  --execution-db data/c07_verification/e2e_final/c07.sqlite3 \
  report 81412ad588fa34b20f11577c875da1f2ada1e7cb98195638330a0810f8d6fd52
```

Read the manifest and command log, compare exact costs/timestamps/provenance, inspect rejected reports for null fills, and rerun a listed completed execution command. To repeat the whole E2E, use a fresh directory or omit `--output`. These are independent paper exposure scenarios, not detected strategies or completed trade outcomes.

## Public Binance smoke and offline saved replay

The ordinary restricted-network attempt could not reach Binance. The approved public-network retry captured C01 exchange metadata plus **one BTCUSDT quote and one mark** through existing C02 public adapters. It then evaluated synthetic minimum-notional exposure at the latest input availability. A final saved offline replay after production code was frozen matched direct evaluation and repeated-run summaries exactly.

Actual result under explicit zero delay and illustrative taker rate `0.0005`:

| Item | Recorded-replay result |
| --- | --- |
| Proposed base quantity | 0.001 |
| Source midpoint / ask | 83408.05 / 83408.1 |
| Quote / mark event ages | 1346ms / 146ms |
| Source ask size | 8.161; requested participation 0.000122534003 |
| Modeled market buy | 83424.8 |
| Fee | 0.0417124 USDT |
| Execution shortfall plus fee | 0.0584624 USDT |
| Next-settlement funding estimate | −0.0035865483 USDT |
| Projected execution cost with that estimate | 0.0620489483 USDT |
| Tradability under declared policy | Admitted; simulated fill is explicitly not guaranteed |

This is public-data integration and recorded-prefix parity, not verification that the exchange accepted an order, that this account pays that fee, or that the quoted size remained available. The clock is latest recorded availability, not later socket-shutdown wall time. No freshness limit was relaxed. Funding covers the next known timestamp only.

- Dataset: `b1c876a27802b701199f432c31c12cd7f535f932388f4d0f2f00f7895bda66e6`.
- Decision: `1791910376146` UTC milliseconds.
- Final public run: `4a594f204c61fc8e20bf62277d2e709f095176f3e13188d3ba0ca737f6c81bf4`.
- Final public report: `64ec306a3cc72659e125cc8b37f3d2fdf66305e95d041749776e36c3dbd43aef`.
- Final verified production source-tree hash: `e35309c28a7299bff94047c89090860a778ccafdb18635dd50a888c6b834164d`.

Capture and final report are in `data/c07_checks/public1/`. Replay without network:

```sh
conda run -n tradee python -m scripts.verify_c07_live --replay --output data/c07_checks/public1
```

## Scope and remaining gates

- Fees, impact and human/delivery latency are explicit versioned assumptions. Calibration from actual forward observations is C07-U03/C14/C15. No empirical cost-error bounds or strategy edge is established here.
- Quote scenarios allow independent full fills only within declared displayed-size caps. Depth reconstruction, queue priority, passive maker fills, partial fills and shared liquidity consumption remain unbuilt. Displayed size can cancel.
- Candle-only history supplies a coarse sensitivity model, not an exact 30-second entry. Historical rule/mark/quote gaps remain explicit; current metadata and bar-close mark proxies never become verified past evidence.
- Required C03 readiness is checked at action; strategy thesis/level/route invalidation belongs to C08/C09. Intents remain caller-supplied scenarios. Default BTC/ETH eligibility can also suppress exits; C09 must explicitly design its emergency/disabled-symbol exit policy rather than bypassing this model silently.
- Costs describe one leg. Next-funding projections do not certify a swing hold's complete funding. C09 owns resulting quantities, booked fills/fees and C06 settled funding reconciliation; C11 produces net trade ledgers, C10 estimates expectancy and C13 shares capital/risk.
- Account fee evidence, income/fill reconciliation, margin/leverage/liquidation/account restrictions and automated orders remain future or separate product scope. Caller-supplied reduce-only position evidence is not authenticated account state.
- Representative multi-year/universe throughput, sustained recording, backup/migration and physical failure recovery remain operational validation. Functional SQLite rollback/resume tests do not prove those properties.
- C08 candidate generation is next. Full historical trading E2E arrives at C11, research-selection E2E at C12 and Telegram E2E at C14. The current connected E2E ends at paper execution/cost reports.
