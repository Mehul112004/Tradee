from pathlib import Path
import sqlite3
import tempfile
import unittest
from tradee.c01 import ValidationError
from tradee.c10 import EstimatorStore
from tradee.c11 import SimulationStore
from tests.c10_support import *


class EstimatorPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
        self.ss=SimulationStore(self.root/'s.db'); r,_=simulation(); self.h=self.ss.commit(r)['run_hash']
        self.store=EstimatorStore(self.root/'e.db',clock=lambda:(window().cutoff_ms+100)/1000)

    def test_atomic_model_publication_fit_snapshot_and_idempotent_reads(self):
        a=self.store.fit(self.ss,[self.h],window(),config()); b=self.store.fit(self.ss,[self.h],window(),config())
        self.assertEqual(a,b); self.assertEqual(a['availability_basis'],'recorded'); self.assertTrue(a['ready'])
        self.store.training_snapshot(a['snapshot_hash']); self.store.fitted(a['fit_hash'])
        self.assertEqual(self.store.model(a['model_hash'])['fit_hash'],a['fit_hash'])
        with self.store.connection() as db:
            for table in ('snapshots','fits','models'): self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],1)

    def test_actual_publication_after_cutoff_and_explicit_modeled_publications(self):
        self.store.clock=lambda:0
        with self.assertRaises(ValidationError): self.store.fit(self.ss,[self.h],window(),config())
        a=self.store.fit(self.ss,[self.h],window(),config(),window().cutoff_ms)
        b=self.store.fit(self.ss,[self.h],window(),config(),window().cutoff_ms+1)
        self.assertEqual(a['fit_hash'],b['fit_hash']); self.assertNotEqual(a['model_hash'],b['model_hash'])
        self.assertEqual(a,self.store.fit(self.ss,[self.h],window(),config(),window().cutoff_ms))

    def test_sql_failure_rolls_back_every_training_artifact_and_retry_succeeds(self):
        with self.store.connection() as db: db.execute("CREATE TRIGGER fail BEFORE INSERT ON models BEGIN SELECT RAISE(ABORT,'injected C10 publication failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.store.fit(self.ss,[self.h],window(),config())
        with self.store.connection() as db:
            for table in ('snapshots','fits','models'): self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
            db.execute('DROP TRIGGER fail')
        self.assertTrue(EstimatorStore(self.root/'e.db').fit(self.ss,[self.h],window(),config())['ready'])

    def test_model_fit_and_snapshot_corruption_are_detected(self):
        a=self.store.fit(self.ss,[self.h],window(),config())
        for table,field in (('models','model_hash'),('fits','fit_hash'),('snapshots','snapshot_hash')):
            with self.store.connection() as db:
                old=db.execute('SELECT document FROM '+table+' WHERE hash=?',(a[field],)).fetchone()[0]
                db.execute('UPDATE '+table+" SET document='{}' WHERE hash=?",(a[field],))
            with self.assertRaises(ValidationError): self.store.summary(a['model_hash'])
            with self.store.connection() as db: db.execute('UPDATE '+table+' SET document=? WHERE hash=?',(old,a[field]))

    def test_wrong_store_aliases_versions_and_missing_records_fail(self):
        for p in (':memory:',self.ss.path):
            with self.assertRaises(ValidationError): EstimatorStore(p)
        with self.assertRaises(ValidationError): EstimatorStore(self.root/'e.db',forbidden_paths=[self.root/'e.db'])
        for method in (self.store.model,self.store.fitted,self.store.training_snapshot,self.store.estimate_record,self.store.evaluation):
            with self.assertRaises(ValidationError): method('unknown')

    def test_stored_inference_and_evaluation_are_immutable_and_idempotent(self):
        m=self.store.fit(self.ss,[self.h],window(),config(),window().cutoff_ms)
        r,_=simulation(start=START+13*BIN); later=self.ss.commit(r)['run_hash']; q=request(self.ss,later)
        a=self.store.estimate(m['model_hash'],q); b=self.store.estimate(m['model_hash'],q)
        self.assertEqual(a,b); self.assertEqual(self.store.estimate_record(a['estimate_hash']),a)
        e=self.store.evaluate(m['model_hash'],self.ss,[later],window(start=START+13*BIN))
        self.assertEqual(self.store.evaluation(e['evaluation_hash']),e)
        self.assertEqual(self.store.evaluate(m['model_hash'],self.ss,[later],window(start=START+13*BIN)),e)

    def test_insufficient_evidence_models_are_saved_without_ready_claims(self):
        from dataclasses import replace
        a=self.store.fit(self.ss,[self.h],window(),replace(config(),min_trades=30))
        self.assertFalse(a['ready']); self.assertEqual(self.store.summary(a['model_hash']),a)
