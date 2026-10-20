# C06 verification

Verified 13 October 2026 in the dedicated `tradee` Conda environment, Python 3.13.15 on macOS arm64. C06's agreed funding scope is implemented: exact cash flows, position quantity inputs, coverage/boundary statuses, prefix-causal estimates, immutable reports and atomic restart. Broader derivatives features and operational/data upgrades are recorded in [COMPONENT_UPGRADES.md](../../platform/COMPONENT_UPGRADES.md#c06-funding-and-derivatives-context).

## Offline results

```sh
conda run -n tradee python -m unittest discover -s tests -q
```

**240 tests passed in 4.442 seconds:** all 196 existing C01/C02/C03 tests plus **44 C06 tests**. Ordinary tests use isolated databases and no external network, secrets or account access. Existing CI discovery includes the new tests; remote Linux/Python 3.11 CI execution is not claimed by this local result.

| Test file | Cases | Evidence |
| --- | ---: | --- |
| [test_c06_math.py](../../../tests/test_c06_math.py) | 9 | Independent long/short signs, fractional exact arithmetic, low external Decimal context, high-precision products and cancellation, invalid inputs, quantity/guard/calendar/config schemas, defensive copies |
| [test_c06_engine.py](../../../tests/test_c06_engine.py) | 22 | Partial quantity exits, variable intervals, missing versus zero, unknown/conflicting calendars, strict/nominal boundaries, missing/expired/stale estimates, no future quantity/rate leakage, same-ms prefixes, corrections without duplicate full charges, instrument isolation, checkpoint splits/compatibility, stable cash-flow revisions and decision horizons |
| [test_c06_persistence.py](../../../tests/test_c06_persistence.py) | 9 | Actual C01/C02 integration, recorded receipt semantics, resume/idempotency, SQL write rollback, immutable dataset vintages, corruption, metadata/database isolation and backward/conflicting checkpoints |
| [test_c06_cli.py](../../../tests/test_c06_cli.py) | 3 | Explain without database creation, JSON errors for missing/aliased inputs and strict collection schema |
| [test_c06_e2e.py](../../../tests/test_c06_e2e.py) | 1 | Connected current-foundation workflow through 26 actual CLI commands/processes, independently expected amounts and recovery/error scenarios |

The E2E case exercises many assertions; its single test count is not a claim of one checked behavior. [The golden fixture](../../../tests/fixtures/c06/golden_scenario.json) contains independent arithmetic, and [the implementation contract](C06_IMPLEMENTATION.md) states the exact formula, boundary choices and information roles. No binary float is used in funding amounts.

## End to end evidence

Executed both in the automatic suite and as a retained manual demo:

```sh
conda run -n tradee python -m scripts.verify_c06 --output data/c06_verification/e2e_verified
```

The demo uses real production entry points and databases. It imports raw C01 metadata and C02 candle/funding/mark payloads, pins data, computes C03 features, and produces C06 reports. Internal modules are not mocked. C03 replay is explicitly modeled; C06 funding/mark availability remains recorded at actual import receipt. No historical receipt is fabricated.

Verified:

- **55 C03 snapshots**, with **36 nominally ready** under the declared diagnostic configuration: 1m `log_return_1`, `vwap20`, `rsi14`, `require_stable=false`. This is not the default multi-timeframe stabilization test.
- Base funding totals: long **+0.04 USDT**, short **−0.42 USDT**, from explicitly supplied partial-exit/held-exposure timelines.
- Reimporting the same three funding records adds no new normalized events and does not repeat charges.
- A real SQLite trigger aborts a report write after the first batch commits. The CLI exits 1; exactly one prior report/checkpoint remains. After removing the trigger, a new CLI process resumes successfully. This is a statement-failure/recovery test, not a power-loss or physical-disk test.
- Completed rerun returns the same summary, hashes and counts.
- Unknown calendar, missing expected settlement and ambiguous entry within the default settlement guard save unresolved reports and exit 2; totals remain null.
- A later first-settlement rate correction changes funding totals to long **−0.06** and short **−0.27**, without adding a second full charge.
- The original pinned dataset/report still gives **+0.04/−0.42** after that correction.

Final base run: `82aa3e0ef7e58c4ef2995bfc4bb8f883da8e5bd3db687e00cd811fac113d63e8`.

Final base report: `f402096df5c474c87b06736c7f971e77da607ed40434d81fc48f7f8013f38a90`.

The retained demo is in `data/c06_verification/e2e_verified/`, excluded from version control. It contains four component databases, raw inputs, position/calendar files, configs, `e2e_commands.json` and `e2e_report.json`. Inspect it manually:

```sh
conda run -n tradee python -m tradee funding \
  --funding-db data/c06_verification/e2e_verified/c06.sqlite3 \
  report f402096df5c474c87b06736c7f971e77da607ed40434d81fc48f7f8013f38a90
```

To repeat the complete E2E, use a fresh output directory or omit `--output` for a temporary run. To inspect missing/boundary/corrected runs, use the command log or query the same funding database. The demo is synthetic exposure accounting, not strategy trading P&L.

## Public Binance smoke and saved replay

The ordinary sandboxed attempt could not reach Binance. The approved public-network retry captured:

- C01 metadata through the existing public provider.
- **Three BTCUSDT settled funding records** from the public REST endpoint.
- **One mark/funding estimate observation** through the existing public WebSocket adapter.

Incremental engine evaluation and `FundingStore.run` replay produced identical reports. Synthetic exposure was a constant **0.001 base-unit long**, with an explicitly declared calendar containing only the selected test timestamps. Its known funding sum was **−0.0141214810258852077 USDT**. This amount is an unrounded calculation on public data, not an actual wallet transaction or proof of complete historical coverage.

The initial smoke compared context after socket shutdown: the mark was **5,155ms old**, and C06 correctly returned `stale_estimate` with a null estimated amount. The final saved comparison evaluates at the recorded latest input availability, where mark age was **152ms**. It produced a next-funding estimate of **−0.002730806738 USDT**. The smoke's clock was corrected to match the declared recorded-replay test; the engine's freshness budget was not relaxed. This does not establish current wall-clock actionability or sustained live latency.

- Dataset: `e0237e510f0fea72adaea3a5c3ff29e6dd096f4833cd04a476a3f3fcca2aa4c9`.
- Decision: `1791906775152` UTC milliseconds.
- Final public replay run: `d21e814cce32922b7dac12ae493ae2ed2a7f06a53267cd9f8550e23c3dded48a`.
- Public replay report: `bf2995a20e9a6300f9a51fa8813a80f283b9a4163c1d76562013ad7b251bd5ea`.
- Verified production source-tree hash: `37bc4f5f6d2832c6ac0abc00ce75c7d13160c3f6b0f51901b502c4be117d5af8`.

Capture databases and `live_report.json` are in `data/c06_verification/public_session/`. Recheck offline:

```sh
conda run -n tradee python -m scripts.verify_c06_live --replay --output data/c06_verification/public_session
```

## Scope and remaining gates

- Public settlement history supplies outcome evidence; historical downloaded records never become earlier forecast features. C02 modeled mode remains candle-only.
- Calendar completeness is conditional on supplied evidence. Automatic audited calendar/interval acquisition is C06-U01/C02-U04; observed records alone cannot certify that no settlements are missing.
- Strict boundary ambiguity remains unresolved without account transaction evidence. Nominal simulation is explicit; actual account rounding, income reconciliation and margin effects are future extensions.
- Position timelines are inputs/scenarios. Executable entries/exits, shared quantity state and one-time booking belong to C09; C06 supplies stable identities and revised amounts for reconciliation.
- No strategy expectancy, whole-trade P&L, portfolio risk or Telegram workflow is implemented by C06. Current E2E covers C01/C02/C03/C06; later complete workflows remain the milestones in [PLATFORM_PLAN.md](../../platform/PLATFORM_PLAN.md).
- Funding/mark state is retained in a single-host SQLite/reference implementation. No multi-year/full-universe service benchmark, migration drill or unattended-deployment claim is made. The connected functional checks do not establish those properties.
- Premium/OI/liquidation predictors and more advanced funding models remain deferred, with dependencies and acceptance gates in the upgrade register. No secrets were read, no account endpoints were used and no orders or messages were sent.
