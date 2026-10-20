from pathlib import Path
from copy import deepcopy
import sqlite3
import tempfile
import unittest
from tradee.c01 import ValidationError
from tradee.c03.contracts import FrozenRecord
from tradee.c14 import SignalStore
from tests.c14_support import deployment,cycle,STAMP,START


class SignalStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.path=Path(self.tmp.name)/'s.db'; self.s=SignalStore(self.path); self.s.create(deployment())
    def publish(self,**kw):
        c=cycle(self.s,**kw); return self.s.publish('paper',self.s.session('paper')['revision'],c,0)
    def test_deployment_and_cycle_are_immutable_idempotent_and_reopenable(self):
        first=self.s.session('paper'); self.assertEqual(self.s.create(deployment()),first)
        c=cycle(self.s); published=self.s.publish('paper',0,c,1)
        self.assertEqual(self.s.publish('paper',0,c,999),published)
        self.assertEqual(SignalStore(self.path).session('paper'),published)
        self.assertEqual(self.s.signals('paper')[0]['delivery']['state'],'pending')
    def test_changed_deployment_cannot_reuse_name(self):
        with self.assertRaises(ValidationError): self.s.create(deployment(max_notice_age_ms=11000))
    def test_cycle_book_signal_and_outbox_rollback_together(self):
        before=self.s.session('paper')
        with self.s.connection() as db:
            n=db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0]
            db.execute("CREATE TRIGGER fail BEFORE INSERT ON outbox BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.publish()
        self.assertEqual(self.s.session('paper'),before)
        with self.s.connection() as db:
            for table in ('cycles','signals','outbox'): self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0],n); db.execute('DROP TRIGGER fail')
        self.assertEqual(self.publish()['revision'],1)
    def test_cas_conflict_and_backward_source_clock_do_not_publish(self):
        self.publish()
        with self.assertRaises(ValidationError): self.s.publish('paper',0,cycle(self.s,when=STAMP+1),0)
        with self.assertRaises(ValidationError): self.publish(when=STAMP-1)
    def test_missing_stale_or_closed_paper_entry_never_queues_action(self):
        for kw in (dict(health=False),dict(when=STAMP+10000),dict(phase='paper_closed')):
            with self.subTest(kw=kw):
                with tempfile.TemporaryDirectory() as tmp:
                    s=SignalStore(Path(tmp)/'s'); s.create(deployment()); s.publish('paper',0,cycle(s,**kw),0)
                    self.assertEqual(s.signals('paper')[0]['delivery']['state'],'suppressed')
    def test_processing_latency_is_measured_and_enforced(self):
        h=self.s.publish('paper',0,cycle(self.s),5000)
        self.assertEqual(h['fault'],'processing_latency_exceeded'); self.assertEqual(self.s.signals('paper')[0]['delivery']['state'],'suppressed')
    def test_pause_resume_does_not_revive_old_notices(self):
        self.publish(); self.s.pause('paper',True,'maintenance',STAMP)
        self.assertEqual(self.s.signals('paper')[0]['delivery']['state'],'suppressed')
        self.s.pause('paper',False,'recovered',STAMP+1); self.publish(when=STAMP+1)
        self.assertEqual(self.s.signals('paper')[0]['delivery']['state'],'suppressed')
    def test_new_candidate_can_queue_after_recovery_but_old_identity_stays_suppressed(self):
        self.publish(); self.s.fault('paper','pipeline_failed',STAMP)
        self.publish(when=STAMP+1,extra='f'*64)
        states={x['signal']['signal_id']:x['delivery']['state'] for x in self.s.signals('paper')}
        self.assertEqual(states['c'*64],'suppressed'); self.assertEqual(states['f'*64],'pending')
    def test_shadow_tracks_paper_without_any_outbox(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=SignalStore(Path(tmp)/'s'); s.create(deployment(mode='shadow',bot_id=None,chat_id=None)); s.publish('paper',0,cycle(s),0)
            self.assertIsNone(s.signals('paper')[0]['delivery'])
    def test_historical_admission_cannot_disappear_or_change_fill(self):
        self.publish()
        for mutate in (lambda d:d.update(signals=[]),lambda d:d['signals'][0].update(entry_ms=None),lambda d:d['signals'][0]['decision']['execution']['fill'].update(price='103')):
            d=cycle(self.s,when=STAMP+1).document(); mutate(d)
            with self.assertRaisesRegex(ValidationError,'Historical'): self.s.publish('paper',1,FrozenRecord.create(d),0)
    def test_signal_and_delivery_index_corruption_fail_closed(self):
        self.publish(); sid='c'*64
        with self.s.connection() as db: db.execute("UPDATE outbox SET attempts=9 WHERE signal_id=?",(sid,))
        with self.assertRaisesRegex(ValidationError,'delivery index'): self.s.signal(sid)
    def test_signal_inventory_missing_or_repointed_to_old_cycle_is_detected(self):
        self.publish(); old=self.s.signal('c'*64)['document_hash']; self.publish(when=STAMP+1,phase='paper_closed')
        with self.s.connection() as db: db.execute('UPDATE signals SET document_hash=?',(old,))
        with self.assertRaisesRegex(ValidationError,'current cycle'): self.s.signal('c'*64)
        with self.assertRaisesRegex(ValidationError,'inventory'): self.s.signals('paper')
    def test_artifact_audit_revision_and_pause_corruption_detected(self):
        with self.s.connection() as db: db.execute('UPDATE sessions SET paused=1')
        with self.assertRaisesRegex(ValidationError,'pause index'): self.s.session('paper')
        with self.s.connection() as db: db.execute('UPDATE sessions SET paused=0,revision=7')
        with self.assertRaisesRegex(ValidationError,'revision'): self.s.session('paper')
        with self.s.connection() as db: db.execute("UPDATE artifacts SET document='{}'")
        with self.assertRaisesRegex(ValidationError,'Corrupt'): self.s.session('paper')
    def test_resource_budgets_abort_without_truncation(self):
        for cfg in (dict(max_cycle_bytes=1),dict(max_candidates=1),dict(max_cycles=1)):
            with self.subTest(cfg=cfg),tempfile.TemporaryDirectory() as tmp:
                s=SignalStore(Path(tmp)/'s'); s.create(deployment(**cfg))
                if 'max_cycles' in cfg:
                    s.publish('paper',0,cycle(s),0)
                    with self.assertRaises(ValidationError): s.publish('paper',1,cycle(s,when=STAMP+1),0)
                else:
                    with self.assertRaises(ValidationError): s.publish('paper',0,cycle(s,extra='e'*64),0)
    def test_own_database_unknown_records_and_clock_bounds(self):
        for p in (':memory:',self.path):
            with self.assertRaises(ValidationError): SignalStore(p,forbidden_paths=[self.path])
        for fn in (lambda:self.s.session('missing'),lambda:self.s.signal('x'),lambda:self.s.artifact('x'),lambda:self.s.pause('paper',True,'why',START-1)):
            with self.assertRaises(ValidationError): fn()
    def test_status_exposes_staleness_and_keeps_live_disabled(self):
        self.publish(); self.assertTrue(self.s.status('paper',STAMP)['ready'])
        self.assertFalse(self.s.status('paper',STAMP+5000)['ready']); self.assertFalse(self.s.status('paper',STAMP)['live_approved'])
