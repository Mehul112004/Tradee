"""Frozen cohort fit and inference; never reads a candidate's later outcomes."""
from copy import deepcopy
from decimal import Decimal
import platform
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c02.domain import integer
from tradee.c06.engine import code_hash
from .contracts import ExpectancyRecord,EstimatorConfig,TrainingWindow,EstimateRequest,cohort_key
from .statistics import summarize


def fit(snapshot,config):
    d=snapshot.document(); window=TrainingWindow.from_dict(d['window'])
    if d.get('kind')!='training_snapshot' or d.get('schema_version')!=1: raise ValidationError('Verified training snapshot required')
    if d.get('cohort_fields')!=list(config.cohort_fields): raise ValidationError('Fit cohort definition differs from frozen training snapshot')
    bins=(window.end_ms-window.start_ms+config.bin_ms-1)//config.bin_ms
    if bins>config.max_bins or len(d['rows'])>config.max_rows or len(d['cohorts'])>config.max_cohorts: raise ValidationError('Expectancy fit budget exceeded')
    cohorts={}; work=0
    for key,decl in sorted(d['cohorts'].items()):
        rows=[r for r in d['rows'] if r['cohort_hash']==key]
        if cohort_key(decl['protocol_hash'],decl['attributes'],config)!=key: raise ValidationError('Corrupt training cohort identity')
        result=summarize(rows,window,config)
        # Empty draws consume work too, even though they supply no statistic.
        if result['uncertainty']['draw_manifest_hash'] is not None: work+=bins*config.bootstrap_replicates
        if work>config.max_bootstrap_work: raise ValidationError('Total cohort bootstrap-work budget exceeded')
        cohorts[key]=dict(**decl,**result,observed_mature_symbols=sorted({r['attributes']['symbol'] for r in rows if r['status']=='mature'}))
    return ExpectancyRecord.create(dict(schema_version=1,component='C10',kind='cohort_fit',snapshot_hash=snapshot.digest,
        window=window.document(),config=config.document(),protocols=d['protocols'],cohorts=cohorts,
        training_candidates=[dict(protocol_hash=r['protocol_hash'],candidate_id=r['candidate_id']) for r in d['rows']],
        sources=d['sources'],coverage=d['coverage'],ready=any(c['status']=='ready' for c in cohorts.values()),
        code_hash=code_hash(),python=platform.python_version(),numeric_policy='Exact Decimal400 sums; C09 net R diagnostic and output ratios 12dp; nearest-rank percentiles',
        estimand=d['estimand'],inference='Frozen broad cohorts; no learned feature transform, shrinkage, calibrated classifier, current-outcome lookup or automatic fallback',
        release_status='research artifact; C12 later-period policy validation and C13/C14 release integration required'))


def publish(fitted,available_ms,basis):
    integer(available_ms,'estimator availability')
    if available_ms<fitted.document()['window']['cutoff_ms'] or basis not in ('recorded','modeled'):
        raise ValidationError('Estimator cannot be available before its training cutoff')
    return ExpectancyRecord.create(dict(schema_version=1,component='C10',kind='estimator',fit_hash=fitted.digest,fit=fitted.document(),
        available_ms=available_ms,availability_basis=basis))


def verified_model(model):
    d=model.document() if isinstance(model,ExpectancyRecord) else deepcopy(model)
    supplied=d.pop('model_hash',None)
    if supplied is not None and supplied!=fingerprint(d): raise ValidationError('Corrupt estimator model hash')
    if set(d)!={'schema_version','component','kind','fit_hash','fit','available_ms','availability_basis'}: raise ValidationError('Invalid estimator envelope fields')
    if (d.get('schema_version')!=1 or type(d['schema_version']) is not int or d.get('kind')!='estimator' or
            fingerprint(d.get('fit'))!=d.get('fit_hash')): raise ValidationError('Corrupt estimator artifact')
    fitted=ExpectancyRecord.create(d['fit']); publish(fitted,d['available_ms'],d['availability_basis'])
    return ExpectancyRecord.create(d)


def estimate(model,request):
    model=verified_model(model); d=model.document(); f=d['fit']; request=request if isinstance(request,EstimateRequest) else EstimateRequest.from_dict(request)
    q=request.document(); c=q['candidate']; now=request.evaluation_ms; config=EstimatorConfig.from_dict(f['config'])
    ph=fingerprint(request.protocol); attrs=dict(side=c['side'],horizon=q['scenario']['horizon'],symbol=c['symbol']); key=cohort_key(ph,attrs,config)
    cohort=f['cohorts'].get(key); reasons=[]
    if now<d['available_ms']: reasons.append('estimator_not_yet_available')
    if now<=f['window']['cutoff_ms']: reasons.append('training_not_strictly_earlier')
    if now-f['window']['cutoff_ms']>=config.max_model_age_ms: reasons.append('stale_estimator')
    if c['candidate_id'] in {r['candidate_id'] for r in f['training_candidates']}: reasons.append('candidate_seen_in_training')
    if ph not in f['protocols']: reasons.append('incompatible_strategy_policy_cost_or_feature_protocol')
    if cohort is None: reasons.append('unseen_cohort')
    elif cohort['status']!='ready': reasons.extend(cohort['reasons'])
    elif c['symbol'] not in cohort['observed_mature_symbols']: reasons.append('unseen_mature_symbol')
    applicable=not reasons
    statistics=cohort['statistics'] if applicable else None; uncertainty=cohort['uncertainty'] if applicable else None
    eligible=applicable and cohort['positive_lower_bound']
    return ExpectancyRecord.create(dict(schema_version=1,component='C10',kind='expectancy_estimate',model_hash=model.digest,fit_hash=d['fit_hash'],
        candidate_id=c['candidate_id'],feature_snapshot_hash=c['feature_snapshot_hash'],protocol_hash=ph,cohort_hash=key,
        evaluation_ms=now,model_available_ms=d['available_ms'],model_availability_basis=d['availability_basis'],
        status='estimated' if applicable else 'abstained',ready=applicable,eligible=eligible,
        reasons=reasons if reasons else ([] if eligible else ['lower_bound_not_above_buffer']),
        statistics=statistics,uncertainty=uncertainty,coverage=None if cohort is None else cohort['coverage'],
        lower_bound_buffer_r=config.lower_bound_buffer_r,request_hash=fingerprint(q),estimand=f['estimand'],
        note='Empirical frequency is not a calibrated probability; uncertainty/admission are conditional research estimates, not profitability or release approval.'))
