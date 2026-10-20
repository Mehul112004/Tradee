# C01 verification — 19 September 2026

## Implemented scope

Git initialized on `main`; Python package, CLI, SQLite schema v1, public Binance metadata adapter, rule normalization, observation history, explicit universe policy, immutable saved universe records, optional polling and CI configuration are present. No remote or initial commit has been created. Runtime databases are excluded from Git.

## Results

- Local Python 3.13 automated suite: **80 tests pass** (31 existing plus 49 new tests, with additional parameterized subcases). Coverage includes parsing and exact increments, product restrictions, Unicode symbols, missing/invalid metadata, identity conflicts, chronological queries, freshness, snapshot reproducibility, restart persistence, CLI behavior, retries and secure TLS configuration.
- Local module compilation succeeds.
- The implemented provider successfully fetched and normalized 897 live Binance contract records using the system CA bundle through `SSL_CERT_FILE=/etc/ssl/cert.pem`. BTCUSDT and ETHUSDT were eligible immediately after that observation. Unsupported products remain outside the enabled universe.
- The provider was then updated to load the macOS system bundle automatically while retaining certificate and hostname verification. Mocked transport tests cover this change and explicit CA overrides.
- The final live recheck of that automatic CA-loading path was blocked by automatic approval review reporting that the workspace was out of credits. No bypass was attempted. The earlier successful live fetch remains valid evidence for transport/parsing with the explicit system bundle; the final automatic path has local tests but awaits a new live check.
- A later local health query correctly reported the stored metadata as stale. No watcher is running, so a fresh observation is required before new-entry eligibility returns.
- CI is configured for Python 3.11 and 3.13; remote CI has not been run.

## Remaining operational actions

After the network-execution approval service is available, run `python3 -m tradee refresh`, then `python3 -m tradee health`. For continuous freshness, explicitly start `python3 -m tradee watch`. See README.md for commands, assumptions, exit codes and historical-evidence limitations.

Further components, an HTTP/dashboard surface, a PostgreSQL migration, identity reconciliation and historical metadata reconstruction are outside this first C01 increment.

## Test hardening — 19 September 2026

Run the full offline suite with `python3 -m unittest discover -v`. Tests use temporary SQLite databases, injected clocks, mocked HTTP responses and simulated sleeps. The subprocess test exercises the real CLI across separate processes. No Binance credentials, network calls, Telegram access or running watcher are needed. The existing CI configuration discovers these tests automatically.

| File | Primary coverage |
| --- | --- |
| `tests/test_c01.py` | Original registry, provider, TLS and CLI regression suite |
| `tests/test_c01_domain.py` | Exact decimals, malformed payloads, every required constraint, optional filter validation, policy inputs, input aliasing and deterministic hashes under reordered data |
| `tests/test_c01_persistence.py` | Exact freshness boundaries, historical noninterference, equal-time ordering, missing/reappearing contracts, onboarding dates, raw checksums, rollback after an injected SQLite write failure, immutable snapshots and an interleaved reader/writer transaction |
| `tests/test_c01_transport.py` | Retryable/permanent HTTP failures, exhausted retries, numeric/date Retry-After, malformed/non-finite headers, truncated bodies, invalid JSON/UTF-8, response-size boundary, request configuration and resource closure |
| `tests/test_c01_cli.py` | JSON errors and exit codes, readiness after import, timezone equivalence, polling cooldown/recovery/halt/interrupt, and persistence through the actual module entry point |
| `tests/support.py` | Shared fixture loading and isolated database/clock helpers |

The new regression tests exposed and led to fixes for:

- Policy container types that were accidentally accepted or raised inconsistent exceptions.
- Normalized filter dictionaries retaining mutable references to caller input.
- Optional numeric filters bypassing validation. Invalid fields now quarantine the affected contract. Position controls other than `NONE` are conservatively unsupported by C01; this is a local policy restriction, not a claim that Binance disallows other values.
- Invalid timeout/retry configuration, infinite Retry-After values and unhandled truncated HTTP responses. Configuration now rejects invalid values, malformed cooldowns use bounded backoff, and incomplete reads use the normal retry budget.

The transaction test injects a SQLite statement failure; it does not simulate a physical disk failure. The interleaving test proves a consistent read snapshot during one committed write, not sustained multi-process load performance. These offline results do not revalidate live Binance connectivity, and remote CI has not run. C02 remains unimplemented.


## Live recheck — 21 September 2026

The provider's automatic macOS CA-loading path successfully fetched and normalized 905 instruments during `python3 -m tradee.check_connectivity`, with zero quarantined metadata records. No credentials or explicit CA override were added. This resolves the earlier blocked automatic-TLS-path recheck. Temporary test databases were removed afterward.
