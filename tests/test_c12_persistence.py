from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from tradee.c01 import ValidationError
from tradee.c12 import ResearchStore
from tests.c12_support import plan,START,BIN


class ResearchRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.path=Path(self.tmp.name)/'r.db'; self.s=ResearchStore(self.path)
    def register(self,**kw): return self.s.register(plan(**kw))['experiment_hash']
    def alternative(self,name,start,budget=8):
        d=plan(name=name,family_trial_budget=budget); d['policy']['bootstrap_replicates']=400
        d['holdout']['split']['test']=dict(start_ms=START+start*BIN,end_ms=START+(start+12)*BIN,cutoff_ms=START+(start+12)*BIN)
        return d

    def test_registration_idempotence_preserves_complete_variant_inventory(self):
        h=self.register(); first=self.s.events(h); self.assertEqual(self.register(),h); self.assertEqual(self.s.events(h),first)
        self.assertEqual(len(self.s.ledger('range')['experiments'][0]['variants']),4)
        self.assertEqual(self.s.ledger('range')['remaining_trials'],0)

    def test_cumulative_budget_cannot_reset_with_new_experiment_or_code(self):
        a=self.alternative('first',48); b=self.alternative('second',64); c=self.alternative('third',80)
        self.s.register(a); self.s.register(b)
        self.assertEqual(self.s.ledger('range')['used_trials'],8)
        with self.assertRaisesRegex(ValidationError,'exhausted'): self.s.register(c)
        c['family_trial_budget']=10
        with self.assertRaisesRegex(ValidationError,'cannot be reset'): self.s.register(c)

    def test_holdout_period_cannot_be_resealed_under_another_family(self):
        self.register(); d=plan(family='another')
        with self.assertRaisesRegex(ValidationError,'reserved or consumed'): self.s.register(d)

    def test_new_development_history_cannot_inspect_reserved_period(self):
        self.register(); d=plan(name='new',family='new')
        d['holdout']['split']['test']=dict(start_ms=START+80*BIN,end_ms=START+92*BIN,cutoff_ms=START+92*BIN)
        d['holdout']['split']['train'].update(end_ms=START+64*BIN,cutoff_ms=START+64*BIN)
        with self.assertRaisesRegex(ValidationError,'overlaps a reserved'): self.s.register(d)

    def test_own_database_and_forbidden_paths(self):
        for p in (':memory:',self.path):
            with self.assertRaises(ValidationError): ResearchStore(p,forbidden_paths=(self.path,))
        p=Path(self.tmp.name)/'foreign.db'
        from contextlib import closing
        with closing(sqlite3.connect(p)) as db:
            db.execute('CREATE TABLE unrelated(x)'); db.commit()
        with self.assertRaises(ValidationError): ResearchStore(p)

    def test_atomic_publication_failure_ledger_and_retry(self):
        h=self.register()
        with self.s.connection() as db: db.execute("CREATE TRIGGER fail BEFORE INSERT ON artifacts BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError,'injected'): self.s._job(h,'fixture',lambda:dict(result=1))
        with self.s.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0],0); db.execute('DROP TRIGGER fail')
        self.assertEqual(self.s.jobs(h)[0]['status'],'failed'); self.assertEqual(self.s._job(h,'fixture',lambda:dict(result=1)),dict(result=1))
        self.assertEqual(self.s.jobs(h)[0]['attempts'],2)
        self.s._job(h,'fixture',lambda:(_ for _ in ()).throw(AssertionError('must not recompute')))

    def test_process_interruption_leaves_running_job_resumable(self):
        h=self.register()
        with self.assertRaises(KeyboardInterrupt): self.s._job(h,'interrupted',lambda:(_ for _ in ()).throw(KeyboardInterrupt()))
        self.assertEqual(self.s.jobs(h)[0]['status'],'running')
        self.s._job(h,'interrupted',lambda:{'done':True}); self.assertEqual(self.s.jobs(h)[0]['attempts'],2)

    def test_artifact_and_event_corruption_fail_closed(self):
        h=self.register(); self.s._job(h,'fixture',lambda:dict(x=1)); artifact=self.s.jobs(h)[0]['artifact']
        with self.s.connection() as db: db.execute("UPDATE artifacts SET document='{}' WHERE hash=?",(artifact,))
        with self.assertRaisesRegex(ValidationError,'Corrupt research artifact'): self.s.jobs(h)
        with self.s.connection() as db: db.execute("UPDATE events SET document='{}' WHERE experiment=? AND sequence=1",(h,))
        with self.assertRaisesRegex(ValidationError,'audit chain'): self.s.events(h)

    def test_deleted_completed_job_cannot_be_silently_rerun(self):
        h=self.register(); self.s._job(h,'done',lambda:dict(x=1))
        with self.s.connection() as db: db.execute('DELETE FROM jobs WHERE experiment=?',(h,))
        with self.assertRaisesRegex(ValidationError,'missing'): self.s._job(h,'done',lambda:dict(x=2))

    def test_changed_experiment_document_detected(self):
        h=self.register()
        with self.s.connection() as db: db.execute("UPDATE experiments SET document='{}' WHERE hash=?",(h,))
        with self.assertRaisesRegex(ValidationError,'manifest'): self.s.manifest(h)

    def test_kernel_lock_prevents_concurrent_runners(self):
        other=ResearchStore(self.path)
        with self.s._lock():
            with self.assertRaisesRegex(ValidationError,'already active'):
                with other._lock(): pass
        with other._lock(): pass

    def test_history_count_is_in_ledger(self):
        d=self.alternative('history',48); d['historical_trials']=2
        self.s.register(d); self.assertEqual(self.s.ledger('range')['used_trials'],6)

    def test_artifact_size_bound_no_partial_publication(self):
        h=self.register()
        # Patch the record wrapper to avoid allocating a huge fixture.
        from tradee.c03.contracts import FrozenRecord
        class Oversize:
            serialized=''
            def __init__(self): self.serialized=type('LengthOnly',(),{'__len__':lambda s:50000001})()
        original=FrozenRecord.create
        def create(d): return Oversize() if d=={'oversize':True} else original(d)
        with patch('tradee.c12.store.FrozenRecord.create',side_effect=create):
            with self.assertRaisesRegex(ValidationError,'byte budget'): self.s._job(h,'oversize',lambda:dict(oversize=True))

    def test_reader_uses_one_snapshot_when_another_connection_completes_a_job(self):
        from contextlib import contextmanager
        import threading
        h=self.register(); self.s._job(h,'first',lambda:dict(result=1))
        with self.s.connection() as db: db.execute('PRAGMA journal_mode=WAL')
        other=ResearchStore(self.path); original=self.s.connection; errors=[]; triggered=[]
        def write():
            try: other._job(h,'second',lambda:dict(result=2))
            except Exception as exc: errors.append(exc)
        def interleave(sql):
            if sql.startswith('SELECT * FROM jobs') and not triggered:
                triggered.append(True); worker=threading.Thread(target=write); worker.start(); worker.join(timeout=5)
                if worker.is_alive(): errors.append(AssertionError('Concurrent writer blocked by reader'))
        @contextmanager
        def connection():
            with original() as db:
                db.set_trace_callback(interleave)
                yield db
        with patch.object(self.s,'connection',connection):
            seen=self.s.jobs(h)
        self.assertFalse(errors,errors); self.assertTrue(triggered)
        self.assertEqual([j['key'] for j in seen],['first'])
        self.assertEqual([j['key'] for j in self.s.jobs(h)],['first','second'])
