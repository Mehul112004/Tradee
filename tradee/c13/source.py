"""Read C11 execution opportunities and revisions without using final outcomes for admission."""
from collections import defaultdict
from copy import deepcopy
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c10.source import pages
from tradee.c09 import TradeIntent


def load(simulations,pins,start=None,end=None,max_candidates=10000):
    if not isinstance(pins,dict) or not pins or len(pins)>100: raise ValidationError('Pinned C11 run/report pairs required')
    sources=[]; manifests={}; candidates={}; revisions=defaultdict(list); entries=defaultdict(list); common=None; baseline={}; inventory=[]; all_economics=set()
    for run,expected in sorted(pins.items()):
        summary=simulations.summary(run)
        if summary['report_hash']!=expected: raise ValidationError('Portfolio source report differs from frozen content')
        m=simulations.manifest(run); report=simulations.report(expected); manifests[run]=m
        if m['dataset']['mode']!='recorded' or m['execution']['market_model']!='recorded_quote': raise ValidationError('Funded replay requires recorded quotes/marks and funded outcome coverage')
        signature={k:m[k] for k in ('dataset','fees','execution','candidates','funding','calendars','metadata_snapshots','metadata_versions','code_hash','python')}
        signature['input_prefix_hash']=report['input_prefix_hash']; signature['input_cursor']=report['input_cursor']
        if common is not None and signature!=common: raise ValidationError('Portfolio sources must share identical market content, costs, funding, metadata and producer')
        common=signature
        a,b=m['decision_window_ms']; a=a if start is None else start; b=b if end is None else end
        if not m['decision_window_ms'][0]<=a<b<=m['decision_window_ms'][1]: raise ValidationError('Portfolio decision window outside a source scenario window')
        if sources and [a,b]!=sources[0]['decision_window_ms']: raise ValidationError('Explicit common decision window required')
        sources.append(dict(run_hash=run,report_hash=expected,decision_window_ms=[a,b]))
        features={p['payload']['snapshot_hash']:p['payload'] for p in pages(simulations,run,'feature')}
        scenarios={s['name']:s for s in m['scenarios']}
        seen=set()
        for artifact in pages(simulations,run,'candidate_decision'):
            p=artifact['payload']; c=p['record']['candidate']
            if not p['selected'] or c is None or not a<=c['detected_ms']<b: continue
            scenario=scenarios[artifact['scenario']]; f=features[c['feature_snapshot_hash']]; intent=TradeIntent(c,f,scenario['quantity'],scenario['policy']); key=(run,artifact['scenario'],intent.trade_id)
            economic=(c['candidate_id'],intent.policy.policy_hash,intent.quantity,scenario['horizon'])
            if economic in seen: raise ValidationError('Duplicate source opportunity')
            seen.add(economic)
            # A second run for the same offer is not another independent trial.
            if economic in all_economics: raise ValidationError('Overlapping duplicate portfolio offer sources')
            all_economics.add(economic)
            candidates[key]=dict(candidate=c,feature=f,scenario=scenario,manifest=m,intent=intent,economic=economic,candidate_artifact_hash=artifact['artifact_hash'])
            if len(candidates)>max_candidates: raise ValidationError('Portfolio candidate budget exceeded; no truncation')
        first=set()
        for artifact in pages(simulations,run,'transition'):
            p=artifact['payload']; key=(run,artifact['scenario'],p['trade_id'])
            if key not in candidates or key in first: continue
            state=p['state']
            if state['entry_ms'] is None: continue
            fill=next((v['estimate'] for v in state['attempts'] if v['kind']=='entry' and v['estimate'].get('fill')),None)
            if fill is None: raise ValidationError('Entry transition lacks C07 evidence')
            when=state['entry_ms']
            if p['evaluation_as_of_ms']!=when or fill['fill']['execution_as_of_ms']!=when: raise ValidationError('Noncausal source entry clock')
            entries[when].append((key,fill)); first.add(key)
        for artifact in pages(simulations,run,'outcome_revision'):
            p=artifact['payload']; key=(run,artifact['scenario'],p['outcome']['trade_id'])
            if key in candidates: revisions[p['observed_ms']].append((key,deepcopy(p['outcome'])))
        for t in report['trades']:
            key=(run,t['scenario'],t['trade_id'])
            if key in candidates: baseline[key]=t
        inventory.extend(dict(source_key=list(key),candidate_id=candidates[key]['candidate']['candidate_id'],quantity=candidates[key]['intent'].quantity) for key in candidates if key[0]==run)
    return dict(sources=sources,manifests=manifests,common=common,candidates=candidates,revisions=dict(revisions),entries=dict(entries),baseline=baseline,inventory=inventory,
        start_ms=sources[0]['decision_window_ms'][0],end_ms=sources[0]['decision_window_ms'][1])
