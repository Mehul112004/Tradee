# Pilot implementation and research journal

## Frozen starting point — 2 November 2026

Baseline commit: `5beb1db`. This checkpoints the earlier prerequisites and the untested v1 designs before any pilot market-performance inspection. Implementation is now authorized. The three family definitions and the four separately reported modes remain the baseline.

Research protocol is registered in [pilot_research_v1.json](../../configs/pilot_research_v1.json). Data acquisition is restricted to October 2022–June 2025. July–December 2025 remains reserved and will not be acquired/read by the runner. Its prior inspection status is **unattested**, so it cannot be called an untouched holdout or used for promotion. Earlier TBot trials are not known; no adjusted significance claim will assume they were zero.

Each mode gets baseline geometry plus its predeclared 0.8/1.2 neighbors. Four additional earlier-training-only selection recipes bring planned trial accounting to 58 of the 64 new-recipe budget. Outer quarterly results cannot select or change rules. Failed/zero-sample configurations remain in reports. No strategy is promised a target win rate.

Binance's public checksum-verified archives supply price history. Minute candles support a **modeled execution diagnostic**, not recorded quotes or an exact intraminute path. Strict unknown outcomes stay unknown; stop-first is a separate adverse sensitivity. Fees/spread/slippage and reconstructed schedule/rule assumptions remain explicit. Backtest and walk-forward reports cannot create C12 releases, qualify live notifications, or imply forward-paper evidence.

Implementation, correctness validation, acquisition coverage, experiments and any deviations/results will be appended here with their commits and reproducible commands.
