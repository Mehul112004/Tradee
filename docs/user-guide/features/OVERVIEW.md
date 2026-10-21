# Overview dashboard

**Location:** Overview, `/`. **Access:** viewer. **Prerequisites:** API and selected workspace; a recorded session/cycle is needed for paper wallet metrics. Opening this page starts no strategy, collector or simulation.

## Use it

1. Choose the workspace in the top bar. Confirm whether it is **Local recording** or explicitly synthetic.
2. Select a deployment/session where available. Review its frozen scope and paper mode.
3. Read paper equity, net paper P&L, funded positions and candidate counts together. They answer different questions.
4. Review **Needs your attention**, then inspect the linked signal, forward report or operation.
5. Check **Evidence stores** for missing/unavailable sources before interpreting absent charts as zero activity.

## Interpret the results

- The capital trajectory belongs to a shared **paper** wallet, not an authenticated Binance balance.
- Candidate count includes detected/rejected history; it is not the number of funded trades or delivered messages.
- **Service connected** describes the browser/API event connection. Source age is separate: connected UI plus stale recording does not mean current market data.
- Missing values stay unavailable. A missing component database is not automatically initialized or filled by a viewer request.
- Overview is a current operational summary. Use [historical replay](HISTORICAL_REPLAY.md) for scoped earlier session evidence rather than treating every summary card as a point-in-time backtest.

## Common issues

An empty first workspace is expected until data/research/session artifacts exist. Use the [synthetic demo](SYNTHETIC_DEMO.md) to learn with populated evidence. If an expected deployment is missing, check the [workspace database paths](SETTINGS_AND_WORKSPACES.md) and the corresponding job receipt.

Related: [signals](SIGNALS.md), [portfolio](PORTFOLIO.md), [forward review](FORWARD_REVIEW.md), [dashboard acceptance/limits](../../dashboard/DASHBOARD_IMPLEMENTATION.md).
