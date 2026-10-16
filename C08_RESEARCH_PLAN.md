# C08 candidate generation research and implementation plan

Scope agreed 16 October 2026: implement **range breakout and trend continuation as two independent hypothesis families**, using Binance USDT perpetual inputs and the existing component/testing workflow. Both initial presets use 15-minute completed bars. The hypotheses produce inspectable setups; C09/C11/C12 will determine executable outcomes, costs and evidence for promotion.

## Hypotheses and exact definitions

| Family | Long trigger | Short trigger | Initial parameters |
| --- | --- | --- | --- |
| `prior_range_breakout` | Current close strictly exceeds the highest high of the previous 20 bars | Current close strictly falls below the lowest low of the previous 20 bars | 15m; 20 contiguous prior bars; current bar excluded |
| `ema_pullback_continuation` | EMA20 > EMA50, previous close ≤ previous EMA20, current close > current EMA20 | EMA20 < EMA50, previous close ≥ previous EMA20, current close < current EMA20 | 15m; SMA-seeded EMA20/50; current and lagged EMA measurements stabilized |

For range breakout, a close outside a completed range may indicate continuation. Random excursions, reversal and generic market exposure are alternative explanations. Wick-only breaks and equality do not trigger. A new higher close can trigger again on a later bar; there is no hidden crossing or position filter.

For trend continuation, recovery across the fast EMA in the direction of the fast/slow trend may identify a pullback followed by continuation. Lagging filters, serial dependence, reversals and repeated hypothesis selection can explain apparent performance. This baseline needs one prior close at/beyond the EMA, not a multi-bar pullback pattern or a discretionary trend interpretation.

The Donchian convention uses rolling high/low extrema; **excluding the decision bar** and requiring its close are explicit Tradee strategy choices. EMA formulas follow C03's SMA seed and `alpha=2/(n+1)`. [QuantConnect's primary indicator reference](https://www.quantconnect.com/docs/v2/writing-algorithms/indicators/supported-indicators/donchian-channel).

Both presets use a five-minute exclusive entry window anchored to the decision bar's end, zero strategy cooldown and a separate maximum detection lag of one minute. These are engineering assumptions frozen before performance inspection. Long/short evaluation, eligibility and execution remain separate. Each parameter/family change produces a different strategy hash; there is no performance-based parameter search in C08.

## Dependencies and ownership

| Component | C08 consumes | Consumer or boundary |
| --- | --- | --- |
| C01 | Frozen observed universe/history and instrument versions | Eligibility remains causal; current metadata can be an explicitly labeled historical research assumption |
| C02 | Pinned normalized candles and exact available-event prefix | Recorded receipt and modeled candle availability remain distinct; gaps and revisions remain visible |
| C03 | Shared finalized-bar aggregation, reusable features, seed stability, feature/lineage hashes and restart state | Range extrema are strategy-specific trigger boundaries; reusable EMA math stays in C03 |
| C04/C05/C06 | No predictive/context inputs required by either initial preset | Optional future filters need separate hypotheses and after-cost validation |
| C09 | Receives candidate identity, side, reference/trigger context, detection and exclusive expiry | Owns order/stop/target/holding/cancellation rules, quantities and position state |
| C11/C14 | Drive the same incremental C08 engine through historical/live events | C08 does not run a separate strategy implementation for each environment |
| C12 | Receives family/version/spec/config/source identities and complete opportunity inventory | Owns trial accounting, fold isolation, baselines, selection and promotion |

Binance kline updates distinguish partial from closed candles; C02 normalizes this flag and C03 only completes finalized buckets. [Official market-stream reference](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market).

## Files and implementation sequence

| Files | Work |
| --- | --- |
| `tradee/c08/contracts.py` | Strict versioned strategy/config contracts, economic rationale/alternative, immutable validated candidate output |
| `tradee/c08/strategy.py` | Exact prior high/low comparisons and explicit EMA recovery predicates |
| `tradee/c03/catalog.py`, `evaluator.py` | Add reusable `ema20_prior`/`ema50_prior` with one-bar lag, readiness and seed-weight rules |
| `tradee/c08/metadata.py` | Freeze C01 observation snapshots and exact versions; separate observed and research modes |
| `tradee/c08/engine.py` | Same C03 prefix core, per-direction opportunity decisions, source lineage, cooldown and revision diagnostics |
| `tradee/c08/store.py`, `cli.py`, `__init__.py` | Separate atomic SQLite store, hashed manifests/inventory, complete-prefix checks, pagination, inspection and resume |
| `configs/c08_*.json` | Two 15m strategy presets plus observed/research eligibility policies |
| `tests/c08_support.py`, `test_c08_*.py` | Independent formulas/threshold cases, actual C01/C02/C03 integration, rollback/corruption/restart and complete CLI E2E |
| `scripts/verify_c08.py`, `verify_c08_live.py` | Retained manual E2E and opt-in public-feed/saved replay checks |
| `C08_IMPLEMENTATION.md`, `C08_VERIFICATION.md` and existing overview/register | Final contracts, commands, evidence and explicit remaining work |

## C09 and C12 research boundaries

C08 candidates contain no invented stop, target, quantity, leverage, confidence or success probability. Those choices change the predicted outcome and require C09/C12 contracts before strategy performance experiments. C09 must revalidate the thesis at action time, respect expiry and decide how corrections affect an already active position. A C08 candidate is not an executable signal.

C12 must compare each family against no-trade and an explicitly matched simple-exposure baseline using identical data/cost assumptions. Intraday and swing remain separate studies. All tried families, parameters, eligibility and outcome-policy versions belong in trial accounting; renaming a variant does not erase earlier trials. Repeated strategy selection can overfit backtests, which motivates this separation. [Bailey and coauthors, The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

Prior TBot-inspected data remains development data. Synthetic trigger fixtures and public functional smoke do not establish out-of-sample trading evidence. C08's acceptance is functional: correct formulas/prefixes, complete inspectable opportunities, immutable decisions and deterministic recovery. Performance acceptance remains C11/C12.
