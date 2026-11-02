# EMA200 rejection v1: first controlled trend pullback

**Proposed design only — 2 November 2026.** No implementation or evidence of an EMA200 edge. Period 200 and all thresholds are predeclared research conventions, not a guarantee that an average acts as support/resistance.

All [shared rules](PILOT_STRATEGY_DESIGN.md) apply. Proposed family ID: `ema200_rejection_v1`. This version trades rejection in an established hourly trend; reversal against that trend is excluded.

## 1. Arm only after separation

For a long, require active `TREND_UP`, current execution EMA200 five-bar slope `>=0.01` ATR/bar and `crosses32<=2`. For a short use `TREND_DOWN`, slope `<=-0.01` and the same crossing limit.

Before seed s, require **eight consecutive completed execution bars**, each with close at least `0.10*its ATR14` on the intended side of **its then-known EMA200**. Each of their full ranges must stay outside the moving touch band `EMA200_i ± max(0.15*ATR14[i-1],2*ticks)` on that same side. At least one close must have been at least `0.75*its ATR14` from its EMA200. All analytical values must be stable and available at those historical evaluation points.

This is a first return after observed separation. Resting on a flat EMA, repeated oscillations, and a fresh cross from the wrong side cannot arm. Do not retroactively substitute today's EMA into those eight historical comparisons.

## 2. Freeze the reference, then require rejection

On seed evaluation freeze the pre-seed references `E=EMA200[s-1]`, `A=ATR14[s-1]`, and `z_E=max(0.15*A,2*ticks)`. Their indices exclude s, and the inputs must actually be available at the closed-bar decision. This does not assume zero-latency delivery at s open. E is a moving-average reference frozen for this short attempt, not a C05 swing.

The first band intersection after arming consumes the touch episode regardless of wick, body or volume quality. A weak/deep first touch fails that episode; the detector cannot wait for a prettier second touch. If health/context fails at that first encounter, return to unarmed and require a fresh separation sequence.

| Condition | Long | Short |
| --- | --- | --- |
| Seed intersects touch band | `L_s<=E+z_E` and `H_s>=E-z_E` | Same intersection |
| Controlled penetration | `L_s>=E-0.35*A` | `H_s<=E+0.35*A` |
| Seed rejection wick | Lower wick fraction `>=0.30` | Upper wick fraction `>=0.30` |
| Seed range | Positive and `TR_s<=2.5*A` | Same |
| Confirmation relative to frozen E | `C_c>=E+z_E` | `C_c<=E-z_E` |
| Confirmation relative to current EMA | `C_c>=EMA200[c]+b` | `C_c<=EMA200[c]-b` |
| Confirmation strength | Shared bullish body/CLV, `RV_c>=1.0` | Shared bearish body/CLV, `RV_c>=1.0` |

Confirm on s if every condition passes. Otherwise allow only s+1, which must also close `>H_s+b` long / `<L_s-b` short. Penetration across the whole attempt must remain within 0.35A. A close beyond the frozen EMA by b on the wrong side, a context change, or `abs(EMA200[c]-E)>0.15*A` cancels before confirmation. There is no moving the frozen band to chase a failed touch.

Both the seed's and the confirmation's shared dull/shock gates must pass. A large, volume-heavy candle immediately after dull chop does not override the quiet-seed veto. Hourly trend and execution slope/cross count are rechecked at confirmation and entry assessment.

## 3. Entry, fixed risk and exit

Long stop is `min(L_s..L_c)-stop_buffer`; short stop is `max(H_s..H_c)+stop_buffer`, adversely rounded. Apply shared D0, room, cost and entry-window constraints. Desired target distance from P0 is `2.5*D0`, capped before a known opposing previous-day/swing barrier; require the final net ratio `>=1.8`. A nearby resistance directly over an EMA bounce is a rejection reason, not an invitation to assume a breakout.

Pending/entered long invalidates on an execution close `<=EMA200_current-b`; short on `>=EMA200_current+b`. Use A frozen at the seed for b, and the currently available stable EMA for this future close comparison. This is a prospective invalidation action, not a stop rewrite. Hourly state failure, shock, two dull flags, stall and time exits follow the shared policy. Maximum hold is 3h; no partial, trailing or automatic break-even rule.

Only one attempt per touch episode. After any seed, success or failure, the instrument/direction cannot rearm until it has a fresh **eight-bar separation sequence** satisfying section 1. It also obeys the shared four-bar qualified-observation cooldown and three-bundle daily family cap. A closed candle touching the band again during this separation restarts that separation count at zero.

## 4. State transitions

| State | Event | Result |
| --- | --- | --- |
| `UNARMED` | Eight valid separation bars and allowed trend | `ARMED` |
| `ARMED` | First band intersection | Freeze E/A/context; consume touch episode; `TOUCHED` if geometry/health permit, otherwise fail the episode |
| `ARMED` | Trend/health failure | `UNARMED`; establish separation again |
| `TOUCHED` | s or s+1 confirms all conditions | `CONFIRMED`; shared qualification and conditional entry apply |
| `TOUCHED` | Deep penetration, wrong close, moving-reference drift, changed state/data, correction or second-bar deadline | Terminal failure of this episode; return to `UNARMED` |
| `CONFIRMED` | Drift/expiry/invalidation or costs/room fail | No entry; no replacement anchor for the same episode |

Unfilled/expired plans and notification failure do not grant a second attempt. After a software restart, either restore the same evidence-qualified state or rebuild from available history with missed opportunities notification-suppressed. Never start `ARMED` merely because price is currently near EMA200.

## 5. Worked geometry and failure examples

With valid hourly uptrend/separation, tick 0.01, frozen E=100 and A=1, take `O=100.50,H=101.00,L=99.85,C=100.90`, RV=1.10. It intersects E±0.15, penetrates only 0.15A, lower wick is 0.65/1.15, body is 0.40A and CLV is about 0.913. If current EMA=100.02 with adequate slope, same-bar confirmation passes. S=99.70, D0=1.20, desired T=103.90 before barriers. Entry and modeled net RR still require separate checks.

The mirrored short has E=100, `O=99.50,H=100.15,L=99.00,C=99.10`; with valid downtrend, separation and volume it gives S=100.30, D0=1.20, desired T=96.10 before barriers.

Reject the same shapes when the hourly state is range/transition, the EMA is flat, crossing count exceeds two, there was a recent touch without eight clean separation bars, penetration is too deep, confirmation lacks body/volume, the stop is too tight after rounding, a closer barrier ruins net room, or source data cannot establish the approach. A wick at EMA200 is not sufficient by itself.

## 6. Validation focus

Report first-return episodes versus repeated-touch exclusions and all opportunities lost to context/cost gates. Compare with the same EMA touch/rejection shape without regime/exhaustion filters, using common data/costs. Trend gains do not establish range safety: verify zero **new** qualified entries in disallowed range/dull states, and separately mark any carried position loss after its trend changes. Apply [the validation gates](PILOT_EDGE_CASES_AND_VALIDATION.md).
