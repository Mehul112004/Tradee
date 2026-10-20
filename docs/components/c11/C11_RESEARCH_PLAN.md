# C11 historical simulation research and decisions

Authorized 19 October 2026 under the established implementation, robust-test, E2E, documentation and local-commit workflow. C11 measures the existing frozen hypotheses; C10 estimates conditional expectancy, C12 controls research selection and C13 supplies shared-capital admission. Engineering fixtures establish accounting and causal behavior, not a profitable strategy.

## Dependencies, consumers and ownership

| Component | C11 receives or drives | C11 supplies / boundary |
| --- | --- | --- |
| C01 | Pinned universe observations and exact instrument versions | Eligibility/rule evidence accompanies every run; observed metadata and historical research assumptions remain distinct |
| C02 | Frozen dataset, receipt/model availability, exact ordered replay | Both passes must consume identical full cursor/hash/count; later imports cannot rewrite a run |
| C03 | Shared feature computation, stabilization, gaps and lineage through C08/C09 | Persisted feature artifacts and lineage for candidate diagnostics and C10 joins |
| C06 | Calendar evidence, settlement revisions and quantity-based funding | Reconciled signed cash flows; unknown coverage stays null |
| C07 | Shared entry/exit delays, rule gates, fill prices, fees and shortfall | Fill evidence and drift/spread/slippage attribution; shortfall is not subtracted twice |
| C08 | Each strategy's complete direction-by-bar diagnostics and independent candidates | Full emitted, rejected, warm-up and out-of-window inventory; no outcome-based admission |
| C09 | Shared activation, quantities, stop/target/partial/time exits, maturity and ledger | Source-bound trade outcomes and revision availability; no duplicate lifecycle implementation |
| C10 | Future consumer: earlier matured outcome revisions and causal feature joins | Will produce frozen inference artifacts for later injected policies; no fitting inside simulation |
| C12 | Future caller: frozen windows, hypotheses and cost assumptions | Complete artifacts support folds, purging, experiments and sensitivity; C11 does not certify holdouts |
| C13 | Future integration: risk sizing, shared capital and concurrent admission | A separate finite-capital track must preserve the independent baseline |
| C15 | Future consumer: historical expected behavior and evidence | Replay/forward reconciliation, coverage and cost comparisons |

## Major decisions

1. **Independent scenarios first.** A scenario freezes a C08 strategy, C09 policy, positive quantity and intraday/swing label. Both range breakout and EMA pullback continuation are supported. Concurrent candidates do not consume each other's capital or recorded liquidity. Identical hypothesis/policy/size duplicates are rejected.
2. **Shared logic, two passes.** C08 first builds immutable candidates and source-bound feature evidence. C09 then receives those intents and activates each only when its exact detection cursor and prefix arrive. Both passes must consume the same full pinned event count, cursor and hash. Knowing an intent's identity in advance cannot cause entry, expiry, valuation or label publication before activation. Each scenario has its own child lifecycle, avoiding cross-family feature-state contamination.
3. **Clock and execution.** Process source events in `(available_ms,id)` order, running C09 per event. Inject entry-action, expiry, holding-limit, exit-delay and timeout ticks between source times. At equal timestamps process the ordered source group before additional scheduled ticks and regular valuation samples. An existing quote from before the exit's not-before time cannot execute that exit. Missing liquidity keeps exposure open/unresolved.
4. **Decision windows.** Select by `detected_ms` in an explicit half-open interval. Earlier source data remains warm-up. Selected candidates consume the pinned tail to `as_of_ms`; no forced closing fill appears at the boundary. C12 will own cross-fold position ownership, overlapping-label purging and holdout isolation. A C11 window alone is not a walk-forward test.
5. **Point-in-time outcomes.** Evaluate C09 maturity at every known source/timer prefix. Persist economic/label revisions with their observation time, including initially unresolved states, first mature recognition and later corrections/revocations. Latest outcomes remain in the report. C10 must select the last revision observable strictly before inference, rather than filtering today's final table by exit date.
6. **Regular valuation.** Sample independent P&L on a fixed grid from decision-start through the dataset cutoff. Use fresh recorded marks, or the explicitly declared modeled bar-close proxy. Missing/stale marks produce null valuation; no forward fill. Gross unrealized P&L excludes hypothetical liquidation fees/spread. Book only actual simulated fill fees and C06 settled funding. Combined scenario P&L is a diagnostic sum, not a funded equity curve.
7. **Descriptive reporting.** Preserve all candidate, unfilled and unresolved counts; report mature-only mean net USDT/R, win fraction, positive net amounts and loss magnitudes, profit factor and empirical order statistics. Group by scenario, hypothesis, horizon, symbol, direction and timeframe. Outcomes can overlap and are statistically dependent. No confidence interval, trained expectancy, annualized return, ROI or Sharpe is invented.
8. **Attribution and sensitivity.** Reconcile quantities, fill evidence, gross, fees and net. Explain delay drift + spread crossing + slippage/rounding = implementation shortfall. Compare explicitly rerun fee/execution variants on the same dataset/hypotheses/windows/code; report matched mature deltas and gained/lost coverage. Do not automatically select a winning configuration.
9. **Publication and scale.** Publish a complete run, report and ordered artifacts in one SQLite transaction. A failed run exposes no partial research result. Deterministic rerun restarts both passes; successful reruns verify and reuse immutable evidence. Explicit candidate/sample/artifact budgets fail rather than truncate. Mid-run checkpoints, out-of-core execution and large-history performance are documented upgrades, not claims of this implementation.

## Formulas and evidentiary limits

For a linear USDT future, realized gross is `Σ side_sign × (exit_fill − entry_fill) × exit_quantity`; total paid fees are `Σ fill_quantity × fill_price × fee_rate`. Net is `realized_gross − fees + signed_settled_funding` only when closed and funding is known. C09 owns these calculations; C11 independently checks the ledger identity and quantity conservation.

At a regular sample, gross unrealized is `Σ side_sign × remaining_quantity × (fresh_mark − entry_fill)`. Sample P&L is `realized_gross − booked_fees + settled_funding + gross_unrealized`, null if required marks/funding are unknown. For complete samples, dollar P&L drawdown is `max_t(max(0, max_{u≤t} PnL[u]) − PnL[t])`. Missing samples make full drawdown unknown; the available-sample drawdown is only a lower bound. It is not portfolio percentage drawdown.

QuantConnect documents regular equity/drawdown reporting and distinguishes realized from unrealized results. Its liquidation-value convention includes closing costs; our explicitly labeled **gross mark** convention does not estimate a hypothetical exit. [Official results documentation](https://www.quantconnect.com/docs/v2/local-platform/backtesting/results), checked 19 October 2026. Market replay cannot change the historical book; fill assumptions and size therefore matter. [HftBacktest order-fill documentation](https://hftbacktest.readthedocs.io/en/v1.8.4/order_fill.html), checked 19 October 2026. These references inform scope; Tradee reuses its own C06/C07/C09 models.

## Acceptance and future gates

Literal long/short/partial golden ledgers; exact timers during feed gaps; complete causal inventories; warm-up/window isolation; same-time source/sample ordering; mark staleness; funding revision/revocation times; streaming iterator parity; changed-source failure; atomic write rollback and deterministic retry; immutable reruns; matched fee/delay sensitivity; both-family real-CLI E2E; and saved public candle replay with honest unknown funding/net labels.

Finite-capital equity, margins/liquidation, C10/C13 injection, C12 walk-forward/selection control, tick-path certification, empirical execution calibration and unattended live operations remain explicit dependencies/upgrades in [COMPONENT_UPGRADES.md](../../platform/COMPONENT_UPGRADES.md). No account keys or authenticated endpoints are needed.
