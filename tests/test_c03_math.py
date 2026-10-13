from decimal import Decimal, localcontext
import json
import math
from pathlib import Path
import unittest

from tradee.c03.rolling import smooth, Smoother, Window, exact_floats, sd0, finite
from tradee.c03.price import log_return, prior_z, shape
from tradee.c03.volatility import atr, true_ranges, realized_variance
from tradee.c03.oscillators import rsi, bands
from tradee.c03.participation import vwap, relative_volume, imbalance, mean_trade_notional
from tradee.c03.evaluator import Evaluator
from tradee.c03.catalog import CATALOG, definition, seed_weight
from tests.c03_support import event

CASES=json.loads((Path(__file__).parent/'fixtures/c03/reference_cases.json').read_text())


class MathTests(unittest.TestCase):
    def assertSeries(self,actual,expected):
        self.assertEqual(len(actual),len(expected))
        for a,b in zip(actual,expected):
            if b is None:
                self.assertIsNone(a)
            else:
                self.assertTrue(math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-12),(a,b))

    def test_ema_rma_independent_seed_fixtures(self):
        for mode in ('ema','rma'):
            case=CASES[mode]
            self.assertSeries(smooth(case['input'],case['period'],mode),case['expected'])

    def test_smoother_restart_at_seed_and_mid_recursion(self):
        for mode in ('ema','rma'):
            for split in range(5):
                obj=Smoother(3,mode)
                first=[obj.push(v) for v in range(1,split+1)]
                resumed=Smoother.restore(obj.document())
                values=first+[resumed.push(v) for v in range(split+1,9)]
                self.assertSeries(values,smooth(list(range(1,9)),3,mode))

    def test_window_retains_only_declared_history(self):
        w=Window(3)
        self.assertIsNone(w.push(1)); self.assertIsNone(w.push(2))
        self.assertEqual(w.push(3),(1,2,3))
        self.assertEqual(w.push(4),(2,3,4))
        self.assertEqual(Window(**w.document()).push(5),(3,4,5))

    def test_rsi_fixture_and_flat_directional_limits(self):
        case=CASES['rsi']
        self.assertSeries(rsi(case['input'],case['period'])[0],case['expected'])
        for values,expected in ((list(range(1,31)),100),(list(range(30,0,-1)),0),([100]*30,50)):
            output,flat=rsi(values)
            self.assertTrue(all(v is None for v in output[:14]))
            self.assertEqual(output[14],expected)
            self.assertEqual(flat[-1],expected==50)

    def test_true_range_uses_previous_close_and_atr_no_tr0(self):
        self.assertEqual(true_ranges([101,108],[99,104],[100,106]),[8])
        # All prior closes 100: bar ranges below generate TR=[3,5,4,7].
        values=atr([100,103,105,104,107],[100]*5,[100]*5,3)
        self.assertSeries(values,[None,None,None,4,5])

    def test_population_variance_and_cancellation_resistance(self):
        self.assertAlmostEqual(sd0([1,2,3,4,5]),math.sqrt(2))
        self.assertAlmostEqual(sd0([1e12,1e12+1,1e12+2]),math.sqrt(2/3))
        self.assertEqual(sd0([100]*20),0)
        self.assertEqual(sd0([.01]*20),0)
        self.assertAlmostEqual(realized_variance([.01]*4),.0004)

    def test_log_returns_match_independent_decimal_reference(self):
        with localcontext() as ctx:
            ctx.prec=60
            expected=float((Decimal(121)/100).ln())
        self.assertAlmostEqual(log_return(121,100),expected)
        self.assertAlmostEqual(log_return(121,110)+log_return(110,100),expected)
        self.assertAlmostEqual(log_return(1e100,1e-100),200*math.log(10))

    def test_prior_windows_and_bollinger_fixtures(self):
        case=CASES['prior_z']
        self.assertAlmostEqual(prior_z(case['current'],case['prior']),case['expected'])
        actual=bands(CASES['bands']['input'])
        for key,value in CASES['bands']['expected'].items():
            self.assertAlmostEqual(actual[key],value)
        flat=bands([100]*20)
        self.assertEqual(flat['width'],0); self.assertIsNone(flat['pct_b'])

    def test_exact_volume_weights_and_signed_imbalance(self):
        rows=[dict(volume='2',quote_volume='200'),dict(volume='3',quote_volume='330')]
        self.assertEqual(vwap(rows),106)
        self.assertEqual(relative_volume({'quote_volume':'60'},[{'quote_volume':str(v)} for v in (10,20,30)]),3)
        self.assertAlmostEqual(imbalance([dict(volume='10',taker_base='7')]),.4)
        self.assertEqual(mean_trade_notional(dict(quote_volume='1000',trades=4)),250)
        self.assertEqual(relative_volume({'quote_volume':'0'},[{'quote_volume':'10'}]),0)
        with self.assertRaises(ZeroDivisionError):
            vwap([dict(volume='0',quote_volume='0')])

    def test_shape_units_and_zero_range(self):
        values=shape(100,110,90,105)
        self.assertEqual(values,dict(body_fraction=.25,upper_wick_fraction=.25,lower_wick_fraction=.5,close_location=.5))
        self.assertEqual(abs(values['body_fraction'])+values['upper_wick_fraction']+values['lower_wick_fraction'],1)
        with self.assertRaises(ZeroDivisionError):
            shape(100,100,100,100)

    def test_all_bar_features_have_correct_nominal_masks(self):
        for name,spec in CATALOG.items():
            if spec.inputs==('quote',) or 'session' in name:
                continue
            rows=[event(i)['data'] for i in range(spec.min_bars)]
            with self.subTest(feature=name):
                self.assertEqual(Evaluator(rows[:-1]).get(name).status,'insufficient_history')
                self.assertEqual(Evaluator(rows).get(name).status,'valid')
                self.assertTrue(math.isfinite(Evaluator(rows).get(name).value))
                self.assertEqual(Evaluator(rows+[event(spec.min_bars)['data']]).get(name).status,'valid')

    def test_stability_includes_lagged_dependency(self):
        self.assertGreater(seed_weight('ema50',395),1e-6)
        self.assertLessEqual(seed_weight('ema50',396),1e-6)
        self.assertGreater(seed_weight('atr14',201),1e-6)
        self.assertLessEqual(seed_weight('atr14',202),1e-6)
        self.assertGreater(seed_weight('ema20_slope5_atr14',25),seed_weight('ema20',25))

    def test_numerical_errors_and_zero_denominator_are_distinct(self):
        with self.assertRaises(ArithmeticError):
            exact_floats(['10000000000000000','10000000000000001'])
        with self.assertRaises(ArithmeticError):
            finite('NaN')
        rows=[event(i,100)['data'] for i in range(25)]
        self.assertEqual(Evaluator(rows).get('close_z20_prior').status,'zero_denominator')
        rows[-1]['close']='100.00000000000000000001'
        self.assertEqual(Evaluator(rows).get('close_z20_prior').status,'numeric_error')

    def test_scale_properties(self):
        rows=[event(i)['data'] for i in range(70)]
        scaled=json.loads(json.dumps(rows))
        for r in scaled:
            for key in ('open','high','low','close','quote_volume','taker_quote'):
                r[key]=str(Decimal(r[key])*10)
        first,second=Evaluator(rows),Evaluator(scaled)
        for name in ('log_return_12','ema20_distance_atr14','atr14_fraction','rsi14','vwap20_distance_atr14','body_fraction'):
            with self.subTest(feature=name):
                self.assertAlmostEqual(first.get(name).value,second.get(name).value,places=10)
        self.assertAlmostEqual(second.get('vwap20').value,10*first.get('vwap20').value)

    def test_parameterized_simple_return(self):
        rows=[event(i,100+i)['data'] for i in range(8)]
        self.assertAlmostEqual(Evaluator(rows).get('simple_return_7').value,.07)
