# Component research and review template

Use one copy per component when its deep research begins. The [component specification](../platform/COMPONENT_RESEARCH.md) is the overall architecture reference. Unfilled fields are unresolved; they are not implicit approval or implementation instructions.

## Identity and status

- Component ID and name:
- Research date and revision:
- Status: not researched / researching / ready for review / reviewed / needs revision.
- Reviewer decision and date:
- Upstream/downstream components affected by this revision:

## Purpose and scope

- Question this component answers:
- Contribution to expectancy estimation, validity, risk or operation:
- Mandatory first version:
- Optional extensions:
- Responsibilities explicitly owned elsewhere:

## Dependencies and consumers

Use the main specification's D/O/A/R/F relationship types. Include a named record/interface, not only a component ID.

| Provider | Type | Record or capability received | When it is available | Missing/stale/version-mismatch behavior |
| --- | --- | --- | --- | --- |
| To research | | | | |

| Consumer | Type | Record or capability supplied | Consumer's use | Compatibility and change impact |
| --- | --- | --- | --- | --- |
| To research | | | | |

- External data, services and operator inputs:
- Bootstrap plan before downstream artifacts exist:
- Feedback/artifact boundaries that avoid circular imports or future-data use:

## Major internal parts

| Part | Responsibility | Inputs and outputs | State/persistence | First version or later |
| --- | --- | --- | --- | --- |
| To research | | | | |

## Evidence and design alternatives

| Source and date | Finding or documented behavior | Market/horizon/sample | Limitations | Design implication |
| --- | --- | --- | --- | --- |
| To research | | | | |

- Competing approaches and tradeoffs:
- Recommended approach and rationale:
- Evidence against the recommendation:
- Claims that still require our own empirical test:

## Definitions and contracts

- Mathematical definitions, units and rounding:
- Data schemas, identifiers and versioning:
- Event time, receipt time, availability time and outcome maturity:
- Lookback/warm-up and fitted-state rules:
- Determinism and historical/live parity:
- Batch/stream interface and persistence ownership:
- Failure modes, recovery, degraded operation and suppression rules:
- Performance/storage requirements to benchmark:

## Verification and incremental-value experiment

- Hand-calculated examples or reference fixtures:
- Causality and boundary cases:
- Integration checks with providers and consumers:
- Recovery checks where applicable:
- Baseline and proposed variant, if predictive or policy-changing:
- Permitted development/test data and selection budget:
- Metrics, uncertainty and stress scenarios:
- Acceptance criteria declared before performance inspection:

## Review outcome and later implementation scope

- Agreed decisions:
- Open questions/blockers:
- Changes required in the main dependency matrix and affected components:
- Smallest implementation increment after review:
- Prerequisites for that increment:
- Definition of done:
- Explicitly deferred work:
