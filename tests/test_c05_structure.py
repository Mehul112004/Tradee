from copy import deepcopy
from decimal import Decimal, localcontext
import json
import unittest

from tradee.c01 import ValidationError
from tradee.c05 import StructureConfig, StructureEngine, reference_levels, relationships
from tradee.c05.levels import DAY, WEEK
from tests.c03_support import event, dataset, START


def rows(count, **kwargs):
    return [event(i, **kwargs)['data'] for i in range(count)]


class LevelTests(unittest.TestCase):
    def test_swings_require_right_confirmation_strict_extrema_and_contiguity(self):
        data = rows(5, close=100); data[2]['high'] = '110'
        self.assertFalse([l for l in reference_levels(data[:4], 60000)['levels'] if l['kind'] == 'swing'])
        high = next(l for l in reference_levels(data, 60000)['levels'] if l['kind'] == 'swing')
        self.assertEqual(high['price'], '110')
        self.assertEqual(high['confirmed_ms'], START+5*60000)
        self.assertEqual(high['known_ms'], START+5*60000)
        tied = deepcopy(data); tied[4]['high'] = '110'
        self.assertFalse([l for l in reference_levels(tied, 60000)['levels'] if l['kind'] == 'swing'])
        self.assertFalse([l for l in reference_levels(data[1:3]+data[4:], 60000)['levels'] if l['kind'] == 'swing'])

    def test_prior_range_excludes_current_and_requires_full_contiguous_window(self):
        data = rows(4, close=100); data[-1]['high'] = '999'
        config = StructureConfig(range_bars=3)
        result = reference_levels(data, 60000, config=config)
        level = next(l for l in result['levels'] if l['kind'] == 'prior_range' and l['side'] == 'high')
        self.assertEqual(level['price'], '101')
        self.assertEqual(level['source_end_ms'], data[-1]['open_ms'])
        missing = reference_levels(data[:2]+data[3:], 60000, config=config)
        self.assertEqual(missing['coverage']['prior_range'], 'insufficient_or_gapped_history')

    def test_previous_day_boundary_and_missing_period_inputs(self):
        data = rows(1441, close=100); data[20]['high'] = '111'
        midnight = reference_levels(data[:-1], 60000)
        high = next(l for l in midnight['levels'] if l['kind'] == 'previous_day' and l['side'] == 'high')
        self.assertEqual(high['price'], '111')
        self.assertEqual(high['confirmed_ms'], START+DAY)
        self.assertEqual(reference_levels(data[1:], 60000)['coverage']['previous_day'], 'anchor_incomplete')
        before = reference_levels(data[:1439], 60000)
        self.assertEqual(before['coverage']['previous_day'], 'anchor_incomplete')

    def test_previous_week_uses_completed_monday_to_monday_period(self):
        monday = START-DAY
        data = [dict(open_ms=monday+i*DAY, high=str(110+i), low='90', close='100') for i in range(7)]
        result = reference_levels(data, DAY)
        level = next(l for l in result['levels'] if l['kind'] == 'previous_week' and l['side'] == 'high')
        self.assertEqual(level['price'], '116')
        self.assertEqual(level['source_start_ms'], monday)
        self.assertEqual(level['confirmed_ms'], monday+WEEK)
        self.assertEqual(reference_levels(data[1:], DAY)['coverage']['previous_week'], 'anchor_incomplete')

    def test_late_confirmation_availability_prevents_intrabar_hindsight(self):
        data = rows(5, close=100); data[2]['high'] = '110'
        data[1]['available_ms'] = START+10*60000
        level = next(l for l in reference_levels(data, 60000, as_of_ms=START+10*60000)['levels'] if l['kind'] == 'swing')
        self.assertEqual(level['known_ms'], START+10*60000)
        r = relationships([level], data[-1], data[-2])[0]
        self.assertFalse(r['level_known_before_bar'])
        self.assertIsNone(r['touched_in_bar'])
        with self.assertRaises(ValidationError):
            reference_levels(data, 60000, as_of_ms=START+5*60000)

    def test_exact_relationships_and_independent_atr_status(self):
        level = dict(level_id='x', revision_hash='y', price='100.00000000000000001', known_ms=START)
        current = dict(open_ms=START+60000, high='101', low='99', close='100')
        with localcontext() as ctx:
            ctx.prec = 3
            relation = relationships([level], current, dict(close='101'), dict(value=2, status='valid', stable=True))[0]
        self.assertEqual(relation['close_relation'], 'below')
        self.assertEqual(Decimal(relation['distance_price']), Decimal('-0.00000000000000001'))
        self.assertTrue(relation['touched_in_bar'])
        self.assertEqual(relation['previous_close_relation'], 'above')
        self.assertAlmostEqual(relation['distance_atr14'], -5e-18)
        zero = relationships([level], current, atr=dict(value=0, status='valid'))[0]
        self.assertEqual(zero['distance_atr14_status'], 'zero_denominator')

    def test_invalid_and_future_bars_are_rejected(self):
        data = rows(5)
        for invalid in (data[::-1], data+[data[-1]], [dict(data[0], low='999')]):
            with self.assertRaises(ValidationError):
                reference_levels(invalid, 60000, as_of_ms=START+5*60000)
        with self.assertRaises(ValidationError):
            reference_levels(data, 60000, as_of_ms=START+4*60000)
        with self.assertRaises(ValidationError):
            reference_levels(data, 64000)


class StructureEngineTests(unittest.TestCase):
    def test_prefix_immutability_correction_and_restart(self):
        config = StructureConfig(timeframes=('1m',), range_bars=3)
        a = StructureEngine(dataset(), config)
        original = list(a.run(event(i, 100+i) for i in range(5)))
        saved = [s.serialized for s in original]
        correction = event(1, 109, event_id=6, available=START+5*60000)
        revised = a.advance(correction)[0].document()
        self.assertEqual(revised['trigger'], 'revision')
        self.assertEqual([s.serialized for s in original], saved)
        self.assertNotEqual(revised['levels'], original[-1].document()['levels'])
        b = StructureEngine.restore(a.dataset, config, json.loads(json.dumps(a.checkpoint())))
        next_event = event(5, 104, event_id=7)
        self.assertEqual([s.serialized for s in a.advance(next_event)], [s.serialized for s in b.advance(next_event)])

    def test_partial_and_stale_sources_never_claim_readiness(self):
        config = StructureConfig(timeframes=('1m',), range_bars=2)
        a = StructureEngine(dataset(), config)
        self.assertFalse(a.advance(event(0, final=False)))
        list(a.run(event(i) for i in range(1, 4)))
        stale = a.advance(event(1, 103, event_id=5, available=START+10*60000))[0].document()
        self.assertFalse(stale['ready'])
        self.assertEqual(stale['source_status'], 'stale_input')
        self.assertNotIn('candidate', stale)

    def test_snapshot_defensive_copy_and_pivot_bound(self):
        config = StructureConfig(timeframes=('1m',), max_pivots_per_side=2)
        a = StructureEngine(dataset(), config)
        last = list(a.run(event(i) for i in range(50)))[-1]
        doc = last.document(); doc['levels'].clear()
        self.assertTrue(last.document()['levels'])
        swings = [l for l in last.document()['levels'] if l['kind'] == 'swing']
        self.assertLessEqual(len(swings), 4)

    def test_configuration_rejects_implicit_strategy_options(self):
        for bad in ({'pivot_left': 0}, {'pivot_right': True}, {'range_bars': 1},
                    {'previous_day': 1}, {'stop_atr': 2}, {'timeframes': ['7m']}):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                StructureConfig.from_dict(bad)
