import hashlib
import json
import sqlite3

from tradee.c01 import ValidationError
from tradee.c02 import MarketStore, aggregate
from tests.c02_support import DataCase, START, row, ws
from tests.support import payload, contract


class MarketPersistenceTests(DataCase):
    def test_binding_requires_known_supported_unambiguous_identity(self):
        with self.assertRaises(ValidationError):
            self.store.binding('UNKNOWNUSDT')
        data = payload(); contract(data)['onboardDate'] += 1
        self.registry.ingest(json.dumps(data))
        with self.assertRaises(ValidationError):
            self.store.binding('BTCUSDT')

    def test_collection_does_not_depend_on_enabled_or_fresh_trading_universe(self):
        self.now += 3600000
        self.assertTrue(self.store.binding('SOLUSDT')['instrument_id'])

    def test_database_separation_and_schema_guard(self):
        with self.assertRaises(ValidationError):
            MarketStore(self.registry, self.registry.path)
        from contextlib import closing
        with closing(sqlite3.connect(self.root/'wrong.sqlite3')) as db:
            db.execute('CREATE TABLE unrelated (id INTEGER)')
        with self.assertRaises(ValidationError):
            MarketStore(self.registry, self.root/'wrong.sqlite3')

    def test_duplicate_raw_retained_but_semantic_event_not_repeated(self):
        self.assertEqual(self.ingest()['added'], 1)
        self.assertEqual(self.ingest()['duplicates'], 1)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM raw_observations').fetchone()[0], 2)
            raw = db.execute('SELECT raw,sha256 FROM raw_observations LIMIT 1').fetchone()
        self.assertEqual(hashlib.sha256(raw['raw']).hexdigest(), raw['sha256'])
        self.assertEqual(len(list(self.store.replay(self.snapshot()))), 1)

    def test_correction_and_reversion_preserved(self):
        self.ingest()
        self.now += 100
        self.ingest([row(close='102')])
        self.now += 100
        self.ingest()
        events = list(self.store.replay(self.snapshot()))
        self.assertEqual([e['data']['close'] for e in events], ['101', '102', '101'])

    def test_saved_dataset_does_not_change_after_repairs_or_restart(self):
        self.ingest()
        digest = self.snapshot()
        expected = list(self.store.replay(digest))
        self.now += 100
        self.ingest([row(close='102')])
        reopened = MarketStore(self.registry, self.store.path, clock=lambda: self.now/1000)
        self.assertEqual(list(reopened.replay(digest)), expected)
        self.assertNotEqual(self.snapshot(), digest)

    def test_recorded_data_not_available_at_historical_event_time(self):
        self.ingest()
        digest = self.snapshot()
        self.assertEqual(self.store.view(digest, START+60000), [])
        self.assertEqual(len(self.store.view(digest, self.now)), 1)

    def test_modeled_availability_requires_explicit_candle_only_delay(self):
        self.ingest()
        for kwargs in ({'mode': 'modeled'}, {'mode': 'modeled', 'delay_ms': -1},
                       {'mode': 'modeled', 'delay_ms': 0, 'kinds': ('trade',)}, {'delay_ms': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                self.snapshot(**kwargs)
        digest = self.snapshot(mode='modeled', delay_ms=250)
        self.assertEqual(self.store.view(digest, START+60249), [])
        e = self.store.view(digest, START+60250)[0]
        self.assertEqual(e['availability_basis'], 'modeled')
        self.assertEqual(e['received_ms'], self.now)

    def test_partial_candles_never_become_finalized_bars(self):
        self.store.ingest_ws(ws(final=False))
        digest = self.snapshot()
        self.assertEqual(self.store.view(digest, self.now), [])
        self.assertEqual(self.store.quality(digest)['partial_updates'], 1)
        self.store.ingest_ws(ws())
        self.store.ingest_ws(ws(final=False, close='102'))
        self.assertEqual(self.store.view(self.snapshot(), self.now)[0]['data']['close'], '101')

    def test_asof_join_honors_receipt_and_staleness(self):
        self.ingest()
        digest = self.snapshot()
        self.assertIsNone(self.store.asof(digest, 'BTCUSDT', 'candle', self.now-1, 1000000))
        self.assertIsNotNone(self.store.asof(digest, 'BTCUSDT', 'candle', self.now, 1000000))
        self.assertIsNone(self.store.asof(digest, 'BTCUSDT', 'candle', self.now, 1))

    def test_future_appends_cannot_alter_replay_prefix(self):
        self.ingest()
        cutoff = self.now
        expected = list(self.store.replay(self.snapshot()))
        for i in range(5):
            self.now += 100
            self.ingest([row(close=str(100+i))])
            self.assertEqual(list(self.store.replay(self.snapshot(), until_ms=cutoff)), expected)

    def test_atomic_batch_quarantine_and_checkpoint_rollback(self):
        with self.store.connection() as db:
            db.execute("""CREATE TRIGGER fail_event BEFORE INSERT ON events WHEN NEW.event_key!='1800000000000'
                BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
        with self.assertRaises(ValidationError):
            self.store.ingest_rest(json.dumps([row(), row(START+60000)]), 'BTCUSDT', checkpoint=('test', {'next_ms': 5}))
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT accepted FROM raw_observations').fetchone()[0], 0)
        self.assertIsNone(self.store.checkpoint('test'))

    def test_malformed_and_future_observations_quarantined(self):
        for raw in ('{bad', json.dumps([row(close='999')]), json.dumps([row(self.now+60000)])):
            with self.assertRaises(ValidationError):
                self.store.ingest_rest(raw, 'BTCUSDT')
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM raw_observations WHERE accepted=0').fetchone()[0], 3)

    def test_replay_resume_uses_dataset_order_not_numeric_id(self):
        self.ingest([row(START+60000), row()])
        digest = self.store.snapshot(['BTCUSDT'], START, START+120000, mode='modeled', delay_ms=0)['dataset_hash']
        events = list(self.store.replay(digest))
        self.assertGreater(events[0]['id'], events[1]['id'])
        self.assertEqual(list(self.store.replay(digest, after_id=events[0]['id'])), events[1:])
        with self.assertRaises(ValidationError):
            list(self.store.replay(digest, after_id=999))

    def test_gap_report_and_repair_preserve_previous_experiment(self):
        self.ingest([row(), row(START+120000)])
        old = self.store.snapshot(['BTCUSDT'], START, START+180000)['dataset_hash']
        self.assertEqual(self.store.quality(old)['symbols'][0]['gaps'], [{'start_ms': START+60000, 'end_ms': START+120000}])
        self.ingest([row(START+60000)])
        new = self.store.snapshot(['BTCUSDT'], START, START+180000)['dataset_hash']
        self.assertEqual(self.store.quality(new)['symbols'][0]['gaps'], [])
        self.assertTrue(self.store.quality(old)['symbols'][0]['gaps'])

    def test_aggregation_requires_complete_final_constituents(self):
        self.ingest([row(START+i*60000) for i in (0, 1, 2, 4)])
        digest = self.store.snapshot(['BTCUSDT'], START, START+300000)['dataset_hash']
        self.assertEqual(aggregate(self.store.view(digest, self.now), 300000), [])
        self.ingest([row(START+180000)])
        digest = self.store.snapshot(['BTCUSDT'], START, START+300000)['dataset_hash']
        parts = self.store.view(digest, self.now)
        bar = aggregate(parts, 300000)[0]
        self.assertEqual(bar['data']['volume'], '50')
        self.assertEqual(bar['data']['trades'], 15)
        self.assertEqual(len(bar['constituents']), 5)
        self.assertEqual(bar['available_ms'], self.now)
        with self.assertRaises(ValidationError):
            aggregate(parts+parts[:1], 300000)

    def test_equal_receipt_time_has_stable_sequence(self):
        self.ingest([row(), row(START+60000)])
        digest = self.store.snapshot(['BTCUSDT'], START, START+120000)['dataset_hash']
        events = list(self.store.replay(digest))
        self.assertEqual([e['id'] for e in events], sorted(e['id'] for e in events))
        self.assertEqual(events[0]['available_ms'], events[1]['available_ms'])

    def test_unknown_dataset_fails_explicitly(self):
        with self.assertRaises(ValidationError):
            self.store.dataset('missing')

    def test_availability_includes_batch_processing_time(self):
        original = self.store.binding
        def slow_binding(symbol):
            self.now += 100
            return original(symbol)
        self.store.binding = slow_binding
        receipt = self.now
        self.store.ingest_rest(json.dumps([row()]), 'BTCUSDT', received_ms=receipt)
        event = list(self.store.replay(self.snapshot()))[0]
        self.assertGreater(event['available_ms'], event['received_ms'])

    def test_wall_clock_regression_does_not_reorder_arrival_history(self):
        self.now += 1000
        self.ingest()
        self.now -= 100
        self.ingest([row(close='102')])
        self.now += 100
        events = list(self.store.replay(self.snapshot()))
        self.assertEqual([e['data']['close'] for e in events], ['101', '102'])
        self.assertGreaterEqual(events[1]['available_ms'], events[0]['available_ms'])

    def test_small_clock_skew_cannot_expose_final_bar_before_close(self):
        self.now = START+59900
        # Metadata was received earlier in this isolated scenario.
        self.registry.clock = lambda: (START+600000)/1000
        self.store.ingest_ws(ws())
        digest = self.snapshot()
        self.assertEqual(self.store.view(digest, self.now), [])
        self.now = START+60000
        digest = self.snapshot()
        self.assertEqual(len(self.store.view(digest, self.now)), 1)
