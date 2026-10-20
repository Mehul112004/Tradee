"""Fixed-look diagnostic block intervals; no IID per-trade significance claims."""
from decimal import Decimal
from fractions import Fraction
from random import Random
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c06.contracts import decimal_text
from tradee.c07.math import exact,ratio
from tradee.c10.statistics import circular_indices
from tradee.c12.statistics import percentile


def review(rows,policy,start_ms,deadline_ms):
    """Cumulative admitted-paper forecast residuals, known at a fixed deadline.

    The entire candidate cohort must have mature labels. Dropping unresolved
    admissions can preferentially omit losses. Related assets move together.
    """
    selected=[r for r in rows if r['track']=='portfolio' and r['detected_ms']<deadline_ms]
    reasons=[]; eligible=[r for r in selected if r['status']=='mature' and r['decision_recorded_before_outcome'] and r['predicted_mean_net_r'] is not None]
    if len(eligible)!=len(selected): reasons.append('incomplete_or_nonprospective_admitted_cohort')
    if len(eligible)<policy.min_mature: reasons.append('insufficient_mature_admissions')
    origin=start_ms//policy.bin_ms*policy.bin_ms
    bins=(deadline_ms-origin+policy.bin_ms-1)//policy.bin_ms
    if bins<=0 or bins>policy.max_bins or bins*policy.bootstrap_replicates>policy.max_work: raise ValidationError('C15 statistical work budget exceeded')
    sums=[Decimal(0)]*bins; net_sums=[Decimal(0)]*bins; counts=[0]*bins; residuals=[]; net_values=[]; max_span=0
    with exact():
        for row in eligible:
            i=(row['detected_ms']-origin)//policy.bin_ms
            if not 0<=i<bins: raise ValidationError('Forward row outside frozen observation window')
            residual=Decimal(row['net_r'])-Decimal(row['predicted_mean_net_r'])
            sums[i]+=residual; counts[i]+=1; residuals.append(residual)
            net=Decimal(row['net_r']); net_sums[i]+=net; net_values.append(net)
            max_span=max(max_span,row['label_end_ms']-row['label_start_ms'])
    occupied=len({i//policy.block_bins for i,n in enumerate(counts) if n})
    if occupied<policy.min_occupied_spans: reasons.append('insufficient_occupied_time_spans')
    if bins<=policy.block_bins: reasons.append('block_covers_observation_window')
    if max_span>policy.bin_ms*policy.block_bins: reasons.append('block_shorter_than_label_span')
    if len(set(residuals))<2 or len(set(net_values))<2: reasons.append('degenerate_residuals_or_net_outcomes')
    lower=upper=net_lower=net_upper=draw_hash=None
    tail=Fraction(policy.alpha)/(4*len(policy.review_times_ms))
    with exact():
        mean=ratio(sum(residuals,Decimal(0)),Decimal(len(residuals)))
        mean_net=ratio(sum(net_values,Decimal(0)),Decimal(len(net_values)))
        if not reasons:
            rng=Random(policy.seed); samples=[]; net_samples=[]; draw_hash=fingerprint([]); empty=0
            for _ in range(policy.bootstrap_replicates):
                indices=circular_indices(bins,policy.block_bins,rng); draw_hash=fingerprint([draw_hash,indices])
                n=sum(counts[i] for i in indices)
                if not n: empty+=1; continue
                samples.append(Decimal(ratio(sum((sums[i] for i in indices),Decimal(0)),Decimal(n))))
                net_samples.append(Decimal(ratio(sum((net_sums[i] for i in indices),Decimal(0)),Decimal(n))))
            if empty or len(set(samples))<2 or len(set(net_samples))<2: reasons.append('empty_or_degenerate_resampling')
            else:
                lower=percentile(samples,tail); upper=percentile(samples,1-tail)
                net_lower=percentile(net_samples,tail); net_upper=percentile(net_samples,1-tail)
    triggers=[]
    if not reasons:
        if Decimal(upper)<-Decimal(policy.residual_tolerance_r): triggers.append('forecast_residual_degradation')
        if Decimal(net_upper)<Decimal(policy.net_mean_floor_r): triggers.append('mean_net_r_below_floor')
    degraded=bool(triggers)
    return dict(deadline_ms=deadline_ms,status='insufficient_evidence' if reasons else 'degraded' if degraded else 'no_degradation_detected',
                reasons=reasons,admitted=len(selected),usable_mature=len(eligible),occupied_spans=occupied,
                mean_forecast_residual_r=mean,lower=lower,upper=upper,mean_net_r=mean_net,net_lower=net_lower,net_upper=net_upper,
                degraded=degraded,degradation_reasons=triggers,draw_manifest_hash=draw_hash,
                family_looks=len(policy.review_times_ms),family_statistics=2,tail_fraction=f'{tail.numerator}/{tail.denominator}',
                method='paired circular calendar-block percentile intervals of admitted paper mean net R and mean(net R - frozen C10 forecast)',
                limitations='Approximate intervals assume representative blocks and weak/stable dependence. Finite-look tail allocation does not fix invalid intervals, selective reporting or adaptive policy reuse. No profitability/promotion conclusion.')
