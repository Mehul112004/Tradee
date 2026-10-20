"""Forward monitoring consumes records; it neither trades nor retrains models."""
from collections import Counter
from pathlib import Path
import platform
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c02.domain import integer
from tradee.c03.contracts import FrozenRecord
from tradee.c06.engine import code_hash
from tradee.c12.contracts import identifier
from tradee.c14 import SessionSpec
from .contracts import MonitorPolicy
from .source import verified_cycle,outcome_row,summarize
from .statistics import review


class ForwardMonitor:
    def __init__(self,store,signals,simulations,portfolios):
        self.store,self.signals,self.simulations,self.portfolios=store,signals,simulations,portfolios
        if len({Path(s.path).resolve() for s in (store,signals,simulations,portfolios)})!=4: raise ValidationError('C15/C14/C11/C13 stores must differ')

    def register(self,name,session,policy,when):
        identifier(name); integer(when,'registration clock')
        p=policy if isinstance(policy,MonitorPolicy) else MonitorPolicy.from_dict(policy)
        source=self.signals.evidence(session); h=source['head']; m=h['manifest']; spec=SessionSpec.from_dict(m['spec'])
        if source['cycles'] or not when<=spec.start_ms or any(t<=spec.start_ms for t in p.review_times_ms): raise ValidationError('Freeze C15 rules before the first C14 cycle and prospective review deadlines')
        if when<max([e['at_ms'] for e in source['events'] if e['kind']!='deployment_created']+[0]): raise ValidationError('Cannot backdate C15 registration behind recorded C14 controls')
        if when<max(e['recorded_ms'] for e in source['events']): raise ValidationError('Cannot backdate C15 registration behind actual C14 recording')
        if m['code_hash']!=code_hash() or m['python']!=platform.python_version(): raise ValidationError('Current-source C14 deployment required for prospective C15 monitoring')
        return self.store.register(dict(schema_version=1,component='C15',kind='forward_monitor',name=name,session=session,
            deployment_hash=h['deployment_hash'],policy=p.document(),registered_ms=when,registration_event_hash=source['events'][-1]['event_hash'],
            code_hash=code_hash(),python=platform.python_version(),live_approved=False,
            scope='Paper/shadow outcomes and delivery telemetry; optional actual-user fills remain separate and unsupported'))

    def _source(self,name,when):
        integer(when,'observation clock'); head=self.store.head(name); m=head['manifest']
        if m['code_hash']!=code_hash() or m['python']!=platform.python_version(): raise ValidationError('Frozen C15 code/runtime changed; new counted deployment required')
        if when<max([head['last_ms']]+[e['at_ms'] for e in self.store.events(name)]): raise ValidationError('C15 observation clock moved backward')
        source=self.signals.evidence(m['session'])
        if source['head']['deployment_hash']!=m['deployment_hash']: raise ValidationError('C15 deployment changed')
        if m['registration_event_hash'] not in {e['event_hash'] for e in source['events']}: raise ValidationError('C14 registration audit anchor changed')
        if when<max([e['at_ms'] for e in source['events'] if e['kind']!='deployment_created']+[e['recorded_ms'] for e in source['events']]): raise ValidationError('C15 cannot observe future C14 decisions or controls')
        p=MonitorPolicy.from_dict(m['policy'])
        if len(source['cycles'])>p.max_cycles: raise ValidationError('C15 source cycle budget exceeded')
        return head,source,p

    @staticmethod
    def _rows(cycles,baselines,cutoff,policy):
        first={}; revisions={}; chosen=None
        for item,baseline in zip(cycles,baselines):
            c=item['cycle']
            if c['as_of_ms']>=cutoff: break
            if item['recorded_ms']>=cutoff: continue
            chosen=(item,baseline)
            for s in c['signals']:
                f=first.setdefault(s['signal_id'],dict(detection=dict(cycle_hash=item['cycle_hash'],as_of_ms=c['as_of_ms'],recorded_ms=item['recorded_ms']),admission=None))
                if s['entry_ms'] is not None and f['admission'] is None:
                    f['admission']=dict(cycle_hash=item['cycle_hash'],as_of_ms=c['as_of_ms'],recorded_ms=item['recorded_ms'],decision=s['decision'])
                for track,t in (('independent',baseline.get(s['candidate_id'])),('portfolio',s['paper_outcome'])):
                    key=(s['signal_id'],track); rev=None if t is None else t['outcome_revision_hash']
                    if key not in revisions or revisions[key][0]!=rev: revisions[key]=(rev,max(c['as_of_ms'],item['recorded_ms']))
        if chosen is None: return []
        item,baseline=chosen; c=item['cycle']; rows=[]
        for s in c['signals']:
            for track,t in (('independent',baseline.get(s['candidate_id'])),('portfolio',s['paper_outcome'])):
                if track=='portfolio' and t is None: continue
                available=revisions[(s['signal_id'],track)][1]
                if t is not None: available=max(available,t['outcome_known_ms'] or available)
                rows.append(outcome_row(s,t,track,item['cycle_hash'],c['as_of_ms'],first[s['signal_id']],cutoff,policy.maturity_lag_ms,available))
        return rows

    def observe(self,name,when):
        head,source,p=self._source(name,when); h=source['head']; m=head['manifest']; spec=SessionSpec.from_dict(h['manifest']['spec'])
        events=source['events']; cycles=source['cycles']; baselines=[]; integrity=[]
        # Every referenced report/inventory is verified, even on an idempotent retry.
        try:
            for item in cycles: baselines.append(verified_cycle(item,h['manifest'],self.simulations,self.portfolios))
        except ValidationError:
            integrity.append('source_evidence_verification_failed'); baselines=[]
        reconciliations=[self.store.artifact(e['payload']['receipt_hash']) for e in self.store.events(name) if e['kind']=='replay_checked']
        if reconciliations and not reconciliations[-1]['ready']: integrity.append('deterministic_replay_mismatch')
        key=fingerprint(dict(manifest=head['manifest_hash'],when=when,audit=[e['event_hash'] for e in events],reconciliations=reconciliations,integrity=integrity))
        cached=self.store.cached(name,key)
        if cached is not None: return cached
        if head['revision']>=p.max_observations: raise ValidationError('C15 observation count budget exceeded')
        rows=[] if integrity else self._rows(cycles,baselines,when,p)
        old=head['report']; reviews=[] if old is None else list(old['reviews'])
        for deadline in p.review_times_ms[len(reviews):]:
            if deadline>when: break
            eligible=[] if integrity else self._rows(cycles,baselines,deadline,p)
            reviews.append(review(eligible,p,spec.start_ms,deadline))
        operational=[]; c=h['cycle']; completed=bool(c and when>=spec.end_ms and not c['paper_account']['positions'])
        awaiting=when<spec.start_ms
        if c is None and not awaiting: operational.append('no_paper_cycle')
        elif c is not None:
            if not completed and when-c['as_of_ms']>=min(p.max_cycle_age_ms,spec.runtime.max_cycle_age_ms): operational.append('stale_paper_cycle')
            if not c['health']['ready']: operational.append('paper_data_or_risk_unready')
            if cycles[-1]['processing_ms']>=spec.runtime.max_cycle_age_ms: operational.append('analysis_latency_exceeded')
        if h['fault']: operational.append('c14_operational_fault')
        states=Counter(d['state'] for d in source['deliveries'])
        if states['ambiguous']: operational.append('delivery_reconciliation_required')
        if states['failed']: operational.append('delivery_failed')
        if any(d['state']=='in_flight' and when>=d['lease_until_ms'] for d in source['deliveries']): operational.append('delivery_lease_elapsed')
        if any(d['state'] in ('pending','retry_wait') and when>=d['expires_ms'] for d in source['deliveries']): operational.append('delivery_expiry_unrecovered')
        statistical=sorted({reason for r in reviews for reason in r['degradation_reasons']})
        requested=bool(integrity or (operational and p.pause_on_operational_failure) or (statistical and p.pause_on_statistical_degradation))
        receipts=[dict(signal_id=e['payload']['delivery']['signal_id'],kind=e['kind'],at_ms=e['at_ms'],
            state=e['payload']['delivery']['state'],http_elapsed_ms=e['payload'].get('http_elapsed_ms'),
            operator_assertion=e['kind']=='outbox_reconciled',message_id=e['payload']['delivery']['message_id'])
            for e in events if 'delivery' in e['payload']]
        claims={}
        current_signals={} if c is None else {s['signal_id']:s for s in c['signals']}
        for r in receipts:
            sid=r['signal_id']
            if r['kind']=='outbox_claimed': claims[sid]=r['at_ms']
            r['claim_to_result_ms']=r['at_ms']-claims[sid] if r['kind']=='outbox_result' and sid in claims else None
            signal=current_signals.get(sid)
            r['detection_to_claim_ms']=r['at_ms']-signal['detected_ms'] if r['kind']=='outbox_claimed' and signal else None
            r['paper_entry_to_claim_ms']=r['at_ms']-signal['entry_ms'] if r['kind']=='outbox_claimed' and signal and signal['entry_ms'] is not None else None
        previous={} if old is None else {(r['signal_id'],r['track']):r for r in old['rows']}
        changes=[]
        for row in rows:
            prior=previous.get((row['signal_id'],row['track']))
            if prior and (prior['outcome_revision_hash']!=row['outcome_revision_hash'] or prior['status']!=row['status']):
                changes.append(dict(signal_id=row['signal_id'],track=row['track'],previous_revision=prior['outcome_revision_hash'],
                    revision=row['outcome_revision_hash'],previous_status=prior['status'],status=row['status']))
        source_doc=dict(deployment_hash=h['deployment_hash'],revision=h['revision'],cycle_hash=h['cycle_hash'],event_hashes=[e['event_hash'] for e in events])
        report=dict(schema_version=1,component='C15',kind='forward_report',manifest_hash=head['manifest_hash'],observed_ms=when,source=source_doc,
            rows=rows,summary=summarize(rows),label_changes=changes,reviews=reviews,
            health=dict(operational=sorted(set(operational)),statistical=statistical,integrity=integrity,already_paused=bool(h['paused']),paper_session_complete=completed,awaiting_session_start=awaiting),
            pause_requested=requested,ready=not (operational or statistical or integrity or h['paused'] or awaiting),
            telemetry=dict(delivery_states=dict(states),delivery_receipts=receipts,
                processing_ms=[dict(cycle_hash=i['cycle_hash'],as_of_ms=i['cycle']['as_of_ms'],elapsed_ms=i['processing_ms']) for i in cycles],
                paper_account=None if c is None else c['paper_account'],
                note='Telegram acceptance and operator assertions do not establish user receipt or an actual exchange fill.'),
            live_approved=False,promotion_authorized=False,
            scope='Prospective paper/shadow engineering evidence. Statistical absence of detected degradation is not proof of profitability.')
        frozen=FrozenRecord.create(report)
        if len(frozen.serialized.encode())>p.max_report_bytes: raise ValidationError('C15 report byte budget exceeded')
        return self.store.publish(name,head['revision'],key,frozen)

    def apply_pause(self,name,report_hash,when):
        integer(when,'pause clock'); head=self.store.head(name)
        report=self.store.artifact(report_hash)
        if report.get('manifest_hash')!=head['manifest_hash'] or not report.get('pause_requested'): raise ValidationError('C15 report has no pause request for this monitor')
        session=head['manifest']['session']; reason='c15:'+report_hash
        # Recover the cross-store gap: the C14 pause is durable before its C15 receipt.
        prior=[e for e in self.signals.events(session) if e['kind']=='paused' and e['payload'].get('reason')==reason]
        if prior:
            event=prior[0]
            return self.store.receipt(name,report_hash,dict(report_hash=report_hash,c14_event_hash=event['event_hash'],at_ms=event['at_ms'],paused=True))
        if head['report_hash']!=report_hash: raise ValidationError('Stale C15 pause request; observe again')
        if when<report['observed_ms']: raise ValidationError('Cannot backdate a C15 pause')
        self.signals.pause(session,True,reason,when,expected_revision=report['source']['revision'],expected_event_hash=report['source']['event_hashes'][-1])
        event=next(e for e in self.signals.events(session) if e['kind']=='paused' and e['payload'].get('reason')==reason)
        return self.store.receipt(name,report_hash,dict(report_hash=report_hash,c14_event_hash=event['event_hash'],at_ms=event['at_ms'],paused=True))

    def export(self,name,report_hash=None):
        h=self.store.head(name); key=h['report_hash'] if report_hash is None else report_hash
        if key is None: raise ValidationError('Observe forward evidence before export')
        report=self.store.artifact(key)
        if report.get('kind')!='forward_report' or report['manifest_hash']!=h['manifest_hash']: raise ValidationError('C15 export/report mismatch')
        rows=[r for r in report['rows'] if r['status']=='mature']
        return dict(schema_version=1,component='C15',kind='forward_outcome_dataset',report_hash=key,as_of_ms=report['observed_ms'],
            deployment_hash=h['deployment_hash'],rows=rows,dataset_hash=fingerprint(rows),live_approved=False,
            use='A versioned research input, not automatically admitted to C10 fitting or C12 holdouts. Tracks and selectively reported actual fills must never be pooled.')
