# Execution costs, funding and trade lifecycle

C06/C07/C09 supply the economics and outcome rules shared by backtests and paper processing. They do not place exchange orders. Inspect their frozen inputs before comparing any result or fitting expectancy.

## What you configure

| Area | Files / inputs | Why it matters |
| --- | --- | --- |
| Fees | [Fee assumptions](../../../configs/c07_fee_assumptions.json) | Explicit assumptions are not authenticated account-tier evidence |
| Entry execution | [Recorded execution](../../../configs/c07_execution.json) | Manual delay, observed metadata, fresh quotes, spread/drift, top-book size and slippage/impact assumptions |
| Funding | [Funding config](../../../configs/c06_funding.json) plus independently declared settlement calendars | Missing settlement/position coverage can leave net outcomes unknown |
| Lifecycle | [Trade policy](../../../configs/c09_trade_policy.json) | Stop fraction, target R, holding limit, trigger source, partials and exit timing |
| Scenario | [Scenarios](../../../configs/c11_scenarios.json) | Joins a strategy, policy, tested base-asset quantity and horizon |

Use the complete schemas in the linked files/component docs; empty dashboard JSON objects are not complete runnable policies.

## Inspect capabilities

```sh
conda activate tradee
python -m tradee funding --help
python -m tradee execution --help
python -m tradee lifecycle --help
```

The normal combined workflow supplies these definitions to [C11 simulation](BACKTESTING.md), then preserves compatible evidence for expectancy, portfolio and paper runtime. In Signals, inspect **Execution, spread, fees and next-funding estimate**, **Paper path, fills and mature outcome**, and exact source provenance.

## Interpret money correctly

- Reconciled net uses fill-price gross P&L minus fees plus signed settled funding. Funding can be a debit or credit; it is not always a cost.
- Fill-price execution already contains modeled shortfall where applicable. Do not subtract a displayed slippage attribution a second time.
- Published funding rates/forecasts are different from actual settled position cash flows. An empty calendar in a synthetic test is not evidence that actual perpetual funding was zero.
- Unfilled, pending/open and unresolved outcomes are different states. Missing quote/trigger/funding evidence must not be turned into a zero loss or an assumed successful exit.
- C11 scenarios use declared base-asset quantities. Invalid lot/notional/liquidity sizes may be rejected; the platform does not silently resize every setup upward.

## Changes and common issues

Manual delay affects which later evidence can support entry; browser replay speed does not change it. Changing fees, delay, lifecycle or tested quantity changes the protocol and may invalidate an existing model/release match. A bar-only model requires its explicit [modeled execution](../../../configs/c07_modeled_bar.json) and [bar lifecycle](../../../configs/c09_bar_policy.json); it does not become recorded-quote evidence.

For unknown net, inspect both market path and calendar coverage. For rejected fills, inspect spread, quote age, metadata, entry expiry, size constraints and source receipt times before interpreting a rejected candidate as a strategy loss.

Technical references: [funding](../../components/c06/C06_IMPLEMENTATION.md), [execution](../../components/c07/C07_IMPLEMENTATION.md), [lifecycle](../../components/c09/C09_IMPLEMENTATION.md).
