# Markets and charts

**Location:** Markets, `/markets`. **Access:** viewer. **Prerequisites:** a C02 dataset with bars; compatible C03 materialization is needed for indicator overlays.

## Use the workspace

1. Choose a dataset and instrument. The dropdown shows the recorded dataset identity/mode, not an exchange-wide live instrument browser.
2. Choose **1m, 15m, 1h, 4h or 1d**. Chart aggregation does not change the frozen strategy timeframe.
3. Toggle **C03 overlays** to inspect available valid/stable indicators. Use **Two-chart workspace** when the selected dataset contains another instrument.
4. Inspect tape context, recorded spread/delay, published funding observations and evidence/quality tabs alongside price.
5. Check dataset range, source provenance, gaps and provisional observations before interpreting a visual pattern.

Time axes are UTC. Table timestamps use the selected display timezone. Changing timezone does not change bar boundaries or calculations. Range selection and chart aggregation cannot manufacture missing source data.

## Indicators and evidence

Indicators are read from a materialized C03 run or supported saved feature inventory. The UI does not calculate replacement trading formulas in JavaScript. When the UI labels reconstruction, it is reconstructed context, not necessarily the originally stored decision snapshot. Inspect the manifest and original signal feature evidence when reproducing a decision.

If it says indicators are not materialized for the vintage, use [feature materialization](FEATURE_ENGINE.md) with that dataset and the required names/timeframes. Sparse/unstable or incomplete warm-up values remain unavailable rather than becoming zeroes or attractive lines.

Funding observation charts show **rates/observations**, not realized USDT funding P&L. A displayed quote is a recorded observation, not a promise that a given order quantity can fill there.

## Common issues

- No chart: check dataset selection, selected instrument, API errors and captured range.
- Bars exist but no overlay: check feature-run compatibility, requested timeframe, selected feature names and stability.
- Connected but old price: the API is reachable; inspect collector/source age and the dataset's pinned end/cutoff.
- Historical view lacks later observations: this is the intended knowledge filter. Return to current context deliberately rather than mixing later data into earlier decisions.

Related: [historical replay](HISTORICAL_REPLAY.md), [features](FEATURE_ENGINE.md), [chart specification](../../dashboard/DASHBOARD_CHARTS.md).
