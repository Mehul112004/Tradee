# Feature-by-feature manual

Start with [running the system](START_HERE.md). Each file below covers one user-facing feature or workflow: its purpose, prerequisites, steps, configuration, results and common issues. Existing component specifications remain the source for formulas and full JSON contracts.

## Learn the dashboard

| Feature | What you will learn |
| --- | --- |
| [Synthetic demo](features/SYNTHETIC_DEMO.md) | Generate current-source example evidence and open it in an isolated workspace |
| [Overview](features/OVERVIEW.md) | Read wallet summaries, evidence availability, deployments and attention items |
| [Markets and charts](features/MARKETS_AND_CHARTS.md) | Select datasets/symbols/timeframes, inspect overlays, quotes and funding |
| [Signals](features/SIGNALS.md) | Inspect admission, rejection, lifecycle, costs and delivery evidence |
| [Historical replay](features/HISTORICAL_REPLAY.md) | Navigate recorded knowledge without mixing later results into earlier views |
| [Exports](features/EXPORTS.md) | Download signal/session/run evidence and understand export scope |

## Build and evaluate evidence

| Feature | What you will learn |
| --- | --- |
| [Instrument registry](features/INSTRUMENT_REGISTRY.md) | Refresh Binance rules and evaluate the explicit universe |
| [Historical data and quality](features/MARKET_DATA.md) | Backfill, freeze snapshots and inspect gaps/recording clocks |
| [Live collection](features/LIVE_COLLECTION.md) | Run Binance WebSocket recording independently of the browser |
| [Feature engine](features/FEATURE_ENGINE.md) | Materialize indicators and understand warm-up/validity |
| [Strategy candidates](features/STRATEGY_CANDIDATES.md) | Use range-breakout and trend-continuation definitions |
| [Execution, funding and lifecycle](features/EXECUTION_AND_COSTS.md) | Declare costs, funding evidence, stops/targets and outcome rules |
| [Backtesting](features/BACKTESTING.md) | Run independent simulations and interpret complete versus ready |
| [Expectancy](features/EXPECTANCY.md) | Fit statistical estimates, inspect uncertainty and understand abstention |
| [Walk-forward research](features/WALK_FORWARD_RESEARCH.md) | Register experiments, run chronological validation and control final holdout access |
| [Portfolio](features/PORTFOLIO.md) | Evaluate shared capital, risk budgets, rejections and paper equity |

## Operate and maintain

| Feature | What you will learn |
| --- | --- |
| [Paper sessions and runners](features/PAPER_SESSIONS.md) | Create frozen sessions, start bounded processing, pause, stop and recover |
| [Forward review](features/FORWARD_REVIEW.md) | Observe prospective outcomes, fixed reviews, replay and pause requests |
| [Telegram](features/TELEGRAM.md) | Test real delivery and distinguish connectivity from strategy dispatch |
| [Operator jobs](features/OPERATOR_JOBS.md) | Authorize requests, fill JSON templates and inspect durable job receipts |
| [Settings and workspaces](features/SETTINGS_AND_WORKSPACES.md) | Configure access, database profiles, timezone and selection state |
| [Testing and troubleshooting](features/TESTING_AND_TROUBLESHOOTING.md) | Run focused/full/browser E2E checks and resolve common symptoms |
| [Backup and shutdown](features/BACKUP_AND_SHUTDOWN.md) | Stop owners correctly and back up/restore SQLite evidence and queues |

[Configuration reference](CONFIGURATION_REFERENCE.md) maps environment variables, JSON files, command placement and units. Advanced examples use placeholders such as `DATASET_HASH`, `RUN_HASH`, `MODEL_HASH`, `EXPERIMENT_HASH` and `path/to/...`; replace them with actual outputs/files from your selected workspace. A placeholder command is a command shape, not a ready-to-run experiment.
