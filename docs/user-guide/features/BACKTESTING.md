# Historical backtesting

**Location:** Research → Independent candidate runs; Operations → Research & data jobs → simulation. **Access:** viewer for stored reports, operator plus worker for UI simulations. **Prerequisites:** pinned C02 evidence, C01 rules, declared scenarios/costs and enough warm-up/outcome tail.

C11 simulates independent candidate scenarios using the same production features, detectors, execution, funding and lifecycle components. Independent candidates do not share a finite wallet; use [Portfolio](PORTFOLIO.md) for capital-constrained results.

## Run and inspect

This is a command shape: replace `DATASET_HASH` and the calendar file with real compatible evidence. The calendar must declare the actual relevant instruments/range/settlement assumptions; no valid universal calendar is shipped.

```sh
conda activate tradee
python -m tradee simulate explain
python -m tradee simulate run DATASET_HASH \
  --scenarios configs/c11_scenarios.json \
  --fees configs/c07_fee_assumptions.json \
  --execution configs/c07_execution.json \
  --funding configs/c06_funding.json \
  --calendar path/to/declared_calendar.json \
  --config configs/c11_simulation.json
python -m tradee simulate summary RUN_HASH
python -m tradee simulate manifest RUN_HASH
python -m tradee simulate records RUN_HASH --kind outcome_revision --limit 100
```

Use `report REPORT_HASH` for the full report identity returned by the run. For custom stores, provide the same component database options on creation and later inspection. Use `has_more`/`next_after_sequence` from records output to request subsequent pages with `--after-sequence`.

In the UI, a **simulation** request requires the full scenario array, fee/execution documents and optional funding/calendars/config. The template's empty objects require editing; it does not select a valid experiment automatically.

## Read the report

Inspect candidate coverage, no-setup/rejection inventory, mature/unfilled/unresolved counts, gross/fees/funding/net attribution, source/feature identities and exact outcome revisions. The independent cumulative P&L chart is not account equity or a deployable return series.

`completed` means publication succeeded. `ready` additionally concerns candidate/outcome completeness; neither means profitable or statistically sufficient. Exit **2** can retain a valid completed report with no candidates or insufficient/unresolved evidence; inspect the JSON rather than deleting it as a crash. Exit **1** indicates an actual input/source/budget/publication error.

## Configuration and limits

[Simulation config](../../../configs/c11_simulation.json) controls detection windows, sampling and budgets. Earlier data supplies warm-up; later pinned data supplies the outcome tail. The shipped scenarios are intraday engineering examples. Swing research requires an explicitly chosen holding policy, horizon and sufficient history/tail.

A candle-only historical backfill does not supply historical quote/contract-trade execution. Explicit coarse bar-mode research retains its modeling limits and unknown funding/net where applicable. See [execution and costs](EXECUTION_AND_COSTS.md) before interpreting results.

Compare only compatible declared runs. Next stages are [expectancy fitting](EXPECTANCY.md), [walk-forward validation](WALK_FORWARD_RESEARCH.md) and [shared-capital replay](PORTFOLIO.md), not immediate live signals.

Full contract: [C11 operation](../../components/c11/C11_IMPLEMENTATION.md).
