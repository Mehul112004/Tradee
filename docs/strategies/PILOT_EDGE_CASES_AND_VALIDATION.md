# Pilot edge cases, reference examples and validation gates

**Design-only acceptance plan — 2 November 2026. No strategy code or market-performance tests have been run for these proposals.** The checks below are required future implementation/research work, not a record of passing tests. [Shared definitions](PILOT_STRATEGY_DESIGN.md) and the three family specifications are authoritative.

The goal is a strategy that can abstain and keep modeled exposure bounded when conditions deteriorate. No classifier identifies every regime change in advance, and a stop/loss circuit breaker is not a guaranteed monetary loss ceiling during gaps or outages.

## 1. Data, timing and source cases

| ID | Scenario | Required behavior |
| --- | --- | --- |
| D01 | Fewer than the required stable 15m/hourly bars | Show per-source warming up; no qualified notification. A nominal 200-bar EMA is insufficient. |
| D02 | Native bootstrap and streamed aggregation disagree on a closed bar | Quarantine/reconcile provenance; do not stitch a synthetic continuous history. Preserve the prior snapshot. |
| D03 | Missing minute inside a strategy/hourly candle | No aggregate or confirmation from that bucket; reset/cancel affected state until verified repair restores current readiness. |
| D04 | Data repair after a qualifying historical shape | Restore context with availability labels; no repaired/missed setup as a fresh live alert. |
| D05 | Forming bar briefly satisfies every shape condition | Chart update only; no seed/confirmation based on provisional close. |
| D06 | A 15m close arrives before the simultaneously needed hourly close | Wait within the 30-second detection deadline; use only the hour actually available. Missing by deadline means skip. |
| D07 | Final correction changes a pivot, EMA, volume or regime during a pending attempt | Cancel its current version; never rewrite prior observations or backdate a new setup. |
| D08 | Same event repeated or a late provisional update follows a final | Idempotent; do not undo finality, duplicate setups, reset expiry or consume a second attempt. |
| D09 | Receipt after market close | Preserve `confirmed_ms` versus `known_ms`; late knowledge cannot authorize an earlier approach/touch. |
| D10 | Future event time, mixed symbols/contracts, crossed quote or invalid OHLC | Fail source validation and suppress qualification. A relisted contract is a new instrument identity. |
| D11 | Zero range, ATR, historical volume or ER denominator | Explicit flat/undefined status and no qualifying arithmetic. No NaN, infinity or fabricated trend. |
| D12 | Price distinctions collapse in float64 or required indicator is unstable | Numerical/readiness rejection; exact level comparisons alone cannot rescue missing analytical evidence. |
| D13 | Server/exchange clock differs by more than 1s, quote ages >=2s, or mark age >=5s | Data gate blocks; local browser connectivity is irrelevant. |
| D14 | Feed disconnects after pattern detection but before send/entry | Recheck and cancel/suppress; no fallback REST live polling or guaranteed fill from the last quote. |
| D15 | Process restart with unfinished state or changed build | Same build: deterministic restore/rebuild with notification cutoff. Changed build: new analysis session, retained old evidence. Neither resets live workspace cooldown/attempt ledgers. |
| D16 | Calendar date/time revision, DST transition or unknown event timezone | Use versioned knowledge and proper conversion; unknown coverage/timing blocks qualification rather than assuming no event. |
| D17 | Historical candles exist but original quotes/calendars/rules do not | Permit a labeled price-pattern scan; no recorded-execution claim or invented complete net outcome. Research exclusions stay in coverage. |
| D18 | Reserved research holdout overlaps a quick scan | Apply existing acquisition/read protection. Quick access must not consume protected evidence silently. |
| D19 | Contract is suspended, scheduled to delist inside the holding horizon, or its rules change | No new qualification; after entry, retain original evidence and request a representable exit when necessary. Missing execution remains unresolved. |

## 2. Levels and pattern-state cases

| ID | Scenario | Required behavior |
| --- | --- | --- |
| L01 | Equal swing highs/lows or a pivot missing either right-hand confirmation | No strict pivot; no hindsight level. |
| L02 | The level is only confirmed during its apparent sweep/retest bar | It was unavailable for approach; reject. Do not treat confirmation time as its older anchor. |
| L03 | Current/partial UTC day substitutes for previous day | Reject the incomplete period. Select the seed's known day, not a later rolling label. |
| L04 | A daily-level pending confirmation lands exactly at midnight | Cancel on level rollover. An existing entered plan keeps its original frozen levels. |
| L05 | A 15m swing older than 96 bars, hourly obstacle older than 48h, or A/A_L outside [0.5,2] | Exclude expired/stale-scale reference before seed; no target-room bypass using an invalid source. |
| L06 | More than two prior touch episodes | Exhausted reference; no new level-based attempt. Consecutive touching candles are one episode. |
| L07 | Reclaim/entry after one attempt on the same level/direction/day | Remain consumed despite failure, new session, new delivery attempt or source revision. |
| L08 | Previous-day and swing references both qualify | Apply fixed pre-seed reference priority; retain alternatives, consume co-seeded opportunity references, no later winner-based fallback. |
| L09 | Wick pierces both sides in one candle | Sweep family rejects `dual_sweep`; do not infer order or emit both directions. |
| L10 | Sweep penetration exactly b or 0.75A | Inclusive geometry boundary; all other conditions still required. Greater than max depth fails. |
| L11 | Sweep needs a third candle to reclaim | Expired, even if the later move is attractive. Two accepted outside closes are a break. |
| L12 | Sweep shape appears at a range midpoint or against the established hourly trend | No qualified sweep; a visual wick does not override context. |
| L13 | EMA touches repeatedly, oscillates around price, or an eight-bar separation is incomplete | No arm/rearm. A fresh trend label alone does not reset the touch episode. |
| L14 | EMA changes enough to make an untouched candle look like a rejection | Use the frozen pre-touch EMA/band and the 0.15A drift limit; no moving-line chase. |
| L15 | EMA seed closes beyond the frozen EMA on the wrong side by b | Cancel, even if its wick is large. No future two-bar rescue beyond the defined window. |
| L16 | Retest happens on b0 or acceptance b1 | No accepted-break retest; b1 zone overlap is `early_retest`. |
| L17 | Retest appears on b0+6 / b0+7 | First touch at +6 is eligible, with possible confirmation +7; first touch at +7 is expired. |
| L18 | Retest is a second separated touch or follows >2A pre-touch close extension | Reject repeated/extended return; do not relabel it as first touch after resetting state. |
| L19 | Retest closes wrong-side by b or exceeds 0.50A depth | Cancel; no automatic conversion to opposite-side sweep. |
| L20 | Required context changes during any wait state | Cancel that attempt; no post-hoc change of strategy/mode. |
| L21 | A nearer opposing barrier appears/was known at confirmation | Freeze its ID and shorten T; reject insufficient costed room. Do not skip the inconvenient barrier. |
| L22 | Rounded stop becomes too tight/wide, target crosses entry or quantity is below minimum | Reject. No forced widening, optimistic target rounding or upward quantity adjustment. |
| L23 | A previously accepted level is later reclaimed, or ATR changes the displacement buffer | Preserve the original event using its frozen birth-scale buffer; do not reset it using current ATR or call it a fresh sweep. |
| L24 | First armed EMA band intersection has an inadequate wick/body | Consume/fail that episode; require eight new clean separation bars rather than selecting the next better-looking touch. |
| L25 | A new watch downloads a level that was already touched repeatedly or broken earlier | Reconstruct post-confirmation/publication behavioral context with knowledge/provenance labels and the original birth-scale zone. Missing history blocks freshness; startup cannot reset touch/break counts or backdate live attempts. |

## 3. Regime and market-environment cases

| ID | Scenario | Required behavior |
| --- | --- | --- |
| M01 | Stable uptrend / downtrend | Enable only aligned trend modes after two hourly snapshots; thresholds still require shapes, room, costs and source readiness. |
| M02 | Wide proven range | Only edge sweeps can qualify. EMA/retest cannot enter new trades merely because a local candle looks directional. |
| M03 | Narrow or unproven range, low relative volume, ATR below gates | All off. No requirement to stay invested or maintain an alert rate. |
| M04 | Constant tiny candles make percentile ties common | Midrank avoids all ties becoming a high-volatility signal; absolute activity/range gates and flat ER handle inactivity. |
| M05 | Trend slows into chop before hourly classifier changes | Entry gates may still lag; include subsequent losses in validation. Protective/family/stall/dull exits and risk pauses apply; do not claim this case is impossible. |
| M06 | A new strong move starts from dull/transition state | Skip until declared gates/persistence pass. Missed early profit is a measured tradeoff, not permission to retrospectively enable the detector. |
| M07 | One huge bar in otherwise dull conditions | Seed's prior activity veto and shock filter prevent self-qualifying expansion. Do not normalize the shock solely by its inflated current ATR. |
| M08 | Shock cools for seven / eight qualifying bars | Seven cannot rearm; eight permits reconsideration only if all other gates pass. Any new shock restarts the count. |
| M09 | Healthy range migrates or turns into a breakout | Validate frozen-box integrity; cancel pending or request exit. No expanding midpoint/target to keep the range thesis alive. |
| M10 | Weekend/holiday activity differs from weekdays | Apply measured activity, source and scheduled-event rules; report subperiods without tuning a new weekend rule after results. |
| M11 | Scheduled macro release occurs within maximum hold | No new qualified entry under this profile. An unexpected rescheduling is handled from its receipt time, never with future knowledge. |
| M12 | Unscheduled news, venue outage or flash gap | Suppress new risk when observed and follow unresolved/gap accounting. Calendar coverage cannot guarantee avoidance of the first adverse jump. |

## 4. Execution, outcome, risk and notification cases

| ID | Scenario | Required behavior |
| --- | --- | --- |
| X01 | Signal is detected but the human never enters | Observation only. No fee, fill, position or loss streak is invented. |
| X02 | Entry quote moves adversely or favorably beyond its band | Cancel equally; no chase, favorable hindsight entry or target reset. |
| X03 | S or T is observed after confirmation but before delayed entry | Cancel original plan. A completed historical excursion is not a fresh entry. |
| X04 | Pending plan reaches exactly the exclusive 180s expiry | Cannot enter; a queued message cannot extend expiry. Send start after close+60s is suppressed. |
| X05 | Spread/fees/size impact consume >0.25D_m or net RR falls below 1.8 | Reject despite a high gross target. Do not use a guessed maker fill or subtract costs twice. |
| X06 | Quote is fresh but order size is too large for declared liquidity/impact | Paper size/admission rejects or rounds down within the original risk budget; an observational alert is not a fill guarantee. |
| X07 | Stop and target are both reachable in one post-entry candle | Strict outcome unresolved; a separately labeled coarse stress uses stop-first with ambiguity flag. Never select target-first because it improves results or certify the stress result as a mature outcome. |
| X08 | Candle straddles the modeled fill, or trade/quote history has missing path | No claim about post-entry extrema without evidence. Coarse sensitivity is labeled; exact outcome may remain unresolved. |
| X09 | Price gaps through S | Use first available adverse executable exit with fees/slippage; allow realized net loss below -1 price R. No fill exactly at the stop by assumption. |
| X10 | Data unavailable while a paper position is open | Keep exposure/risk reserved and outcome unresolved. Do not pretend a market exit happened during the outage. |
| X11 | Mark-price move differs from contract last price | Use the declared contract stop source; mark remains separate for valuation/funding. No silent trigger substitution. |
| X12 | Settlement unexpectedly occurs during exposure, or funding boundary is ambiguous | C06/C09 reconcile signed amounts once; unknown/ambiguous funding keeps total net null. |
| X13 | Stall at 60m or exact maximum-hold deadline | Request exit only from available observations; record delay to an executable price. Unknown MFE is not zero MFE. |
| X14 | Qualified modes overlap on one symbol/bar | One bundle, primary priority sweep→retest→EMA, one hypothetical risk allocation; retain rejected alternatives/tags. |
| X15 | Opposite qualified directions, or duplicate session covers same opportunity | Suppress direction conflict / deduplicate across sessions; no extra wallet or extra attempt allowance. |
| X16 | Three daily family bundles, four-bar cooldown, or eight-bar EMA rearm is incomplete | Do not emit another entry bundle. Diagnostic pattern inventory may continue. |
| X17 | Third consecutive actual modeled loss / daily or weekly marked loss limit | Stop new paper admissions per frozen policy. An alert itself cannot trip an invented P&L breaker. |
| X18 | Campaign reaches 6% drawdown or gap exceeds a daily limit | Halt campaign/new risk; retain overshoot and all outcomes. No automatic restart/new name to erase it. |
| X19 | Midnight/Monday resets risk periods with positions or unresolved fills outstanding | Carry exposure/reserves and record actual equity; do not regain capacity through calendar reset. |
| X20 | Token/chat changes, pause, restart or 429/ambiguous Telegram result | Preserve existing one-attempt/frozen-destination behavior, suppression and durable waiting period. No automatic uncertain resend. |
| X21 | Overlap includes a capped family, or two instruments compete for remaining risk capacity | Suppress the capped bundle without dropping tags; use the frozen prefix/admission ordering for capital competition. Pending exits do not release risk before a fill. |

This matrix is intentionally adversarial, not exhaustive. Unexpected price/provider behavior is recorded and fails qualification until a reviewed version specifies it. Deterministic expected results must precede implementation tests; tests that merely call the detector twice are insufficient.

## 5. Independent arithmetic and state examples

Family files contain long and mirrored short candle examples. Each is conditional on its declared context; it is not a complete synthetic profitability scenario. Build independent raw OHLCV/quote fixtures with their complete warm-up and receipt clocks, not expected values generated by the production detector.

### Cost example

At assessment let bid=99.99, ask=100.01, M=100, S=98, T=105, f=0.0005 and p=0.0002. D_m=2 and assumed exit width is max(0.02,0.05)=0.05. The long estimates are:

- Entry `F_e=100.030002`; stopped exit `F_s=97.9554`; target exit `F_t=104.954`.
- Costed loss `2.173594701`; costed gain `4.821505999`; net reward/risk about **2.218**.
- Largest friction increment is below 0.25D_m=0.50; both cost gates pass before any size impact or separately applicable funding.
- If that estimated entry is actually admitted, outcome `D_entry=2.030002`; net-R divides by quantity times this actual-fill distance, not midpoint D_m=2 or all-in stopped loss.

Moving T to 102 with the same S does not produce an acceptable plan merely because it remains a gross 1:1 trade; it fails the net-RR gate. If price drifts, recompute with the unchanged S/T. If using actual C07 execution fills, do not charge embedded spread/slippage again.

### Required temporal examples

1. A swing anchored at 10:00, confirmed by 10:45 but received at 10:45:03 cannot authorize a 10:30 approach. Its earliest fully eligible approach bars start after knowledge.
2. Sweep s closes at 12:15; s+1 at 12:30 may confirm, s+2 at 12:45 never rescues it. The same-bar confirmation always wins if it already passed.
3. Retest b0=12:00–12:15, b1=12:15–12:30 acceptance; first retest can be b0+2 through +6. Touch at +6 and confirmation at +7 is eligible; first touch at +7 is not.
4. A qualified close at 12:15:00 with detection at 12:15:02 has baseline modeled entry assessment no earlier than 12:15:32. It cannot use the 12:15:00 candle close as its fill. Latest entry is strictly before 12:18:00.
5. After a qualified confirmation at 12:15, the four-bar observation cooldown permits the next confirmation no earlier than 13:15. Historical scans use isolated state and do not consume that live slot.

## 6. Research protocol before inspecting performance

### Freeze the procedure

Four primary **mode** hypotheses are counted: sweep range edge, sweep trend pullback, EMA trend rejection, and key-level trend retest. Mode/source/timeframe choices, exits, actual fee assumptions, entry delay, overlap priority, capital limits and inspected-history disclosure are frozen before evaluation. A fixed R target does not supply a known win rate; stall/invalidation exits also change payoff distributions.

Target at least 36 months of audited history spanning different conditions, plus required prehistory; actual provider coverage is audited before exact dates are chosen. Reserve the last six months as uninspected final evidence. Earlier development contains at least four disjoint quarterly outer tests, each selected/fitted using only earlier history with at least 12 months of training where applicable. Purge actual outcome intervals plus a predeclared 24h pre-test gap. Feature warm-up may use earlier observations but never future outcomes. Rolling ER/percentiles are evaluated point in time, not refitted on the complete dataset.

Once inspected, data stays development/diagnostic data, including earlier TBot work. A new repository/source hash does not create a new holdout. Final access remains deliberate and one-way through C12. If honest untouched history is unavailable, use prospective validation; do not relabel already viewed candles.

### Trial budget and comparisons

Predeclare a family-wide budget of **64 new configurations/recipes plus the disclosed historical material-trial count H**. Fifty-four planned entries are:

| Comparison | Count |
| --- | --- |
| Four primary modes | 4 |
| Matched raw-geometry baselines without regime/quality filters, still charged compatible costs | 4 |
| Two ablations per mode: remove dull gate; remove exhaustion/first-touch restrictions | 8 |
| Four adverse scenarios per mode: fees ×1.5, slippage ×2 with 10bps assumed exit width, delay 60s, delay 120s | 16 |
| Combined adverse scenario per mode | 4 |
| ATR-distance geometry neighbors ×0.8 and ×1.2 per mode | 8 |
| Joint regime-cutoff loose/tight neighbors per mode | 8 |
| One fixed combined capital/overlap recipe and its combined adverse scenario | 2 |
| **Total planned** | **54** |

Unused budget is not permission for undocumented search. Any later variant must be registered before its performance is inspected and remain within the reserved budget; a consumed final window cannot validate adaptive changes.

ATR geometry neighbors multiply ATR-based distances only (buffers, penetration, body size, separation, range width); time limits, risk, fees, volume, percentile/ER and net RR stay fixed. The two regime neighbors are: loose trend ER>=0.30/range ER<=0.30, trend slope magnitude>=0.008/range slope<=0.006; tight trend ER>=0.40/range ER<=0.20, trend slope>=0.012/range slope<=0.004. Other classifier conditions stay fixed. These are limited neighborhood checks, not proof of global parameter robustness. Cost scenarios retain the same detector rules and baseline selection; changed entry/exit timing is explicitly a protocol sensitivity.

Compare identical permitted data/costs/windows. Report sample loss and forgone winners when filters remove trades. A short quote-history slice cannot be compared with a long candle baseline as if only the filter changed. Never select the best outer fold, symbol, side or subset after viewing it. Reduced-mode portfolios after a failed mode require a new counted recipe and untouched validation; they do not inherit the full portfolio's result.

## 7. Acceptance gates and regime damage checks

These are proposed evidence requirements, not empirical guarantees or already implemented C12 settings. Freeze them with exact source/date coverage and numeric policies before results.

| Gate | Required evidence |
| --- | --- |
| Software causality | Every applicable matrix case has independent expectations; prefix/batch/restart parity, clock/rounding correctness and immutable evidence pass |
| Outcome coverage | Every admitted trade past the predeclared maturity cutoff has a resolved path, costs and funding; unknowns cannot be dropped or set to zero to obtain acceptance. Incomplete cohorts remain insufficient, with all unknowns reported |
| Primary mode sample | At least 100 mature evaluable entries across outer tests, at least 20 per selected instrument, at least 30 occupied synchronized 3-day calendar blocks; fewer means insufficient |
| Uncertainty | Approximate synchronized time-block inference, alpha=0.05 with family-wide adjustment using budget `64+H`, at least 50000 declared draws and resolvable tails; lower net-R bound >0 for each deployed mode |
| Chronological consistency | At least three of four outer tests positive net for a deployed mode; aggregate evidence positive; removal of the best calendar block leaves net >=0 |
| Stress and neighbors | Positive aggregate net under each predeclared adverse cost/delay case and its combination; geometry/state neighbors cannot depend on an isolated favorable threshold spike |
| Final evidence | Frozen mode has positive final net and positive adjusted lower bound, with at least 30 mature final entries and 10 per selected instrument; otherwise insufficient/rejected rather than assumed transferable |
| Capital policy | Independent setups are replayed with one shared wallet, overlap/cooldown rules, quantity constraints and all costs; maximum marked campaign drawdown <=6%, including the actual halted path |
| Forward paper | At least 60 calendar days and 50 mature entries per deployed mode, whichever takes longer; same source/latency/cost definitions; failed forward evidence pauses promotion |

Net-R uses the repository convention: net P&L divided by initial **price-risk** amount `q*D_entry`, where `D_entry=abs(actual_entry_fill-S)` is frozen at admission. Costs can make a stop loss worse than -1R. Monetary position sizing separately budgets the estimated all-in stopped loss. Annualized returns or a fictional compounded curve cannot be inferred from overlapping independent setups.

### The ranging/dull-market audit is mandatory

For every family/mode, publish both:

1. **Entry-regime report:** decisions, patterns, vetoes, qualified plans, fills/unknowns, net R, cost burden, expectancy/uncertainty, losers and worst clusters, labeled with the regime actually available at the decision.
2. **Time-in-regime report:** regular marked P&L, exposure, drawdown and exits during subsequently observed trend/range/dull/transition/shock periods, **including positions carried in from a preceding trend**. No retrospective relabeling of the original entry. Later-known regimes are diagnostic, not inputs to earlier decisions.

Expected entry invariants: EMA/retest have zero new qualified range/dull/transition entries; range sweeps have zero midpoint/dull entries; trend sweeps never oppose the active trend. Check queued entries again at assessment. Zero entries is abstention, not a positive win rate; undefined estimates remain null. Carry losses during regime changes remain visible even when those invariants hold.

Require deployed range-sweep and trend-sweep modes to meet their own gates independently. Trend profits cannot cover a negative range mode in the decision. Compare mark-to-market damage during range/dull transitions against the cost-matched ungated baseline; a strategy that merely delays the same large losses fails its stated purpose. Report scheduled-event, weekend, volatility-tail, side and symbol slices as diagnostics; selecting a slice after seeing it is another trial.

### Tail and uncertainty cases

Add deterministic stop-gap scenarios at 1A, 2A and 5A adverse jumps, widened/crossed/missing books, missing funding, exchange-rule changes and downtime. Report exact loss/overshoot and unresolved coverage, not a guarantee that normal daily limits cap a gap. Calibrate trade-size impact and manual latency with prospective records; if plausible friction removes the edge, reject the policy.

Simulated examples, a high gross RR or attractive candles do not establish these gates. Published level/order-flow evidence comes from other samples and markets. [Backtest-overfitting research](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) motivates controlling selection; it does not validate this classifier, these bootstrap assumptions or future returns.

## 8. Definition of design completion versus build completion

This package completes a proposed **rule design**: bounded scope, mode routing, exact states/thresholds, timing, conditional entry/exit/risk rules, source failures and acceptance criteria. It does not mean any pilot is registered, selectable, profitable or live approved. Current C04/C05 are measurement prerequisites only.

The later build must implement the missing shared measurements/state, automatic data/calendar preparation, history/retention changes, UI/notification contracts, checkpointed attempt/cooldown state and structural lifecycle support described in [the shared integration section](PILOT_STRATEGY_DESIGN.md#7-planned-quick-flow-integration-and-observable-reasons). Preserve [quick analysis](../dashboard/ANALYSIS_FLOW.md) as the low-friction observation entry point; research evidence remains a separate deliberate workflow.
