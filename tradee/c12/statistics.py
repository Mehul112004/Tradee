"""Joint calendar blocks of independent-signal utility, never portfolio returns."""
from collections import Counter
from decimal import Decimal
from random import Random
from fractions import Fraction
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c06.contracts import decimal_text
from tradee.c07.math import exact, ratio
from tradee.c10.statistics import circular_indices


def percentile(values, probability):
    rank=-(-(len(values)*probability.numerator)//probability.denominator)
    return decimal_text(sorted(values)[max(0, min(len(values)-1, rank-1))])


def evidence(rows, policy, trials, windows=None):
    """An abstention has zero selected utility; an unknown selected label is not zero."""
    if type(trials) is not int or trials<1: raise ValidationError('Positive declared trial budget required')
    tail=Fraction(policy.alpha)/(2*trials)
    if policy.bootstrap_replicates*tail<1: raise ValidationError('Too few draws to resolve family-adjusted tail')
    bounds=[] if windows is None else sorted((w['start_ms'],w['end_ms']) for w in windows)
    if windows is not None and (not bounds or any(type(a) is not int or type(b) is not int or a>=b for a,b in bounds) or any(bounds[i][0]<bounds[i-1][1] for i in range(1,len(bounds)))):
        raise ValidationError('Disjoint nonempty declared evaluation windows required')
    counts=Counter(); groups={}; leave={}; reasons=[]; identities=set()
    for r in rows:
        if bounds and not any(a<=r['detected_ms']<b for a,b in bounds): raise ValidationError('Opportunity outside declared evaluation ownership')
        key=(r['protocol_hash'], r['candidate_id'])
        if key in identities: raise ValidationError('Duplicate outer opportunity ownership')
        identities.add(key)
        counts['candidates']+=1; counts['estimated']+=int(r['prediction']['ready'])
        if r['prediction']['eligible']:
            counts['eligible']+=1
            counts['eligible_mature' if r['outcome_status']=='mature' else 'eligible_unknown']+=1
    if counts['candidates']<policy.min_candidates: reasons.append('insufficient_candidates')
    if counts['eligible_mature']<policy.min_eligible_mature: reasons.append('insufficient_eligible_mature')
    if counts['eligible_unknown']: reasons.append('selected_outcomes_unresolved_or_unfilled')
    with exact():
        if counts['estimated']<Decimal(policy.min_estimated_fraction)*counts['candidates']: reasons.append('insufficient_estimated_coverage')
    if not rows: reasons.append('empty_evaluation')
    values=[]; max_span=0; lower=upper=None; draws=None; occupied=0; bins=0
    with exact():
        if rows:
            start=bounds[0][0] if bounds else min(r['detected_ms'] for r in rows)
            end=bounds[-1][1] if bounds else max(r['detected_ms'] for r in rows)+1
            origin=start//policy.bin_ms*policy.bin_ms
            bins=(end-origin+policy.bin_ms-1)//policy.bin_ms
            if bins>policy.max_bins or bins*policy.bootstrap_replicates>policy.max_work: raise ValidationError('C12 time-block work budget exceeded')
            sums=[Decimal(0)]*bins; denominators=[0]*bins; selected_bins=set()
            for r in rows:
                i=(r['detected_ms']-origin)//policy.bin_ms; denominators[i]+=1
                value=None
                if r['prediction']['eligible'] and r['outcome_status']=='mature':
                    value=Decimal(r['net_r']); sums[i]+=value; values.append(value); selected_bins.add(i)
                    if r['label_start_ms'] is not None and r['label_end_ms'] is not None:
                        max_span=max(max_span,r['label_end_ms']-r['label_start_ms'])
                for typ,key in (('symbol',r['symbol']),('fold',r['fold']),('period',str(i//policy.block_bins))):
                    g=groups.setdefault(typ,{}).setdefault(key,dict(candidates=0,eligible_mature=0,net=Decimal(0)))
                    g['candidates']+=1
                    if value is not None: g['eligible_mature']+=1; g['net']+=value
            occupied=len({i//policy.block_bins for i in selected_bins})
            if occupied<policy.min_occupied_spans: reasons.append('insufficient_independent_time_spans')
            if bins<=policy.block_bins: reasons.append('block_covers_evaluation_span')
            if policy.block_bins*policy.bin_ms<max_span: reasons.append('block_shorter_than_selected_label_span')
            if len(set(values))<2: reasons.append('degenerate_selected_outcomes')
            total=sum(sums,Decimal(0)); denominator=sum(denominators)
            utility=ratio(total,Decimal(denominator)) if not counts['eligible_unknown'] else None
            for typ,items in groups.items():
                leave[typ]=[]
                for key,g in sorted(items.items()):
                    d=denominator-g['candidates']; rest=total-g['net']
                    leave[typ].append(dict(excluded=key,remaining_candidates=d,utility_r_per_candidate=ratio(rest,Decimal(d)) if d and not counts['eligible_unknown'] else None))
                    g['utility_r_per_candidate']=ratio(g.pop('net'),Decimal(g['candidates'])) if not counts['eligible_unknown'] else None
                    g.pop('net',None)
            if policy.require_leave_group_positive:
                checks=[x['utility_r_per_candidate'] for typ in ('period','symbol') for x in leave.get(typ,[]) if x['remaining_candidates']]
                if not checks or any(x is None or Decimal(x)<=Decimal(policy.lower_bound_buffer_r) for x in checks):
                    reasons.append('leave_period_or_asset_out_not_positive')
            if not reasons:
                rng=Random(policy.seed); samples=[]; empty=0; draws=fingerprint([])
                for _ in range(policy.bootstrap_replicates):
                    indices=circular_indices(bins,policy.block_bins,rng); draws=fingerprint([draws,indices]); n=sum(denominators[i] for i in indices)
                    if not n: empty+=1; continue
                    samples.append(Decimal(ratio(sum((sums[i] for i in indices),Decimal(0)),Decimal(n))))
                if empty or len(set(samples))<2: reasons.append('empty_or_degenerate_resampling')
                else: lower=percentile(samples,tail); upper=percentile(samples,1-tail)
        else: utility=None
        if lower is not None and Decimal(lower)<=Decimal(policy.lower_bound_buffer_r): reasons.append('family_adjusted_lower_bound_not_positive')
        return dict(ready=not reasons,reasons=reasons,coverage=dict(counts),utility_r_per_candidate=utility,
                    mean_eligible_mature_r=ratio(sum(values,Decimal(0)),Decimal(len(values))) if not counts['eligible_unknown'] else None,
                    uncertainty=dict(method='joint circular calendar-block percentile bootstrap: selected net R / all candidate opportunities',
                        family_trial_budget=trials,alpha=policy.alpha,tail_probability=ratio(Decimal(tail.numerator),Decimal(tail.denominator)),tail_fraction=f'{tail.numerator}/{tail.denominator}',
                        lower=lower,upper=upper,draw_manifest_hash=draws,replicates=policy.bootstrap_replicates,
                        calendar_bins=bins,declared_windows_ms=[list(w) for w in bounds],occupied_nonoverlapping_spans=occupied,max_selected_label_span_ms=max_span),
                    groups=groups,leave_group_out=leave,
                    limitations='Independent signal utility, not capital returns. Bonferroni tail allocation is conditional on valid block-bootstrap intervals and declared trial accounting; it does not repair adaptive data reuse. Weak/stable dependence and representative time blocks are assumptions. No Sharpe, DSR or PBO on irregular trade R.')
