# Pilot strategy design v1: shared rules and market-state policy

**Later implementation status:** the Analysis detectors and dedicated experimental research runner are now implemented; see [implementation/evaluation](IMPLEMENTATION_REPORT.md) and the separately preregistered [context alternative](CONTEXT_PROFILE_V2_EXPERIMENT.md). The proposal below is the frozen v1 design, not a claim that its thresholds passed validation. Its original implementation-gap descriptions record the starting point; the report tracks what was built and what still needs evidence.

**Status: proposed design, 2 November 2026. Documentation only.** No detector, configuration, runtime or trading change is made by this specification. The numerical thresholds below are declared starting hypotheses, chosen without examining new performance. They are not optimized settings or demonstrated protection against loss. Implementation needs a separate instruction; profitability and deployment require later evidence.

The objective is to avoid applying trend-continuation rules indiscriminately to ranges and quiet markets. The design permits abstention, restricts reversal attempts, charges costs, limits repeated exposure and specifies how to reject inadequate evidence. Market-state estimates lag; gaps, reversals and slippage can still produce losses exceeding a planned stop. No finite rule list covers every possible market event.

## Documents and precedence

| Document | Owns |
| --- | --- |
| This document | Scope, mathematics, causal timing, regime routing, execution/risk policy and integration contract |
| [Liquidity sweep](LIQUIDITY_SWEEP_V1.md) | Sweep/reclaim pattern, range-edge and trend-pullback modes |
| [EMA200 rejection](EMA200_REJECTION_V1.md) | First controlled return to the execution EMA200 in an established trend |
| [Key-level retest](KEY_LEVEL_RETEST_V1.md) | Accepted break followed by a distinct first retest |
| [Edge cases and validation](PILOT_EDGE_CASES_AND_VALIDATION.md) | Adversarial scenarios, reference examples, trial accounting and rejection criteria |

All strategy conditions are AND conditions unless an explicit OR is written. Shared vetoes override pattern matches. Missing, nonfinite, unstable or ambiguous required evidence means **not qualified**. Exactly meeting a stated inclusive bound passes; strict comparisons are written explicitly. An unlisted operational case produces `unsupported_case` and no new qualified setup until reviewed, rather than a guessed default.

## 1. Pilot scope and the quick workflow

Proposed research scope: **Binance linear USDT perpetual BTCUSDT and ETHUSDT; 15-minute execution candles; 1-hour context; both directions**. These are scope assumptions, not recommendations to trade those assets. Other instruments/timeframes require separately versioned evaluation. The current form's 1m/4h/1d options do not automatically validate these new definitions. No mandatory 4h filter, OI, liquidation prediction, LLM verdict or depth model is included.

The entry point remains [New analysis session → Watch live / Scan history](../dashboard/ANALYSIS_FLOW.md). The API must prepare the declared inputs automatically; no C12 release, research hashes or account credentials are added as mandatory quick-form inputs.

Three evidence levels must remain distinct:

1. **Pattern match:** the geometric/state-machine conditions matched; retained with all missing/rejection reasons. Historical candles alone can support a labeled pattern scan.
2. **Qualified setup observation:** pattern, causal context, regime, price geometry, fresh market data, event/funding timing and the declared modeled-cost checks all pass. Only this level is eligible for the proposed pilot Telegram message. It remains an unvalidated observation, with assumed fees disclosed and `live_approved: false`.
3. **Paper trade/outcome:** an explicitly modeled entry/exit and, where applicable, finite-capital admission occurred. Only this track can produce fills, net R, loss streaks and drawdown. An alert is never treated as a fill or a winning/losing trade.

If cost/quote/calendar inputs are missing, price patterns may remain visible as **execution unchecked**, with notifications withheld under this strict profile. Starting a session still works and reports preparation/missing-input status. This distinction must be visible; it cannot silently downgrade a strict qualified alert to a candle-only assertion.

## 2. Common mathematical and timing definitions

- `t`: a completed 15m contract-price candle; `O,H,L,C` are exact source prices. `end(t)` is exclusive. Forming candles cannot seed or confirm a pattern. Observed contract trades may still invalidate pending plans or trigger protective exits intrabar; protection does not wait for a candle close.
- `s`: the pattern's seed bar. `A = ATR14_15m[s-1]`, stable and positive, is frozen for its lifetime. `A_h` is the stable 1h ATR14 at the seed's context. All fixed distance thresholds below use this frozen `A`.
- `E200_t`: C03 SMA-seeded EMA200 of completed 15m closes. `slope200_5 = (EMA200[t]-EMA200[t-5])/(5*ATR14[t])`, in ATR per bar. Hourly measurements use hourly ATR. Analytical values follow C03's float64/error rules. For price/ATR/EMA threshold comparisons, freeze their finite round-trip decimal serializations and use exact decimal arithmetic; do not add an undisclosed epsilon. Structural prices and tick comparisons stay exact.
- `b = max(0.10*A, 2*tick_size)`: break/reclaim comparison buffer. `stop_buffer = max(0.15*A, 2*tick_size)`.
- `CLV=(C-L)/(H-L)`. A bullish confirmation requires `C>O`, `C-O >= 0.25*A`, and `CLV >= 0.75`; a bearish confirmation requires `C<O`, `O-C >= 0.25*A`, and `CLV <= 0.25`. A zero-range candle cannot confirm.
- `RV_t = quote_volume[t] / mean(quote_volume[t-20:t])`, excluding current from the denominator. A confirmation requires `RV_t >= 1.0`. Undefined/zero historical volume is not evidence of participation. Retest's initial breakout has its own stronger volume/body thresholds.
- `ER24_h = abs(C_h-C_(h-24)) / sum(abs(C_i-C_(i-1)), i=h-23..h)`. This uses 25 contiguous hourly closes. A zero path has ER=0 plus a flat flag and is classified dull; it is never division by zero or a perfect trend.
- `ATR_percentile_t`: midrank of `ATR14_t/C_t` against the **672 preceding** 15m values: `100*(count(prior<current)+0.5*count(prior=current))/672`. No future sample, full-history percentile or fitted global threshold is used.
- `crosses32`: sign changes of `C_i-E200_i` over 32 adjacent 15m pairs/33 closes. Equality retains the preceding nonzero sign; unknown history makes the measurement unavailable.

At a pattern seed, every frozen level must have `known_ms <= open(s)` and all approach bars using that level must also start after it became known. A pivot's historical anchor is not its knowledge time. The seed freezes context and level versions; confirmation and pre-entry assessment recheck currently available context without rewriting the seed.

For live bootstrap, historical native candles may initialize analytical context under explicitly modeled historical timing, with their actual download receipt also saved. They do not retroactively create live pattern states. A newly observed level uses its actual live knowledge time: sweep/retest wait for three complete post-knowledge approach bars before seeding, unless persisted earlier knowledge can be verified. Starting a watch can therefore precede its first eligible level-based opportunity by at least 45 minutes. Do not backdate a level merely to shorten startup. Historical scans may use a separately declared availability model; their observations are not evidence of recorded historical execution.

Bootstrap must nevertheless reconstruct a level's **behavioral context** from its structural confirmation/publication onward, using the history now available: prior touches, accepted breaks and source coverage. This is a summary learned now, not a retroactive live attempt. Use the pivot's completed right-hand confirmation or the completed day's publication endpoint, never its older anchor. Preserve both historical event times and the actual summary knowledge time. Missing required level-lifetime history means unknown freshness, not zero touches. A new watch therefore cannot make an old exhausted/broken level appear fresh.

For a decision at a 15m close `T`, the expected hourly candle ends at `floor(T/1h)*1h`. It must actually be available. At simultaneous 15m/1h closes, wait for both required finalized inputs, up to `T+30s`; do not substitute a future/partial hour or silently use an older hour. No new qualified notification after this detection deadline. Replay orders `(available_ms,event_id)` and uses the same rule as live processing.

## 3. Market-state classifier and routing

Evaluate raw hourly state from closed data. `TREND_UP`, `TREND_DOWN` or `HEALTHY_RANGE` becomes active only after **two consecutive hourly raw snapshots** agree. A raw mismatch immediately produces `TRANSITION` for new entries; two snapshots are needed to establish a new active state. Dull/shock/data vetoes override this persistence rule immediately.

In this classifier, `a_h=ATR14_1h[h]` is the current hourly snapshot's ATR; recompute it with each new closed hour. A pattern separately freezes that snapshot's value as `A_h` at its seed decision. Frozen range geometry does not replace the current classifier's volatility measurements.

| Raw state | Exact conditions |
| --- | --- |
| `TREND_UP` | `C_h > EMA200_h + 0.25*a_h`; `EMA20_h > EMA50_h > EMA200_h`; `(EMA20_h-EMA50_h)/a_h >= 0.25`; hourly `slope200_5 >= 0.01`; `ER24_h >= 0.35` |
| `TREND_DOWN` | `C_h < EMA200_h - 0.25*a_h`; `EMA20_h < EMA50_h < EMA200_h`; `(EMA50_h-EMA20_h)/a_h >= 0.25`; hourly `slope200_5 <= -0.01`; `ER24_h >= 0.35` |
| `HEALTHY_RANGE` | `ER24_h <= 0.25`; `abs(hourly slope200_5) <= 0.005`; valid wide box and boundary evidence below |
| `TRANSITION` | Everything else, including ER/slope dead bands, insufficient state persistence, or unstable range boundaries |

A healthy box is `[B_low,B_high]` from the lows/highs of the last **24 completed hourly bars**. Require `4 <= (B_high-B_low)/a_h <= 10`. Each boundary needs at least two already-confirmed hourly 2-left/2-right pivots with anchors inside that same 24-bar window and prices within `0.25*a_h` of it; same-side pivot anchors must be at least three hours apart. Confirmation must actually be available at the snapshot. The box/its evidence is frozen at seed. No confirmed pivots or complete box means no range reversal. A rolling high/low alone is not a demonstrated range.

Frozen-box integrity persists only while the active state remains healthy range, the latest hourly close stays in `[frozen B_low-0.25*frozen A_h, frozen B_high+0.25*frozen A_h]`, and each current rolling box edge differs from its frozen edge by at most `0.50*frozen A_h`. Failure cancels a pending range sweep or requests an exit for an entered one. The original target/midpoint never moves with the new box.

| Active state | Liquidity sweep | EMA200 rejection | Key-level retest |
| --- | --- | --- | --- |
| `TREND_UP` | Long pullback sweeps only | Long only | Long accepted-break retests only |
| `TREND_DOWN` | Short pullback sweeps only | Short only | Short accepted-break retests only |
| `HEALTHY_RANGE` | Reversal at the appropriate outer boundary only | Off | Off |
| `TRANSITION`, dull, shock, unknown | Off | Off | Off |

Thus EMA/retest deliberately do not trade range middles or the first breakout out of an unclassified range. The filter may miss early trends. A failed trend entry is never reclassified retrospectively as a range trade.

### Dull and shock vetoes

Compute seed gates on data through `s-1`, then recheck current gates at confirmation. A quiet seed cannot qualify itself merely by producing one large confirmation candle.

**Dull if any condition holds:** `ATR14/C < 0.0010`; ATR percentile `<20`; median of the last eight available RV values `<0.70`; or high-low span of the last 16 execution bars `<2*ATR14`. Zero ATR/path/volume and undefined required features also block qualification. These gates apply in healthy ranges too. There is no unconditional weekend ban: an active weekend can pass, and a dull weekday cannot.

**Shock if any condition holds:** a new bar has `TR/ATR14_prior >3`; opening gap `abs(O-C_prior)/ATR14_prior >0.75`; ATR percentile `>97.5`; or `ATR14/C >0.02`. Cancel pending patterns and new entries. Resume only after **eight consecutive** complete execution bars with `TR/ATR_prior <=2`, percentile `<=95`, `ATR/C <=0.02`, and no opening-gap shock; other gates must also pass. A spread/data fault pauses qualification independently and does not prove normal volatility has returned.

Trend modes additionally require `crosses32 <=2`. A wide orderly range can contain EMA crossings; its sweep mode is instead constrained by the box edge, confirmation, room and cost rules. Quiet chop is not equated with a healthy tradable range.

## 4. Level inventory, freshness and exhaustion

Seed levels are **previous completed UTC day high/low** and **confirmed 15m swing highs/lows** (strict 2-left/2-right, ties excluded). Previous-week and discretionary drawn zones are not seed levels in v1. Known hourly swings may act as opposing obstacles.

- Daily levels are active for the following UTC day only. Pending patterns whose daily seed level rolls over are canceled at 00:00 UTC, including a final candle confirming exactly at that boundary. An already entered plan keeps its frozen levels across midnight.
- A 15m swing expires 96 execution bars after confirmation; an hourly obstacle expires 48 hourly bars after confirmation. Unknown/noncontiguous confirmation evidence is ineligible.
- Freeze `A_L`, the latest stable execution ATR ending at/before the level's structural confirmation/publication endpoint, and a touch half-width `z=max(0.10*A_L,2*ticks)`. It is usable only after the level and that analytical evidence actually become known; bootstrap labels its reconstructed historical timing. Strategy use also requires `0.5 <= A/A_L <=2`. Missing birth-scale ATR blocks use. Do not initialize an old level's zone from today's volatility.
- A touch episode begins with a closed bar intersecting `[X-z,X+z]` and remains open until two consecutive whole bars are completely outside that zone. One outside bar does not reset it; the next intersection after two outside bars starts a new episode. Count episodes first touched on bars opening at/after structural confirmation/publication and before the seed, with their evidence known at the decision, including reconstructed context described above. More than two prior episodes makes the level exhausted. An episode first touched on the seed is not prior; an earlier episode still ongoing at the seed is counted.
- One pattern attempt per level, direction and UTC day is consumed **when seeded**, including attempts that fail or expire. Ledger identity uses the stable level ID, not a new revision hash. No automatic second chance after a failed break/reclaim. No second pending attempt on that same level/direction across a day boundary. Repaired historical patterns do not consume fresh-notification capacity retroactively.
- Maintain a causal accepted-displacement ledger over the same post-confirmation/publication behavioral history: two consecutive complete closes at least `b_L=max(0.10*A_L,2*ticks)` beyond X in the same direction create an immutable event, usable only from its actual knowledge time. For sweep exclusion, a low previously accepted below / high previously accepted above is no longer a fresh sweep reference. For retest, an already accepted break in the intended breakout direction excludes a new breakout seed. Within a pending pattern, its frozen `b` governs its separate acceptance/invalidation comparisons. A single close followed by reclaim can still be a sweep. No strategy guesses where actual stop orders rest.
- If several eligible same-family levels are seeded on one bar, choose previous-day level first, otherwise the most recently confirmed swing, then lexical ID. Record alternatives as context and consume those co-seeded opportunity references too; do not fall back to a different reference after observing which pattern succeeds. No extra confidence votes or transitive level merging.
- A correction or instrument-rule change affecting the seed/context/level version cancels an unconfirmed or queued plan. After entry, preserve original stop/target and record any new action prospectively; never rewrite the trade's earlier basis.

## 5. Common confirmation, entry, target and exit policy

The family documents define seed/confirmation/invalidation. All require the relevant active state, no shared veto, confirmation body/CLV and RV, and confirmation range `TR <=2.5*A`. After selecting levels and rounding, stop distance from reference close must be `0.75*A <= D0 <=2.5*A` and at least ten ticks. A tight stop is rejected rather than widened to fit; an oversized stop is rejected rather than given smaller nominal R after the fact.

### Frozen plan and room

At confirmation, `P0=C_confirm`. Long structural stop is rounded **down** to a tick; short stop **up**. The family supplies the pre-rounded stop. `D0=abs(P0-S)`.

Trend-mode desired target is `P0 + side*2.5*D0`, with side=+1 long/-1 short. Range-sweep desired target is the nearer of that distance and the frozen range midpoint. All modes also stop their target **0.10*A before** the nearest opposing previous-day or unexpired 15m/1h swing reference in the profit direction, if nearer: highs for longs, lows for shorts. Obstacles must have anchors before seed and be known by confirmation. Use exact levels, not an imagined next round number. A reference at/between entry and the nominal target limits room even if its label is not a seed family.

Target rounding is toward entry. Freeze the final absolute target and all obstacle IDs. If no positive room remains, reject. A missing enabled obstacle source is not “no resistance”; mark room unknown. Empty, completely covered pivot searches can legitimately contain no obstacle.

### Entry timing and drift

- Baseline modeled reaction delay: **30 seconds after detection**. Stress delays are defined in validation. Entry uses the first available valid executable quote at/after that clock, strictly after confirmation; never the inspected candle close.
- Entry expires at `end(confirm)+180s` (exclusive). Notification may start only before `end(confirm)+60s`; a late/expired queued alert is suppressed. The transport timeout cannot extend entry validity.
- At assessment, midpoint `M` must satisfy `abs(M-P0) <= min(0.10*A,0.15*D0)`. Favorable moves beyond that band also require a fresh setup; no opportunistic re-anchoring.
- Recheck allowed state, seed version, health/event/funding gates, required side of the rejection/reclaim level and original stop/target. An observed stop/target hit after confirmation, material feed gap, or invalidation before entry cancels the plan. A fresh quote alone is not proof of an uninterrupted price path. Recorded contract-trade prices with the declared sequence/gap checks provide the trigger path; unavailable path evidence means `path_unknown`, not permission to enter. Historical candle-only scans cannot satisfy this execution claim.
- Recalculate stop distance and net reward/risk at the actual assessment price with the **same** absolute stop and target. Both midpoint-to-stop and prospective executable-fill-to-stop distance must remain within `0.75*A..2.5*A` and at least ten ticks, with the stop on the correct side, before paper admission. Reject if no longer admissible. Do not move levels to preserve an advertised ratio.

### Quote and modeled-cost gate

Required for qualified notifications/paper assessment: noncrossed positive book top, quote event and receipt ages each `<2000ms`, metadata age `<=15m`, server/exchange clock discrepancy `<=1000ms`, stream connected, spread `<=5bps` **and** absolute spread `<=0.05*A`. Current mark/next-settlement observation age must be `<5000ms`. Missing required history or calendar coverage fails qualification.

The current instrument must be trading, with verified tick/quantity/notional rules and no known suspension/delisting inside the proposed maximum hold plus five minutes. Relisting creates a new identity, not a continuation of an old level ledger. After entry, a rule change that prevents representing the original protective plan requests exit at the first valid executable observation; record the reason and any delay rather than silently altering the stop. No valid exit observation means unresolved exposure.

For the initial research assumption use taker fees **0.0005 each side**, matching the repository's illustrative fee preset, and adverse slippage **2bps each side**. These are explicitly assumed, not authenticated account fees or guaranteed upper bounds. A known higher applicable fee supersedes the assumption; a lower fee is a new version. Quantity-dependent impact is added by C07 for paper sizing and can reject an otherwise valid pattern.

For a transparent per-unit planning estimate, let `w_e=ask-bid`, `M=(ask+bid)/2`, `w_x=max(w_e,0.0005*M)`, and `p=0.0002`. `w_x` is an assumed exit spread, not known future depth. Funding reserve is zero only under the no-settlement-through-horizon gate below.

| Direction | Estimated entry `F_e` | Estimated stopped exit `F_s` | Estimated target exit `F_t` |
| --- | --- | --- | --- |
| Long | `ask*(1+p)` | `S-w_x/2-p*S` | `T-w_x/2-p*T` |
| Short | `bid*(1-p)` | `S+w_x/2+p*S` | `T+w_x/2+p*T` |

With direction `d=+1/-1`, define planning distance `D_m=d*(M-S)>0`, `loss=d*(F_e-F_s)+f*(F_e+F_s)`, and `gain=d*(F_t-F_e)-f*(F_e+F_t)`. Require positive prices/loss/gain, **`gain/loss >=1.8`**, and `max(loss-D_m, d*(T-M)-gain) <=0.25*D_m`. Add any separately declared funding/impact exactly once before checking. Execution-price spread/slippage are already embedded and must not be deducted twice. Realized gaps can exceed this estimate.

After an admitted paper fill, separately freeze `D_entry=abs(actual_entry_fill-S)` for outcome R and excursion ratios, consistent with C09. Do not substitute midpoint distance, reference-close distance or all-in stopped loss for that denominator. Quantity sizing still budgets the all-in stopped loss.

### Event and funding exposure

The strict qualified profile requires versioned official FOMC decision/press-conference, CPI and Employment Situation schedules plus a declared coverage interval, refreshed within 24h. CPI/employment blackout is `[event-30m,event+30m)`; FOMC decision and press conference each use `[event-30m,event+60m)`, merged when overlapping. Convert source timezone with daylight-saving rules. A known event date without a verified time blocks that whole source-local calendar date converted to UTC, possibly spanning two UTC dates; unknown timezone blocks qualification. Missing coverage is unknown, not an empty calendar.

No entry whose maximum holding interval intersects a known blackout. An event revision learned after entry requests an exit before the newly known blackout, or immediately if it has begun; it cannot change past results. Unexpected news is not predictable from this calendar and remains gap/shock risk.

No entry if an observed next funding settlement is at/before `entry_time+maximum_hold+5m`, or if that schedule observation is unknown. Never hard-code eight-hour funding. Unexpected interval changes/held exposure are still reconciled through C06; missing/ambiguous funding keeps the net outcome unknown.

### Position exit policy for later paper/outcome work

Fixed structural stop, one fixed target, **no partial exits, averaging down, stop widening, break-even move or trailing stop** in v1. Maximum hold: range sweep **2h**; trend sweep, EMA rejection and retest **3h**, measured from admitted entry. At 60 minutes, request exit if observed MFE is `<0.5*D_entry`; MFE is the maximum of zero and the observed direction-adjusted contract-price excursion from actual entry since admission. Unavailable path evidence cannot be treated as a measured MFE.

Exit at the first executable observation after a family invalidation close or a confirmed hourly state outside the entry mode; range sweeps also invalidate if the frozen box is no longer a valid current healthy range. Two consecutive execution-bar dull flags request exit; a shock requests exit immediately when observed. Already active protective stops/targets retain priority over later discretionary/time exit requests. No reverse entry on that same bar.

Deterministic precedence at a shared observed time: existing stop → existing target → data/event/shock/family/state exit request → stall/time exit. If both protective levels are reachable in an unresolved post-entry candle, a separately labeled coarse sensitivity uses stop-first and flags ambiguity; it is not a mature path-evidenced outcome. The strict outcome remains unresolved until finer evidence establishes order, consistent with current C09. A candle straddling entry cannot establish which extremes occurred after the fill. Missing stop-path/exit observations remain unresolved; never book an invented flat position during an outage. Stops use declared contract-price trigger semantics, not a silent switch to mark price.

## 6. Overlap, cooldown and risk containment

### Mandatory observation controls

- At most one qualified bundle per instrument/direction/confirmation bar. Tags retain every matched family, but the primary plan is chosen in fixed order: **sweep → retest → EMA rejection**. Use the primary plan's levels; do not blend stops/targets. Primary selection is a policy to validate, not a confidence score.
- Opposite qualified directions for the same instrument/bar suppress both with `direction_conflict`. No follow-up choice based on later price.
- After a qualified bundle is published, the next confirmation for that instrument must end no earlier than the previous confirmation end plus four execution intervals (60 minutes), across families/sessions. A successful send is not required to consume cooldown. Stop/target invalidation updates are not new entry alerts.
- Maximum three qualified bundles per family/instrument/UTC day; overlapping tags each consume their family slot. The day ledger and consumed level attempts are workspace-wide across sessions so restarting/renaming cannot reset them. Historical scans have isolated diagnostic state and never consume the live ledger.
- Apply bundle controls after fixed overlap selection. If any retained family tag has exhausted its daily allowance, suppress the entire bundle; do not remove that tag or choose another primary to evade the cap. Only a durably published qualified bundle increments the bundle counters; seeded attempts remain consumed even when publication is blocked.
- An EMA touch episode also requires its own eight-bar separation/rearm rule. There is no fallback family/direction when a gate blocks a plan.

### Mandatory policy for evaluated pilot paper capital

These constraints apply when producing a paper account/outcomes, not as fabricated balances/loss counts on the quick page. No account connection is required merely to observe patterns.

| Limit | Proposed frozen research policy |
| --- | --- |
| Initial paper capital | Explicitly supplied at experiment registration; fixed before results |
| Per-entry risk | At most 0.25% of marked equity, **including modeled stopped-exit fees/slippage** |
| Size | Round quantity down to exchange steps; reject below minimum/notional; never round up to make a trade eligible |
| Exposure | One position/pending admission per instrument, at most two total, all BTC/ETH in one correlation group, total reserved loss risk <=0.50% equity, gross notional <=equity (1x) |
| Repetition | Two stopped/negative completed trades for a family/instrument in one UTC day pause that family/instrument through day end |
| Session loss | Three consecutive negative completed trades pause new entries for the rest of the UTC day |
| Equity loss | Daily marked loss >=1% from UTC start equity or weekly marked loss >=3% from Monday start equity pauses new entries until the next corresponding boundary |
| Campaign drawdown | Peak-to-current marked drawdown >=6% halts the campaign; review/new frozen campaign required |

Per-unit quantity budget uses C07's prospective stopped loss, not just price distance; check size impact and iterate downward over admissible exchange quantities. Unresolved exposure retains its risk reserve. Equity/time-boundary resets do not release existing risk or erase losses. Loss limits stop new entries; existing positions retain their exits. Gap losses can overshoot these thresholds, and quick observations cannot enforce a human's actual account risk.

Replay inputs in `(available_ms,event_id)` order. For each input, process existing-position protective actions and ledger changes actually known at that prefix before considering new admissions; an unfilled exit does not release risk. Simultaneous eligible admissions within that input use lexical instrument ID, then the fixed family priority, then setup ID. Never select the more profitable later candidate or assign each family a separate wallet to evade shared limits.

## 7. Planned quick-flow integration and observable reasons

Preserve the existing simple form. Proposed IDs are `liquidity_sweep_v1`, `ema200_rejection_v1`, `key_level_retest_v1`; they are **not currently registered**. Allow selection together; do not require C14 multi-model deployment to watch them. Record sweep's range/trend mode separately.

Before implementation, resolve these concrete gaps as part of the build:

- Shared ER/cross-count/percentile, regime persistence, range qualification, level freshness/touch and state-machine definitions are new. Existing C04 is continuous context; it does not already implement this classifier.
- Prepare at least **1587 contiguous 15m and 1587 contiguous 1h bars**, plus scan history/tails and a safety margin. The latter is about 66.1 days of warm-up. Current 500-bar live/420-extra historical preparation and 2000-bar retention are insufficient for all requested scans. Do not load 66 days of minutes into the feed's 15000-record cache. Design durable feature/context checkpoints and separate plotting retention, without changing seeds to force readiness.
- Native bootstrap and C02 live minute aggregates must share formulas while retaining modeled versus recorded provenance. Hourly context must be assembled/updated automatically, including simultaneous-close ordering. Repair restores current context but does not replay missed entry notifications.
- Automatically acquire quotes, sequence-checked contract trades, instrument status/rules, marks/next funding and official calendar coverage needed by strict qualification. The current quick feed subscribes only to candles. Account fees remain explicitly assumed unless separately evidenced. Pattern-only history stays useful when execution evidence is absent.
- Extend shared C08 contracts/predicates and the analysis adapter together; frontend names/descriptions/readiness are currently a local two-family map. C05 zone aging/touch policies and arbitrary structural C09 stops/targets also need implementation; current prerequisites do not provide every policy above.
- Save seed/confirmation clocks, full feature/level/version IDs, regime raw/active history, veto reasons, target barriers, cost assumptions/estimate, conditional entry band, expiry and overlap tags. Persist unfinished state/consumed attempts/cooldowns or rebuild deterministically from pinned evidence after restart. Data repair/corrections cannot create a retroactive live signal.
- Proposed notification remains `SETUP OBSERVATION / UNVALIDATED PLAN`, with mode, context, conditional entry band, frozen invalidation/target and expiry, plus cost-assumption and risk-scope disclosure. Do not claim actual fills, win probability or execution approval. Current message formatting does not yet carry this plan.

Core reasons include `warmup`, `missing_context`, `unstable_feature`, `dull`, `shock_cooldown`, `transition`, `wrong_direction`, `range_middle`, `range_unproven`, `exhausted_level`, `level_unknown_at_approach`, `accepted_break_not_sweep`, `reclaim_failed`, `early_retest`, `late_retest`, `repeated_touch`, `no_room`, `cost_too_large`, `net_rr_low`, `quote_stale`, `calendar_unknown`, `event_window`, `funding_window`, `late_detection`, `drift`, `correction`, `opportunity_consumed`, `overlap`, `cooldown`, `risk_pause`, `path_unknown`. Retain complete denominators and reasons; quiet conditions must be inspectable.

## 8. Evidence and design limits

This is an original, untested rule proposal. Research on FX order clustering supports investigating reactions near levels, while research on stop cascades also explains why blindly fading a breach can be dangerous. Neither validates these crypto thresholds or EMA200. See [New York Fed level research](https://www.newyorkfed.org/research/staff_reports/sr125.html) and [stop-cascade research](https://www.newyorkfed.org/research/staff_reports/sr150.html).

Source contracts: [Binance futures market data/rules](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data), official [FOMC calendars](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm), [CPI schedule](https://www.bls.gov/schedule/news_release/cpi.htm), and [Employment Situation schedule](https://www.bls.gov/schedule/news_release/empsit.htm), checked 1 November 2026. These support source semantics/calendar inputs, not the numerical trading gates.

The validation plan must count repeated search, rejected variants, unknown outcomes and every active mode. A strong trend result cannot compensate for an untested or destructive range mode. See [backtest-overfitting research](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) and [the explicit validation gates](PILOT_EDGE_CASES_AND_VALIDATION.md).
