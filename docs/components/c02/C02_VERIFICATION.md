# C02 verification — 19 September 2026

The local Python 3.13 suite passes **137 tests: 80 C01 regressions and 57 C02 tests**, with additional parameterized subcases. Tests are offline, use isolated databases and injected clocks/transports, and do not alter runtime market data. Module compilation also passes.

| Test file | Evidence |
| --- | --- |
| `tests/test_c02_domain.py` | Exact numbers; candle alignment/OHLC/volume/finality; raw and combined WebSockets; trades, quotes, marks and historical derivatives; malformed/nonfinite inputs |
| `tests/test_c02_store.py` | C01 identity separation; deduplication and corrections; immutable datasets across restart; recorded/modelled availability; replay prefix and resume; as-of joins; rollback/quarantine/checkpoints; gaps and complete aggregation; clock skew and processing time |
| `tests/test_c02_provider.py` | REST pagination, resume, failure recovery and endpoint selection; archive checksums, raw-byte preservation, filenames/date bounds, traversal rejection, invalid ZIPs and size limits |
| `tests/test_c02_live.py` | Routed subscriptions; durable high-water/gap checkpoints; received-event preservation on repair failure; startup repair; bounded reconnects, inactivity, rate-limit waits, permanent stops and stopped worker lifecycle |
| `tests/test_c02_cli.py` | Operator JSON/exit contracts; imports, snapshots, replay and aggregation; actual module entry point across separate processes |
| `tests/c02_support.py` | Synthetic provider messages, aligned candles, isolated C01/C02 databases and deterministic clocks |

Run `python3 -m unittest discover -v` or just C02 with `python3 -m unittest discover -s tests -p 'test_c02*.py' -v`.

At the original 19 September implementation checkpoint, no live Binance REST/archive/WebSocket connectivity check or sustained load test had been performed. WebSocket behavior is fault-injected rather than tested against a live connection. CI is configured for Python 3.11 and 3.13; remote CI has not run. A real network smoke test and forward recording session remain operational checks before using this collector for research evidence.

See `C02_IMPLEMENTATION.md` for availability semantics, supported coverage, automatic-repair limits and remaining extensions.


## Live connectivity verification — 21 September 2026

`python3 -m tradee.check_connectivity` passed all seven checks using the actual adapters, verified TLS and temporary C01/C02 databases:

- Exchange metadata: 905 instruments normalized, zero quarantined records.
- REST candles: three recent closed BTCUSDT one-minute candles, zero gaps.
- REST funding and historical open interest: one observation each, normalized and persisted.
- Public archive: 1,440 BTCUSDT one-minute candles; ZIP SHA-256 checked and import completed.
- `/market` WebSocket: candle, aggregate-trade and mark events received, normalized and persisted.
- `/public` WebSocket: best-quote event received, normalized and persisted.

The initial sandboxed attempt could not reach the network. The same command succeeded with approved network access. No Binance credentials were read or used, no account endpoints were accessed, and temporary databases were removed. This resolves the outstanding connectivity smoke test, including automatic macOS CA loading. Sustained forward recording, long-duration reconnect behavior and load testing remain unverified live.
