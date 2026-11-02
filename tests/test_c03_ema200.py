from decimal import Decimal, localcontext
import unittest

from tradee.c03 import FeatureConfig, FeatureEngine
from tradee.c03.catalog import BASELINE, definition, seed_weight
from tradee.c03.evaluator import Evaluator
from tests.c03_support import event, dataset, START


class Ema200Tests(unittest.TestCase):
    def test_independent_seed_recurrence_prior_distance_and_slope(self):
        rows = [event(i, 100 + i)['data'] for i in range(210)]
        with localcontext() as ctx:
            ctx.prec = 60
            average = sum(Decimal(r['close']) for r in rows[:200]) / 200
            values = [average]
            for row in rows[200:]:
                average += Decimal(2) / 201 * (Decimal(row['close']) - average)
                values.append(average)
        e = Evaluator(rows)
        self.assertAlmostEqual(e.get('ema200').value, float(values[-1]))
        self.assertAlmostEqual(e.get('ema200_prior').value, float(values[-2]))
        atr = e.get('atr14').value
        self.assertAlmostEqual(e.get('ema200_distance_atr14').value, (309 - float(values[-1])) / atr)
        self.assertAlmostEqual(e.get('ema200_slope5_atr14').value,
                               float(values[-1] - values[-6]) / (5 * atr))

    def test_nominal_and_stabilized_history_are_distinct(self):
        rows = [event(i)['data'] for i in range(205)]
        self.assertEqual(Evaluator(rows[:199]).get('ema200').status, 'insufficient_history')
        self.assertFalse(Evaluator(rows[:200]).get('ema200').stable)
        self.assertEqual(Evaluator(rows[:200]).get('ema200_prior').status, 'insufficient_history')
        self.assertEqual(Evaluator(rows[:204]).get('ema200_slope5_atr14').status, 'insufficient_history')
        for name, count in (('ema200', 1582), ('ema200_prior', 1583), ('ema200_slope5_atr14', 1587)):
            self.assertGreater(seed_weight(name, count - 1), 1e-6)
            self.assertLessEqual(seed_weight(name, count), 1e-6)
        self.assertEqual(dict(definition('ema200').parameters)['period'], 200)
        self.assertNotIn('ema200', BASELINE)

    def test_gap_resets_ema200_and_corrections_preserve_earlier_snapshot(self):
        config = FeatureConfig(features=('ema200',), timeframes=('1m',), require_stable=False,
                               output_start_ms=START+199*60000)
        engine = FeatureEngine(dataset(), config)
        original = list(engine.run(event(i, 100+i) for i in range(200)))[0]
        serialized = original.serialized
        revision = engine.advance(event(0, 102, event_id=201, available=START+200*60000))[0]
        self.assertEqual(revision.document()['trigger'], 'revision')
        self.assertAlmostEqual(revision.document()['values']['ema200']['value'], 199.51)
        self.assertEqual(original.serialized, serialized)
        after_gap = engine.advance(event(201, 300, event_id=202))[0]
        self.assertEqual(after_gap.document()['values']['ema200']['status'], 'gap_in_window')
