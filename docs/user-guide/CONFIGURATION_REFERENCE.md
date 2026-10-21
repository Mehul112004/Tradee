# Configuration reference

Read [the startup report](START_HERE.md) for runnable startup commands. This reference maps settings to their owners; individual [feature guides](FEATURES.md) explain when to change them.

## Environment: root `.env`

| Setting | Purpose | Default / requirement |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | Token reused unchanged from TBot | Required only for explicit real Telegram sends |
| `TELEGRAM_CHAT_ID` | Numeric destination for the standalone Telegram test | Required unless supplied through `--chat-id`; never overrides a frozen session |
| `TRADEE_TELEGRAM_BOT_TOKEN` | Backward-compatible alternative token name | Optional; avoid defining both names |
| `TRADEE_WEB_OPERATOR_TOKEN` | Authorizes browser mutation requests | Blank means viewer-only backend |
| Exported `PYTHON_DOTENV_DISABLED=1` | Ignores the root `.env` | Useful for isolated tests; exported credentials still work |
| Exported `SSL_CERT_FILE` | Explicit trusted CA bundle | Optional; TLS verification remains enabled |

Exported settings beat file values, including an explicitly empty export. Within one source, `TRADEE_TELEGRAM_BOT_TOKEN` wins over `TELEGRAM_BOT_TOKEN`. Secrets are not sent to the frontend build. Do not prefix credentials with `VITE_`. Full loading rules and TBot reuse decisions: [environment guide](../operations/ENVIRONMENT.md). The loader does not treat arbitrary `.env` entries as strategy configuration.

## Services, access and storage

| Setting | Where configured | What it changes |
| --- | --- | --- |
| Frontend development port 5173 / API target 8787 | `frontend/vite.config.ts` | Local Vite server and `/api` proxy |
| Built/API port, default 8787 | `python -m backend.tradee_web --port PORT` | Python listener; nondefault browser origins require deliberate backend configuration |
| Workspace IDs, roots, synthetic labels, database overrides | [profile example](../../backend/profiles.example.json), passed with `--config` | Which local stores the API/worker read or operate on |
| Web request/runner state | Profile JSON `state_path`, default `data/web.sqlite3` | Durable queue and ownership receipts; separate from domain stores |
| Core store paths | CLI database options | Which files a direct CLI command uses; it does not automatically inherit the dashboard profile |
| Timezone, workspace, session, market selection, knowledge cursor | Browser URL / Settings | Display and evidence selection; not strategy parameters |

Start API and worker with the same profile JSON. Changing a workspace in the browser switches configured evidence; it does not copy, regenerate or collect data.

Core global options precede the component. Component database options precede the action:

```sh
python -m tradee --db data/c01.sqlite3 features \
  --market-db data/c02.sqlite3 --feature-db data/c03.sqlite3 \
  run DATASET_HASH --config configs/c03_baseline.json
```

Each component must have a distinct store. Output inspection must use the same custom paths used to create it. The core currently uses C01, C02, C03, C06–C15; a consecutive `c01`–`c15` filename range does not imply every component store exists.

## Strategy and research JSON files

These are engineering presets/schema examples, not established profitable settings. Freeze an experiment's choices before evaluating its outcomes.

| File | Main settings / purpose | User guide |
| --- | --- | --- |
| [c03_baseline.json](../../configs/c03_baseline.json) | Feature names, timeframes, stability, quote/candle freshness and processing delay | [Features](features/FEATURE_ENGINE.md) |
| [c06_funding.json](../../configs/c06_funding.json) | Funding accounting/estimate policy; settlement calendars are separate declared inputs | [Costs](features/EXECUTION_AND_COSTS.md) |
| [c07_execution.json](../../configs/c07_execution.json) | Recorded quote model, observed metadata, manual delay, spread/impact/drift constraints | [Costs](features/EXECUTION_AND_COSTS.md) |
| [c07_fee_assumptions.json](../../configs/c07_fee_assumptions.json) | Explicit assumed fees; not authenticated account fee tiers | [Costs](features/EXECUTION_AND_COSTS.md) |
| [c07_modeled_bar.json](../../configs/c07_modeled_bar.json) | Explicit coarse bar-model research alternative | [Backtesting](features/BACKTESTING.md) |
| [c08_candidates.json](../../configs/c08_candidates.json) / [modeled variant](../../configs/c08_modeled_candidates.json) | Candidate universe, metadata and detection configuration | [Candidates](features/STRATEGY_CANDIDATES.md) |
| [c08_range_breakout.json](../../configs/c08_range_breakout.json) | Prior-range breakout, timeframe, lookback, sides, entry window, cooldown | [Candidates](features/STRATEGY_CANDIDATES.md) |
| [c08_trend_continuation.json](../../configs/c08_trend_continuation.json) | EMA pullback continuation and its fixed v1 feature definitions | [Candidates](features/STRATEGY_CANDIDATES.md) |
| [c09_trade_policy.json](../../configs/c09_trade_policy.json) / [bar variant](../../configs/c09_bar_policy.json) | Stops, target R, holding duration, trigger source, optional partials and exit timing | [Lifecycle](features/EXECUTION_AND_COSTS.md) |
| [c10_estimator.json](../../configs/c10_estimator.json) | Cohorts, evidence minima, bootstrap, model age and eligibility buffer | [Expectancy](features/EXPECTANCY.md) |
| [c11_scenarios.json](../../configs/c11_scenarios.json) | Strategy + lifecycle + quantity + horizon per scenario | [Backtesting](features/BACKTESTING.md) |
| [c11_simulation.json](../../configs/c11_simulation.json) | Detection window, sample schedule and replay budgets | [Backtesting](features/BACKTESTING.md) |
| [c12_experiment.example.json](../../configs/c12_experiment.example.json) | Source/report pins, variants, fold/holdout windows and evidence policy; placeholder hashes must be replaced | [Research](features/WALK_FORWARD_RESEARCH.md) |
| [c13_risk_policy.json](../../configs/c13_risk_policy.json) / [replay config](../../configs/c13_replay.json) | Risk limits, shared capital and replay sampling | [Portfolio](features/PORTFOLIO.md) |
| [c14_runtime.json](../../configs/c14_runtime.json) / [session example](../../configs/c14_session.example.json) | Shadow/paper-test mode, frozen bot/chat, session times and freshness/resource limits | [Paper sessions](features/PAPER_SESSIONS.md) |
| [c15_monitor.example.json](../../configs/c15_monitor.example.json) | Prospective review deadlines, maturity, evidence thresholds and health rules; replace example historical deadlines | [Forward review](features/FORWARD_REVIEW.md) |

## Units, identifiers and changing settings

- CLI date arguments such as `--start` use timezone-aware ISO timestamps, e.g. `2026-10-01T00:00:00Z`. Fields ending in `_ms` use Unix milliseconds for timestamps or milliseconds for durations, according to their schema. Most window ends are exclusive; use the component contract for boundaries.
- Monetary/quantity/rate JSON inputs often require **decimal strings**, such as `"0.001"`. Basis points and fractions are different units: 20 bps is 0.2%, not 20%. Do not convert an existing exact string to a rounded chart number for replay input.
- `DATASET_HASH` identifies an immutable data selection; feature, simulation run, report, model, experiment and deployment hashes identify different artifacts. A run hash is not interchangeable with its report hash.
- Edits to a preset do not change existing immutable artifacts. Rerun the appropriate feature/research stage with a new frozen definition. Model/source/policy compatibility checks can reject mismatches.
- Producer source/Python changes require a new compatible research/paper release for operation. Historical evidence remains readable under its original identity. Never edit stored hashes to make a release appear current.

For definitions of `ready`, `eligible`, mature/unresolved outcomes and fixed review evidence, start with the relevant feature guide; these terms describe distinct conditions.
