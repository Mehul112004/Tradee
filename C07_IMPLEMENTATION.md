# C07 execution, costs and tradability

Implemented 13 October 2026, following the C06 workflow: explicit contracts, independent arithmetic checks, unit/integration tests, actual-process E2E, public-data smoke, durable replay and documented upgrades. C07 evaluates proposed **independent market-execution scenarios** for Binance crypto USDT perpetual futures. It provides one-leg prices/costs and admission reasons under declared assumptions. It does not establish positive expectancy or confirm an exchange fill.

## Dependencies and consumers

| Input/component | C07 uses | C07 supplies to |
| --- | --- | --- |
| C01 | Pinned universe, observed rule versions, identity, status, quantity/tick/notional rules | C09/C11/C13/C14 receive rule-gated execution estimates |
| C02 | Immutable dataset, exact available-event prefix, quotes, marks and completed candles | C11 replays the same execution model; C14 evaluates available live observations |
| C03 | Optional required feature artifacts from the **same dataset**, with availability, prefix, age and stability gates | C08/C09/C14 can request the readiness required by their strategy |
| C06 | Fresh next-settlement funding estimate for proposed side/quantity | C10/C13 consume estimated cost context; C09 owns actual exposure and funding booking |
| Caller, later C08/C09/C13 | Intent, proposed base quantity, reference/stop, detection/expiry, horizon and explicit fees/config | C09 owns lifecycle and outcomes; C10 owns net expectancy; C15 compares estimates with forward observations |

C07 never constructs a strategy, fits thresholds from outcomes, grants a maker fill, shares capital between intents or books funding. C08 creates candidates; C09 requests entry/exit scenarios and produces executed quantity timelines; C11 orchestrates historical trades. Rechecking current feature readiness does not rerun the strategy or invalidate its thesis: C08/C09 own those decisions.

## Files and major parts

| File | Responsibility |
| --- | --- |
| `tradee/c07/contracts.py` | Frozen intent, versioned fee evidence, strict config and immutable records |
| `tradee/c07/math.py` | Exact quantities, common lot grid, rational impact price, adverse tick rounding, fees and cost attribution |
| `tradee/c07/engine.py` | Causal replay prefix, source selection, latency/rule/readiness gates, one-leg fill scenarios, funding context and checkpoints |
| `tradee/c07/store.py` | Separate C07 SQLite database, hashed manifests/reports, atomic report/checkpoint writes and resume |
| `tradee/c07/cli.py` | Explain/run/report/manifest/summary commands and strict JSON collections |
| `configs/c07_execution.json` | Observed quote model, 30-second manual delay and conservative size/freshness budgets |
| `configs/c07_modeled_bar.json` | Explicit completed-bar research model, synthetic spread, volume participation and mark/metadata assumptions |
| `configs/c07_fee_assumptions.json` | Illustrative taker/maker rates, labeled unverified account assumptions |
| `scripts/verify_c07.py` | Offline raw-import-to-feature/funding/execution E2E through actual CLI processes |
| `scripts/verify_c07_live.py` | Opt-in public metadata/quote/mark capture and saved replay parity |
| `tests/test_c07_{math,engine,persistence,cli,e2e}.py` | Independent numeric, causal, recovery and connected workflow checks |

## Provider rules and evidence

Fee calculations use base quantity × execution price × fractional rate for each leg. Market scenarios use the explicit **taker** rate. Fee tiers/discounts vary; the supplied `0.0005` taker and `0.0002` maker are illustrative assumptions, not a query of this account. Maker rates are retained for a later passive model; they are never awarded by the current engine. [Binance fee explanation](https://www.binance.com/en/support/faq/detail/360033544231), checked 13 October 2026.

Use `PRICE_FILTER.tickSize` and quantity filter step sizes rather than display precision. C07 checks both general and market lot limits/grids and checks the reported market-take bound against available mark evidence. The price bound check is a conservative model plausibility gate. [Official market-data/exchange-information reference](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data).

Market minimum notional uses quantity × mark. A declared reduce-only exit can skip the minimum-notional gate only with caller-supplied position quantity and a quantity that does not exceed it. This is scenario evidence, not authenticated account verification. `PERCENT_PRICE` for limit orders is not applied to the simulated market price. Account margin/leverage/position controls remain downstream or future account integrations. [Official trade reference](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade).

## Intent, fees and configuration

An intent pins its ID, full C01 instrument identity, symbol, buy/sell side, proposed base quantity, detection and exclusive expiry timestamps, reference price and entry/exit purpose. Optional fields declare directional stop, planned holding end, required feature IDs/timeframe, and reduce-only exit position evidence. Numbers are exact decimal strings; timestamps are UTC milliseconds. A long entry is buy, short entry sell. An exit's side is its order direction, not its original position side.

Only `MARKET` can produce a current fill scenario. A `LIMIT` intent is accepted as a declared type but rejected with `passive_execution_unsupported`; touching a limit in a bar cannot prove execution or maker fees. No partial fill is invented when the full requested quantity fails the liquidity cap.

A fee schedule requires taker/maker rates and named evidence. `source_kind=assumption` makes the assumption explicit. `observed` additionally requires `available_ms` and `effective_from_ms`; optional exclusive `effective_until_ms` prevents an expired fee schedule from being used. Fees known/effective after evaluation cannot enter that decision. Account-specific fee acquisition is deferred.

Key default budgets:

| Setting | Default and role |
| --- | --- |
| Processing/delivery/manual delay | 0 / 0 / 30000ms; additive **engineering assumptions**, not measured distributions |
| Quote and mark age | Strictly less than 5000ms, measured from economic event time |
| Metadata age | Strictly less than 1800000ms, with observed availability |
| Spread budget | ≤20bps of quote midpoint |
| Adverse entry drift | ≤50bps from reference to final modeled price, including spread/impact/tick effects |
| Extra slippage / impact coefficient | 2bps + 5bps × requested quantity / visible same-side best size |
| Best-size fraction | Full quantity ≤25% of displayed same-side size; displayed size can cancel |
| Quantity rounding | Reject off-grid by default; opt-in floor never increases requested quantity |
| Cost/R | Optional ceiling on **execution shortfall plus fee**, excluding unresolved/estimated funding |
| Required features | Valid, available, sufficiently recent and stable by default; only declared IDs gate |
| Funding requirement | Optional; unknown projection remains null unless configured to reject it |

These thresholds are versioned assumptions for engineering/research, not calibrated Binance execution guarantees. Stress tests should vary delays, size and cost parameters before performance research. Empirical calibration is C07-U03.

## Recorded quote and coarse bar models

**Recorded quote model:** requires a recorded C02 dataset, available observed C01 metadata, current best bid/ask and fresh mark. Buying crosses the ask; selling crosses the bid. A late older quote cannot refresh/replace a newer economic quote. The engine chooses observations already present in the exact replay prefix and evaluates at the requested logical time.

**Modeled bar model:** requires an explicitly modeled, candle-only C02 dataset. It uses the newest available finalized **one-minute close** at or after the earliest action time. Synthetic bid/ask bracket that close by half the configured spread. Historical volume is a declared liquidity proxy: default full size ≤0.1% of bar volume, with impact coefficient 100bps per participation fraction. It never claims an exact intrabar fill or next-open price.

The bar preset explicitly selects `metadata_mode=research_assumption` and `bar_mark_proxy=bar_close`. Current metadata vintage and contract close are then labeled research assumptions; they are not verified historical rules/mark prices. Omitting the mark proxy leaves historical mark coverage unsupported. Without usable historical funding forecasts the projection remains null. Observed mode never silently substitutes these assumptions.

A decision between completed bars can use a completed close only if that close is at/after its **earliest allowed action** and still within the bar freshness budget. This is an available-price sensitivity scenario, not a guarantee that a later market action obtained the old close. A previous close before a 30-second delayed action is rejected. More faithful historical execution needs recorded quotes/trades/marks and historical metadata; gaps remain in the upgrade register.

## Formulas and exact monetary policy

Let `s=+1` for buy and `−1` for sell; `q` is effective base quantity, `r` the reference price, `m` the observed midpoint, `t` the ask/bid touch, `v` same-side visible size or the declared bar-volume proxy, `a` extra slippage bps and `b` impact coefficient.

```text
raw execution price = t × [1 + s × (a + b × q/v) / 10000]
fill = adverse tick rounding(raw execution price)
fee = q × fill × taker_rate

delay drift = s × (m − r) × q
spread crossing = s × (t − m) × q
extra slippage and rounding = s × (fill − t) × q
implementation shortfall = s × (fill − r) × q
                       = drift + spread + extra
execution-plus-fee cost = shortfall + fee
planned risk = |r − stop| × q
cost bps = execution-plus-fee cost / (r × q) × 10000
cost R = execution-plus-fee cost / planned risk
projected cost with next funding = execution-plus-fee cost − signed funding cashflow
```

The price calculation uses exact rational arithmetic before final tick rounding: buy rounds up, sell down, including non-power-of-ten ticks. This avoids a rounded repeating participation quotient pushing a price across a tick. Monetary products/differences use isolated Decimal precision 400 with traps on inexact/rounded arithmetic. Diagnostic ratios alone round half-even to 12 decimal places. Budget comparisons use unrounded multiplication, not rounded displayed ratios.

The common quantity grid is the decimal least common multiple of `LOT_SIZE` and `MARKET_LOT_SIZE` steps. Floor mode subtracts the exact remainder, then rechecks both limits and positive size. It never silently rounds an invalid quantity upward. Fee/amount outputs are canonical strings; unknown amounts are null.

**Accounting ownership:** for a realized long, `q × (exit_fill − entry_fill) − both_leg_fees + booked_signed_funding` already includes spread/impact/drift through the fill prices. Do not subtract implementation shortfall again. For short, reverse the fill-price difference. C07 costs are attribution and decision estimates; C09 books fills/fees/funding once, and C11 reconciles ledgers. Two independent intents do not share or consume book liquidity/capital.

## Timing, feature gates and funding

`action_not_before_ms = detected_ms + processing_delay_ms + delivery_delay_ms + manual_delay_ms`.

Before that time, at/after exclusive expiry, or after a declared holding horizon, the intent cannot fill. At evaluation, C07 rechecks rules, required feature readiness, fee validity, fresh price/mark, spread, quantity, liquidity, notional, final-price drift, stop invalidation, market-take bound and optional execution cost/R. Rejected estimates have `fill=null` and `costs=null` with explicit reasons.

Required C03 artifacts must match identity/timeframe and the same pinned C02 dataset. Their evaluation/input/assumed-usable/end timestamps cannot exceed the decision; their input cursor must already be in this prefix. Age is strictly less than the timeframe plus configured grace. A globally unready optional feature does not block a separately declared valid required feature. Artifacts have verified hashes; checksums provide integrity, not proof that arbitrary externally authored JSON is trustworthy.

Funding uses C06's newest available, fresh mark context. For a holding horizon before the next settlement it is zero; across it, only that **next known settlement estimate** is supplied. Entry or planned close within inclusive ±15 seconds of that timestamp makes the projection ambiguous/null. Longer-hold additional settlements remain unresolved. `require_funding_estimate` requires this defined projection only, not full-horizon funding certification. Exits do not book/project an additional funding charge. C09/C06 calendar accounting will provide settled outcomes.

## Replay, persistence and CLI

C07 validates and consumes `(available_ms,event_id)` order. Economic timestamp selects latest quotes/candles; receipt/availability selects what can be known. Timer evaluation cannot move backward or inspect beyond its prefix/decision horizon. Same-ms revisions keep prior immutable records and a stable fill key with a new revision hash. A fill key identifies a scenario for later reconciliation; it is not proof that an order was executed.

Run manifests pin dataset/vintage, all intents, fees/config, universe and exact metadata versions, feature artifacts, decision horizon, Python version and production source-tree hash. Separate SQLite `data/c07.sqlite3` uses application C07/schema 1. Report and checkpoint commit in one transaction. Checkpoints retain latest relevant sources, child funding state, cursor, prefix hash, event count and evaluation clock. Resume validates compatibility/integrity. Repeating the same completed run returns the same hashes/counts; changed code/config/data/fees creates a new run. Operational computation time is excluded from deterministic hashes.

```sh
conda activate tradee
python -m tradee execution explain
python -m tradee --db data/c01.sqlite3 execution \
  --market-db data/c02.sqlite3 --execution-db data/c07.sqlite3 \
  run DATASET_HASH --intents intents.json --fees configs/c07_fee_assumptions.json \
  --config configs/c07_execution.json --features features.json
python -m tradee execution summary RUN_HASH
python -m tradee execution manifest RUN_HASH
python -m tradee execution report REPORT_HASH
```

Database options precede the action. Optional `--as-of` is a timezone-aware ISO timestamp bounded by the pinned dataset cutoff; default is that cutoff. `--batch-size` selects checkpoint frequency. C01/C02/C07 paths must differ. Exit **0** means a successful command and, for run, all scenarios admitted; **2** means persisted policy rejection; **1** means invalid input/operational failure. Admission means model/data-policy acceptance, not a good trading signal.

Intent file schema:

```json
{
  "schema_version": 1,
  "intents": [{
    "intent_id": "paper-entry-1",
    "instrument_id": "REPLACE_WITH_FULL_C01_INSTRUMENT_ID",
    "symbol": "BTCUSDT", "side": "buy", "quantity": "0.001",
    "detected_ms": 1791910300000, "expires_ms": 1791910420000,
    "reference_price": "83000", "stop_price": "82000",
    "holding_until_ms": 1791914000000,
    "required_features": ["log_return_1"], "feature_timeframe": "1m"
  }]
}
```

This is illustrative schema, not a current executable trade. The E2E script creates fully bound, runnable fixtures. An optional feature file has `{"schema_version":1,"feature_snapshots":[...]}` where each entry is the complete output of C03 `features snapshot`, including its hash. If no features are requested, omit the file and required-feature fields.

## E2E and manual acceptance

```sh
conda run -n tradee python -m unittest tests.test_c07_e2e -v
conda run -n tradee python -m scripts.verify_c07 --output data/c07_checks/demo1
```

Use a fresh directory; omitting output uses temporary artifacts. The script performs 27 actual production CLI commands, imports synthetic metadata/candles/mark/quotes with real receipt times, pins data, computes real C03 artifacts on that same recorded dataset, joins C06 context and persists C07 reports. It injects a real SQLite statement failure after a committed batch and resumes in another process. It tests repeat/correction immutability, expiry, quantity, unsupported passive order, spread and delay rejections, and the separate modeled-bar path. No internal component is mocked.

Independent one-unit quote expectations at reference/midpoint 100, bid 99.9, ask 100.1, size 10, tick 0.1, rates +0.001 funding and 0.0005 taker:

| Scenario | Fill | Fee | Shortfall + fee | Next funding cashflow | Projected cost |
| --- | ---: | ---: | ---: | ---: | ---: |
| Buy | 100.2 | 0.0501 | 0.2501 | −0.1 | 0.3501 |
| Sell | 99.8 | 0.0499 | 0.2499 | +0.1 | 0.1499 |

The quote fixture explicitly sets zero manual delay; a separate run verifies the default 30-second delay rejects an early action. The bar scenario admits a close at its 30-second action boundary, giving fill 100.1/cost 0.15005 and **null funding projection**. Synthetic instrument rules are clearly separate from Binance historical claims.

Manual review: inspect `e2e_report.json`, raw inputs/configs and `e2e_commands.json`; read execution report/manifest using the retained database; compare the table above, timestamps, feature hash and funding source; repeat a completed command and confirm identical hashes/counts. Inspect rejected reports for null fills/costs. This is a connected foundation workflow through C07, not a strategy backtest or Telegram flow.

Public read-only smoke and saved replay:

```sh
conda run -n tradee python -m scripts.verify_c07_live --output data/c07_checks/public1
conda run -n tradee python -m scripts.verify_c07_live --replay --output data/c07_checks/public1
```

Capture needs network and the existing optional live dependency. It records public metadata, quote and mark only, then compares direct prefix evaluation with persisted replay for a synthetic minimum-notional buy. Fees/zero delay are explicit assumptions; a legitimate business-policy rejection is a passing fail-closed integration check. Evaluation is at latest recorded input availability, not proof of wall-clock actionability. See [verification](C07_VERIFICATION.md) for the actual outcome and [upgrade register](COMPONENT_UPGRADES.md#c07-execution-and-tradability) for passive fills, calibration, historical coverage and other limits.
