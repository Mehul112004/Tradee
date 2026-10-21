# Live Binance collection

The collector is a separate Python process that records public Binance WebSocket observations into C02. The browser reads local evidence through the API; it does not maintain the Binance recording connection. Viewer/operator permission does not start or stop this process.

## Start

Prerequisites: installed live dependencies, network access, a registered enabled instrument and enough disk space for the intended capture. No Binance API keys are required.

```sh
conda activate tradee
python -m tradee refresh
python -m tradee data collect --symbols BTCUSDT,ETHUSDT \
  --streams candle,trade,quote,mark
```

Keep this terminal running. Use a **separate terminal** for periodic metadata observation:

```sh
conda activate tradee
python -m tradee watch --interval-seconds 900
```

For custom paths, explicitly align both components with the dashboard profile:

```sh
python -m tradee --db data/c01.sqlite3 data --market-db data/c02.sqlite3 \
  collect --symbols BTCUSDT,ETHUSDT --streams candle,trade,quote,mark
```

## Verify and use

Create a [dataset snapshot](MARKET_DATA.md) covering the captured interval with the required kinds, then inspect Data quality and Markets. A snapshot is immutable: later collection requires a new snapshot or the frozen runtime's next recorded-prefix tick; an old chart dataset does not become an indefinitely live view.

Inspect actual recording/source ages as well as API connectivity. Quote/trade data cannot generally be reconstructed from OHLCV after a recording gap. Funding history/calendar coverage is a separate requirement; selecting `mark` does not certify all actual settlement cash flows.

The collector reconnects/repairs supported recent candle gaps, but a reconnected socket does not prove a complete lost tape. Existing source/quality limits remain visible. Collection alone does not calculate every feature, fit an expectancy model, create a session or send Telegram.

## Stop and troubleshoot

Ctrl+C in the collector terminal stops recording; Ctrl+C in the metadata watcher stops refreshes. Stop each independently. Closing the dashboard has no effect on either process.

If TLS verification fails, repair the trusted CA setup or use a trusted `SSL_CERT_FILE`; do not disable TLS. For an isolated public provider check, `python -m tradee.check_connectivity` performs real network requests into temporary stores. It is not a Telegram test.

Related: [market data](MARKET_DATA.md), [session runners](PAPER_SESSIONS.md), [C02 verification](../../components/c02/C02_VERIFICATION.md).
