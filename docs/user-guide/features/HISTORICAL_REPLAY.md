# Historical replay and knowledge cursor

**Location:** top-level knowledge cursor and Signals replay controls. **Access:** viewer. **Prerequisites:** a recorded C14 session with cycle history; market data/report availability remains bounded by its own pinned scope.

This replays **what the platform had recorded by an earlier knowledge time**, not an unrestricted view of later outcomes over old candles. It is different from running a new historical simulation.

## Use it

1. Select the correct workspace and session.
2. Open the knowledge cursor or Signals replay controls and choose an available recorded cycle. Cursor timestamps are **Unix epoch milliseconds**.
3. Step or play recorded cycle vintages at **1× / 2× / 4×**.
4. Inspect the earlier Signals/Portfolio state and market availability. A later close or matured outcome must not appear as already known at the earlier cycle.
5. Return to the current view explicitly before submitting operator actions.

Replay speed only controls browser navigation. It does not alter the frozen manual execution delay, change strategy parameters, execute a new backtest or start a collector.

## Scope and persistence

Workspace, session, display timezone, market dataset/symbol/timeframe and cursor are bookmarkable URL state. Changing workspace resets incompatible selections. Clock navigation can expose later cursor positions without granting later payloads/outcomes in the earlier view.

Markets filters availability against the cutoff; Signals/Portfolio use the selected recorded cycle; Forward review filters reports by observation clock. Research and Data archives ask you to leave session replay to use their own separately pinned artifact/dataset vintages. Some operational summary/source metadata remains current: do not treat the entire application as one historical account snapshot.

Table display timezone is separate from epoch milliseconds; chart axes remain UTC. A cursor before the first suitable recorded cycle may legitimately show no evidence.

## Limits and common issues

Operator controls are intentionally disabled in historical views. Clearing the cursor allows current controls but does not resume a session or start a process.

The [session CSV/JSON export](EXPORTS.md) currently exports latest state and has no historical-cursor parameter. Do not assume a download inherits the screen's earlier cursor. Use explicitly identified report/artifact hashes for a frozen historical investigation.

If stepping seems not to advance an outcome, check whether another cycle/report was recorded and whether the selected window contains its publication/availability time. Playback cannot invent intermediate ticks.

Related: [signals](SIGNALS.md), [charts](MARKETS_AND_CHARTS.md), [forward reports](FORWARD_REVIEW.md).
