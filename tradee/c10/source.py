"""Revision-aware C11 selection: never train from the latest final trade table."""
from collections import Counter
from decimal import Decimal
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c06.contracts import decimal_text
from tradee.c07.math import exact,ratio
from tradee.c09 import TradeIntent
from tradee.c11 import Scenario
from .contracts import ExpectancyRecord,protocol,cohort_key


def pages(store,run,kind):
    cursor=0
    while True:
        page=store.records(run,kind=kind,after_sequence=cursor,limit=1000)
        yield from page['records']
        if not page['has_more']: return
        cursor=page['next_after_sequence']


def covered(intervals,start,end):
    point=start
    for a,b in sorted(intervals):
        if b<=point: continue
        if a>point: return False
        point=max(point,b)
        if point>=end: return True
    return point>=end


def validate_outcome(t,observed,cutoff,intent):
    if t['trade_id']!=intent.trade_id or t['state']['candidate_id']!=intent.candidate.document()['candidate_id']:
        raise ValidationError('Outcome/candidate identity mismatch')
    if type(t['ready']) is not bool or type(observed) is not int or not observed<cutoff: raise ValidationError('Future/invalid outcome revision')
    if not t['ready']: return
    if (t['status']!='closed' or t['label_status']!='mature' or t['ambiguity_flags'] or t['remaining_quantity']!='0' or
            t['outcome_known_ms'] is None or not t['entry_ms']<=t['exit_ms']<=t['outcome_known_ms']<=observed<cutoff):
        raise ValidationError('Invalid mature outcome availability')
    expected=fingerprint(dict(ledger=t['state']['ledger'],status=t['status'],ambiguity=t['ambiguity_flags'],funding=t['funding_usdt']))
    if expected!=t['outcome_revision_hash']: raise ValidationError('Corrupt mature outcome revision')
    with exact():
        gross=Decimal(t['gross_realized_usdt']); fees=Decimal(t['fees_usdt']); funding=Decimal(t['funding_usdt']); net=Decimal(t['net_usdt']); risk=Decimal(t['risk_usdt'])
        fills=[v for v in t['state']['ledger'].values() if v['kind'] in ('entry','exit')]
        if (risk<=0 or net!=gross-fees+funding or net!=sum((Decimal(v['amount_usdt']) for v in t['state']['ledger'].values()),Decimal(0)) or
                gross!=sum((Decimal(v['gross_usdt']) for v in fills),Decimal(0)) or fees!=sum((Decimal(v['fee_usdt']) for v in fills),Decimal(0)) or
                t['net_r']!=ratio(net,risk) or t['profitable']!=(net>0)):
            raise ValidationError('Mature outcome monetary reconciliation failed')


def snapshot(store,runs,window,config):
    runs=sorted(set(runs))
    if not runs: raise ValidationError('At least one pinned C11 run required')
    if len(runs)>config.max_source_runs: raise ValidationError('Expectancy source-run budget exceeded')
    rows=[]; sources=[]; protocols={}; intervals={}; implementations={}; identities=set(); declarations={}
    for run in runs:
        summary=store.summary(run); manifest=store.manifest(run)
        sources.append(dict(run_hash=run,report_hash=summary['report_hash'],producer_code_hash=manifest['code_hash'],
            dataset=manifest['dataset'],decision_window_ms=manifest['decision_window_ms'],
            funding_calendar_evidence=[dict(symbol=c['symbol'],calendar_hash=fingerprint(c),evidence=c['evidence']) for c in manifest['calendars']]))
        scenarios={s['name']:Scenario.from_dict(s) for s in manifest['scenarios']}
        # Validate all C11 artifacts first, then select only historically observable revisions.
        features={a['payload']['snapshot_hash']:a['payload'] for a in pages(store,run,'feature')}
        revisions={}
        for a in pages(store,run,'outcome_revision'):
            p=a['payload']; t=p['outcome']; key=(a['scenario'],t['trade_id'])
            if p['observed_ms']>=window.cutoff_ms: continue
            previous=revisions.get(key)
            if previous is None or (p['observed_ms'],a['sequence'])>(previous['payload']['observed_ms'],previous['sequence']): revisions[key]=a
        for name,s in scenarios.items():
            definitions={k:v for k,v in manifest['detectors'][name]['feature_manifest']['definitions'].items() if k in s.strategy.feature_config().features}
            p=protocol(s,manifest['execution'],manifest['fees'],manifest['funding'],manifest['candidates'],manifest['dataset']['mode'],definitions)
            ph=fingerprint(p); protocols[ph]=p; implementations.setdefault(ph,set()).add(manifest['code_hash'])
            for side in s.strategy.sides:
                for symbol in manifest['dataset']['symbols']:
                    attributes=dict(side=side,horizon=s.horizon,symbol=symbol)
                    declarations[cohort_key(ph,attributes,config)]=dict(protocol_hash=ph,attributes={k:attributes[k] for k in config.cohort_fields})
            a,b=manifest['decision_window_ms']; a=max(a,window.start_ms); b=min(b,window.end_ms,window.cutoff_ms)
            if a<b:
                for old_a,old_b,old_run in intervals.get(ph,[]):
                    if max(a,old_a)<min(b,old_b) and old_run!=run: raise ValidationError('Overlapping decision windows for the same protocol; choose one source vintage or disjoint runs')
                intervals.setdefault(ph,[]).append((a,b,run))
        for a in pages(store,run,'candidate_decision'):
            p=a['payload']; c=p['record']['candidate']
            if not p['selected'] or c is None or not window.start_ms<=c['detected_ms']<window.end_ms or c['detected_ms']>=window.cutoff_ms: continue
            s=scenarios[a['scenario']]; f=features.get(c['feature_snapshot_hash'])
            if f is None: raise ValidationError('Missing candidate feature artifact')
            intent=TradeIntent(c,f,s.quantity,s.policy.document())
            prot=protocol(s,manifest['execution'],manifest['fees'],manifest['funding'],manifest['candidates'],c['availability_basis'],f['definition_hashes']); ph=fingerprint(prot)
            if prot!=protocols[ph]: raise ValidationError('Candidate feature definitions differ from detector')
            key=(ph,c['candidate_id'])
            if key in identities: raise ValidationError('Duplicate training opportunity')
            identities.add(key)
            rev=revisions.get((a['scenario'],intent.trade_id)); t=None if rev is None else rev['payload']['outcome']
            if t is not None: validate_outcome(t,rev['payload']['observed_ms'],window.cutoff_ms,intent)
            status='not_observed' if t is None else 'mature' if t['ready'] else 'unfilled' if t['label_status']=='unfilled' else 'unresolved'
            attributes=dict(side=c['side'],horizon=s.horizon,symbol=c['symbol'])
            rows.append(dict(protocol_hash=ph,cohort_hash=cohort_key(ph,attributes,config),attributes=attributes,candidate_id=c['candidate_id'],trade_id=intent.trade_id,
                detected_ms=c['detected_ms'],status=status,filled=bool(t and t['entry_ms'] is not None),
                label_start_ms=None if t is None else t['label_start_ms'],label_end_ms=None if t is None else t['label_end_ms'],
                outcome_known_ms=None if t is None else t['outcome_known_ms'],
                net_r=t['net_r'] if status=='mature' else None,net_usdt=t['net_usdt'] if status=='mature' else None,
                risk_usdt=t['risk_usdt'] if status=='mature' else None,
                source_run_hash=run,candidate_artifact_hash=a['artifact_hash'],feature_snapshot_hash=c['feature_snapshot_hash'],
                revision_artifact_hash=None if rev is None else rev['artifact_hash'],revision_observed_ms=None if rev is None else rev['payload']['observed_ms'],
                outcome_revision_hash=None if t is None else t['outcome_revision_hash']))
            if len(rows)>config.max_rows: raise ValidationError('Expectancy training-row budget exceeded; no truncation')
    for ph in protocols:
        if len(implementations[ph])!=1: raise ValidationError('Cannot pool different producer implementations under one protocol')
        if not covered([(a,b) for a,b,_ in intervals.get(ph,[])],window.start_ms,window.end_ms):
            raise ValidationError('C11 decision coverage does not cover the full declared training window')
    rows.sort(key=lambda r:(r['detected_ms'],r['protocol_hash'],r['candidate_id']))
    return ExpectancyRecord.create(dict(schema_version=1,component='C10',kind='training_snapshot',window=window.document(),
        sources=sources,cohort_fields=list(config.cohort_fields),protocols=protocols,cohorts=declarations,rows=rows,coverage=dict(sorted(Counter(r['status'] for r in rows).items())),
        selection='Last revision observed strictly before cutoff; only mature known outcomes train, unresolved/unfilled remain in coverage. No final-trade-table labels.',
        estimand='Mean net R conditional on simulated fill and mature evidence; not unconditional profit per alert'))
