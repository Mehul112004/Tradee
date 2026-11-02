# Pilot implementation and research journal

## Frozen starting point — 2 November 2026

Baseline commit: `5beb1db`. This checkpoints the earlier prerequisites and the untested v1 designs before any pilot market-performance inspection. Implementation is now authorized. The three family definitions and the four separately reported modes remain the baseline.

Research protocol is registered in [pilot_research_v1.json](../../configs/pilot_research_v1.json). Data acquisition is restricted to October 2022–June 2025. July–December 2025 remains reserved and will not be acquired/read by the runner. Its prior inspection status is **unattested**, so it cannot be called an untouched holdout or used for promotion. Earlier TBot trials are not known; no adjusted significance claim will assume they were zero.

Each mode gets baseline geometry plus its predeclared 0.8/1.2 neighbors. Four additional earlier-training-only selection recipes bring planned trial accounting to 58 of the 64 new-recipe budget. Outer quarterly results cannot select or change rules. Failed/zero-sample configurations remain in reports. No strategy is promised a target win rate.

Binance's public checksum-verified archives supply price history. Minute candles support a **modeled execution diagnostic**, not recorded quotes or an exact intraminute path. Strict unknown outcomes stay unknown; stop-first is a separate adverse sensitivity. Fees/spread/slippage and reconstructed schedule/rule assumptions remain explicit. Backtest and walk-forward reports cannot create C12 releases, qualify live notifications, or imply forward-paper evidence.

Implementation, correctness validation, acquisition coverage, experiments and any deviations/results will be appended here with their commits and reproducible commands.

## Detector and first diagnostic

- `689aceb`: preregistered research protocol and accounting.
- `46d1cf5`: causal detectors, strict qualification/cost checks and independent geometry tests.
- `cb8855b`: checksum acquisition, modeled minute-close lifecycle, reconstructed official calendars and chronological selection tests.
- All 198 requested archives (33 months × two symbols × 15m/1m/funding) downloaded with verified published checksums; no acquisition failure. Reserved price months were not acquired/read.
- `python3 -m tradee.pilots.research --output data/pilot-research/baseline-64ab` completed at `cb8855b`. Baseline geometry produced 24 trend-sweep plans and one retest plan across BTC/ETH; all failed modeled admission. EMA/range modes produced no plans. The 0.8/1.2 neighbors also admitted no entries. All six outer quarterly selections for every mode abstained. Win rate is **undefined**, not 0%/100%, and zero exposure does not establish a working edge.
- The first diagnostic is retained under its original implementation hash. The result motivates a correctness/funnel audit and the registered comparisons, not a claim of successful optimization. No thresholds or release gates were weakened to manufacture a result.
- Official BLS pages were accessible through the research browser, but direct backend fetch returned HTTP 403 during source inspection. Historical event facts were independently verified from the official annual pages and saved as reconstructed schedules, with DST-aware conversion. Strict live calendar preparation fails closed if those official sources remain unavailable; it cannot silently assume an empty calendar.
- An early full-suite run overlapped implementation edits, invalidating four source-hash-pinned research checks. That run is not a valid regression result; the full suite must run again against frozen source after edits finish. Focused detector/research and existing analysis tests passed independently.

## Registered comparison operationalization

The comparison runner reports all 54 planned mode/cost/geometry/regime/baseline/capital comparisons plus the four training-selection recipes (58 planned new recipes; six remain unallocated). Raw geometry retains source/continuity, shock, attempt and cost controls. Its range case gets a separate detector pass so a lack of the hourly range label cannot silently remove the raw range comparison. The no-exhaustion ablation removes the level touch-episode cap and EMA clean-separation restriction; the defining accepted-break/retest sequence and risk/attempt caps remain. These choices precede comparison outcome inspection.

Stress scenarios freeze detector plans. A different reaction delay may change modeled entry eligibility; it does not refit the detector or choose its geometry. This is reported as execution-protocol sensitivity, never as stress trading added to the original wallet. Capital replay is a separate finite shared wallet with marked risk pauses, current notional constraints and retained unresolved exposure. It is not a C09 recorded-execution account and does not create C12 promotion artifacts.
