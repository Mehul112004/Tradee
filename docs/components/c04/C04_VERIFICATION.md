# C04 prerequisite verification

Verification date: 1 November 2026. Tests cover same-prefix multi-timeframe joins, incomplete higher-timeframe exclusion, missing/stale quotes, candle age, nominal/stable readiness, future-prefix independence, gaps, immutable configuration, restart parity and incompatible checkpoints. EMA200 is checked against independent high-precision Decimal arithmetic and exact seed-weight boundaries.

Shared persistence tests use actual C01/C02 stores and cover decreasing modeled replay IDs, SQL rollback, idempotent resume, pagination, database isolation, corrupt records, conflicting prefixes and incomplete inventories. CLI tests exercise explanation, materialization, inspection and invalid configuration.

```sh
python -m unittest tests.test_c03_ema200 tests.test_c04_context tests.test_observation_persistence tests.test_observation_cli -v
python -m unittest tests.test_structure_prerequisites_e2e -v
python -m scripts.verify_structure_prerequisites --output /tmp/tradee-prerequisites-verification
```

Use a fresh output directory for the standalone verifier. It imports raw metadata and 1589 synthetic minute candles through actual CLI processes; checks full default stabilization against a Decimal EMA oracle; verifies C04/C05 output-only ranges, lineage, idempotency and recovery from an injected SQLite failure; and saves a JSON report and command inventory. It establishes software behavior, not strategy profitability or real-service acceptance. See [C05 verification](../c05/C05_VERIFICATION.md) for final regression results.
