# C03 mathematical feature specification

Implemented v1 — 21 September 2026. This is the approved formula contract for [the implementation plan](C03_RESEARCH_PLAN.md). See [verification results](C03_VERIFICATION.md). A feature is a measurement, not evidence of profitability or a trading instruction.

C08 extension — 16 October 2026: `ema20_prior` and `ema50_prior` add reusable one-bar-lagged EMA measurements for pullback/recovery detection. Existing baseline formulas remain unchanged.

## 1. Shared notation and conventions

Bars belong to one instrument and timeframe, have consecutive integer indices starting at 0, and are finalized and available at the evaluation cursor. `O_t, H_t, L_t, C_t` are prices; `V_t` is base-asset volume; `Q_t` is quote-asset volume; `TB_t` and `TQ_t` are taker-buy base and quote volumes. All sums below require complete, contiguous windows. A missing bar is not a zero-volume bar.

- Current-inclusive window: `W_n(t) = {t-n+1, …, t}`.
- Prior-only window: `P_n(t) = {t-n, …, t-1}`.
- `mean(X,S) = sum(X_i for i in S)/len(S)`.
- `sd0(X,S) = sqrt(sum((X_i-mean(X,S))² for i in S)/len(S))`.
- `n` counts bars, not days. On a 15m timeframe, 20 bars represent five hours; on 1d, they represent twenty days.
- Ratios are fractions unless the name explicitly contains `bps` or `pct`. One basis point is `0.0001`. RSI and ADX use a 0–100 scale; Bollinger `%B` below is a fraction.
- No implicit rounding, clipping, denominator epsilon, annualization, forward fill or backfill.
- An undefined denominator produces `value=null` with a reason. Insufficient history is distinct from a valid zero.

Population standard deviation (`ddof=0`) is our descriptive-window convention. Sample estimation would divide by `n-1` and must have another definition/version. [NumPy's definition](https://numpy.org/doc/stable/reference/generated/numpy.std.html).

**Warm-up counts below are mathematical minima after a valid segment starts, not claims that recursive seeds have become negligible.** See the separate stabilization policy in the plan.

## 2. Smoothing primitives

### SMA

`SMA_n(t) = mean(C, W_n(t))`.

First output: index `n-1`, after `n` closes. Recommended reusable periods: 20; other periods must be explicit configuration. Price units.

### EMA, SMA-seeded

`alpha = 2/(n+1)`.

`EMA_n(n-1) = mean(C_0, …, C_(n-1))`.

For `t >= n`: `EMA_n(t) = EMA_n(t-1) + alpha*(C_t-EMA_n(t-1))`.

First output: `n` closes. Proposed periods: 20 and 50. Seed, segment start and smoothing coefficient are part of the definition. [TA-Lib EMA implementation](https://raw.githubusercontent.com/TA-Lib/ta-lib/main/src/ta_func/ta_EMA.c).

### One bar prior EMA

`ema20_prior(t) = EMA20(t-1)` and `ema50_prior(t) = EMA50(t-1)` over the same contiguous segment. They require 21/51 bars respectively and exclude the current close from the returned measurement. Their definitions inherit the EMA seed and add one bar of lag to the seed-weight/readiness calculation. Under threshold `1e-6`, prior EMA50 needs 397 contiguous bars; current EMA50 needs 396. C08 uses these current-prefix measurements to avoid treating a historical-target snapshot as a fresh indicator. EMA values remain C03 float64 analytical outputs.

### Wilder running average, RMA

For an input series beginning at index `a`, seed at `a+n-1` with the arithmetic mean of its first `n` valid observations. Subsequently:

`RMA_n(X)_t = ((n-1)*RMA_n(X)_(t-1) + X_t)/n`.

`alpha=1/n`, not `2/(n+1)`. ATR, RSI and optional ADX share this primitive with explicitly different input streams/start indices. `ewm(alpha=1/n, adjust=False)` alone does not supply this SMA seed; pandas starts its recurrence from the first observation. `min_periods` changes visibility, not initialization. [pandas EWM semantics](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.ewm.html).

## 3. Returns and trend

| Feature ID | Formula | Units | Minimum bars |
| --- | --- | --- | --- |
| `log_return_1` | `ln(C_t/C_(t-1))` | Log-return fraction | 2 |
| `log_return_4`, `log_return_12` | `ln(C_t/C_(t-h))`, `h=4,12` | Log-return fraction | `h+1` |
| `simple_return_h` — diagnostic | `C_t/C_(t-h)-1` | Fraction | `h+1` |
| `ema20_distance_atr14` | `(C_t-EMA_20(t))/ATR_14(t)` | ATR multiples | 20 |
| `ema20_50_spread_atr14` | `(EMA_20(t)-EMA_50(t))/ATR_14(t)` | ATR multiples | 50 |
| `ema20_slope5_atr14` | `(EMA_20(t)-EMA_20(t-5))/(5*ATR_14(t))` | ATR multiples per bar | 25 |

All `h+1` closes must belong to a contiguous segment. Rolling log returns also equal the sum of the corresponding one-bar log returns. The slope is a five-bar finite difference, not an OLS regression slope or an angle. These normalized trend formulas are **Tradee-defined features**, not standardized named indicators. Their denominators include the current finalized bar, which is available at evaluation time.

Positive distance, spread or slope describes orientation; it does not prescribe a long trade. EMA-derived measurements are correlated and should not be counted as independent confirmations.

## 4. Volatility

### True range and Wilder ATR

For `t >= 1`:

`TR_t = max(H_t-L_t, abs(H_t-C_(t-1)), abs(L_t-C_(t-1)))`.

`ATR_n(n) = (TR_1 + … + TR_n)/n`.

For `t > n`: `ATR_n(t) = ((n-1)*ATR_n(t-1)+TR_t)/n`.

No synthetic `TR_0` is inserted. ATR14 first becomes defined at index 14: **15 bars**. ATR has price units and is not directional. `atr14_fraction = ATR_14(t)/C_t`; raw ATR14 is also available as a dependency/diagnostic. [Fidelity ATR formula](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr); [TA-Lib initialization/lookback](https://raw.githubusercontent.com/TA-Lib/ta-lib/main/src/ta_func/ta_ATR.c).

### Return dispersion and squared-return variation

Let `r_t = log_return_1(t)`.

| Feature | Formula | Minimum bars | Meaning |
| --- | --- | --- | --- |
| `return_sd20` | `sd0(r, W_20(t))` | 21 | Dispersion of one-bar log returns around their window mean |
| `realized_variance20` — diagnostic | `sum(r_i² for i in W_20(t))` | 21 | Sum of squared log returns over the window |
| `realized_vol20` — diagnostic | `sqrt(realized_variance20)` | 21 | Square root of window variation, not per-bar standard deviation |
| `return_surprise20_prior` | `(r_t-mean(r,P_20(t)))/sd0(r,P_20(t))` | 22 | Current return relative to the preceding 20 returns |

These are explicitly different quantities. There is no division by 20 in realized variance and no demeaning there. For example, constant nonzero returns have zero dispersion but positive squared-return variation. `return_surprise20_prior` is a descriptive standardized shock, **not a statistical jump detector or p-value**. The current return cannot inflate its own baseline denominator.

V1 does not annualize any quantity. A later annualized estimate must specify the bar rate, calendar and assumptions; multiplying by a square root of time is not universally valid for dependent returns.

## 5. Reversion and location

### Prior-window close deviation

`close_z20_prior = (C_t-mean(C,P_20(t)))/sd0(C,P_20(t))`.

Minimum: 21 closes. The current close is excluded from both baseline mean and scale. This differs from current-inclusive Bollinger location. A zero baseline standard deviation is undefined, even if the numerator is also zero. It is a price-location score, not proof of stationarity or expected reversal.

### Rolling execution-volume VWAP

`VWAP_n(t) = sum(Q_i for i in W_n(t))/sum(V_i for i in W_n(t))`.

`vwap20_distance_atr14 = (C_t-VWAP_20(t))/ATR_14(t)`.

Minimum: 20 complete bars and positive total base volume; normalized distance additionally needs positive ATR14. Raw `vwap20` is available. Use Binance's reported quote and base volume fields, whose ratio represents a volume-weighted trade price up to exchange reporting precision. Do not substitute `sum(((H+L+C)/3)*V)/sum(V)`, which is a candle-price approximation. Do not average constituent VWAPs without weights. [Binance candle field definitions](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data); [Sierra Chart's distinction between rolling and resetting VWAP](https://www.sierrachart.com/index.php?page=doc/StudiesReference.php&ID=352).

### UTC-session VWAP — optional v1 output, disabled in baseline

Let `e_t` be the target bar's exclusive end in milliseconds, and let `a = floor((e_t-1)/86400000)*86400000`. Sum finalized one-minute `Q` and `V` over `[a,e_t)` and divide their totals. This measures the UTC session containing the target bar's final minute, including a bar ending exactly at midnight. Require complete base-minute coverage from `a`; starting the collector mid-session does not redefine the anchor.

Output `vwap_utc_session` in price units and optionally `(C_t-vwap_utc_session)/ATR14_t`. The anchor is a clock convention for a 24/7 market. Strategy-selected swing anchors belong to a later C05 integration and must record when the anchor became known.

## 6. Participation

| Feature | Formula | Minimum bars / missingness |
| --- | --- | --- |
| `relative_quote_volume20_prior` | `Q_t / mean(Q,P_20(t))` | 21; prior mean must be positive |
| `taker_base_imbalance20` | `(2*sum(TB_i)-sum(V_i))/sum(V_i)` over `W_20(t)` | 20; total base volume positive |
| `taker_quote_imbalance20` — diagnostic | Same formula with `TQ` and `Q` | 20; total quote volume positive |
| `mean_trade_quote_notional` — diagnostic | `Q_t / trade_count_t` | 1; positive reported count |

Imbalance lies in `[-1,1]` for valid source data. It measures which side initiated volume; it is not net capital entering an asset. Do not average individual bar imbalance ratios; sum the underlying volumes first. A current bar with zero volume and a positive prior-volume baseline has relative volume 0, not missing.

Recorded aggregate trades can later provide `sum(sign_j*price_j*quantity_j)`, where buyer-is-maker implies seller aggression and `sign=-1`; otherwise `+1`. **Do not enable trade-window flow as a production feature yet:** current C02 explicitly does not certify trade-stream completeness. Candle taker totals support the first version without inventing historical tick coverage.

## 7. RSI and Bollinger indicators

### Wilder RSI14 — included in baseline

For `t>=1`: `gain_t=max(C_t-C_(t-1),0)`, `loss_t=max(C_(t-1)-C_t,0)`.

Seed average gain/loss at index `n` from changes `1…n`; apply the RMA recurrence thereafter. For nonzero total smoothed movement:

`RSI_n(t) = 100*avg_gain_t/(avg_gain_t+avg_loss_t)`.

First output: `n+1` closes, 15 for RSI14. Gain-only → 100; loss-only → 0. **Both zero → 50 with `flat_series=true`**, an explicit Tradee neutral convention. It is not a universal library convention; reference comparisons must special-case it. No trading thresholds are emitted. [Fidelity RSI calculation](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI); [TA-Lib RSI implementation](https://raw.githubusercontent.com/TA-Lib/ta-lib/main/src/ta_func/ta_RSI.c).

### Bollinger Bands(20,2) — supported diagnostics, baseline disabled

`M_t = mean(C,W_20(t))`, `S_t = sd0(C,W_20(t))`.

`U_t=M_t+2*S_t`; `L_t=M_t-2*S_t`.

`bb20_width_fraction=(U_t-L_t)/M_t`; `bb20_pct_b=(C_t-L_t)/(U_t-L_t)`.

First output: 20 closes. The bands have price units. Width is a fraction, not percent. `%B` is not clipped to `[0,1]`. For a flat series, all bands equal the close, width is 0 and `%B` is undefined. We explicitly select SMA and population variance. This is not a 95% confidence interval. [John Bollinger's rules](https://www.bollingerbands.com/bollinger-band-rules); [TA-Lib bands](https://raw.githubusercontent.com/TA-Lib/ta-lib/main/src/ta_func/ta_BBANDS.c) and [variance calculation](https://raw.githubusercontent.com/TA-Lib/ta-lib/main/src/ta_func/ta_VAR.c).

## 8. Candle shape — supported diagnostics, baseline disabled

Let `R=H_t-L_t`:

- `body_fraction=(C_t-O_t)/R`, signed, `[-1,1]`.
- `upper_wick_fraction=(H_t-max(O_t,C_t))/R`, `[0,1]`.
- `lower_wick_fraction=(min(O_t,C_t)-L_t)/R`, `[0,1]`.
- `close_location=(2*C_t-H_t-L_t)/R`, `[-1,1]`.
- `range_atr14_prior=R/ATR14_(t-1)`, ATR multiples, first defined after 16 bars.

The first four need one bar and positive range; a zero-range candle returns undefined shape ratios. When defined, `abs(body_fraction)+upper_wick_fraction+lower_wick_fraction=1`. The fifth has a prior-only ATR denominator so the range being measured cannot inflate its own reference scale. No candlestick-pattern labels are inferred.

## 9. Quote features — optional source-dependent diagnostics

Use the most recent quote **by event time** among observations available at the exact evaluation cursor. Require `quote.event_ms<=decision_ms`. Choose revisions by recorded cursor for ties. Configure `max_quote_age_ms=5000` initially as an engineering freshness budget, not a latency claim; at age equal to the limit, the quote is stale.

For bid `b`, ask `a`, bid base quantity `B`, ask base quantity `A`:

| Output | Formula / units |
| --- | --- |
| `mid_price` | `(a+b)/2`, quote/base price |
| `spread_bps` | `10000*(a-b)/mid_price` |
| `top_bid_quote_notional` | `b*B`, quote units |
| `top_ask_quote_notional` | `a*A`, quote units |
| `top_base_imbalance` | `(B-A)/(B+A)`; undefined if both sizes are zero |
| `quote_event_age_ms` | `decision_ms-quote.event_ms` |
| `quote_receipt_age_ms` | `decision_ms-quote.received_ms`, for recorded observations |

Locked quotes (`bid=ask`) have zero spread; crossed quotes are invalid. Stale/missing quotes return missing price/size features while available age diagnostics explain why. Best-level quantities are **not full order-book depth**, and a spread observation is not an executable fill or a complete transaction-cost model. Candle-only historical snapshots have no synthetic quotes. Current C02 can supply these fields through recorded quotes; C07 later owns execution interpretation.

## 10. Deferred indicator definitions — no v1 implementation

These are documented alternatives, not extra default votes. Add only after a strategy hypothesis explains why they are needed.

### MACD(12,26,9)

`M_t=EMA12_t-EMA26_t`; signal `S_t=EMA9(M)_t`; histogram `H_t=M_t-S_t`. Use independently SMA-seeded price EMAs from the same segment origin. `M` starts at index 25; seed its signal with `M_25…M_33`; histogram starts at 33, after 34 price bars. Optional normalization is `H_t/ATR14_t` and needs positive ATR. This explicit seeding variant may differ from library MACD routines that realign the fast EMA to the slow EMA's start. [Fidelity MACD definition](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/macd).

### ADX14 / directional indicators

For `t>=1`, `u=H_t-H_(t-1)`, `d=L_(t-1)-L_t`. Set `+DM=u` if `u>d` and `u>0`, otherwise 0. Set `-DM=d` if `d>u` and `d>0`, otherwise 0; ties give both 0.

Smooth TR and both DM streams from index 1 using the defined RMA seed. `DI_plus=100*RMA(+DM)/RMA(TR)` and `DI_minus=100*RMA(-DM)/RMA(TR)`. With positive TR and positive DI sum, `DX=100*abs(DI_plus-DI_minus)/(DI_plus+DI_minus)`. For positive TR but both DI zero, DX=0; zero TR is undefined. Seed ADX from `DX_n…DX_(2n-1)` and thereafter RMA-smooth DX. Nominal first ADX: `2n` bars, 28 for n=14, provided every required DX is defined. This is our explicit textbook-style seed contract; any reference library must be checked for DM seed differences. [TA-Lib ADX source](https://raw.githubusercontent.com/TA-Lib/ta-lib/main/src/ta_func/ta_ADX.c).

ADX measures strength, not direction. Keltner channels, stochastic RSI, Supertrend, OBV/CVD, swing-derived levels and volume-profile features are also deferred. Their exclusion avoids implementing multiple overlapping transforms before we have an evaluated baseline.

## 11. Formula status and references

The named indicator recurrences were checked against the primary implementations/provider documentation linked above. Tradee-derived ratios are specified by their equations rather than represented as universal indicator standards. The seed, zero-case and denominator conventions are approved design choices. Tests now cover hand-derived fixtures, independent 70-digit Decimal recurrences and frozen TA-Lib 0.6.8 wrapper / C library 0.6.4 outputs, generated with NumPy 2.4.1. The standard test suite and production engine need neither external package. Tradee's neutral flat RSI of 50 deliberately differs from TA-Lib's 0.

Exact reference versions and conventions are recorded in `tests/fixtures/c03/talib_0_6_8.json`; `scripts/generate_c03_oracle.py` reproduces that fixture without calling Tradee calculations. See [the validation plan](C03_VALIDATION_PLAN.md) for numerical and causal acceptance checks.
