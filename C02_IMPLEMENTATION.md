# C02 — market observations and replay

Implemented 19 September 2026. C02 depends on C01 for instrument identity. It supplies observations to C03–C07, historical simulation/validation in C11/C12, and later live operation/measurement in C14/C15. C01 may eventually consume a completed liquidity snapshot; collection does not depend on that feedback path.

## Implemented contracts and responsibilities

| Part | Implementation | Produces / consumers |
| --- | --- | --- |
| Normalization | `tradee/c02/domain.py` | Schema-v1 market events: one-minute candles, aggregate trades, best bid/ask, mark/index price and funding estimates, settled funding history, five-minute historical open interest |
| Persistence | `tradee/c02/store.py` | Separate SQLite database; raw payloads/checksums, quarantined input, append-only event revisions, C01 identity/version references, checkpoints and collector lifecycle log |
| Historical acquisition | `tradee/c02/provider.py` | Binance USD-M daily/monthly one-minute ZIP archives with SHA-256 verification; paginated REST candles, funding and open interest; resumable page checkpoints |
| Forward recording | `tradee/c02/live.py` | Routed combined WebSockets, durable receipt timestamps, bounded reconnects, startup/candle-gap repair, foreground shutdown |
| Replay and quality | `MarketStore.snapshot/replay/view/asof/quality`, `aggregate` | Immutable datasets for C03/C11/C12; availability-bounded joins; missing/stale/partial/revised-data reports; complete UTC candle aggregation |
| Operator interface | `tradee/c02/cli.py` | `tradee data …` commands; JSON reports and JSON-lines replay |

C02 does not calculate features, entry signals, realized funding cashflows, fills, P&L or Telegram messages. Those remain with their planned components.

## Timing and identity contract

Each event retains exchange/event time, application receipt time, availability time, source, raw checksum, schema, finality, instrument ID and observed C01 metadata version. Numbers remain exact decimal strings. Market-event `event_ms` means candle close time, trade/quote transaction time, mark event time, funding timestamp or the provider's open-interest timestamp. Candle opens are also stored explicitly.

Availability is assigned after normalization and batch insertion, immediately before transaction commit. It is conservatively clamped against prior recorded availability and finalized event time; it is not a measurement of network arrival at the kernel or exact durable disk-flush time. More than five seconds of future clock skew is quarantined. Use synchronized system clocks. C01 itself remains fail-closed if clock regression makes identity evidence unavailable.

Collection scope is explicit and independent of trading eligibility. Known in-scope instruments can continue to be recorded despite stale metadata, disabled entry policy or non-TRADING status. Missing, malformed or conflicting identities fail closed. A metadata binding observed today does **not** establish that the same rules or universe were historically valid. Backtests must retain that limitation until historical metadata evidence is available.

Raw payloads are retained even when parsing fails. An invalid row rejects the whole REST page/archive atomically; previously committed pages remain available. Exact duplicate normalized observations retain another raw receipt but do not repeat the event. Corrections and reversions append revisions. Partial candle updates are recorded for replay but cannot replace finalized candles in `view`.

## Two distinct availability policies

- **Recorded (default):** replay events at recorded application availability, with `(available_ms, event_id)` tie-breaking. Includes partial updates and revisions. A candle downloaded today does not become visible to yesterday's recorded decision.
- **Modeled (explicit, candle-only):** pin the latest finalized candle revision known at the dataset cutoff and assign availability at exclusive candle end plus `delay_ms`. The user must provide the delay. This is a historical research assumption, not verified original latency or proof that an archived revision was available historically.

Every saved dataset pins exact event IDs and replay times, source-vintage cutoff, symbols, kinds, range, policy and a manifest checksum. Later repairs produce a different dataset and cannot rewrite an old one. Historical ranges use **[start, end)**; candle boundaries must be whole UTC minutes. `as_of_ms` on snapshot creation limits recorded evidence; `until_ms` during replay limits decision availability.

`replay` yields the input stream; it deliberately does not hide revisions. Consumers that need current finalized values use `view`. `asof` selects the newest event-time observation available by the decision time and enforces an explicit age limit. A late, older quote cannot replace a newer event-time quote in that join. `after_id` resumes after an event in the pinned replay order, including modeled datasets whose IDs are not chronological.

Higher timeframe aggregation accepts a finalized one-minute view. It requires every constituent, uses UTC boundaries, sums exact volumes, preserves constituent IDs and waits for the latest constituent's availability. Supported aggregation durations are whole minutes dividing a day. There is no forward filling or partial-bucket emission.

## Recovery and quality

REST pages and their progress checkpoint commit together. A failed page resumes from the previous committed cursor. `repair` explicitly revisits the range even if an earlier download completed. Empty/sparse responses never count as proof of complete coverage; inspect `quality` afterward.

The live collector uses one connection per route: candles/trades/mark data on `/market`, quotes on `/public`. Receipt is timestamped when the application reads the message. The WebSocket library handles ping/pong and verified TLS. Each connection has a bounded queue, message-size limit, handshake timeout, inactivity reconnect and a maximum of 20 reconnects per invocation. Permanent handshake failures and certificate errors stop it; Retry-After is respected. Run a fresh invocation after the retry budget is exhausted.

Candle collection repairs on connect and when a finalized candle jumps over a minute. It overlaps the prior candle, retains unresolved gaps in a separate durable checkpoint, and stores the arriving candle before attempting repair. Automatic repair is capped at 24 hours per symbol; a longer outage is explicitly logged and needs manual backfill for its earlier portion. Without a prior checkpoint, startup collects the last five closed minutes. No persistent background service is installed.

Quality reports expose missing minute ranges, finalized counts, partial updates, revisions, event-time staleness and the store-wide quarantine count. `ready` means complete and fresh candle coverage for the requested dataset; it is not permission to trade and says nothing about C01 eligibility. An old historical dataset can be complete but stale relative to now; supply its historical decision time when assessing freshness.

## Supported limits and remaining extensions

- Initial deployment is a single-host SQLite recorder for an explicitly selected universe. Snapshot creation/replay materializes its selected records in memory. This is not yet a validated full-exchange tick warehouse; partitioned storage and streaming manifests can be introduced behind these APIs when volume requires them.
- Archive import/download supports one-minute **contract** candles only. REST supports those candles, settled funding and five-minute historical open interest. Forward WebSockets support aggregate trades, best quotes, candles and mark/index/funding estimates. Historical best quotes are not fabricated.
- Trade/quote/derivatives coverage is explicitly **not** certified gap-free. Quote history cannot be repaired from current quotes. Collector disconnections are audited, but there is no full order-book reconstruction or trade-ID repair adapter yet. A strategy requiring such evidence must reject unsupported coverage.
- Liquidations, economic calendars, scheduled-event feeds and additional derivatives endpoints are not enabled. Funding accounting belongs to C06/C09/C11; an estimated funding rate in a mark event is not a settled charge.
- REST/archive request failures are surfaced; REST uses C01's bounded retry/TLS/Retry-After handling. Archive downloads make one bounded request per file and may be rerun safely. Request pacing is local, not a coordinated rate limiter shared with other programs on the same IP.
- C01 and C02 use separate databases. Back up both, using SQLite backup facilities or with writers stopped. Application history is append-only, not tamper-proof against direct database edits.
- Snapshot IDs reproduce inputs. Proving identical **trading decisions** will require C03 and the later strategy/runtime components; C02 currently verifies input replay and finalized data views.

## Provider references checked during implementation

- [Binance USD-M REST market data](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data): endpoints, candle fields, pagination limits and historical derivatives contracts.
- [Binance WebSocket connections](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect) and [route migration](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Important-WebSocket-Change-Notice): route mapping and connection limits.
- [Binance public archives](https://github.com/binance/binance-public-data): USD-M candle column layout, daily/monthly files and checksum/revision policy.
- [websockets synchronous client](https://websockets.readthedocs.io/en/stable/reference/sync/client.html): maintained WebSocket transport. Optional live dependency: `websockets>=16,<18`; local environment has 16.0.

TBot informed the pagination, combined-stream and candle-close patterns. Its float conversions, in-memory-only callbacks and missing point-in-time persistence were not carried over.
