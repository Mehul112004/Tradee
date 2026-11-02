from copy import deepcopy
import sqlite3

from tradee.c01 import ValidationError
from tradee.c03 import FeatureStore
from tradee.c04 import ContextConfig, ContextEngine, ContextStore
from tradee.c05 import StructureConfig, StructureEngine, StructureStore
from tests.c02_support import DataCase, START, row


class ObservationPersistenceTests(DataCase):
    def prepared(self):
        self.now = START+13*60000
        self.ingest([row(START+i*60000, str(100+i%4)) for i in reversed(range(12))])
        dataset = self.store.snapshot(['BTCUSDT'], START, START+12*60000, mode='modeled', delay_ms=0)
        return dataset, list(self.store.replay(dataset['dataset_hash']))

    def components(self):
        return ((ContextEngine, ContextConfig(timeframes=('1m',)), ContextStore, 'context'),
                (StructureEngine, StructureConfig(timeframes=('1m',), range_bars=2), StructureStore, 'structure'))

    def test_resume_idempotency_nonmonotone_source_ids_and_evidence(self):
        dataset, events = self.prepared()
        self.assertGreater(events[0]['id'], events[-1]['id'])
        for engine_type, config, store_type, name in self.components():
            with self.subTest(component=name):
                store = store_type(self.root/(name+'.sqlite3'))
                engine = engine_type(dataset, config)
                store.commit(engine, list(engine.run(events[:5])))
                result = store.run(self.store, dataset['dataset_hash'], config, batch_size=2)
                self.assertTrue(result['completed'])
                self.assertEqual(result['event_count'], 12)
                self.assertEqual(result['snapshots'], 12)
                self.assertEqual(store.run(self.store, dataset['dataset_hash'], config), result)
                direct = list(engine_type(dataset, config).run(events))
                page = store.records(result['run_hash'], limit=5)
                second = store.records(result['run_hash'], limit=5, after=page['next_sequence'])
                self.assertEqual([r['sequence'] for r in second['records']], list(range(6, 11)))
                for snapshot in direct:
                    doc = store.snapshot(snapshot.digest); doc.pop('snapshot_hash')
                    self.assertEqual(doc, snapshot.document())
                    self.assertTrue(store.lineage(doc['lineage_hash'])['events'])
                    self.assertEqual(doc['feature_snapshot']['input_prefix_hash'], doc['input_prefix_hash'])

    def test_atomic_sql_failure_rolls_back_checkpoint_outputs_and_lineage(self):
        dataset, events = self.prepared()
        for engine_type, config, store_type, name in self.components():
            with self.subTest(component=name):
                store = store_type(self.root/(name+'.sqlite3'))
                engine = engine_type(dataset, config)
                store.commit(engine, engine.advance(events[0]))
                checkpoint = store.load_checkpoint(engine.manifest.digest)
                with store.connection() as db:
                    db.execute("CREATE TRIGGER failure BEFORE INSERT ON checkpoints BEGIN SELECT RAISE(ABORT, 'failure'); END")
                pending = engine.advance(events[1])
                with self.assertRaises(sqlite3.IntegrityError):
                    store.commit(engine, pending)
                self.assertEqual(store.load_checkpoint(engine.manifest.digest), checkpoint)
                self.assertEqual(store.summary(engine.manifest.digest)['snapshots'], 1)
                with store.connection() as db:
                    db.execute('DROP TRIGGER failure')
                store.commit(engine, pending)
                self.assertEqual(store.summary(engine.manifest.digest)['snapshots'], 2)

    def test_component_databases_are_isolated_and_snapshots_checked(self):
        dataset, events = self.prepared()
        target = self.root/'observations.sqlite3'
        store = ContextStore(target)
        for wrong in (StructureStore, FeatureStore):
            with self.assertRaises(ValidationError):
                wrong(target)
        for path in (self.registry.path, self.store.path):
            with self.assertRaises(ValidationError):
                ContextStore(path)
        engine = ContextEngine(dataset, ContextConfig(timeframes=('1m',)))
        pending = engine.advance(events[0]); store.commit(engine, pending)
        with store.connection() as db:
            db.execute("UPDATE snapshots SET document='{}'")
        with self.assertRaises(ValidationError):
            store.snapshot(pending[0].digest)

    def test_checkpoint_source_config_and_prefix_conflicts_fail_closed(self):
        dataset, events = self.prepared()
        for engine_type, config, store_type, name in self.components():
            with self.subTest(component=name):
                engine = engine_type(dataset, config)
                pending = engine.advance(events[0])
                store = store_type(self.root/(name+'.sqlite3')); store.commit(engine, pending)
                checkpoint = engine.checkpoint()
                changed = deepcopy(checkpoint); changed['feature_checkpoint']['prefix_hash'] = 'bad'
                with self.assertRaises(ValidationError):
                    engine_type.restore(dataset, config, changed)
                changed = deepcopy(dataset); changed['mode'] = 'recorded'
                with self.assertRaises(ValidationError):
                    engine_type.restore(changed, config, checkpoint)
                engine.features.prefix_hash = 'f'*64
                with self.assertRaises(ValidationError):
                    store.commit(engine, [])

    def test_changed_pinned_event_count_does_not_report_completion(self):
        dataset, events = self.prepared()
        original = self.store.replay
        self.store.replay = lambda *args, **kwargs: iter(events[:3])
        self.addCleanup(setattr, self.store, 'replay', original)
        with self.assertRaises(ValidationError):
            StructureStore(self.root/'structure.sqlite3').run(
                self.store, dataset['dataset_hash'], StructureConfig(timeframes=('1m',)))
