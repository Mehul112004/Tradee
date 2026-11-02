# Liquidity sweep v1: failed breach and reclaim

**Proposed design only — 2 November 2026.** No implementation or profitability claim. The name describes a price pattern around a known level; candles do not establish that resting stop orders existed or were deliberately hunted.

Read [the shared specification](PILOT_STRATEGY_DESIGN.md) first. Its gates, exact timing, cost checks, frozen levels, target selection, execution and risk policy are mandatory. Proposed family ID: `liquidity_sweep_v1`. Two mode tags are separate research hypotheses under this family: `trend_pullback` and `range_edge`.

## 1. Allowed conditions and references

Long seeds use a previous UTC day **low** or an unexpired confirmed 15m swing **low**, `X`. Short seeds use the corresponding **high**. A broken resistance becoming support belongs to retest, not this family. The level must be known before the approach, unexhausted and unconsumed for its direction/day. Apply shared deterministic reference priority if several qualify.

Exclude a low with a previously known accepted displacement below it, or a high with one above it, using the shared immutable level ledger. A later reclaim does not turn that broken reference back into a fresh sweep level.

| Mode | Long | Short |
| --- | --- | --- |
| Trend pullback | Active hourly `TREND_UP`; execution `crosses32<=2`; confirmation above current execution EMA200 by at least `b` | Active hourly `TREND_DOWN`; `crosses32<=2`; confirmation below EMA200 by at least `b` |
| Range edge | Active `HEALTHY_RANGE`; `abs(X-B_low)<=0.25*A_h`; X lies in bottom 20% of the frozen box | Active `HEALTHY_RANGE`; `abs(X-B_high)<=0.25*A_h`; X lies in top 20% of the frozen box |

Range low/high conditions mean `X<=B_low+0.20*(B_high-B_low)` / `X>=B_high-0.20*(B_high-B_low)`. The absolute boundary-distance test also limits levels outside the box. A level near the midpoint is not eligible. A trend sweep opposing the hourly trend is never allowed, even if its wick looks attractive.

## 2. Approach, probe and confirmation

At prospective seed `s`, freeze `A=ATR14[s-1]`, `b`, seed level/version and hourly context. Require three immediately preceding contiguous execution candles entirely **known after X became available**, with long closes `>X+b` / short closes `<X-b`. This establishes an approach from the intended side. No missing approach bars or start already outside the level.

| Condition | Long low sweep | Short high sweep |
| --- | --- | --- |
| Open on approach side | `O_s >=X+b` | `O_s <=X-b` |
| Probe depth | `b <=X-L_s <=0.75*A` | `b <=H_s-X <=0.75*A` |
| Seed rejection wick | `(min(O_s,C_s)-L_s)/(H_s-L_s) >=0.30` | `(H_s-max(O_s,C_s))/(H_s-L_s) >=0.30` |
| Seed range | Positive; `TR_s<=2.5*A` | Same |
| Reclaim close | `C_c>=X+b` | `C_c<=X-b` |
| Confirmation body/CLV/RV | Shared bullish confirmation and `RV_c>=1.0` | Shared bearish confirmation and `RV_c>=1.0` |

Confirmation `c` is **s or the immediately next candle s+1**. If s satisfies reclaim plus all confirmation conditions, it confirms at s close; never wait to choose a better later entry. If it does not, one additional candle is allowed and must also close `>H_s+b` for a long / `<L_s-b` for a short. It still must satisfy the reclaim, body, CLV and volume conditions. No third-candle rescue.

During that two-bar window, deepest penetration must remain `<=0.75*A`; any shock, common veto, changed/rolled level, different allowed mode, or required direction failure cancels. Two consecutive closes at least b on the breached side are an accepted break, not a late sweep. A bar probing qualifying levels on **both** sides is `dual_sweep`: reject both rather than infer the intrabar sequence. A single additional touch inside the same contiguous probe episode is allowed only within s/s+1; the two-bar lifetime still applies.

The seed consumes the level opportunity, even if the next bar fails. Current source corrections update future context but cannot manufacture a historical reclaim alert.

## 3. Entry plan, invalidation and exits

Let `P0=C_c`. For long, `S=min(L_s..L_c)-stop_buffer`; for short, `S=max(H_s..H_c)+stop_buffer`, with adverse tick rounding. Apply shared `0.75*A..2.5*A` stop-distance, modeled-cost and net-RR checks after rounding.

- **Trend mode target:** shared `2.5*D0` desired distance from P0, capped before the nearest eligible opposing obstacle.
- **Range mode target:** nearer of `2.5*D0` and the frozen midpoint distance from P0, then capped by any nearer opposing obstacle. There is no assumption that price will traverse the full range.
- **Pending invalidation:** any post-confirmation observed breach of S/T, close back beyond X by b, wrong allowed context/mode, data fault, expiry or drift violation. Long close `<=X-b` / short close `>=X+b` invalidates. The same condition requests an exit after entry.
- **No upgrade:** a range reversal is not converted into a trend runner if the range later breaks. A trend pullback is not relabeled a range trade if hourly trend fails.
- **Maximum hold:** 2h for range mode, 3h for trend mode; shared 60-minute stall rule and all other exits apply.

The conditional entry is after confirmation and modeled reaction delay. A bar that merely pierces a level produces no filled trade and no early signal while forming.

## 4. State transitions

| State | Event | Result |
| --- | --- | --- |
| `AVAILABLE` | Eligible approach and seed probe | Freeze evidence; consume level/day attempt; `PROBING` |
| `PROBING` | Same-bar reclaim/confirmation | `CONFIRMED` at s close |
| `PROBING` | No same-bar confirmation, next bar fully qualifies | `CONFIRMED` at s+1 close |
| `PROBING` | Depth, accepted break, dual sweep, context failure, correction, or no confirmation by s+1 | Terminal `REJECTED`; no rearm on same level/day |
| `CONFIRMED` | Shared room/cost/data gates pass | Qualified observation; conditional `PENDING_ENTRY` plan |
| `CONFIRMED` | Any gate unknown/fails | Saved unqualified match with reason; no Telegram |
| `PENDING_ENTRY` | Modeled entry clock, all rechecks pass | Paper policy may admit; analysis does not assume a fill |
| `PENDING_ENTRY` | Expiry/invalidation | Terminal `CANCELED/EXPIRED` |

Shared overlap/cooldown rules apply after qualification. Seed attempts cannot be reused by opening another analysis session. An already entered plan is governed by its fixed policy, never by resetting this detector.

## 5. Worked geometry and failure examples

Assume tick 0.01, `A=1`, `A_h=1.5`, healthy frozen box `[100,112]` with valid boundary pivots, and a known unconsumed low `X=100`. The last three closes are above 100.10. Seed `O=100.60,H=101.00,L=99.60,C=100.95`, RV=1.20. Probe is 0.40A, lower wick is 1.00/1.40, body is 0.35A, and CLV is about 0.964. Same-bar confirmation passes. `S=99.45`, D0=1.50 and desired T=104.70; midpoint 106 does not shorten it. A fresh executable assessment must still pass drift, modeled costs, schedules and net RR. This is geometry, not a forecasted profitable trade.

The mirrored short uses box `[88,100]`, X=100 and `O=99.40,H=100.40,L=99.00,C=99.05`; S=100.55 and desired T=95.30 before any nearer barrier. Short volume/context/cost checks remain required.

Mandatory rejection examples: same wick against a strong opposite hourly trend; active range midpoint; tiny range with insufficient net room; probe deeper than 0.75A; two accepted closes outside; weak close/body; no RV expansion; more than two prior touch episodes; dual-sided whipsaw; favorable price already beyond the allowed entry band; required source unknown. A rejected trend short at a swept high may continue much higher; the design does not treat every breach as a reversal.

## 6. Validation focus

Evaluate range-edge and trend-pullback modes separately, including longs/shorts, both symbols and transitions after entry. Compare raw sweep geometry with the full filters under identical coverage and costs. Measure missed winners as well as avoided losses. If one mode lacks independent evidence or fails net expectancy/risk limits, leave that mode disabled rather than hiding it in the family aggregate. See [the acceptance matrix](PILOT_EDGE_CASES_AND_VALIDATION.md).
