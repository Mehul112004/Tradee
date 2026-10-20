from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from tradee.c01 import ValidationError
from tradee.c03.contracts import FrozenRecord
from tradee.c13 import AccountSnapshot,PortfolioStore,PortfolioReplay,ReplayConfig
from tests.c13_support import setup,batch,policy


class PortfolioPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.ss,cls.pins,cls.model,cls.events=setup(cls.tmp.name)
        cls.state,cls.offers,execute=batch(cls.ss,cls.pins,cls.model,cls.events)
        cls.execute=staticmethod(execute)
        cls.result=PortfolioReplay(cls.ss,cls.pins,[cls.model],cls.events,policy(),ReplayConfig(initial_cash_usdt='320')).run()
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def setUp(self): self.local=tempfile.TemporaryDirectory(); self.s=PortfolioStore(Path(self.local.name)/'portfolio.db')
    def tearDown(self): self.local.cleanup()
    def test_complete_atomic_publication_reconciles_and_reopens(self):
        summary=self.s.commit(self.result); self.assertTrue(summary['ready'])
        self.assertEqual(PortfolioStore(self.s.path).summary(summary['run_hash']),summary)
        self.assertEqual(self.s.commit(self.result),summary)
        self.assertEqual(len(self.s.records(summary['run_hash'])),self.result[1].document()['artifact_count'])
        self.assertEqual(self.s.manifest(summary['run_hash'])['recipe_hash'],self.result[0].document()['recipe_hash'])
    def test_sql_failure_rolls_back_entire_replay_then_retry_completes(self):
        with self.s.connection() as db: db.execute("CREATE TRIGGER fail BEFORE INSERT ON replay_events BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.s.commit(self.result)
        with self.s.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM replays').fetchone()[0],0); db.execute('DROP TRIGGER fail')
        self.assertTrue(self.s.commit(self.result)['ready'])
    def test_metrics_and_wallet_reconciliation_validate_before_publication(self):
        for key in ('metrics','terminal_account'):
            m,r,e=self.result; d=r.document()
            if key=='metrics': d[key]['net_pnl_usdt']='9999'
            else: d[key]['cash_usdt']='9999'
            with self.assertRaises(ValidationError): self.s.commit((m,FrozenRecord.create(d),e))
        with self.s.connection() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0],0)
    def test_missing_event_and_corrupt_artifact_fail_reads(self):
        summary=self.s.commit(self.result)
        with self.s.connection() as db: db.execute('DELETE FROM replay_events WHERE sequence=1')
        with self.assertRaises(ValidationError): self.s.summary(summary['run_hash'])
        with self.s.connection() as db: db.execute("UPDATE artifacts SET document='{}' WHERE hash=?",(summary['run_hash'],))
        with self.assertRaisesRegex(ValidationError,'Corrupt'): self.s.artifact(summary['run_hash'])
    def test_wrong_artifact_kind_cannot_masquerade_as_manifest_or_report(self):
        s=self.s.commit(self.result)
        with self.assertRaises(ValidationError): self.s.manifest(s['report_hash'])
        with self.assertRaises(ValidationError): self.s.report(s['run_hash'])
    def test_atomic_reservation_preserves_cash_and_source_clock_and_is_idempotent(self):
        a=self.s.create_account('paper',self.state); h=a['snapshot_hash']
        result=self.s.allocate('paper',h,self.offers,policy(),self.execute); after=self.s.account('paper')
        self.assertEqual(after['revision'],1); self.assertEqual(after['snapshot']['cash_usdt'],self.state.cash_usdt)
        self.assertEqual(after['snapshot']['as_of_ms'],self.state.as_of_ms); self.assertEqual(len(after['snapshot']['reservations']),2)
        self.assertEqual(self.s.allocate('paper',h,list(reversed(self.offers)),policy(),lambda *a:self.fail('Cached retry executed')),result)
        self.assertEqual(self.s.account('paper')['revision'],1)
    def test_stale_compare_and_swap_rejected_without_partial_artifacts(self):
        a=self.s.create_account('p',self.state)
        with self.assertRaisesRegex(ValidationError,'compare-and-swap'): self.s.allocate('p','0'*64,self.offers,policy(),self.execute)
        self.assertEqual(self.s.account('p'),a)
    def test_interleaved_account_reconciliation_cannot_overwrite_reserved_capacity(self):
        a=self.s.create_account('p',self.state); changed=dict(self.state.document(),cash_usdt='319'); called=[]
        def concurrent(o,t):
            if not called:
                called.append(True); self.s.replace_snapshot('p',a['snapshot_hash'],changed)
            return self.execute(o,t)
        with self.assertRaisesRegex(ValidationError,'compare-and-swap'): self.s.allocate('p',a['snapshot_hash'],self.offers,policy(),concurrent)
        after=self.s.account('p'); self.assertEqual(after['revision'],1); self.assertEqual(after['snapshot']['cash_usdt'],'319')
        self.assertEqual(after['snapshot']['reservations'],[])
        with self.s.connection() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM batches').fetchone()[0],0)
    def test_failed_batch_transaction_restores_snapshot_and_artifact_inventory(self):
        a=self.s.create_account('p',self.state)
        with self.s.connection() as db:
            n=db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0]
            db.execute("CREATE TRIGGER fail BEFORE INSERT ON batches BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.s.allocate('p',a['snapshot_hash'],self.offers,policy(),self.execute)
        self.assertEqual(self.s.account('p'),a)
        with self.s.connection() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0],n)
    def test_explicit_reconciliation_clocks_and_journal_integrity(self):
        a=self.s.create_account('p',self.state); past=dict(self.state.document(),as_of_ms=self.state.as_of_ms-1,available_ms=self.state.available_ms-1,marks=[])
        with self.assertRaisesRegex(ValidationError,'backward'): self.s.replace_snapshot('p',a['snapshot_hash'],past)
        d=dict(self.state.document(),cash_usdt='319'); self.s.replace_snapshot('p',a['snapshot_hash'],d)
        with self.s.connection() as db: db.execute('DELETE FROM account_events WHERE revision=1')
        with self.assertRaisesRegex(ValidationError,'journal'): self.s.account('p')
    def test_cached_index_corruption_is_detected(self):
        a=self.s.create_account('p',self.state); self.s.allocate('p',a['snapshot_hash'],self.offers,policy(),self.execute)
        with self.s.connection() as db: db.execute('UPDATE batches SET after_hash=before_hash')
        with self.assertRaisesRegex(ValidationError,'cached'): self.s.allocate('p',a['snapshot_hash'],self.offers,policy(),self.execute)
    def test_database_identity_and_isolation_rejected(self):
        for path in (':memory:',self.ss.path):
            with self.assertRaises(ValidationError): PortfolioStore(path)
        with self.assertRaises(ValidationError): PortfolioStore(self.s.path,forbidden_paths=[self.s.path])
