from pathlib import Path
import sqlite3
import tempfile
import unittest
from tradee.c01 import ValidationError
from tradee.c14 import SignalStore,Dispatcher,DeliveryResult
from tests.c14_support import deployment,cycle,ready,Clock,STAMP,BOT,ScriptedTelegram


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.s=SignalStore(Path(self.tmp.name)/'s.db'); self.s.create(deployment()); self.s.publish('paper',0,cycle(self.s),0)
        self.clock=Clock(); self.d=Dispatcher(self.s,self.clock); self.sid='c'*64
    def row(self): return self.s.signal(self.sid)['delivery']
    def test_confirmed_acceptance_is_persistent_without_duplicate_retry(self):
        wire=ScriptedTelegram([DeliveryResult('sent','telegram_accepted',12)])
        self.assertEqual(self.d.send_one('paper',ready,wire)['status'],'sent'); self.assertEqual(self.row()['message_id'],12)
        self.assertEqual(Dispatcher(SignalStore(self.s.path),self.clock).send_one('paper',ready,wire)['status'],'idle'); self.assertEqual(len(wire.calls),1)
    def test_explicit_429_backoff_and_chat_throttle_persist(self):
        wire=ScriptedTelegram([DeliveryResult('retry','telegram_rate_limited',retry_after_ms=1000),DeliveryResult('sent','telegram_accepted',2)])
        self.assertEqual(self.d.send_one('paper',ready,wire)['status'],'retry_wait')
        self.clock.ms+=1000; self.assertEqual(self.d.send_one('paper',ready,wire)['status'],'throttled')
        self.clock.ms+=2500; self.assertEqual(self.d.send_one('paper',ready,wire)['status'],'sent')
    def test_retry_after_extending_past_expiry_expires_instead_of_sending(self):
        self.assertEqual(self.d.send_one('paper',ready,ScriptedTelegram([DeliveryResult('retry','telegram_rate_limited',retry_after_ms=20000)]))['status'],'expired')
    def test_http_timeout_is_ambiguous_and_never_auto_retried(self):
        wire=ScriptedTelegram([DeliveryResult('ambiguous','network_outcome_unknown')]); self.d.send_one('paper',ready,wire)
        self.clock.ms+=20000; self.d.recover('paper'); self.assertEqual(self.row()['state'],'ambiguous')
        self.assertEqual(self.d.send_one('paper',ready,wire)['status'],'idle'); self.assertEqual(len(wire.calls),1)
        self.assertIn('delivery_reconciliation_required',self.s.status('paper',self.clock.ms)['reasons'])
    def test_abrupt_worker_loss_leaves_durable_claim_then_ambiguous_lease(self):
        with self.assertRaises(KeyboardInterrupt): self.d.send_one('paper',ready,ScriptedTelegram([KeyboardInterrupt()]))
        self.assertEqual(self.row()['state'],'in_flight'); self.clock.ms+=15000
        Dispatcher(SignalStore(self.s.path),self.clock).recover('paper'); self.assertEqual(self.row()['state'],'ambiguous')
    def test_no_retry_while_other_worker_holds_lease(self):
        with self.assertRaises(KeyboardInterrupt): self.d.send_one('paper',ready,ScriptedTelegram([KeyboardInterrupt()]))
        wire=ScriptedTelegram([]); self.assertEqual(Dispatcher(self.s,self.clock).send_one('paper',ready,wire)['status'],'idle'); self.assertFalse(wire.calls)
    def test_concurrent_control_change_before_claim_cannot_send(self):
        def interleave(h,s,t): self.s.pause('paper',True,'maintenance',t); return ready(h,s,t)
        wire=ScriptedTelegram([]); self.assertEqual(self.d.send_one('paper',interleave,wire)['status'],'conflict'); self.assertFalse(wire.calls)
    def test_claim_publication_failure_rolls_back_before_network(self):
        with self.s.connection() as db: db.execute("CREATE TRIGGER fail BEFORE INSERT ON audit WHEN NEW.sequence>=4 BEGIN SELECT RAISE(ABORT,'injected'); END")
        wire=ScriptedTelegram([])
        with self.assertRaises(sqlite3.IntegrityError): self.d.send_one('paper',ready,wire)
        self.assertEqual(self.row()['state'],'pending'); self.assertEqual(self.row()['attempts'],0); self.assertFalse(wire.calls)
    def test_receipt_commit_failure_leaves_unknown_outcome_for_recovery(self):
        with self.s.connection() as db: db.execute("CREATE TRIGGER fail BEFORE INSERT ON audit WHEN NEW.sequence>=5 BEGIN SELECT RAISE(ABORT,'injected'); END")
        wire=ScriptedTelegram([DeliveryResult('sent','telegram_accepted',22)])
        with self.assertRaises(sqlite3.IntegrityError): self.d.send_one('paper',ready,wire)
        self.assertEqual(self.row()['state'],'in_flight'); self.assertEqual(len(wire.calls),1)
        with self.s.connection() as db: db.execute('DROP TRIGGER fail')
        self.clock.ms+=15000; self.d.recover('paper'); self.assertEqual(self.row()['state'],'ambiguous')
    def test_positive_late_receipt_is_recorded_even_after_lease_or_expiry(self):
        outer=self
        class Slow:
            bot_id=BOT
            def send(self,*args):
                outer.clock.ms+=20000; Dispatcher(outer.s,outer.clock).recover('paper'); return DeliveryResult('sent','telegram_accepted',99)
        self.assertEqual(self.d.send_one('paper',ready,Slow())['status'],'sent')
        self.assertTrue(self.s.events('paper')[-1]['payload']['accepted_after_expiry'])
    def test_expiry_before_attempt_never_calls_network(self):
        self.clock.ms+=10000; wire=ScriptedTelegram([])
        self.assertEqual(self.d.send_one('paper',ready,wire)['status'],'idle'); self.assertEqual(self.row()['state'],'expired'); self.assertFalse(wire.calls)
    def test_rejected_or_deferred_guard_does_not_attempt_delivery(self):
        for deferred in (True,False):
            def reject(h,s,t): return dict(ready=False,deferred=deferred,reasons=['needs_tick'],checked_ms=t)
            result=self.d.send_one('paper',reject,ScriptedTelegram([]))
            self.assertEqual(result['status'],'deferred' if deferred else 'suppressed'); self.assertEqual(self.row()['attempts'],0)
    def test_preflight_exception_is_redacted_and_blocks_delivery(self):
        token='sensitive-token-value'
        def fail(*args): raise RuntimeError(token)
        self.d.send_one('paper',fail,ScriptedTelegram([])); self.assertNotIn(token,str(self.s.events('paper'))); self.assertEqual(self.row()['state'],'suppressed')
    def test_transport_exception_is_redacted_and_ambiguous(self):
        token='sensitive-token-value'; self.d.send_one('paper',ready,ScriptedTelegram([RuntimeError(token)]))
        self.assertEqual(self.row()['state'],'ambiguous'); self.assertNotIn(token,str(self.s.events('paper')))
    def test_operator_acceptance_assertion_resolves_only_ambiguous(self):
        with self.assertRaises(ValidationError): self.d.reconcile(self.sid,'sent','proof',1)
        self.d.send_one('paper',ready,ScriptedTelegram([DeliveryResult('ambiguous','network_outcome_unknown')]))
        with self.assertRaises(ValidationError): self.d.reconcile(self.sid,'sent','proof')
        self.d.reconcile(self.sid,'sent','Operator saw exact signal identifier',123); self.assertEqual(self.row()['state'],'resolved_sent')
    def test_definitive_not_sent_can_retry_only_before_expiry(self):
        self.d.send_one('paper',ready,ScriptedTelegram([DeliveryResult('ambiguous','network_outcome_unknown')]))
        self.d.reconcile(self.sid,'not_sent','Explicit synthetic non-acceptance assertion'); self.assertEqual(self.row()['state'],'retry_wait')
        self.clock.ms+=10000; self.d.recover('paper'); self.assertEqual(self.row()['state'],'expired')
    def test_shadow_or_mismatched_bot_never_dispatches(self):
        wire=ScriptedTelegram([]); wire.bot_id=BOT+1
        with self.assertRaises(ValidationError): self.d.send_one('paper',ready,wire)
    def test_stable_plain_message_contains_evidence_expiry_and_no_action_claim(self):
        wire=ScriptedTelegram([DeliveryResult('sent','telegram_accepted',3)]); self.d.send_one('paper',ready,wire); body=wire.calls[0]['text']
        for value in ('NO TRADE INSTRUCTION',self.sid,'Notice expires:','Planned stop:','Lower mean net R:','not a user fill'): self.assertIn(value,body)
        self.assertLessEqual(len(body),4096); self.assertLessEqual(wire.calls[0]['timeout_ms'],3000)

    def test_real_concurrent_worker_cannot_claim_a_second_http_attempt(self):
        import threading
        entered=threading.Event(); release=threading.Event(); errors=[]; receipts=[]
        class Blocking:
            bot_id=BOT
            def send(self,*args):
                entered.set()
                if not release.wait(5): raise RuntimeError('Test worker timeout')
                return DeliveryResult('sent','telegram_accepted',45)
        def worker():
            try: receipts.append(Dispatcher(SignalStore(self.s.path),self.clock).send_one('paper',ready,Blocking()))
            except Exception as exc: errors.append(exc)
        thread=threading.Thread(target=worker); thread.start()
        try:
            self.assertTrue(entered.wait(5)); wire=ScriptedTelegram([])
            self.assertEqual(self.d.send_one('paper',ready,wire)['status'],'idle'); self.assertFalse(wire.calls)
        finally: release.set(); thread.join(5)
        self.assertFalse(thread.is_alive()); self.assertEqual(errors,[]); self.assertEqual(receipts[0]['status'],'sent'); self.assertEqual(self.row()['attempts'],1)
