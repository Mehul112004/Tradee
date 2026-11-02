import json
import unittest

from tradee.c01 import ValidationError
from tradee.c04 import ContextConfig, ContextEngine
from tests.c03_support import event, dataset, quote, START, IDENTITY


class ContextTests(unittest.TestCase):
    def test_same_prefix_frames_use_only_complete_higher_timeframes(self):
        engine = ContextEngine(dataset(), ContextConfig(timeframes=('1m', '15m')))
        snapshots = list(engine.run(event(i) for i in range(16)))
        doc = snapshots[-1].document()
        self.assertEqual(doc['timeframe'], '1m')
        self.assertEqual(doc['frames']['1m']['target_open_ms'], START+15*60000)
        self.assertEqual(doc['frames']['15m']['target_open_ms'], START)
        for frame in doc['frames'].values():
            self.assertEqual(frame['input_prefix_hash'], doc['input_prefix_hash'])
            self.assertLessEqual(frame['target_end_ms'], doc['evaluation_as_of_ms'])
        self.assertFalse(doc['ready'])

    def test_nominal_readiness_optional_quotes_and_no_regime_labels(self):
        engine = ContextEngine(dataset(), ContextConfig(timeframes=('1m',), seed_threshold=1,
                                                        output_start_ms=START+204*60000))
        doc = list(engine.run(event(i, 100+i/10) for i in range(205)))[-1].document()
        self.assertTrue(doc['ready'])
        values = doc['feature_snapshot']['values']
        self.assertGreater(values['ema200_slope5_atr14']['value'], 0)
        self.assertEqual(values['spread_bps']['status'], 'missing_source')
        self.assertNotIn('regime', doc)
        self.assertNotIn('candidate', doc)
        self.assertNotIn('side', doc)

    def test_quote_freshness_and_candle_age_remain_explicit(self):
        engine = ContextEngine(dataset(), ContextConfig(timeframes=('1m',)))
        engine.advance(event(0))
        engine.advance(quote(2, START+60000))
        fresh = engine.advance(event(1, available=START+120000))[0].document()
        values = fresh['feature_snapshot']['values']
        self.assertEqual(values['spread_bps']['status'], 'stale_input')
        self.assertEqual(values['quote_event_age_ms']['value'], 60000)
        stale = engine.advance(event(0, 102, event_id=3, available=START+300000))[0].document()
        self.assertEqual(stale['feature_snapshot']['values']['ema200']['status'], 'stale_input')

    def test_partial_gaps_and_restart_match_prefix_execution(self):
        events = [event(i) for i in range(20) if i != 10]
        config = ContextConfig(timeframes=('1m', '15m'))
        a = ContextEngine(dataset(), config)
        out = list(a.run(events[:9]))
        b = ContextEngine.restore(a.dataset, config, json.loads(json.dumps(a.checkpoint())))
        left = [s.serialized for s in a.run(events[9:])]
        self.assertEqual(left, [s.serialized for s in b.run(events[9:])])
        self.assertTrue(all(s.document()['frames']['15m']['target_open_ms'] is None for s in out))
        prior = a.cursor
        self.assertFalse(a.advance(event(20, final=False)))
        self.assertNotEqual(a.cursor, prior)

    def test_future_inputs_do_not_change_earlier_context(self):
        config = ContextConfig(timeframes=('1m', '15m'))
        short = [s.serialized for s in ContextEngine(dataset(), config).run(event(i) for i in range(15))]
        full = [s.serialized for s in ContextEngine(dataset(), config).run(event(i) for i in range(30))]
        self.assertEqual(short, full[:len(short)])

    def test_invalid_configuration_and_checkpoint(self):
        for bad in ({'timeframes': ['7m']}, {'seed_threshold': 0}, {'surprise': True},
                    {'max_quote_age_ms': True}, {'output_end_ms': -1}):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                ContextConfig.from_dict(bad)
        a = ContextEngine(dataset())
        a.advance(event(0))
        cp = a.checkpoint(); cp['prefix_hash'] = 'changed'
        with self.assertRaises(ValidationError):
            ContextEngine.restore(a.dataset, a.config, cp)
