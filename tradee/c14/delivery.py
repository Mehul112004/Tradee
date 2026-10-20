"""Leased outbox dispatch: atomic intent before HTTP, no unknown-outcome retries."""
import time
import uuid
from tradee.c01 import ValidationError
from tradee.c13.contracts import text as evidence
from .contracts import SessionSpec,DeliveryResult
from .message import format_notice


class Dispatcher:
    def __init__(self,store,clock=time.time): self.store,self.clock=store,clock
    def now(self): return int(self.clock()*1000)
    def recover(self,name,when=None):
        when=self.now() if when is None else when; recovered=0
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE'); h=self.store._session(db,name)
            if when<h['control_ms'] or (h['cycle'] and when<h['cycle']['as_of_ms']): raise ValidationError('Delivery clock moved backward')
            rows=db.execute('SELECT o.* FROM outbox o JOIN signals s ON s.id=o.signal_id WHERE s.session=?',(name,)).fetchall()
            for row in rows:
                self.store.outbox_row(db,name,row['signal_id']); state=None; reason=None
                if row['state']=='in_flight' and when>=row['lease_until_ms']: state,reason='ambiguous','worker_lease_elapsed'
                elif row['state'] in ('pending','retry_wait') and when>=row['expires_ms']: state,reason='expired','notice_expired'
                if state:
                    db.execute('UPDATE outbox SET state=?,reason=? WHERE signal_id=?',(state,reason,row['signal_id']))
                    self.store.delivery_event(db,name,row['signal_id'],'outbox_recovered',when); recovered+=1
        return dict(recovered=recovered)

    def send_one(self,name,preflight,transport):
        now=self.now(); self.recover(name,now); head=self.store.session(name); cfg=SessionSpec.from_dict(head['manifest']['spec']).runtime
        if cfg.mode!='paper_test': raise ValidationError('Shadow mode cannot dispatch Telegram')
        if getattr(transport,'bot_id',None)!=cfg.bot_id: raise ValidationError('Transport bot identity differs from frozen destination')
        if head['paused'] or head['fault']: return dict(status='blocked',reasons=['operator_pause' if head['paused'] else head['fault']])
        with self.store.connection() as db:
            rows=db.execute("SELECT o.signal_id FROM outbox o JOIN signals s ON s.id=o.signal_id WHERE s.session=? AND o.state IN ('pending','retry_wait') AND o.next_ms<=? ORDER BY o.next_ms,o.signal_id",(name,now)).fetchall()
        if not rows: return dict(status='idle')
        sid=rows[0][0]; signal=self.store.signal(sid)['signal']
        try: guard=preflight(head,signal,now)
        except Exception: guard=dict(ready=False,deferred=False,reasons=['send_check_failed'],checked_ms=now)
        if type(guard.get('ready')) is not bool or guard.get('checked_ms')!=now: raise ValidationError('Invalid pre-send evidence')
        stamp=self.now(); token=uuid.uuid4().hex; text=None
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE'); current=self.store._session(db,name); row=self.store.outbox_row(db,name,sid)
            if current['revision']!=head['revision'] or row['state'] not in ('pending','retry_wait') or row['next_ms']>stamp: return dict(status='conflict')
            if stamp<now or stamp>=row['expires_ms']:
                state='expired' if stamp>=row['expires_ms'] else 'suppressed'; reason='notice_expired' if state=='expired' else 'clock_moved_backward'
            elif current['paused'] or current['fault'] or stamp-now>=cfg.max_cycle_age_ms:
                state,reason='suppressed','send_context_no_longer_current'
            elif not guard['ready']:
                if guard.get('deferred'): return dict(status='deferred',reasons=guard['reasons'])
                state,reason='suppressed','fresh_send_check_rejected'
            elif row['attempts']>=cfg.max_attempts: state,reason='failed','attempt_budget_exhausted'
            else: state,reason=None,None
            if state:
                db.execute('UPDATE outbox SET state=?,reason=? WHERE signal_id=?',(state,reason,sid))
                self.store.delivery_event(db,name,sid,'outbox_suppressed',stamp,guard=guard)
                return dict(status=state,signal_id=sid,reasons=guard.get('reasons',[]))
            keys=[('bot:'+str(cfg.bot_id),cfg.bot_interval_ms),('chat:'+str(cfg.bot_id)+':'+str(cfg.chat_id),cfg.chat_interval_ms)]
            due=max([stamp]+[r[0] for key,_ in keys if (r:=db.execute('SELECT next_ms FROM throttle WHERE key=?',(key,)).fetchone())])
            if due>stamp: return dict(status='throttled',retry_at_ms=due)
            text=format_notice(head['manifest'],signal,guard); gh=self.store.put(db,guard); th=self.store.put(db,dict(kind='paper_message',text=text))
            db.execute("UPDATE outbox SET state='in_flight',attempts=attempts+1,attempt_token=?,lease_until_ms=?,guard_hash=?,text_hash=?,reason='http_attempt_claimed' WHERE signal_id=?",(token,stamp+cfg.lease_ms,gh,th,sid))
            for key,interval in keys: db.execute('INSERT INTO throttle VALUES(?,?) ON CONFLICT(key) DO UPDATE SET next_ms=excluded.next_ms',(key,stamp+interval))
            self.store.delivery_event(db,name,sid,'outbox_claimed',stamp)
        # The claim is durable before network I/O; abrupt termination remains ambiguous.
        before_http=self.now()
        if before_http<stamp or before_http>=signal['expires_ms']: result=DeliveryResult('failed','expired_before_http')
        else:
            try:
                result=transport.send(cfg.chat_id,text,min(cfg.http_timeout_ms,signal['expires_ms']-before_http))
                if not isinstance(result,DeliveryResult): result=DeliveryResult.from_dict(result)
            except Exception: result=DeliveryResult('ambiguous','transport_outcome_unknown')
        finished=self.now()
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE'); self.store._session(db,name); row=self.store.outbox_row(db,name,sid)
            if row['attempt_token']!=token or row['state'] not in ('in_flight','ambiguous'):
                self.store._event(db,name,'late_receipt_ignored',dict(signal_id=sid,attempt_token=token,result=result.document()),max(stamp,finished))
                return dict(status='late_receipt_ignored',signal_id=sid)
            state=result.status; reason=result.reason; next_ms=row['next_ms']
            if finished<before_http: state,reason='ambiguous','clock_moved_backward'
            elif reason=='expired_before_http': state='expired'
            elif state=='retry':
                next_ms=finished+max(result.retry_after_ms,cfg.retry_base_ms*2**(row['attempts']-1))
                state='failed' if row['attempts']>=cfg.max_attempts else 'expired' if next_ms>=row['expires_ms'] else 'retry_wait'
            db.execute('UPDATE outbox SET state=?,reason=?,next_ms=?,message_id=?,lease_until_ms=NULL WHERE signal_id=?',(state,reason,next_ms,result.message_id,sid))
            self.store.delivery_event(db,name,sid,'outbox_result',max(stamp,finished),result=result.document(),http_elapsed_ms=max(0,finished-before_http),accepted_after_expiry=result.status=='sent' and finished>=signal['expires_ms'])
        return dict(status=state,signal_id=sid,message_id=result.message_id)

    def reconcile(self,sid,decision,proof,message_id=None):
        evidence(proof); now=self.now()
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE'); record=db.execute('SELECT session FROM signals WHERE id=?',(sid,)).fetchone()
            if record is None: raise ValidationError('Unknown C14 signal')
            name=record[0]; head=self.store._session(db,name); cfg=SessionSpec.from_dict(head['manifest']['spec']).runtime; row=self.store.outbox_row(db,name,sid)
            if row is None or row['state']!='ambiguous' or decision not in ('sent','not_sent'): raise ValidationError('Only an ambiguous delivery can be explicitly reconciled')
            if now<head['control_ms'] or now<(head['cycle']['as_of_ms'] if head['cycle'] else 0): raise ValidationError('Reconciliation clock moved backward')
            if decision=='sent':
                DeliveryResult('sent','operator_confirmed',message_id); state='resolved_sent'
            else:
                if message_id is not None: raise ValidationError('Not-sent resolution cannot claim message acceptance')
                state='expired' if now>=row['expires_ms'] else 'suppressed' if head['paused'] or head['fault'] else 'failed' if row['attempts']>=cfg.max_attempts else 'retry_wait'
            db.execute('UPDATE outbox SET state=?,next_ms=?,message_id=?,attempt_token=NULL,lease_until_ms=NULL,reason=? WHERE signal_id=?',(state,now,message_id,'operator_'+decision,sid))
            self.store.delivery_event(db,name,sid,'outbox_reconciled',now,proof=proof,assertion=decision)
        return self.store.signal(sid)
