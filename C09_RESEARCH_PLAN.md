# C09 trade policy and outcome research plan

Scope authorized 19 October 2026: a shared, deterministic **paper trade lifecycle** connecting C08 candidates, C07 market execution and C06 settled funding. It must own quantities, charge each fill fee/funding amount once, preserve independent long/short outcomes, and expose unresolved evidence. Historical strategy orchestration is C11; C12 owns walk-forward trials and promotion.

## Initial decisions and rationale

| Decision | Initial rule | Reason and downstream effect |
| --- | --- | --- |
| Entry | Market execution after C07 processing/delivery/manual delay; candidate expiry is exclusive | Same cost/freshness model as C07; no retroactive candidate-close fill |
| Stop | Fixed 1% from detection-time reference | An explicit engineering baseline, not an optimized stop or exchange order |
| Target | Fixed 2 × reference-to-stop distance | Versioned outcome definition; actual entry slippage changes realized risk/R |
| Holding limit | Four hours from actual paper entry | Shared historical/forward time-exit rule |
| Optional partial | Declared R level before final target, fraction of original filled size, floored to valid lot grid | Remaining quantity supplies settlement exposure; never increase size to satisfy a partial |
| Default trigger | Normalized contract trades | Mark triggers are separately selectable; quotes supply execution, not the trigger |
| Candle alternatives | Explicit `bar_close` or `bar_range` | Close decisions execute through C07's coarse close model; conflicting range touches remain unresolved |
| Exit latency | Explicit zero default; separately configurable | This is a research convention, not measured human exit speed or a protective exchange order |
| Exit failure | Keep remaining quantity; retry within a bounded request window, then mark unresolved | Never infer a flat position merely because a stop was triggered |
| Funding | C06 declared calendars and strict boundary guard | Unknown/missing/ambiguous funding keeps net labels null; next-funding estimates are never booked |
| Capital | Independent trade scenarios with caller-supplied size | Shared capital, leverage and simultaneous trade admission belong to C13/C11 |

Stops and targets are absolute levels frozen from the candidate reference. The stop is not moved after a partial exit. A pending entry rechecks the setup against current C03 context and the original trigger boundary; a lost thesis cancels entry. After entry, explicit invalidation requests a market close, and fixed stop/target/time rules govern the position. Trailing stops and richer automatic strategy-invalidation policies remain extensions.

A stop condition and a market fill are different events. Binance permits last-price or mark-price triggers; its account/order rules remain outside this paper state machine. [Binance stop-order explanation](https://www.binance.com/en/support/faq/detail/360036351051), checked 19 October 2026. A gap can produce a worse fill than the stop level. [QuantConnect stop-market reference](https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/order-types/stop-market-orders).

## Dependency and consumer map

| Component | Required input or output | Boundary |
| --- | --- | --- |
| C08 | Candidate and its complete C03 feature artifact from the same C02 dataset | Activate only at the exact source cursor/prefix; no future candidate knowledge |
| C01 | Frozen universe observations and exact instrument versions | C07 checks rules at entry/exit; unavailable/ineligible metadata can block a paper close |
| C02 | Ordered normalized market observations and pinned vintage | Actual receipt versus explicit modeled availability stays visible |
| C03 | Current reusable feature readiness and strategy context | Revalidate pending setup without changing frozen trade levels |
| C07 | Entry/reduce-only exit estimates, admitted fills and taker fees | Rejected execution remains unfilled; do not subtract shortfall a second time |
| C06 | Position quantity timeline, declared settlement calendar and observed settlement revisions | Reconcile one current amount per funding key; never book published next-rate forecasts |
| C10/C12 | Gross/net R, distinct event/profit labels, maturity and unresolved reasons | Outcomes require the exact policy/source identity; no probability/confidence is invented |
| C11/C14 | Same incremental lifecycle API for historical/forward drivers | C09 is the state machine; C11 owns strategy experiment scheduling and full simulator reporting |
| C13/C15 | Quantities, costs and explicit paper outcomes | Portfolio admission and forward account/cost reconciliation remain separate |

## Implementation package and acceptance

| Files | Major responsibilities |
| --- | --- |
| `tradee/c09/contracts.py` | Versioned `TradePolicy`, evidence-bound `TradeIntent`, exact frozen levels and record contract |
| `tradee/c09/engine.py` | Waiting/entry/open/exit/terminal states, trigger-source semantics, timing, partial quantities, C07/C06 wiring, evidence/revision handling and restore |
| `tradee/c09/ledger.py` | Exact fill-price gross P&L, fee debits, keyed funding reconciliation, risk/R, sampled excursions and distinct mature labels |
| `tradee/c09/store.py` | Separate SQLite manifests/transitions/reports/checkpoints with atomic commits and deterministic resume |
| `tradee/c09/cli.py` | Explain/run/report/manifest/summary/transition commands |
| `configs/c09_*.json` | Contract-trade baseline and explicit close-only candle alternative |
| `tests/test_c09_*.py` | Independent long/short, gap, partial/time/blocked exit, ambiguity, funding, ledger and restart cases |
| `scripts/verify_c09.py` | Raw imports through actual C08/C07/C06/C09 CLI processes, exact net outcomes and failure recovery |
| `scripts/verify_c09_public_replay.py` | Direct/persisted parity using retained public Binance candles under explicit modeled assumptions |

Acceptance requires exact independently expected amounts, source-prefix availability, quantity conservation, no duplicate booking on repeat/resume/corrections, visible unknown funding and incomplete tails, and real-process E2E. It does not establish strategy expectancy. C11/C12 must evaluate both C08 families independently with declared baselines, costs, trials and chronological holdouts. Changing exits or labels creates a new research policy/version.
