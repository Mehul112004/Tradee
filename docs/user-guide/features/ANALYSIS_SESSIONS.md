# Analysis sessions: the everyday workflow

**Location:** Analysis sessions, `/analysis`. The default Local recording home opens this screen. **Access:** read existing sessions as a viewer; creating, pausing, resuming and stopping require the local operator token. No research models, dataset hashes, worker or separate collector are required for this workflow.

## Start watching

1. Start the backend and frontend as described in [Start Here](../START_HERE.md). Select **Local recording** in the header. Synthetic research databases stay separate.
2. Click **New analysis session**. Enable session controls with the operator token from your local `.env` if requested. Configure `TRADEE_WEB_OPERATOR_TOKEN` and restart the backend if it is not set. Authorization clears on browser reload.
3. Enter a name and up to five Binance USDT perpetual instruments, for example `BTCUSDT, ETHUSDT, SOLUSDT`.
4. Choose the strategy timeframe: **1m, 15m, 1h, 4h or 1d**. This controls detection, not just the chart view. The original engineering presets use 15m; configuring another timeframe does not establish its performance.
5. Select **Range breakout**, **EMA pullback**, or both. Choose **Watch live**.
6. Optionally check **Send setup observations to Telegram**. The server needs `TELEGRAM_BOT_TOKEN` and numeric `TELEGRAM_CHAT_ID` in the root `.env`; the bot must have access to that chat.
7. Click **Start watching**. The backend verifies current instrument rules and downloads up to 500 closed native-timeframe candles for preparation, then starts the existing **C02 WebSocket collector** automatically. Live market updates are streamed; there is no REST candle-polling fallback. REST supplies initial history/current-bucket context and C02's gap/reconnect repairs. Opening the browser alone starts no session.

This uses public market data, with no Binance account keys. Instrument eligibility is checked through C01; failed/quarantined/stale rules interrupt the session rather than being ignored. A newly listed instrument may not yet have enough candles for the selected strategy. The EMA strategy requires 397 consecutive closed candles for stable current/prior values; the range strategy requires 21. Missing candles restart the affected warm-up.

## Read the chart

- **Range breakout:** a close strictly above/below the previous 20 candles' high/low. Wick touches and equality are not breakouts.
- **EMA pullback:** a close recovering across EMA20 in the direction of the EMA20/EMA50 trend. Indicators use the existing C03 formulas and the C08 strategy predicate.
- **Range levels:** high and low of the preceding 20 completed candles, excluding the current candle.
- **Previous UTC day levels:** high and low of the fully covered preceding UTC day. Incomplete days are omitted.
- **Confirmed swing levels:** latest strict pivot high/low with two completed candles on each side. A pivot is available only after its two right-hand candles close. These simple reference levels are not the full deferred C05 market-structure/zone engine.

The chart displays up to 500 closed candles, a separately labelled forming candle when a contiguous live prefix exists, setup markers, stable EMA overlays and reference lines. Forming-candle prices/volume update from the stream; they never enter strategy/indicator evaluation. C02 records one-minute candles and only aggregates a finalized strategy candle when every constituent minute is final and present: a 15m setup waits for all 15 closes. Duplicate finals, late provisional updates and corrections cannot create a second setup for an already evaluated candle.

**Binance WebSocket** reports the actual market-stream state and last message/price separately from the header's browser/API **Service connected** indicator. Connecting, repairing, reconnecting or stale streams suppress new notifications. The browser refreshes its backend view approximately once a second; this is not polling Binance. Values below the chart explain the levels and confirmation times. **Detected setups** retains observations, timestamps, trigger levels, explanations and delivery states. Select an observation to inspect the chart/levels known at that setup. Return to the latest chart afterward.

No trades, entry fills, stops, targets, wallet balances or approval claims are invented. Setup observations do not measure profitability. Use [Backtesting](BACKTESTING.md) and [Research](WALK_FORWARD_RESEARCH.md) for costed outcome evaluation.

## Scan historical setups

Choose **Scan history**, then the last **100, 500 or 1500 closed candles**. Extra earlier candles are downloaded for warm-up. The scan counts rule matches, saves their causal level snapshots and completes; it sends **no Telegram messages**. Zero matches is a valid result. This is a historical **setup scan**, not a win-rate, P&L or portfolio backtest.

Historical native Binance candles are stored with receipt times in a separate analysis database. Downloads today are labelled historical inputs; original historical arrival times and instrument rules are not claimed. These warm-up/history downloads do not automatically become C02 research datasets. Live one-minute WebSocket observations and repair inputs now persist in the selected workspace's real C02 database, with raw payloads, receipts, finality, checkpoints and collector logs. You can freeze those observations through the advanced C02 snapshot workflow; collection alone does not publish a research dataset.

## Telegram observations

Only newly closed, unexpired setups after initial preparation are eligible. Preparation/history, stale data and missed setups from a pause/restart are not sent as a backlog. A message includes the instrument, direction, timeframe, strategy reason, reference close, trigger level, expiry, session name and stable reference. It explicitly says **SETUP OBSERVATION**, not a validated trade recommendation, and creates no order or paper fill.

The destination is frozen when the session is created. If bot/chat configuration changes, create a new session. Each alert has one durable send attempt, with a shared minimum 3.5-second interval. Acceptance shows **Telegram accepted**; an uncertain response shows **Delivery uncertain** and is not automatically resent. Rate-limit/rejection failures remain visible and are not retried automatically; Telegram's requested waiting period also blocks subsequent analysis messages and survives restarts. Messages currently use the existing transport's silent-notification setting; Telegram acceptance does not establish that you read the message.

These observational alerts are separate from C14's research-gated paper-fill notices. They never set `live_approved`, admit capital, create a research release or bypass promotion gates for trading instructions.

## Pause, stop and restart

- **Pause:** stop evaluating that session, close its managed C02 subscription and suppress pending alerts. Another session or separately started collector can still record the same instruments.
- **Resume:** reconnect the collector and repair missing minute context; retain historical observations but do not send repaired/missed setups as a backlog.
- **Stop:** close its collector and end the session permanently. Create a new session for another run/settings.
- **Backend restart:** previously running sessions become paused. Resume deliberately. An in-flight send at a crash remains uncertain.
- **Browser closed:** the backend continues explicitly started sessions; stop or pause them first if desired.
- **Limits:** five running sessions, five instruments each, 2000 saved candles per instrument, and up to 24 hours per live session. The UI displays the latest 200 setups; the total includes all retained observations. Data errors pause the affected session with a visible message. These are bounded local sessions, not an unattended deployment supervisor.

Analysis data lives beside the configured web-state database: default `data/web.sqlite3.analysis.sqlite3`. Back it up along with C01, C02 and the other stores. A single API owner processes these sessions and supervises their C02 collectors; the advanced worker remains independent. Subscriptions are bounded per analysis session and their symbols/timeframes; C02 deduplicates identical market events if subscriptions overlap. The raw C02 recording can grow faster than the bounded chart history. Changes to the backend/core build require a new analysis session so older evidence stays tied to its original implementation.
