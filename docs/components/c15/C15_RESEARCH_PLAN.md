# C15 — Forward measurement and monitoring

Implemented 20 October 2026. The user authorized this component under the same testing, E2E, upgrade-register and phased-commit workflow as C06 onward.

## Purpose and ownership

C15 determines whether a frozen paper deployment is behaving like its recorded assumptions. It consumes C14's decision/delivery journal, C11 independent shadow outcomes and C13 funded paper outcomes. It retains the shared C09 labels and exact money accounting. It does not implement another exit engine, send Telegram messages, submit orders, change a model, grant live promotion or automatically resume a pause.

| Dependency | Evidence used | C15 consumer/output |
| --- | --- | --- |
| C01/C02 | Point-in-time instrument metadata and pinned recorded market events | Full raw-input replay reconciliation |
| C03/C06/C07/C08/C09 | Existing production features, funding, costs, candidates and paper policy | Reused through C11/C13; labels validated using C10's shared C09 monetary/revision validator |
| C10 | Admission-time conditional mean net R and execution protocol | Forecast residual review; no reinterpretation as calibrated win probability |
| C11 | Verified independent reports and complete artifact inventories | All candidate outcomes, including capital-rejected shadow candidates |
| C12 | Frozen release/experiment/model identities already bound into C14 | Preserved lineage; future research export requires a separately counted experiment |
| C13 | Verified funded replay, shared cash and accepted trade ledgers | Admitted outcomes and exact paper wallet reconciliation |
| C14 | Frozen deployment, historical cycles, source watermarks, processing/delivery/control journal | Consistent forward evidence and optional audited pause application |
| C14 receives C15 | Persisted, source-qualified pause requests | Explicit `apply-pause` or `--apply-pauses`; revision and audit-head compare-and-swap |
| C12 receives C15 | Versioned matured outcome export | Research input only; no automatic fit, retrain, replacement or holdout import |

## Contracts and causal rules

1. Register one immutable `MonitorPolicy` per deployment in the local store before its first C14 cycle. Registration is anchored to the existing C14 audit head and cannot precede its actual recording. Pre-start registration is supported: a future deployment start is not an already observed decision. Before start the monitor reports awaiting-session status without requesting an operational pause. Do not invent a prospective baseline from completed outcomes. Review times, block settings, maturity lag, evidence minima, tolerance and pause switches are frozen.
2. Obtain one C14 SQLite read transaction containing deployment, all cycle publications and delivery states. Validate the journal, signal/outbox inventories, artifact hashes, downstream C11/C13 summaries and their full inventories. A report remains pinned to that source vintage even if the runner advances concurrently.
3. Retain independent and funded tracks separately. The former does not share capital. Telegram service acceptance, operator acceptance assertions and hypothetical paper fills are three distinct forms of evidence. No actual user fills are supported in this baseline.
4. Use the first cycle recording admission for its frozen forecast. Count an admission in statistical review only when its source cutoff covers entry causally and its **actual C14 audit recording time is strictly before outcome knowledge**. A catch-up or slow cycle that records a trade after its outcome is preserved diagnostically and excluded from inference. Audit recording time precedes final SQLite commit; it does not claim an independent remote publication or fsync-latency guarantee.
5. Export a label only when C09 marks it ready/mature, its ledger/revision and net money reconcile, and its first current revision's source cutoff, actual recording and outcome knowledge plus the frozen maturity lag are **strictly earlier** than the report/review cutoff. Unknown funding, ambiguous paths and open/revoked labels never become zero returns. A later correction replaces the current label; old reports and completed reviews stay immutable. Reappearance after an intervening revision restarts revision availability.
6. A fixed-look review uses the latest cycle with both source cutoff and actual audit recording strictly before that deadline. Late publication of a backdated cutoff cannot backfill unavailable evidence. Insufficient early reviews remain insufficient permanently.

## Measurement and formulas

For a mature trade, `net USDT = fill-price gross PnL − fees + signed settled funding`; `net R = net USDT / actual entry-to-stop risk`. C15 uses C09/C10 validation and exact Decimal sums. Execution shortfall is already reflected in fill prices and is not subtracted again.

Each admitted row records C07 entry shortfall/fee attribution, modeled fill and execution delay, plus entry estimated fee versus the paper ledger's entry fee and their difference. Entry next-settlement funding estimates and full-hold settled funding are retained with different horizons; no misleading whole-hold forecast error is calculated from that one-settlement estimate. These are simulated costs on recorded quotes, not empirically verified exchange/user slippage.

Processing duration comes from C14's monotonic measured interval. Detection-to-first-cycle, detection/entry-to-claim, claim-to-result and HTTP elapsed durations come from the recorded clocks/journal. They do not measure human reaction or exchange execution latency. Manual delivery reconciliation remains explicitly identified as an operator assertion.

The two predeclared degradation statistics are admitted-paper **mean net R** and the mean of `net R − frozen admission predicted mean net R`. Calendar-bin net/residual sums and counts are resampled together in fixed circular blocks, keeping related assets and both statistics paired in the same draws. These statistics are conditional on the admitted cohort, not unconditional profit-per-alert or capital-return estimates.

The whole admitted cohort must be mature and prospective; unresolved admissions block inference rather than disappearing from complete-case analysis. Require the frozen minimum mature observations and occupied nonoverlapping spans, at least two distinct residual and net outcomes, a block at least as long as the longest label span, and a window longer than one block. Empty/degenerate resamples and work-budget failures cannot certify health.

For `K` declared looks, two statistics and family alpha `α`, each interval tail receives `α / (4K)` using exact rational ranks. Statistical degradation requires either the upper residual bound below `−residual_tolerance_r` or the upper net-R bound below `net_mean_floor_r` (default zero). Both rules and their family budget are frozen before observation. This is approximate inference conditional on representative calendar blocks and weak/stable dependence. Tail allocation does not establish valid intervals under arbitrary drift or repair adaptive reuse. “No degradation detected” does not prove profitability.

The [NIST Bonferroni explanation](https://itl.nist.gov/div898/handbook/prc/section4/prc473.htm) supports allocating a fixed family error budget across declared comparisons. The [arch time-series bootstrap documentation](https://bashtage.github.io/arch/bootstrap/timeseries-bootstraps.html), also used by C10/C12, describes circular block resampling. C15 uses the existing standard-library resampling and percentile routines; it introduces no scientific-library dependency. Sources checked 20 October 2026; the implemented interval has the limitations above.

## Operational rules and controls

No cycle, a stale active-session cycle, unhealthy paper data/risk, analysis latency failure, C14 operational faults, failed/ambiguous delivery, an elapsed in-flight lease or an unrecovered pending expiry produce operational reasons. Verified downstream corruption and failed raw replay produce separate integrity reasons. A corrupt C14 audit itself prevents observation; operator repair/pause is required because that control source can no longer be trusted.

Operational and statistical pause switches are explicit; integrity failure always requests a pause. Applying a request checks both the C14 revision and the exact audit head, so delivery-only races are caught. It never resumes a deployment. The request is committed before C14 is changed. If a crash happens after C14's durable pause and before its C15 receipt, retry recovers that exact prior event without another pause. A recovered receipt describes a historical action, even if an operator has subsequently resumed.

The official [Telegram Bot API](https://core.telegram.org/bots/api#sendmessage) returns a Message on successful service acceptance. C15 therefore never interprets that response or a message ID as proof of human receipt or a user trade.

## Explicit limits and acceptance

The shipped interface is CLI/JSON/SQLite, with a bounded foreground watcher. There is no dashboard, external supervision, incremental time-series store, cross-session statistical pool, actual-user fill ingestion, feature-drift detector, probability recalibration or automatic replacement. These are recorded in `COMPONENT_UPGRADES.md` with their gates. Default inference minima need substantially more data than the synthetic demo and must be chosen prospectively for the actual strategy horizon and dependence.

Acceptance covers raw C01→C15 signal-to-matured-outcome E2E, exact funded wallet matching, retained rejected shadow outcomes, causal fixed reviews, deterministic replay of pinned raw inputs, redacted failures, inventory corruption, concurrent publication, stale-control refusal, crash-gap recovery and immutable exports. Engineering acceptance does not establish a real-market edge or remove C12/C13/C14 actionable-live gates.
