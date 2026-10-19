from decimal import localcontext
from unittest.mock import patch
import unittest
from tradee.c01 import ValidationError
from tradee.c03.contracts import FrozenRecord
from tradee.c12 import Experiment, Split
from tradee.c12.engine import choose, testing
from tests.c12_support import plan, split


class ResearchIsolationTests(unittest.TestCase):
    def test_selection_comparison_never_rounds_close_scores_in_callers_decimal_context(self):
        e=Experiment.from_dict(plan())
        class Jobs:
            simulations=None
            def __call__(self,key,fn): return fn()
        def result(e,v,*args): return {'test':{'rows':[{'variant':v.name}]}}
        def evidence(rows,*args):
            return dict(ready=True,utility_r_per_candidate='2.4551' if rows[0]['variant']=='a' else '2.4559')
        with patch('tradee.c12.engine.fitted_test',side_effect=result),patch('tradee.c12.engine.evidence',side_effect=evidence):
            with localcontext() as ctx:
                ctx.prec=3; chosen=choose(e,e.folds[0],Jobs())
        self.assertEqual(chosen['winner'],'b')

    def test_test_producer_cannot_differ_from_training_even_with_matching_protocol(self):
        e=Experiment.from_dict(plan()); variant=e.variants[0]; s=e.folds[0].split
        model=dict(fit=dict(protocols={'p':{}},sources=[dict(producer_code_hash='old')]))
        data=FrozenRecord.create(dict(protocols={'p':{}},sources=[dict(producer_code_hash='new')]))
        with patch('tradee.c12.engine.selected_runs',return_value=['run']),patch('tradee.c12.engine.snapshot',return_value=data),patch('tradee.c12.engine.evaluate',side_effect=AssertionError('must reject first')):
            with self.assertRaisesRegex(ValidationError,'implementation differs'): testing(None,variant,s,model,'development',e.holdout.split.test.start_ms)
