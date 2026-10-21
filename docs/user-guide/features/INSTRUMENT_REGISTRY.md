# Instrument registry and universe

**Location:** Data quality → Instrument registry; Operations → Research & data jobs → refresh registry. **Access:** viewer for inspection; operator plus worker for the dashboard refresh. Direct CLI refresh needs no operator token or Binance keys.

The registry records Binance USDⓈ-M contract rules and observation times. The enabled universe is an explicit policy; discovering a contract does not automatically permit new entries.

## Refresh and inspect

```sh
conda activate tradee
python -m tradee refresh
python -m tradee universe --members-only --save
python -m tradee health
python -m tradee history BTCUSDT
```

Refresh contacts Binance and appends metadata observations. Universe/health evaluates current observations; inspect `ready` and reason codes. The default enabled symbols are BTCUSDT and ETHUSDT. To supply another policy:

```sh
python -m tradee --enabled BTCUSDT,ETHUSDT,SOLUSDT universe --members-only
```

The global `--enabled` option goes before the action. This invocation does not permanently change all other components' enabled lists: freeze compatible candidate/execution/universe settings for the research workflow.

## Keep rules fresh for recording

Run in its own terminal when periodic observations are needed:

```sh
python -m tradee watch --interval-seconds 900
```

It refreshes immediately and periodically; Ctrl+C stops it. A one-time refresh does not keep metadata fresh indefinitely. Polling cannot establish when a rule changed between observations.

## What to inspect

Check trading status, crypto/USDT perpetual eligibility, tick/lot/notional constraints, observation age and exclusion reasons. Missing/changed/malformed identities can be quarantined. Current exchange rules are not verified historical rules for earlier dates; unsupported historical assumptions must remain explicitly labelled.

If `health` exits 2, read its unknown/ineligible reasons rather than retrying a strategy with weakened rules. For custom stores, use `--db path/to/c01.sqlite3` before each subcommand and align the collector/profile with it.

Related: [market data](MARKET_DATA.md), [live collection](LIVE_COLLECTION.md), [C01 research](../../components/c01/C01_RESEARCH_PLAN.md).
