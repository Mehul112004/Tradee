"""Frozen predictions first; later C11 labels join only for diagnostic evaluation."""
from collections import Counter
from decimal import Decimal
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c07.math import exact,ratio
from .contracts import EstimateRequest,ExpectancyRecord,EstimatorConfig
from .engine import estimate,verified_model
from .source import snapshot,pages


def evaluate(model,simulations,runs,window):
    model=verified_model(model); m=model.document(); f=m['fit']; cfg=EstimatorConfig.from_dict(f['config'])
    if window.start_ms<max(m['available_ms'],f['window']['cutoff_ms']): raise ValidationError('Evaluation decisions must follow model availability and training cutoff')
    data=snapshot(simulations,runs,window,cfg); d=data.document(); contexts={}; predictions=[]
    for source in d['sources']:
        run=source['run_hash']; contexts[run]=(simulations.manifest(run),{a['payload']['snapshot_hash']:a['payload'] for a in pages(simulations,run,'feature')})
    # Prediction inputs contain only frozen candidate/feature/policy evidence.
    for row in d['rows']:
        manifest,features=contexts[row['source_run_hash']]
        a=simulations.artifact(row['candidate_artifact_hash']); c=a['payload']['record']['candidate']
        scenario=next(s for s in manifest['scenarios'] if s['name']==a['scenario'])
        q=EstimateRequest(c,features[c['feature_snapshot_hash']],scenario,manifest['execution'],manifest['fees'],manifest['funding'],manifest['candidates'],c['detected_ms'])
        prediction=estimate(model,q)
        predictions.append((row,prediction))
    pairs=[]; reasons=Counter(); squared=Decimal(0); brier=Decimal(0); eligible_net=Decimal(0); all_net=Decimal(0); eligible_count=0; estimated_net=Decimal(0); bins={}
    with exact():
        for row,prediction in predictions:
            p=prediction.document(); reasons.update(p['reasons']); pair=dict(candidate_id=row['candidate_id'],protocol_hash=row['protocol_hash'],
                detected_ms=row['detected_ms'],estimate_hash=prediction.digest,prediction=p,outcome_status=row['status'],
                outcome_known_ms=row['outcome_known_ms'],revision_artifact_hash=row['revision_artifact_hash'],net_r=row['net_r'],net_usdt=row['net_usdt'])
            pairs.append(pair)
            if row['status']!='mature': continue
            all_net+=Decimal(row['net_r'])
            if not p['ready']: continue
            mean=Decimal(p['statistics']['mean_net_r']); probability=Decimal(p['statistics']['empirical_positive_net_fraction']); actual=Decimal(row['net_r']); y=int(actual>0)
            squared+=(mean-actual)**2; brier+=(probability-y)**2; estimated_net+=actual
            index=min(9,int(probability*10)); bucket=bins.setdefault(index,dict(count=0,predicted=Decimal(0),positive=0))
            bucket['count']+=1; bucket['predicted']+=probability; bucket['positive']+=y
            if p['eligible']: eligible_net+=actual; eligible_count+=1
        matched=sum(row['status']=='mature' and p.document()['ready'] for row,p in predictions)
        mature=sum(r['status']=='mature' for r in d['rows'])
        reliability=[dict(bin=index,count=b['count'],mean_empirical_prediction=ratio(b['predicted'],Decimal(b['count'])),
            observed_positive_fraction=ratio(Decimal(b['positive']),Decimal(b['count']))) for index,b in sorted(bins.items())]
        report=dict(schema_version=1,component='C10',kind='frozen_evaluation',model_hash=model.digest,window=window.document(),
            evaluation_snapshot_hash=data.digest,sources=d['sources'],predictions=pairs,ready=matched>0,
            coverage=dict(candidates=len(pairs),estimated=sum(p.document()['ready'] for _,p in predictions),eligible=sum(p.document()['eligible'] for _,p in predictions),
                mature=mature,matched_estimated_mature=matched,matched_eligible_mature=eligible_count,abstention_reasons=dict(sorted(reasons.items()))),
            metrics=dict(mean_squared_net_r_error=ratio(squared,Decimal(matched)),empirical_frequency_brier_score=ratio(brier,Decimal(matched)),
                all_mature_mean_net_r=ratio(all_net,Decimal(mature)),matched_estimated_mean_net_r=ratio(estimated_net,Decimal(matched)),eligible_mature_mean_net_r=ratio(eligible_net,Decimal(eligible_count)),reliability_bins=reliability),
            prediction_manifest_hash=fingerprint([p.digest for _,p in predictions]),
            note='Frozen chronological engineering evaluation; labels join after prediction. Empirical-frequency Brier/reliability diagnostics do not certify calibration or improvement. No capital-weighted policy result, uncertainty on improvement, tuning, folds or promotion; C12/C13 own those gates.')
    return ExpectancyRecord.create(report)
