# Key-level retest v1: accepted break, then a distinct first retest

**Proposed design only — 2 November 2026.** No implementation or proven breakout edge. All [shared rules](PILOT_STRATEGY_DESIGN.md) apply. Proposed family ID: `key_level_retest_v1`.

This version is trend continuation. It does not trade an arbitrary line touch, the middle of a range, or the first uncertain breakout from range into a new regime. The price must establish acceptance before a later retest.

## 1. Define “key” and the pre-break side

Long seeds use a known, unexpired previous-day **high** or confirmed 15m swing **high** X acting as resistance, in active hourly `TREND_UP`. Shorts use a previous-day **low** or confirmed 15m swing **low** acting as support, in `TREND_DOWN`. Apply common known-time, touch count, age and deterministic reference priority. No discretionary lines, inferred order blocks, previous-week seeds or automatic pivot merging.

Before breakout seed b0, the three immediately preceding execution closes must be `<X-b` long / `>X+b` short. X must have been known by the open of all three approach bars. Reject if the shared behavioral ledger already records an accepted break in the intended direction after X's structural confirmation/publication; this is not a second/third retest of an old breakout. Require execution `crosses32<=2` and confirmation on the intended side of its stable EMA200 by at least b.

That prior-break exclusion is evaluated on knowledge before b0. Acceptance created by this attempt's b0/b1 is required for its later retest and does not invalidate the attempt itself.

Freeze A, b, level X/version, original zone `X±z` and hourly context at b0. The shared `0.5<=A/A_L<=2` rule limits old zones under changed volatility.

## 2. Break, acceptance and retest rules

| Stage | Long | Short |
| --- | --- | --- |
| Breakout b0 | `C_b0>=X+0.25*A`; `C-O>=0.50*A`; `CLV>=0.75`; `RV>=1.20`; `TR<=2.5*A` | `C_b0<=X-0.25*A`; `O-C>=0.50*A`; `CLV<=0.25`; same RV/range |
| Acceptance b1, immediately next bar | `C_b1>=X+b` and `L_b1>X+z` | `C_b1<=X-b` and `H_b1<X-z` |
| First retest r | Range intersects `X±z`, with `L_r>=X-0.50*A` | Same intersection, with `H_r<=X+0.50*A` |
| Confirmation c | `C_c>=X+max(0.20*A,b)` plus shared bullish body/CLV and `RV>=1.0` | `C_c<=X-max(0.20*A,b)` plus shared bearish body/CLV and `RV>=1.0` |

For a breakout, meeting both the 0.25A distance and b buffer is required: if `b>0.25*A` due to ticks, use the larger distance. A zero-range bar cannot pass. Acceptance b1 need not have a same-direction body; it must remain entirely outside the zone and close with acceptance. If b1 touches the zone, reject as **early retest** rather than decide after the fact that break/accept/retest happened in a favorable intrabar order.

Only the first zone encounter on bars **b0+2 through b0+6 inclusive** is eligible. No retest within that window means expired opportunity. Before that touch, every intervening close must stay on the accepted side by b. Any observed favorable close extension more than **2A from X** before r cancels as `extended_before_retest`; no waiting for a late exhausted return. All intermediate bars must be complete and all context/health gates remain valid.

Confirm on r if it passes the table. Otherwise allow only r+1, which must additionally close `>H_r+b` long / `<L_r-b` short. Deep penetration limits apply across r..c. Any close back through X by b on the wrong side cancels: long `C<=X-b`; short `C>=X+b`. There can be no additional separated touch episode before confirmation. The latest possible confirmation is b0+7. A failed retest is not automatically converted to a sweep/reversal.

## 3. Entry, structural stop and exits

For a long, S=`min(L_r..L_c)-stop_buffer`; for a short, S=`max(H_r..H_c)+stop_buffer`, with adverse tick rounding. The initial breakout extreme is not used to justify an arbitrarily wide stop. Apply common `0.75*A..2.5*A`, ten-tick, target-room, modeled cost and net RR rules.

Desired target distance from P0 is the shared fixed `2.5*D0`, shortened before a nearer eligible opposing obstacle. No assumption of unlimited trend continuation. Conditional entry is after confirmation and reaction delay, within the shared drift/expiry band. Once a breakout has already traveled past the planned target before an entry assessment, the original plan is canceled, not re-anchored.

The trade invalidates on a later long close `<=X-b` / short close `>=X+b`, hourly state failure, shock/dull/stall/time conditions, or structural stop. Maximum hold is 3h. No target extension to recover fees, no averaging a failed level, no same-bar reverse. One break/retest attempt per level/direction/day is consumed at b0, whether or not acceptance, retest or entry follows.

## 4. State transitions

| State | Event | Result |
| --- | --- | --- |
| `AVAILABLE` | Eligible directional break b0 | Consume attempt; freeze evidence; `BREAK_SEEN` |
| `BREAK_SEEN` | Immediate b1 fully accepts without touching zone | `WAIT_FIRST_RETEST` |
| `BREAK_SEEN` | Wrong close, zone touch, weak/unknown acceptance, context failure or missing b1 | Terminal failure |
| `WAIT_FIRST_RETEST` | First eligible touch on b0+2..b0+6 | `RETEST_SEEN` |
| `WAIT_FIRST_RETEST` | Deadline, pre-touch extension >2A, lost acceptance, correction/rollover or common veto | Terminal failure/expiry |
| `RETEST_SEEN` | r or r+1 confirms | `CONFIRMED`; common qualification applies |
| `RETEST_SEEN` | Deep/wrong close, second episode, context failure or no confirmation by r+1 | Terminal failure |
| `CONFIRMED` | Entry delay/rechecks pass | Paper admission may occur; observation is not a fill |

All wait states are tied to bar IDs, availability prefix and the selected level version. Missing bars cannot be skipped to preserve the numbered sequence. A restart/repair cannot restart the retest window or announce an old confirmation.

## 5. Worked geometry and failure examples

Assume X=100, A=A_L=1, tick 0.01, z=0.10, correct approach and hourly uptrend. Break b0: `O=99.70,H=101.00,L=99.60,C=100.80`, RV=1.30. Acceptance b1: `O=100.80,H=101.30,L=100.30,C=101.00`; its entire range stays above 100.10. First retest b0+2: `O=100.70,H=101.10,L=99.90,C=100.95`, RV=1.10. It touches the zone, penetrates only 0.10A, body is 0.25A and CLV=0.875. Same-bar rejection confirms; S=99.75, D0=1.20, desired T=103.95 before barriers. Quote/cost/event/entry checks are still required.

Mirrored short: b0 `O=100.30,H=100.40,L=99.00,C=99.20`; b1 `O=99.20,H=99.70,L=98.70,C=99.00`; r `O=99.30,H=100.10,L=98.90,C=99.05`. With equivalent downtrend, volume and other gates, S=100.25 and desired T=96.05.

Reject: a breakout wick with no close; one close that immediately falls back; acceptance bar touching the level; retest on b0+7; second/third retest; large extension before return; range/transition context; a retest with poor net room; a close fully through the zone; missing interval; and a source/level revision during the wait. Repeated fake breakouts must not create an unlimited sequence of small losses.

## 6. Validation focus

Count the entire funnel: eligible levels → breaks → acceptance → first retests → confirmations → qualified plans → actual modeled entries → mature outcomes. Distinguish expiration, failed acceptance, exhaustion and missing evidence from losses. Compare one-close breakouts, raw first-retest geometry, and this full policy only as predeclared counted variants. Include regime transitions after entry and all costs; see [validation](PILOT_EDGE_CASES_AND_VALIDATION.md).
