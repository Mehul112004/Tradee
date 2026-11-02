# C05 prerequisite verification

Verification date: 1 November 2026. Coverage includes exact prices, prior-range current-bar exclusion, previous-day and Monday-week boundaries, missing-period suppression, strict/tied swings, right-bar confirmation, late availability, gaps, immutable snapshots, corrections, bounded pivot inventory, Decimal relationships under low ambient precision, ATR missing/zero semantics, and replay/restart parity.

The backend checks that displayed swings cannot bridge missing candles. Existing analysis-session tests cover midnight/day behavior, pivot confirmation, strategy evaluation and session operations with the shared C05 helper.

```sh
python -m unittest tests.test_c05_structure tests.test_observation_persistence tests.test_observation_cli -v
python -m unittest tests.test_structure_prerequisites_e2e backend.tests.test_analysis -v
PYTHON_DOTENV_DISABLED=1 python -m unittest discover -q
```

The actual-process verifier imports raw C01/C02 inputs, invokes real context/structure commands, checks independent EMA200 and known day/swing values, then exercises SQL failure/recovery, idempotency and pagination. Missing week/quote coverage remains explicit. No exchange request, Telegram delivery or trade is required.

Synthetic evidence establishes prerequisite behavior only. The proposed pilot strategies have not been defined, backtested or promoted. Long-history resource measurements and predictive validation remain outstanding.

## Recorded results

On the final revision, **61 focused checks passed in 7.180 seconds**, including all 28 new prerequisite tests, the actual-process raw-input verifier, and analysis/live-collector coverage. **The complete 78-test backend suite passed in 38.390 seconds.** `git diff --check` also passed.

The earlier complete discovery run exercised 907 tests in 593.322 seconds: all 830 core tests passed; seven live-analysis tests exposed a display-adapter cutoff error for candles received after close. That adapter was corrected to retain `known_ms` and use the supplied prefix's availability cutoff. A new delayed-receipt regression and the complete backend rerun passed. The final focused rerun also includes strict whole-minute interval validation. A second complete discovery run was not performed after those corrections; the affected suites above were rerun.
