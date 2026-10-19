"""Nested selection reads inner labels only; outer/holdout winners never reselect."""
from collections import Counter
from decimal import Decimal
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c03.contracts import FrozenRecord
from tradee.c10 import TrainingWindow
from tradee.c10.source import snapshot
from tradee.c10.engine import fit, publish
from tradee.c10.evaluation import evaluate
from .statistics import evidence


def purged_snapshot(data, split):
    d=data.document(); boundary=split.test.start_ms-split.purge_gap_ms; kept=[]; removed=[]
    for r in d['rows']:
        reasons=[]
        if r['detected_ms']>=boundary: reasons.append('decision_in_pretest_gap')
        # Closed outcome intervals: an endpoint on the boundary is excluded.
        if r['label_end_ms'] is not None and r['label_end_ms']>=boundary: reasons.append('label_interval_reaches_pretest_boundary')
        if reasons: removed.append(dict(candidate_id=r['candidate_id'],protocol_hash=r['protocol_hash'],label_start_ms=r['label_start_ms'],label_end_ms=r['label_end_ms'],reasons=reasons))
        else: kept.append(r)
    d['rows']=kept; d['coverage']=dict(sorted(Counter(r['status'] for r in kept).items()))
    d['c12_purge']=dict(source_snapshot_hash=data.digest,boundary_ms=boundary,removed=removed,
                         unresolved_retained=sum(r['status'] in ('not_observed','unresolved') for r in kept),
                         rule='Causal last revision strictly before training cutoff; exclude decisions and closed label endpoints at/after test start minus declared gap. Unknown labels never train C10.')
    return FrozenRecord.create(d)


def selected_runs(simulations, variant, window, stage, holdout_start):
    """Check manifests before reading outcomes; never inspect holdout sources in development."""
    runs=variant.holdout_runs if stage=='holdout' else variant.development_runs
    selected=[]
    for run in runs:
        m=simulations.manifest(run); a,b=m['decision_window_ms']
        if stage!='holdout' and (b>holdout_start or m['dataset']['as_of_ms']>holdout_start):
            raise ValidationError('Development source contains sealed-period decisions or later revisions')
        if max(a,window.start_ms)<min(b,window.end_ms): selected.append(run)
    if not selected: raise ValidationError('No pinned source covers research window')
    return selected


def training(simulations, variant, split, holdout_start):
    runs=selected_runs(simulations,variant,split.train,'development',holdout_start)
    raw=snapshot(simulations,runs,split.train,variant.estimator)
    if len(raw.document()['protocols'])!=1: raise ValidationError('Each research variant must describe exactly one C11 strategy/policy/cost protocol')
    data=purged_snapshot(raw,split); fitted=fit(data,variant.estimator)
    model=publish(fitted,split.train.cutoff_ms,'modeled')
    return dict(snapshot=data.document(),snapshot_hash=data.digest,fit=fitted.document(),model=model.document(),model_hash=model.digest)


def testing(simulations, variant, split, model, stage, holdout_start):
    runs=selected_runs(simulations,variant,split.test,stage,holdout_start)
    data=snapshot(simulations,runs,split.test,variant.estimator)
    if set(data.document()['protocols'])!=set(model['fit']['protocols']): raise ValidationError('Test protocol differs from frozen training variant')
    if {s['producer_code_hash'] for s in data.document()['sources']}!={s['producer_code_hash'] for s in model['fit']['sources']}:
        raise ValidationError('Test simulator implementation differs from frozen training producer')
    result=evaluate(model,simulations,runs,split.test).document()
    rows={(r['protocol_hash'],r['candidate_id']):r for r in data.document()['rows']}
    enriched=[]
    for p in result['predictions']:
        r=rows[(p['protocol_hash'],p['candidate_id'])]
        enriched.append(dict(**p,symbol=r['attributes']['symbol'],label_start_ms=r['label_start_ms'],label_end_ms=r['label_end_ms'],fold=split.name))
    return dict(evaluation=result,rows=enriched)


def stress_protocol(base, stressed):
    """Stress preserves the hypothesis, data and admission; only adverse costs/delays vary."""
    b=dict(base); s=dict(stressed); bf=b.pop('fees'); sf=s.pop('fees'); be=dict(b.pop('execution')); se=dict(s.pop('execution'))
    if b!=s: raise ValidationError('Stress must preserve strategy, trade policy, quantity, funding, features and candidate policy')
    allowed=('processing_delay_ms','delivery_delay_ms','manual_delay_ms','extra_slippage_bps','impact_bps_per_participation',
             'synthetic_spread_bps','bar_impact_bps_per_participation')
    changed=any(Decimal(sf[k])>Decimal(bf[k]) for k in ('taker_rate','maker_rate'))
    if any(Decimal(sf[k])<Decimal(bf[k]) for k in ('taker_rate','maker_rate')): raise ValidationError('Stress fees cannot improve')
    # Evidence identifiers may change; fee schedule timing/source semantics may not.
    if {k:v for k,v in bf.items() if k not in ('evidence','taker_rate','maker_rate')}!={k:v for k,v in sf.items() if k not in ('evidence','taker_rate','maker_rate')}:
        raise ValidationError('Stress fee evidence semantics differ')
    for k in allowed:
        if k not in be: continue
        if Decimal(str(se[k]))<Decimal(str(be[k])): raise ValidationError('Stress cost/delay cannot improve')
        changed|=Decimal(str(se[k]))>Decimal(str(be[k])); be.pop(k); se.pop(k)
    if be!=se or not changed: raise ValidationError('Declare a strictly adverse supported cost/delay stress')


def stressed_testing(simulations, variant, split, baseline, model, stage, holdout_start):
    runs=selected_runs(simulations,variant,split.test,stage,holdout_start)
    data=snapshot(simulations,runs,split.test,variant.estimator).document()
    if len(data['protocols'])!=1: raise ValidationError('One stress protocol required')
    stress_protocol(next(iter(model['fit']['protocols'].values())),next(iter(data['protocols'].values())))
    # Identical underlying market evidence is required, including availability vintage.
    base_sources=baseline['evaluation']['sources']
    if {s['producer_code_hash'] for s in base_sources}!={s['producer_code_hash'] for s in data['sources']}:
        raise ValidationError('Stress simulator implementation differs from baseline')
    if {fingerprint(s['dataset']) for s in base_sources}!={fingerprint(s['dataset']) for s in data['sources']}:
        raise ValidationError('Stress and baseline must use identical pinned source datasets')
    labels={r['candidate_id']:r for r in data['rows']}; rows=[]
    for p in baseline['rows']:
        r=labels.get(p['candidate_id']); d=dict(p)
        if r is None: d.update(outcome_status='missing_stress_candidate',net_r=None,net_usdt=None,label_start_ms=None,label_end_ms=None)
        else: d.update(outcome_status=r['status'],net_r=r['net_r'],net_usdt=r['net_usdt'],label_start_ms=r['label_start_ms'],label_end_ms=r['label_end_ms'],revision_artifact_hash=r['revision_artifact_hash'],outcome_known_ms=r['outcome_known_ms'])
        rows.append(d)
    return dict(rows=rows,stress_variant=variant.name,sources=data['sources'],admission='Baseline frozen predictions reused; no refit or reselection under stress')


def choose(experiment, fold, job):
    bases=[v for v in experiment.variants if v.stress_of is None]
    if len(bases)==1 and not fold.inner: return dict(winner=bases[0].name,selection='predeclared fixed hypothesis; no artificial fitting of strategy parameters',scores=[])
    scores=[]
    for v in bases:
        rows=[]; jobs=[]
        for split in fold.inner:
            key='inner/'+fold.split.name+'/'+v.name+'/'+split.name
            d=job(key,lambda v=v,split=split: fitted_test(experiment,v,split,job.simulations,'development'))
            rows.extend(d['test']['rows']); jobs.append(key)
        result=evidence(rows,experiment.policy,experiment.family_trial_budget,[i.test.document() for i in fold.inner])
        scores.append(dict(variant=v.name,evidence=result,jobs=jobs))
    viable=[s for s in scores if s['evidence']['ready']]
    winner=sorted(viable,key=lambda s:(Decimal(s['evidence']['utility_r_per_candidate']).copy_negate(),s['variant']))[0]['variant'] if viable else None
    return dict(winner=winner,selection='Maximum earlier inner selected net R per candidate among passing variants; lexical tie-break. No outer labels enter selection.',scores=scores)


def fitted_test(experiment, variant, split, simulations, stage):
    trained=training(simulations,variant,split,experiment.holdout.split.test.start_ms)
    tested=testing(simulations,variant,split,trained['model'],stage,experiment.holdout.split.test.start_ms)
    return dict(training=trained,test=tested)


def outer(experiment, fold, selection, job, stage='development', final_training=None):
    if selection['winner'] is None: return dict(fold=fold.split.name,winner=None,rows=[],stresses=[],neighbors=[],reasons=['no_inner_variant_passed'])
    variants={v.name:v for v in experiment.variants}; v=variants[selection['winner']]
    key=('holdout/' if stage=='holdout' else 'outer/')+fold.split.name+'/'+v.name
    if final_training is None:
        result=job(key,lambda:fitted_test(experiment,v,fold.split,job.simulations,stage))
    else:
        result=job(key,lambda:dict(training=final_training,test=testing(job.simulations,v,fold.split,final_training['model'],stage,experiment.holdout.split.test.start_ms)))
    stresses=[]; neighbors=[]; reasons=[]
    for s in experiment.variants:
        if s.stress_of==v.name:
            data=job(key+'/stress/'+s.name,lambda s=s:stressed_testing(job.simulations,s,fold.split,result['test'],result['training']['model'],stage,experiment.holdout.split.test.start_ms))
            stresses.append(dict(variant=s.name,**data,evidence=evidence(data['rows'],experiment.policy,experiment.family_trial_budget,[fold.split.test.document()])))
        # Neighbor outcomes are diagnostics after the selection job is durable.
        if s.stress_of is None and (s.neighbor_of==v.name or v.neighbor_of==s.name):
            data=job(key+'/neighbor/'+s.name,lambda s=s:fitted_test(experiment,s,fold.split,job.simulations,stage))
            neighbors.append(dict(variant=s.name,evidence=evidence(data['test']['rows'],experiment.policy,experiment.family_trial_budget,[fold.split.test.document()])))
    if experiment.policy.require_stress and not stresses: reasons.append('missing_predeclared_stress')
    if any(not s['evidence']['ready'] for s in stresses): reasons.append('stress_evidence_failed')
    if experiment.policy.require_neighbors and not neighbors: reasons.append('missing_predeclared_neighborhood')
    if any(not n['evidence']['ready'] for n in neighbors): reasons.append('neighborhood_evidence_failed')
    return dict(fold=fold.split.name,winner=v.name,job=key,rows=result['test']['rows'],stresses=stresses,neighbors=neighbors,reasons=reasons,
                model_hash=result['training']['model_hash'],purge=result['training']['snapshot']['c12_purge'])


def development(experiment, job):
    folds=[]; rows=[]; reasons=[]
    for fold in experiment.folds:
        selection=job('selection/'+fold.split.name,lambda fold=fold:choose(experiment,fold,job))
        result=outer(experiment,fold,selection,job); folds.append(result); rows.extend(result['rows']); reasons.extend(result['reasons'])
    overall=evidence(rows,experiment.policy,experiment.family_trial_budget,[f.split.test.document() for f in experiment.folds])
    reasons.extend(overall['reasons'])
    # Freeze final choice and training before unlocking any holdout outcomes.
    final=job('final/selection',lambda:choose(experiment,experiment.holdout,job))
    trained=None
    if final['winner'] is None: reasons.append('no_final_variant_passed')
    else:
        variant=next(v for v in experiment.variants if v.name==final['winner'])
        trained=job('training/final',lambda:training(job.simulations,variant,experiment.holdout.split,experiment.holdout.split.test.start_ms))
        if not trained['fit']['ready']: reasons.append('final_estimator_not_ready')
    return dict(component='C12',kind='development_validation',ready=not reasons,reasons=sorted(set(reasons)),folds=folds,evidence=overall,
                final_selection=final,final_training=trained,holdout_accessed=False,
                note='Outer diagnostics cannot change selection; final selection reruns the same predeclared inner procedure on later development history. Historical modeled publication, not actual live model availability.')


def holdout(experiment, development_report, job):
    result=outer(experiment,experiment.holdout,development_report['final_selection'],job,'holdout',development_report['final_training'])
    result['evidence']=evidence(result['rows'],experiment.policy,experiment.family_trial_budget,[experiment.holdout.split.test.document()])
    reasons=result['reasons']+result['evidence']['reasons']
    if experiment.holdout_status!='uninspected': reasons.append('holdout_previously_inspected_or_unattested')
    return dict(component='C12',kind='holdout_validation',ready=not reasons,reasons=sorted(set(reasons)),result=result,
                frozen_development_hash=fingerprint(development_report),research_status='research_candidate' if not reasons else 'rejected',
                live_approved=False,remaining_gates=['C13 finite-capital portfolio/risk validation','C14 operational and notification checks','C15 forward evidence; representative audited real data and costs'],
                note='Application-level holdout access control relies on truthful prior-inspection disclosure; C11/raw-file access outside C12 cannot be prevented. No profitability guarantee or automatic live release.')
