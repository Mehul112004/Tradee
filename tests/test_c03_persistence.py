import json
import unittest
import sqlite3
from copy import deepcopy
from tradee.c01 import ValidationError
from tradee.c03 import FeatureConfig, FeatureEngine, FeatureStore
from tradee.c03.contracts import FeatureSnapshot
from tests.c02_support import DataCase, START, row


class PersistenceTests(DataCase):
    def prepared(self):
        # Deliberately ingest out of market-time order: modeled replay IDs decrease.
        self.ingest([row(START+i*60000, str(100+i%4)) for i in reversed(range(8))])
        d=self.store.snapshot(['BTCUSDT'],START,START+8*60000,mode='modeled',delay_ms=0)
        c=FeatureConfig(features=('log_return_1',),timeframes=('1m',),require_stable=False)
        return d,c,FeatureStore(self.root/'c03.sqlite3',clock=lambda:123)

    def test_real_c02_resume_and_idempotency(self):
        d,c,s=self.prepared(); events=list(self.store.replay(d['dataset_hash']))
        self.assertGreater(events[0]['id'],events[-1]['id'])
        a=FeatureEngine(d,c); outputs=list(a.run(events[:3])); s.commit(a,outputs)
        result=s.run(self.store,d['dataset_hash'],c,batch_size=2)
        self.assertEqual(result['snapshots'],8)
        self.assertEqual(result['ready_snapshots'],7)
        self.assertEqual(s.run(self.store,d['dataset_hash'],c),result)
        b=FeatureEngine(d,c)
        for snapshot in b.run(events):
            doc=s.snapshot(snapshot.digest); doc.pop('snapshot_hash')
            self.assertEqual(doc,snapshot.document())
            link=doc['lineage_hash']
            while link: link=s.lineage(link)['parent']
        with s.connection() as db:
            self.assertEqual({r[0] for r in db.execute('SELECT computed_at_ms FROM snapshots')},{123000})

    def test_atomic_rollback_and_retry(self):
        d,c,s=self.prepared(); a=FeatureEngine(d,c); events=list(self.store.replay(d['dataset_hash']))
        first=a.advance(events[0]); s.commit(a,first)
        before=s.load_checkpoint(a.manifest.digest)
        second=a.advance(events[1]); bad=second[0].document(); bad['run_hash']='wrong'
        with self.assertRaises(ValidationError): s.commit(a,second+[FeatureSnapshot.create(bad)])
        self.assertEqual(s.load_checkpoint(a.manifest.digest),before)
        self.assertEqual(s.summary(a.manifest.digest)['snapshots'],1)
        self.assertTrue(a.lineages)
        s.commit(a,second)
        self.assertEqual(s.summary(a.manifest.digest)['snapshots'],2)

    def test_conflicting_prefix_and_backward_checkpoint(self):
        d,c,s=self.prepared(); a=FeatureEngine(d,c); events=list(self.store.replay(d['dataset_hash']))
        first=a.advance(events[0]); cp=a.checkpoint(); s.commit(a,first)
        a.prefix_hash='conflict'
        with self.assertRaises(ValidationError): s.commit(a,[])
        a=FeatureEngine.restore(d,c,cp); s.commit(a,a.advance(events[1]))
        old=FeatureEngine.restore(d,c,cp)
        with self.assertRaises(ValidationError): s.commit(old,[])

    def test_database_alias_and_wrong_schema_rejected(self):
        d,c,s=self.prepared()
        for path in (self.registry.path,self.store.path):
            with self.assertRaises(ValidationError): FeatureStore(path)
        with self.assertRaises(ValidationError): FeatureStore(self.root/'c03.sqlite3',forbidden_paths=(self.root/'c03.sqlite3',))

    def test_corruption_is_detected(self):
        d,c,s=self.prepared(); a=FeatureEngine(d,c); out=list(a.run(self.store.replay(d['dataset_hash']))); s.commit(a,out)
        with s.connection() as db:
            db.execute("UPDATE checkpoints SET document='{}'")
            db.execute("UPDATE snapshots SET document='{}' WHERE hash=?",(out[0].digest,))
        with self.assertRaises(ValidationError): s.load_checkpoint(a.manifest.digest)
        with self.assertRaises(ValidationError): s.snapshot(out[0].digest)

    def test_sql_failure_cannot_commit_outputs_without_checkpoint(self):
        d,c,s=self.prepared(); a=FeatureEngine(d,c)
        events=list(self.store.replay(d['dataset_hash']))
        s.commit(a,a.advance(events[0])); before=s.load_checkpoint(a.manifest.digest)
        with s.connection() as db:
            db.execute("CREATE TRIGGER fail_checkpoint BEFORE INSERT ON checkpoints BEGIN SELECT RAISE(ABORT, 'injected crash'); END")
        pending=a.advance(events[1])
        with self.assertRaises(sqlite3.IntegrityError): s.commit(a,pending)
        self.assertEqual(s.summary(a.manifest.digest)['snapshots'],1)
        self.assertEqual(s.load_checkpoint(a.manifest.digest),before)
        with s.connection() as db: db.execute('DROP TRIGGER fail_checkpoint')
        s.commit(a,pending)
        self.assertEqual(s.summary(a.manifest.digest)['snapshots'],2)

    def test_recorded_historical_download_is_not_fresh(self):
        self.ingest([row(START),row(START+60000)])
        d=self.store.snapshot(['BTCUSDT'],START,START+120000)
        c=FeatureConfig(features=('log_return_1',),timeframes=('1m',),require_stable=False)
        a=FeatureEngine(d,c); out=list(a.run(self.store.replay(d['dataset_hash'])))
        self.assertFalse(out[-1].document()['ready'])
        self.assertEqual(out[-1].document()['values']['log_return_1']['status'],'stale_input')
