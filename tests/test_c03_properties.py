"""Independent Decimal recurrences and adversarial feature boundaries."""
from decimal import Decimal, localcontext
import math
import random
import unittest
from tradee.c01 import ValidationError
from tradee.c03 import FeatureConfig, FeatureEngine
from tradee.c03.evaluator import Evaluator
from tradee.c03.rolling import smooth, period, finite
from tradee.c03.oscillators import rsi
from tests.c03_support import event, dataset, quote, START, IDENTITY


class PropertyTests(unittest.TestCase):
    def test_long_random_sequences_against_decimal_recurrence(self):
        for seed in (0,17,91):
            rng=random.Random(seed)
            exact=[Decimal(10000+rng.randrange(-100,101))/100 for _ in range(500)]
            floats=[float(x) for x in exact]
            with localcontext() as ctx:
                ctx.prec=70
                for mode in ('ema','rma'):
                    n=14; alpha=Decimal(2)/15 if mode=='ema' else Decimal(1)/14
                    state=sum(exact[:n])/n; expected=[state]
                    for x in exact[n:]:
                        state=(1-alpha)*state+alpha*x; expected.append(state)
                    actual=smooth(floats,n,mode)[n-1:]
                    for a,b in zip(actual,expected):
                        self.assertTrue(math.isclose(a,float(b),rel_tol=1e-10,abs_tol=1e-12))
                gains=[max(exact[i]-exact[i-1],0) for i in range(1,len(exact))]
                losses=[max(exact[i-1]-exact[i],0) for i in range(1,len(exact))]
                g,l=sum(gains[:14])/14,sum(losses[:14])/14
                expected=[float(100*g/(g+l))]
                for dg,dl in zip(gains[14:],losses[14:]):
                    g=(13*g+dg)/14; l=(13*l+dl)/14; expected.append(float(100*g/(g+l)))
                for a,b in zip(rsi(floats)[0][14:],expected):
                    self.assertTrue(0<=a<=100)
                    self.assertTrue(math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-12))

    def test_volume_scale_and_geometry_properties(self):
        rng=random.Random(42)
        rows=[event(i)['data'] for i in range(30)]
        scaled=[dict(r) for r in rows]
        for r in scaled:
            for key in ('volume','quote_volume','taker_base','taker_quote'):
                r[key]=str(Decimal(r[key])*Decimal('0.0003'))
        for name in ('vwap20','relative_quote_volume20_prior','taker_base_imbalance20','taker_quote_imbalance20'):
            self.assertAlmostEqual(Evaluator(rows).get(name).value,Evaluator(scaled).get(name).value)
        from tradee.c03.price import shape
        for _ in range(100):
            low=rng.uniform(1,100); high=low+rng.uniform(.01,10)
            d=shape(rng.uniform(low,high),high,low,rng.uniform(low,high))
            self.assertAlmostEqual(abs(d['body_fraction'])+d['upper_wick_fraction']+d['lower_wick_fraction'],1)
            self.assertLessEqual(abs(d['close_location']),1)

    def test_zero_atr_and_zero_volume_have_distinct_masks(self):
        rows=[event(i,100)['data'] for i in range(22)]
        for r in rows:
            r.update(open='100',high='100',low='100',volume='0',quote_volume='0',taker_base='0',taker_quote='0',trades=0)
        e=Evaluator(rows)
        self.assertEqual(e.get('atr14').value,0)
        self.assertEqual(e.get('return_sd20').value,0)
        for name in ('ema20_distance_atr14','vwap20','relative_quote_volume20_prior','taker_base_imbalance20','mean_trade_quote_notional','body_fraction'):
            self.assertEqual(e.get(name).status,'zero_denominator',name)

    def test_feature_only_checks_its_actual_price_inputs(self):
        rows=[event(i)['data'] for i in range(25)]
        rows[0]['high']='10000000000000000'; rows[0]['low']='9999999999999999.999'
        self.assertEqual(Evaluator(rows).get('log_return_1').status,'valid')
        self.assertEqual(Evaluator(rows).get('atr14').status,'numeric_error')

    def test_bad_periods_extreme_and_nonfinite_conversions(self):
        for n in (True,0,-1,1.5,10001):
            with self.assertRaises(ValidationError): period(n)
        for x in ('1e999','1e-999','NaN','Infinity'):
            with self.assertRaises(ArithmeticError): finite(x)
        self.assertGreater(finite('0.00000000000000000001'),0)

    def test_readiness_waits_for_recursive_stability(self):
        a=FeatureEngine(dataset(),FeatureConfig(features=('ema50',),timeframes=('1m',)))
        last=None
        for i in range(395): last=a.advance(event(i))[0]
        self.assertEqual(last.document()['values']['ema50']['status'],'valid')
        self.assertFalse(last.document()['ready'])
        self.assertTrue(a.advance(event(395))[0].document()['ready'])

    def test_relisting_identity_is_not_stitched(self):
        a=FeatureEngine(dataset(),FeatureConfig(features=('log_return_1',),timeframes=('1m',)))
        a.advance(event(0)); e=event(1); e['instrument_id']='relisted-identity'
        out=a.advance(e)[0].document()
        self.assertIsNone(out['values']['log_return_1']['value'])
        self.assertEqual(out['instrument_id'],'relisted-identity')

    def test_modeled_quote_receipt_age_is_not_fabricated(self):
        a=FeatureEngine(dataset(mode='modeled'),FeatureConfig(features=('quote_receipt_age_ms',),timeframes=('1m',)))
        q=quote(1,START); q['availability_basis']='modeled'; a.push(q)
        out=a.evaluate(IDENTITY,'1m',START).document()
        self.assertEqual(out['values']['quote_receipt_age_ms']['status'],'unsupported_coverage')

    def test_corrupt_receipt_and_range_are_rejected_without_mutation(self):
        a=FeatureEngine(dataset(),FeatureConfig(features=('log_return_1',),timeframes=('1m',)))
        e=event(0); e['received_ms']+=1
        with self.assertRaises(ValidationError): a.push(e)
        with self.assertRaises(ValidationError): a.push(event(10000))
        self.assertEqual(a.event_count,0)
