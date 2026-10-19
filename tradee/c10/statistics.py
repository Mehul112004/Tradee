"""Exact descriptive R statistics and synchronized circular calendar-block bootstrap."""
from collections import Counter
from decimal import Decimal,ROUND_CEILING
from random import Random
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c06.contracts import decimal_text
from tradee.c07.math import exact,ratio


def quantile(values,p):
    if not values: return None
    with exact(): rank=int((Decimal(len(values))*Decimal(str(p))).to_integral_value(rounding=ROUND_CEILING))
    return decimal_text(sorted(values)[max(0,min(len(values)-1,rank-1))])


def circular_indices(size,length,rng):
    indices=[]
    while len(indices)<size:
        start=rng.randrange(size)
        indices.extend((start+k)%size for k in range(min(length,size-len(indices))))
    return indices


def summarize(rows,window,config):
    mature=[r for r in rows if r['status']=='mature']; n=len(mature); total=len(rows)
    bins=(window.end_ms-window.start_ms+config.bin_ms-1)//config.bin_ms
    if bins>config.max_bins: raise ValidationError('Expectancy calendar-bin budget exceeded')
    counts=[0]*bins; sums=[Decimal(0)]*bins; wins=[0]*bins
    with exact():
        values=[Decimal(r['net_r']) for r in mature]
        for r,v in zip(mature,values):
            idx=(r['detected_ms']-window.start_ms)//config.bin_ms
            if not 0<=idx<bins: raise ValidationError('Outcome outside declared training window')
            counts[idx]+=1; sums[idx]+=v; wins[idx]+=int(v>0)
        occupied=sum(c>0 for c in counts); spans=len({i//config.block_bins for i,c in enumerate(counts) if c})
        unfilled=sum(r['status']=='unfilled' for r in rows); filled=sum(r['filled'] for r in rows)
        exposed=total-unfilled
        coverage=dict(candidates=total,filled=filled,mature=n,unfilled=unfilled,unresolved=sum(r['status'] in ('unresolved','not_observed') for r in rows),
            fill_fraction=ratio(Decimal(filled),Decimal(total)),mature_fraction_of_non_unfilled=ratio(Decimal(n),Decimal(exposed)),
            calendar_bins=bins,occupied_bins=occupied,occupied_nonoverlapping_spans=spans)
        positive=[v for v in values if v>0]; negative=[v for v in values if v<0]; aggregate=sum(values,Decimal(0))
        max_span=max((r['label_end_ms']-r['label_start_ms'] for r in mature),default=0)
        events=sorted([(r['label_start_ms'],1) for r in mature]+[(r['label_end_ms'],-1) for r in mature])
        active=0; max_concurrent=0
        for _,delta in events: active+=delta; max_concurrent=max(max_concurrent,active)
        p05=None if not values else Decimal(quantile(values,'0.05'))
        stats=dict(mean_net_r=ratio(aggregate,Decimal(n)),mean_net_usdt=ratio(sum((Decimal(r['net_usdt']) for r in mature),Decimal(0)),Decimal(n)),
            empirical_positive_net_fraction=ratio(Decimal(len(positive)),Decimal(n)),mean_positive_r=ratio(sum(positive,Decimal(0)),Decimal(len(positive))),
            mean_negative_r=ratio(sum(negative,Decimal(0)),Decimal(len(negative))),
            net_r_quantiles={k:quantile(values,p) for k,p in (('p05','0.05'),('p50','0.5'),('p95','0.95'))},
            minimum_net_r=None if not values else decimal_text(min(values)),maximum_net_r=None if not values else decimal_text(max(values)),
            downside_mean_r=ratio(sum((v for v in values if v<=p05),Decimal(0)),Decimal(sum(v<=p05 for v in values))) if values else None,
            max_label_span_ms=max_span,max_simultaneous_exposures=max_concurrent,
            note='Mature filled outcomes only; positive-net frequency is empirical, not a calibrated candidate probability. Tails are nearest-rank empirical order statistics.')
        reasons=[]
        if n<config.min_trades: reasons.append('insufficient_mature_trades')
        if occupied<config.min_occupied_bins: reasons.append('insufficient_occupied_time_bins')
        if spans<config.min_occupied_spans: reasons.append('insufficient_occupied_resampling_spans')
        if not total or Decimal(filled)<Decimal(config.min_fill_fraction)*total: reasons.append('insufficient_fill_coverage')
        if not exposed or Decimal(n)<Decimal(config.min_mature_fraction)*exposed: reasons.append('insufficient_mature_coverage')
        if config.block_bins>=bins: reasons.append('resampling_block_covers_training_span')
        if config.block_bins*config.bin_ms<max_span: reasons.append('resampling_block_shorter_than_label_span')
        if len(set(values))<2: reasons.append('degenerate_outcome_distribution')
        uncertainty=dict(method='circular calendar-block percentile bootstrap of sum(net R)/count',confidence_level=config.confidence_level,
            seed=config.seed,replicates_requested=config.bootstrap_replicates,replicates_used=0,empty_replicates=0,
            lower_mean_net_r=None,upper_mean_net_r=None,lower_positive_fraction=None,upper_positive_fraction=None,draw_manifest_hash=None,
            positive_fraction_uncertainty_status='not_estimated',
            assumptions='Fixed predeclared blocks, weak/stable dependence, representative earlier evidence and adequate coverage; overlapping/cross-symbol rows in each time bin move together. Not a guarantee or multiple-testing correction.')
        if not reasons:
            if bins*config.bootstrap_replicates>config.max_bootstrap_work: raise ValidationError('Expectancy bootstrap-work budget exceeded')
            rng=Random(config.seed); means=[]; proportions=[]; draw_hash=fingerprint([])
            for _ in range(config.bootstrap_replicates):
                idx=circular_indices(bins,config.block_bins,rng); draw_hash=fingerprint([draw_hash,idx]); count=sum(counts[i] for i in idx)
                if not count: continue
                means.append(Decimal(ratio(sum((sums[i] for i in idx),Decimal(0)),Decimal(count))))
                proportions.append(Decimal(ratio(Decimal(sum(wins[i] for i in idx)),Decimal(count))))
            empty=config.bootstrap_replicates-len(means); alpha=(1-Decimal(config.confidence_level))/2
            uncertainty.update(replicates_used=len(means),empty_replicates=empty,draw_manifest_hash=draw_hash)
            if not means or Decimal(empty)>Decimal(config.max_empty_replicate_fraction)*config.bootstrap_replicates:
                reasons.append('excessive_empty_bootstrap_replicates')
            elif len(set(means))<2: reasons.append('degenerate_bootstrap_distribution')
            else:
                uncertainty.update(lower_mean_net_r=quantile(means,alpha),upper_mean_net_r=quantile(means,1-alpha),
                    lower_positive_fraction=quantile(proportions,alpha) if positive and len(positive)<n else None,
                    upper_positive_fraction=quantile(proportions,1-alpha) if positive and len(positive)<n else None,
                    positive_fraction_uncertainty_status='estimated' if positive and len(positive)<n else 'unobserved_positive_or_nonpositive_class')
        return dict(status='ready' if not reasons else 'insufficient_evidence',reasons=reasons,coverage=coverage,statistics=stats,uncertainty=uncertainty,
            positive_lower_bound=not reasons and Decimal(uncertainty['lower_mean_net_r'])>Decimal(config.lower_bound_buffer_r))
