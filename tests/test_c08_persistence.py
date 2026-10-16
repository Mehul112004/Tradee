from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from tradee.c01 import Registry,ValidationError
from tradee.c02 import MarketStore
from tradee.c08 import CandidateStore,CandidateConfig,CandidateEngine
from tradee.c08.metadata import capture
from tests.c08_support import *


class CandidatePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name); self.now=START
        self.registry=Registry(self.root/'c01.sqlite3',clock=lambda:self.now/1000)
        self.registry.ingest(json.dumps(metadata()[0])); self.now+=3*MINUTE
        self.market=MarketStore(self.registry,self.root/'c02.sqlite3',clock=lambda:self.now/1000)
        rows=[]
        for i,c in enumerate(('100','100','102')):
            e=event(i,c); d=e['data']
            rows.append([d[k] for k in ('open_ms','open','high','low','close','volume','close_ms','quote_volume','trades','taker_base','taker_quote')]+['0'])
        self.market.ingest_rest(json.dumps(rows),'BTCUSDT')
        self.ds=self.market.snapshot(['BTCUSDT'],START,START+3*MINUTE,kinds=('candle',))
        self.strategy=spec(); self.config=CandidateConfig(); self.store=CandidateStore(self.root/'c08.sqlite3',clock=lambda:123)

    def run_case(self,**kw): return self.store.run(self.market,self.ds['dataset_hash'],self.strategy,self.config,**kw)

    def make_engine(self):
        snapshots,versions=capture(self.registry,self.ds,self.config)
        return CandidateEngine(self.ds,self.strategy,snapshots,versions,self.config)

    def test_real_store_replay_inventory_feature_lineage_and_idempotency(self):
        result=self.run_case(batch_size=1); self.assertTrue(result['completed']); self.assertEqual(result['evaluations'],6); self.assertEqual(result['emitted_candidates'],1)
        records=self.store.records(result['run_hash']); self.assertEqual([r['sequence'] for r in records['records']],list(range(1,7)))
        emitted=self.store.records(result['run_hash'],status='emitted')['records'][0]
        self.assertEqual(emitted['candidate']['reference_price'],'102')
        feature=self.store.feature(emitted['feature_snapshot_hash']); self.assertEqual(feature['values']['log_return_1']['status'],'valid')
        self.assertTrue(self.store.lineage(feature['lineage_hash']))
        self.assertEqual(self.run_case(batch_size=2),result)
        with self.store.connection() as db: self.assertEqual({r[0] for r in db.execute('SELECT computed_at_ms FROM evaluations')},{123000})

    def test_atomic_failure_rolls_back_features_inventory_and_checkpoint(self):
        a=self.make_engine(); events=list(self.market.replay(self.ds['dataset_hash'])); first=a.advance(events[0]); self.store.commit(a,first)
        cp=self.store.load_checkpoint(a.manifest.digest)
        with self.store.connection() as db:
            before={t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('features','lineage','evaluations')}
            db.execute("CREATE TRIGGER fail_checkpoint BEFORE INSERT ON checkpoints BEGIN SELECT RAISE(ABORT,'injected write failure'); END")
        second=a.advance(events[1])
        with self.assertRaises(sqlite3.IntegrityError): self.store.commit(a,second)
        self.assertEqual(self.store.load_checkpoint(a.manifest.digest),cp)
        with self.store.connection() as db:
            self.assertEqual({t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in before},before)
            db.execute('DROP TRIGGER fail_checkpoint')
        self.assertTrue(self.run_case(batch_size=1)['completed'])

    def test_batch_and_incremental_reports_are_identical(self):
        expected=self.make_engine(); outputs=list(expected.run(self.market.replay(self.ds['dataset_hash'])))
        actual=self.run_case(batch_size=1)
        self.assertEqual([self.store.evaluation(r.digest) for r in outputs],[{'evaluation_hash':r.digest,**r.document()} for r in outputs])
        self.assertEqual(actual['emitted_candidates'],expected.emitted_count)

    def test_pagination_preserves_all_directions_and_filters(self):
        result=self.run_case(); page1=self.store.records(result['run_hash'],limit=2)
        page2=self.store.records(result['run_hash'],limit=2,after_sequence=page1['next_sequence'])
        self.assertEqual([r['sequence'] for r in page2['records']],[3,4])
        for kw in ({'limit':0},{'limit':True},{'after_sequence':-1},{'status':'winner'}):
            with self.assertRaises(ValidationError): self.store.records(result['run_hash'],**kw)

    def test_later_revision_new_dataset_keeps_original_inventory_frozen(self):
        old=self.run_case(); records=self.store.records(old['run_hash']); self.now+=1
        d=event(2,'100')['data']; row=[d[k] for k in ('open_ms','open','high','low','close','volume','close_ms','quote_volume','trades','taker_base','taker_quote')]+['0']
        self.market.ingest_rest(json.dumps([row]),'BTCUSDT')
        newer=self.market.snapshot(['BTCUSDT'],START,START+3*MINUTE,kinds=('candle',))
        changed=self.store.run(self.market,newer['dataset_hash'],self.strategy,self.config)
        self.assertEqual(changed['emitted_candidates'],1); self.assertEqual(changed['status_counts']['revision_only'],2)
        self.assertEqual(self.store.records(old['run_hash']),records); self.assertEqual(self.run_case(),old)

    def test_metadata_observation_timeline_is_frozen_and_causal(self):
        self.now+=1; raw=metadata()[0]; raw['symbols'][0]['status']='BREAK'; self.registry.ingest(json.dumps(raw))
        # Old pinned cutoff predates the status observation.
        self.assertEqual(self.run_case()['emitted_candidates'],1)
        newer=self.market.snapshot(['BTCUSDT'],START,START+3*MINUTE,kinds=('candle',))
        result=self.store.run(self.market,newer['dataset_hash'],self.strategy,self.config)
        self.assertEqual(result['emitted_candidates'],1) # observation is later than every original detection
        manifest=self.store.manifest(result['run_hash']); self.assertEqual(len(manifest['metadata_snapshots']),2)

    def test_missing_complete_buckets_are_reported_not_fabricated(self):
        self.now+=3*MINUTE
        ds=self.market.snapshot(['BTCUSDT'],START,START+6*MINUTE,kinds=('candle',))
        result=self.store.run(self.market,ds['dataset_hash'],self.strategy,self.config)
        self.assertEqual(result['coverage'][0]['missing_buckets'],3)
        self.assertEqual(result['coverage'][0]['represented_buckets'],3)

    def test_bad_schema_aliases_and_missing_hash_fail_closed(self):
        for path in (self.registry.path,self.market.path,':memory:'):
            with self.assertRaises(ValidationError): CandidateStore(path)
        for method in (self.store.manifest,self.store.evaluation,self.store.feature,self.store.summary):
            with self.assertRaises(ValidationError): method('missing')
        for batch in (0,True,-1):
            with self.assertRaises(ValidationError): self.run_case(batch_size=batch)

    def test_corrupt_evaluation_manifest_feature_and_checkpoint_detected(self):
        result=self.run_case(); record=self.store.records(result['run_hash'])['records'][0]
        with self.store.connection() as db:
            for table in ('evaluations','runs','features'): db.execute("UPDATE "+table+" SET document='{}'")
            db.execute("UPDATE checkpoints SET document='{}'")
        for method,key in ((self.store.manifest,result['run_hash']),(self.store.evaluation,record['evaluation_hash']),
                           (self.store.feature,record['feature_snapshot_hash']),(self.store.load_checkpoint,result['run_hash'])):
            with self.assertRaises(ValidationError): method(key)

    def test_missing_output_cannot_commit_a_checkpoint(self):
        a=self.make_engine(); outputs=a.advance(next(self.market.replay(self.ds['dataset_hash'])))
        with self.assertRaises(ValidationError): self.store.commit(a,outputs[:1])
        self.assertIsNone(self.store.load_checkpoint(a.manifest.digest))

    def test_backward_and_conflicting_checkpoints_rejected(self):
        a=self.make_engine(); events=list(self.market.replay(self.ds['dataset_hash'])); outputs=a.advance(events[0]); self.store.commit(a,outputs)
        cp=a.checkpoint(); outputs=a.advance(events[1]); self.store.commit(a,outputs)
        old=CandidateEngine.restore(a.dataset,a.strategy,a.book.snapshots,a.book.versions,a.config,cp)
        with self.assertRaises(ValidationError): self.store.commit(old,[])
        a.features.prefix_hash='f'*64
        with self.assertRaises(ValidationError): self.store.commit(a,[])

    def test_empty_dataset_completes_with_explicit_missing_coverage(self):
        self.now+=3*MINUTE
        ds=self.market.snapshot(['BTCUSDT'],START+3*MINUTE,START+6*MINUTE,kinds=('candle',))
        result=self.store.run(self.market,ds['dataset_hash'],self.strategy,self.config)
        self.assertTrue(result['completed']); self.assertEqual(result['evaluations'],0); self.assertEqual(result['coverage'][0]['missing_buckets'],3)

    def test_deleted_inventory_rows_do_not_masquerade_as_a_complete_run(self):
        result=self.run_case()
        with self.store.connection() as db: db.execute('DELETE FROM evaluations WHERE sequence=1')
        with self.assertRaises(ValidationError): self.store.summary(result['run_hash'])
        with self.assertRaises(ValidationError): self.run_case()

    def test_completed_marker_requires_the_entire_dataset_prefix(self):
        a=self.make_engine(); outputs=a.advance(next(self.market.replay(self.ds['dataset_hash'])))
        with self.assertRaises(ValidationError): self.store.commit(a,outputs,completed=True)
        self.assertIsNone(self.store.load_checkpoint(a.manifest.digest))

    def test_summary_reads_one_snapshot_across_a_real_concurrent_commit(self):
        from contextlib import contextmanager
        a=self.make_engine(); events=list(self.market.replay(self.ds['dataset_hash']))
        first=a.advance(events[0]); self.store.commit(a,first)
        second=a.advance(events[1]); original=self.store.connection; fired=[]
        with original() as db: db.execute('PRAGMA journal_mode=WAL')
        @contextmanager
        def interleaved_connection():
            with original() as db:
                def trace(sql):
                    if sql.startswith('SELECT document,checksum,completed FROM checkpoints') and not fired:
                        fired.append(True)
                        self.store.commit(a,second)
                db.set_trace_callback(trace)
                yield db
        self.store.connection=interleaved_connection
        summary=self.store.summary(a.manifest.digest)
        self.assertTrue(fired); self.assertEqual(summary['evaluations'],2)
        self.store.connection=original
        self.assertEqual(self.store.summary(a.manifest.digest)['evaluations'],4)
