# Shared-capital portfolio

**Location:** Portfolio, `/portfolio`; Operations → Research & data jobs → portfolio. **Access:** viewer for session wallet/results, operator plus worker for UI replay. **Prerequisites:** compatible recorded C11 source/report pins, applicable C10 models and declared C13 risk/replay policy.

C13 evaluates candidates competing for **one finite paper wallet**. It handles admission/ranking, tested size choices, exposure/risk/collateral reservations, cash, marked equity and rejection evidence. It is not an authenticated Binance account or order sender.

## Replay and inspect

Prepare `path/to/source_pins.json` as `{ "ACTUAL_C11_RUN_HASH": "ACTUAL_C11_REPORT_HASH" }`, using actual identities from the same compatible source scope. Replace placeholders below:

```sh
conda activate tradee
python -m tradee portfolio explain
python -m tradee portfolio replay --sources path/to/source_pins.json \
  --models MODEL_HASH --policy configs/c13_risk_policy.json \
  --config configs/c13_replay.json
python -m tradee portfolio summary RUN_HASH
python -m tradee portfolio manifest RUN_HASH
python -m tradee portfolio records RUN_HASH
```

The UI **portfolio** request uses its validated `sources` pins, model IDs and full policy/config documents. Review these rather than assuming the template has picked a valid bank. The standalone completed C13 replay is linked through its receipts; the Portfolio screen specifically displays the selected C14 session's shared paper cycle, so a replay alone does not create a populated session dashboard.

## Read the screen

Select a session with a funded cycle. Inspect equity/cash, open positions, risk budget, capital rejection reasons, stress results, inventory and funded trade evidence. Cash is not equity while positions are open. Unknown/stale marks can make complete equity/returns unavailable.

Compare independent outcomes in Research separately. Independent candidates can overlap capital; summing them is not wallet P&L. Unfilled/rejected candidates are retained as diagnostic evidence, not fabricated funded positions.

## Configuration and limits

[Risk policy](../../../configs/c13_risk_policy.json) sets admission limits; [replay config](../../../configs/c13_replay.json) sets initial capital, sampling and resource/window bounds. Their defaults are engineering settings, not selected account recommendations. Only compatible tested discrete sizes are considered; the system does not rescale prior outcomes arbitrarily or provide exchange liquidation/leverage modeling above the implemented baseline.

Change policy/capital/window as a new declared replay/research variant. Inspect the exact per-offer reasons when an attractive candidate is rejected. A zero-admission run can be mechanically completed but unready. Sampled drawdown is tied to the stated grid; unavailable annualized statistics must not be inferred from a short paper sample.

Related: [sessions](PAPER_SESSIONS.md), [expectancy](EXPECTANCY.md), [C13 operation](../../components/c13/C13_IMPLEMENTATION.md).
