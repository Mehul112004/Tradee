from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c15 import MonitorStore


def manifest(name='forward',deployment='a'*64):
    return dict(kind='forward_monitor',name=name,deployment_hash=deployment,registered_ms=100,live_approved=False)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.path=Path(self.tmp.name)/'m.db'
        self.s=MonitorStore(self.path); self.h=self.s.register(manifest())

    def report(self,**kw):
        return dict(dict(kind='forward_report',manifest_hash=self.h['manifest_hash'],observed_ms=200,
            source=dict(deployment_hash='a'*64,event_hashes=['b'*64]),reviews=[],live_approved=False),**kw)

    def test_register_reopen_and_idempotent_publish(self):
        self.assertEqual(self.s.register(manifest()),self.h)
        r=self.s.publish('forward',0,'x',self.report())
        self.assertEqual(self.s.publish('forward',0,'x',self.report()),r)
        self.assertEqual(MonitorStore(self.path).head('forward')['report_hash'],r['report_hash'])
        self.assertEqual(self.s.cached('forward','x'),r)

    def test_policy_name_and_deployment_cannot_be_reused(self):
        for m in (manifest(deployment='f'*64),manifest('other')):
            with self.subTest(m=m),self.assertRaises(ValidationError): self.s.register(m)

    def test_cas_and_backward_clock(self):
        self.s.publish('forward',0,'x',self.report())
        with self.assertRaisesRegex(ValidationError,'compare-and-swap'): self.s.publish('forward',0,'y',self.report(observed_ms=201))
        with self.assertRaisesRegex(ValidationError,'clock'): self.s.publish('forward',1,'y',self.report(observed_ms=199))

    def test_conflicting_idempotency_key_is_rejected(self):
        self.s.publish('forward',0,'x',self.report())
        with self.assertRaisesRegex(ValidationError,'Conflicting'): self.s.publish('forward',0,'x',self.report(observed_ms=201))

    def test_source_prefix_and_prior_review_are_immutable(self):
        self.s.publish('forward',0,'x',self.report(reviews=[dict(status='insufficient_evidence')]))
        for r in (self.report(source=dict(deployment_hash='a'*64,event_hashes=['c'*64])),self.report(reviews=[])):
            with self.subTest(r=r),self.assertRaises(ValidationError): self.s.publish('forward',1,'y',r)

    def test_report_and_index_and_journal_rollback_together(self):
        with self.s.connection() as db:
            count=db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0]
            db.execute("CREATE TRIGGER fail BEFORE INSERT ON observations BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.s.publish('forward',0,'x',self.report())
        self.assertEqual(self.s.head('forward'),self.h)
        with self.s.connection() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0],count)

    def test_concurrent_writer_cas_has_one_winner(self):
        def publish(i):
            try: self.s.publish('forward',0,str(i),self.report(observed_ms=200+i)); return 'committed'
            except ValidationError: return 'conflict'
        with ThreadPoolExecutor(2) as executor: values=list(executor.map(publish,range(2)))
        self.assertCountEqual(values,['committed','conflict']); self.assertEqual(self.s.head('forward')['revision'],1)

    def test_corrupt_artifact_fails_closed(self):
        r=self.s.publish('forward',0,'x',self.report())
        with self.s.connection() as db: db.execute("UPDATE artifacts SET document='{}' WHERE hash=?",(r['report_hash'],))
        with self.assertRaisesRegex(ValidationError,'Corrupt'): self.s.head('forward')

    def test_deleted_index_or_forged_head_fails_closed(self):
        self.s.publish('forward',0,'x',self.report())
        with self.s.connection() as db: db.execute('DELETE FROM observations')
        with self.assertRaisesRegex(ValidationError,'Missing'): self.s.head('forward')

    def test_journal_gaps_and_deleted_root_fail_closed(self):
        self.s.publish('forward',0,'x',self.report())
        with self.s.connection() as db: db.execute('DELETE FROM journal WHERE sequence=1')
        with self.assertRaisesRegex(ValidationError,'journal'): self.s.head('forward')

    def test_separate_database_and_application_schema(self):
        with self.assertRaises(ValidationError): MonitorStore(':memory:')
        with self.assertRaises(ValidationError): MonitorStore(self.path,forbidden_paths=[self.path])
        foreign=Path(self.tmp.name)/'foreign'
        with closing(sqlite3.connect(foreign)) as db:
            db.execute('CREATE TABLE something(x)'); db.commit()
        with self.assertRaises(ValidationError): MonitorStore(foreign)

    def test_pause_receipt_idempotency_and_corruption(self):
        r=self.s.publish('forward',0,'x',self.report()); receipt=dict(report_hash=r['report_hash'],at_ms=200,paused=True)
        self.assertEqual(self.s.receipt('forward',r['report_hash'],receipt),receipt)
        self.assertEqual(self.s.receipt('forward',r['report_hash'],receipt),receipt)
        with self.assertRaises(ValidationError): self.s.receipt('forward',r['report_hash'],dict(receipt,at_ms=201))
        with self.s.connection() as db: db.execute("UPDATE pauses SET receipt_hash=?",(self.h['manifest_hash'],))
        with self.assertRaises((ValidationError,KeyError)): self.s.head('forward')
