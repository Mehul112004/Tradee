from copy import deepcopy
from dataclasses import replace
from decimal import Decimal,localcontext
import json
import unittest
from tradee.c01 import ValidationError
from tradee.c03.evaluator import Evaluator
from tradee.c03.catalog import definition
from tradee.c08 import CandidateSpec, StrategySpec, CandidateConfig
from tradee.c08.contracts import FAMILY,TREND_FAMILY
from tradee.c08.strategy import prior_range,trend_recovery
from tests.c08_support import *


class CandidateStrategyTests(unittest.TestCase):
    def test_range_is_prior_only_strict_and_wick_independent(self):
        rows=[event(0)['data'],event(1)['data'],event(2,'102',high='900')['data']]
        r=prior_range(rows,2,MINUTE); self.assertEqual((r['upper'],r['lower']),('101','99')); self.assertTrue(r['long']); self.assertFalse(r['short'])
        rows[-1]=event(2,'101',high='900')['data']; self.assertFalse(prior_range(rows,2,MINUTE)['long'])

    def test_short_breakout_and_equality(self):
        rows=[event(0)['data'],event(1)['data'],event(2,'98')['data']]
        self.assertTrue(prior_range(rows,2,MINUTE)['short'])
        rows[-1]=event(2,'99')['data']; self.assertFalse(prior_range(rows,2,MINUTE)['short'])

    def test_range_requires_contiguous_n_plus_one_bars(self):
        self.assertIsNone(prior_range([event(0)['data'],event(1)['data']],2,MINUTE))
        self.assertIsNone(prior_range([event(i)['data'] for i in (0,1,3)],2,MINUTE))

    def test_decimal_range_distinctions_survive_low_external_context(self):
        rows=[event(0,high='100.00000000000000000001')['data'],event(1,high='100.00000000000000000001')['data'],event(2,'100.00000000000000000002')['data']]
        with localcontext() as ctx:
            ctx.prec=3; self.assertTrue(prior_range(rows,2,MINUTE)['long'])

    def test_range_uses_only_selected_tail(self):
        rows=[event(0,high='900')['data']]+[event(i)['data'] for i in (1,2)]+[event(3,'102')['data']]
        self.assertTrue(prior_range(rows,2,MINUTE)['long'])

    def test_trend_recovery_long_and_reverse_short(self):
        p={'ema20':{'value':100.0},'ema50':{'value':99.0}}
        c={'ema20':{'value':101.0},'ema50':{'value':100.0}}
        r=trend_recovery(event(0,'100')['data'],event(1,'102')['data'],p,c); self.assertTrue(r['long']); self.assertFalse(r['short'])
        p={'ema20':{'value':102.0},'ema50':{'value':103.0}}; c={'ema20':{'value':101.0},'ema50':{'value':102.0}}
        self.assertTrue(trend_recovery(event(0,'102')['data'],event(1,'100')['data'],p,c)['short'])

    def test_trend_requires_recovery_and_direction_and_strict_current_close(self):
        p={'ema20':{'value':100.0},'ema50':{'value':99.0}}; c={'ema20':{'value':101.0},'ema50':{'value':100.0}}
        self.assertFalse(trend_recovery(event(0,'101')['data'],event(1,'102')['data'],p,c)['long'])
        self.assertFalse(trend_recovery(event(0,'100')['data'],event(1,'101')['data'],p,c)['long'])
        c['ema50']['value']=101; self.assertFalse(trend_recovery(event(0,'100')['data'],event(1,'102')['data'],p,c)['long'])

    def test_lagged_ema_outputs_match_independent_decimal_recurrence(self):
        rows=[event(i,str(100+Decimal(i)/10))['data'] for i in range(100)]
        with localcontext() as ctx:
            ctx.prec=70
            for n in (20,50):
                values=[Decimal(r['close']) for r in rows[:-1]]; avg=sum(values[:n])/n; alpha=Decimal(2)/(n+1)
                for value in values[n:]: avg+=(value-avg)*alpha
                got=Evaluator(rows).get(f'ema{n}_prior')
                self.assertEqual(got.status,'valid'); self.assertAlmostEqual(got.value,float(avg),places=11)

    def test_lagged_ema_excludes_current_and_delays_warmup_and_stability(self):
        rows=[event(i,str(100+Decimal(i)/10))['data'] for i in range(397)]
        for n in (20,50):
            self.assertEqual(Evaluator(rows[:n]).get(f'ema{n}_prior').status,'insufficient_history')
            self.assertEqual(Evaluator(rows[:n+1]).get(f'ema{n}_prior').status,'valid')
            before=Evaluator(rows).get(f'ema{n}_prior').value
            changed=deepcopy(rows); changed[-1]['close']='10000'
            self.assertEqual(Evaluator(changed).get(f'ema{n}_prior').value,before)
        self.assertFalse(Evaluator(rows[:396]).get('ema50_prior').stable)
        self.assertTrue(Evaluator(rows).get('ema50_prior').stable)

    def test_hashes_separate_families_parameters_and_eligibility(self):
        a=StrategySpec(); b=StrategySpec(family=TREND_FAMILY)
        self.assertNotEqual(a.strategy_hash,b.strategy_hash)
        self.assertNotEqual(a.strategy_hash,replace(a,lookback_bars=21).strategy_hash)
        self.assertNotEqual(a.strategy_hash,replace(a,cooldown_bars=1).strategy_hash)
        self.assertIn('alternative',a.definition()); self.assertIn('C12',a.definition()['downstream'])

    def test_invalid_strategy_configs_fail(self):
        for bad in ({'family':'unknown'},{'version':True},{'timeframe':'2m'},{'lookback_bars':True},{'lookback_bars':1},
                    {'sides':[]},{'sides':['buy']},{'entry_window_ms':0},{'cooldown_bars':-1},{'family':TREND_FAMILY,'lookback_bars':21}):
            with self.subTest(bad=bad),self.assertRaises(ValidationError): StrategySpec(**bad)
        for bad in ({'metadata_mode':'pretend'},{'max_metadata_age_ms':True},{'max_detection_lag_ms':0},{'enabled_symbols':[]}):
            with self.assertRaises(ValidationError): CandidateConfig(**bad)
        with self.assertRaises(ValidationError): StrategySpec.from_dict({'surprise':True})
        with self.assertRaises(ValidationError): CandidateConfig.from_dict({'surprise':True})

    def test_candidate_is_frozen_and_does_not_contain_trade_policy(self):
        a=engine(); list(a.run([event(0),event(1)])); rec=a.advance(event(2,'102'))[0].document()
        specdoc=rec['candidate']; c=CandidateSpec.from_dict(specdoc); specdoc['reference_price']='1'
        self.assertEqual(c.document()['reference_price'],'102'); self.assertNotIn('stop_price',c.document()); self.assertNotIn('quantity',c.document())
        changed=c.document(); changed['candidate_id']='0'*64
        with self.assertRaises(ValidationError): CandidateSpec.create(changed)
        changed=c.document(); changed['reference_price']='101'
        with self.assertRaises(ValidationError): CandidateSpec.create(changed)
