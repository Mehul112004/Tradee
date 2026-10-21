# Prospective forward review

**Location:** Forward review, `/forward`; Operations → forward observe / replay / apply pause. **Access:** viewer for reports; operator plus worker for UI observations, reconciliation and controls. **Prerequisites:** a frozen C14 session and C15 monitor registered before its first cycle.

C15 observes outcomes as they become recorded/knowable, retaining immutable report vintages, original forecasts, revisions and delivery/processing telemetry. A short paper run can correctly have insufficient statistical evidence.

## Observe and inspect

The dashboard **create session** workflow registers its monitor; the owned runner observes it repeatedly. For a CLI-owned session, register a complete actual policy, then observe it separately:

```sh
conda activate tradee
python -m tradee monitor create MONITOR_NAME --session SESSION_NAME \
  --policy path/to/frozen_monitor_policy.json
python -m tradee monitor watch MONITOR_NAME --interval-seconds 5 --max-cycles 720
python -m tradee monitor status MONITOR_NAME
python -m tradee monitor events MONITOR_NAME
```

Replace placeholders with real names/files and align custom stores. Registration must precede the first C14 cycle; do not create a monitor after seeing outcomes and treat the review as prospective.

In Forward review choose the monitor and report vintage. Inspect maturity/coverage, separate independent and funded summaries, fixed-review schedule, integrity/operational/statistical health, label history and delivery telemetry. Earlier report hashes retain their earlier pending/mature states.

## Pause requests and replay

Observation can record a **pause request** without applying it. Dashboard **apply pause** is a separate audited control. CLI `monitor watch --apply-pauses` explicitly permits the frozen monitor rules to apply local C14 pauses; no automatic resume, model retraining or trade execution follows.

To verify reproduction of a stored report's pinned raw data, use:

```sh
python -m tradee monitor reconcile MONITOR_NAME --report REPORT_HASH
python -m tradee monitor export MONITOR_NAME --report REPORT_HASH
```

Reconciliation re-executes the pinned C11/C13 path and compares hashes. It writes a reconciliation receipt and requires compatible current producer/runtime for operational replay. It does not prove that the execution model matches actual user fills.

## Configuration and interpretation

[Monitor example](../../../configs/c15_monitor.example.json) contains illustrative historical deadlines to replace. Review maturity lag, minimum mature samples, occupied blocks, bootstrap settings, review times, freshness and resource budgets before registration. Session horizon and statistical block length must be compatible. A brief intraday demonstration is unlikely to satisfy production evidence minima.

Independent candidate labels and finite-wallet outcomes have different denominators; never add them as one capital return. API acceptance latency is different from human/exchange fill latency. Missing bounds remain unavailable, not “no degradation.” A healthy engineering report is not live-promotion approval.

Related: [paper sessions](PAPER_SESSIONS.md), [exports](EXPORTS.md), [C15 operation](../../components/c15/C15_IMPLEMENTATION.md).
