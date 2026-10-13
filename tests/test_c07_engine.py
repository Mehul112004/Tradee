from copy import deepcopy
import json
import unittest
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c07 import ExecutionConfig, FeeSchedule, ExecutionEngine
from tests.c07_support import *


class ExecutionEngineTests(unittest.TestCase):
    def evaluate(self,e,when=START+1000): return e.evaluate(e.intents[0],when).document()
    def rejected(self,e,reason,when=START+1000):
        d=self.evaluate(e,when); self.assertFalse(d['ready']); self.assertIn(reason,d['reasons']); self.assertIsNone(d['fill']); return d

    def test_buy_golden_fee_spread_slippage_and_funding(self):
        d=self.evaluate(seeded()); self.assertTrue(d['ready'])
        self.assertEqual(d['fill']['price'],'100.2'); self.assertEqual(d['fill']['fee_usdt'],'0.0501')
        self.assertEqual(d['costs']['execution_plus_fee_cost_usdt'],'0.2501')
        self.assertEqual(d['funding']['estimated_cashflow_usdt'],'-0.1')
        self.assertEqual(d['projected_execution_cost_with_next_funding_usdt'],'0.3501')

    def test_sell_is_bid_taker_and_funding_credit_has_correct_sign(self):
        d=self.evaluate(seeded(intents=[intent(side='sell',stop_price='101')]))
        self.assertEqual(d['fill']['price'],'99.8'); self.assertEqual(d['fill']['fee_usdt'],'0.0499')
        self.assertEqual(d['costs']['execution_plus_fee_cost_usdt'],'0.2499')
        self.assertEqual(d['projected_execution_cost_with_next_funding_usdt'],'0.1499')

    def test_latency_budget_and_expiry_are_explicit(self):
        e=seeded(config=ExecutionConfig(manual_delay_ms=30000))
        self.rejected(e,'delay_not_elapsed')
        self.rejected(e,'intent_expired',START+60000)

    def test_delay_recheck_uses_new_quote_not_detection_price(self):
        e=seeded(config=ExecutionConfig(manual_delay_ms=30000))
        e.push(event('mark',eid=3,stamp=START+30000)); e.push(event('quote',eid=4,stamp=START+30000,bid='100.8',ask='101'))
        self.rejected(e,'adverse_entry_drift_exceeded',START+30000)

    def test_quote_age_strict_boundary_and_missing_quote(self):
        e=seeded(); self.rejected(e,'stale_quote',START+6000)
        e=engine(); e.push(event('mark')); self.rejected(e,'missing_quote')

    def test_wide_spread_zero_size_and_liquidity_budget(self):
        for data,reason in ((dict(bid='99',ask='101'),'spread_budget_exceeded'),
                            (dict(ask_qty='0'),'liquidity_budget_exceeded'),(dict(ask_qty='3'),'liquidity_budget_exceeded')):
            e=engine(); e.push(event('mark')); e.push(event('quote',eid=2,**data)); self.rejected(e,reason)

    def test_latest_event_time_wins_over_late_older_quote(self):
        e=seeded(); e.push(event('quote',eid=3,stamp=START+500,available=START+1100,bid='89.9',ask='90.1'))
        d=self.evaluate(e,START+1100); self.assertEqual(d['source_event_id'],2); self.assertEqual(d['fill']['price'],'100.2')

    def test_same_millisecond_prefix_and_immutable_old_estimate(self):
        e=seeded(); first=e.evaluate(e.intents[0],START+1000); frozen=first.serialized
        e.push(event('quote',eid=3,bid='100',ask='100.2'))
        second=e.evaluate(e.intents[0],START+1000)
        self.assertEqual(first.document()['fill']['price'],'100.2'); self.assertEqual(second.document()['fill']['price'],'100.3')
        self.assertEqual(first.serialized,frozen); self.assertEqual(first.document()['fill']['fill_key'],second.document()['fill']['fill_key'])

    def test_no_backward_evaluation_or_duplicate_ordering(self):
        e=seeded()
        with self.assertRaises(ValidationError): e.evaluate(e.intents[0],START)
        self.assertFalse(e.push(event('quote',eid=2)))
        with self.assertRaises(ValidationError): e.push(event('quote',eid=1))

    def test_rounding_is_explicit_never_increases_quantity(self):
        i=intent(quantity='1.0004'); self.rejected(seeded(intents=[i]),'quantity_off_step')
        d=self.evaluate(seeded(intents=[i],config=ExecutionConfig(manual_delay_ms=0,quantity_rounding='floor')))
        self.assertEqual(d['effective_quantity'],'1'); self.assertEqual(d['requested_quantity'],'1.0004')

    def test_notional_and_reduce_only_quantity_limits(self):
        self.rejected(seeded(intents=[intent(quantity='0.001')]),'minimum_notional_not_met')
        i=intent(purpose='exit',side='sell',stop_price=None,holding_until_ms=None,quantity='0.001',reduce_only=True,position_quantity='0.001')
        self.assertTrue(self.evaluate(seeded(intents=[i]))['ready'])
        i=intent(purpose='exit',side='sell',stop_price=None,holding_until_ms=None,quantity='2',reduce_only=True,position_quantity='1')
        self.rejected(seeded(intents=[i]),'reduce_only_exceeds_position')

    def test_limit_touch_cannot_be_awarded_maker_fill(self):
        self.rejected(seeded(intents=[intent(order_type='LIMIT')]),'passive_execution_unsupported')

    def test_stop_invalidation_cost_r_and_market_take_bound(self):
        e=engine(); e.push(event('mark')); e.push(event('quote',eid=2,bid='98.7',ask='98.8'))
        self.rejected(e,'entry_already_invalidated')
        self.rejected(seeded(config=ExecutionConfig(manual_delay_ms=0,max_cost_r='0.25')),'cost_r_budget_exceeded')
        e=engine(); e.push(event('mark',mark_price='90')); e.push(event('quote',eid=2)); self.rejected(e,'market_take_bound_exceeded')

    def test_missing_mark_is_not_replaced_by_contract_quote(self):
        e=engine(); e.push(event('quote')); self.rejected(e,'missing_or_stale_mark')

    def test_observed_fee_not_available_or_expired(self):
        for f,reason in ((FeeSchedule('0.0005','0','test','observed',START+2000,START),'fee_not_available'),
                         (FeeSchedule('0.0005','0','test','observed',START,START,START+1000),'fee_expired')):
            self.rejected(seeded(fees=f),reason)

    def test_feature_prefix_stability_and_timeframe_checks(self):
        i=intent(required_features=['log_return_1'],feature_timeframe='1m')
        self.assertTrue(self.evaluate(seeded(intents=[i],features=[feature()]))['ready'])
        self.rejected(seeded(intents=[i],features=[feature(cursor=[START+1000,3])]),'missing_feature_context')
        self.rejected(seeded(intents=[i],features=[feature(values={'log_return_1':{'status':'valid','value':.1,'stable':False}})]),'unstable_feature:log_return_1')
        self.rejected(seeded(intents=[i],features=[]),'missing_feature_context')

    def test_corrupt_features_universe_and_versions_fail_before_evaluation(self):
        f=feature(); f['values']['log_return_1']['value']=99
        with self.assertRaises(ValidationError): engine(features=[f])
        d=dataset(); _,u,v=metadata(); u['as_of_ms']+=1
        with self.assertRaises(ValidationError): ExecutionEngine(d,[intent()],u,v,FeeSchedule('0','0','test'))

    def test_funding_horizon_boundary_and_optional_coverage(self):
        d=self.evaluate(seeded(intents=[intent(holding_until_ms=START+3600000)]))
        self.assertEqual(d['funding']['status'],'funding_boundary_ambiguous'); self.assertIsNone(d['projected_execution_cost_with_next_funding_usdt'])
        self.rejected(seeded(intents=[intent(holding_until_ms=None)],config=ExecutionConfig(manual_delay_ms=0,require_funding_estimate=True)),'funding_projection_unavailable')
        d=self.evaluate(seeded(intents=[intent(holding_until_ms=START+3500000)])); self.assertEqual(d['funding']['estimated_cashflow_usdt'],'0')

    def test_modeled_bar_is_explicit_coarse_and_has_no_historical_funding_forecast(self):
        cfg=ExecutionConfig(market_model='modeled_bar',metadata_mode='research_assumption',bar_mark_proxy='bar_close',manual_delay_ms=30000)
        e=engine(config=cfg,intents=[intent(expires_ms=START+120000)],mode='modeled'); e.push(bar())
        d=self.evaluate(e,START+60000); self.assertTrue(d['ready']); self.assertEqual(d['fill']['price'],'100.1')
        self.assertEqual(d['funding']['status'],'unsupported_modeled_coverage'); self.assertIsNone(d['projected_execution_cost_with_next_funding_usdt'])

    def test_bar_cannot_supply_an_exact_intrabar_delayed_fill(self):
        cfg=ExecutionConfig(market_model='modeled_bar',metadata_mode='research_assumption',bar_mark_proxy='bar_close',manual_delay_ms=30000)
        e=engine(config=cfg,mode='modeled'); e.push(bar(opened=START-60000))
        self.rejected(e,'bar_predates_action_time',START+30000)

    def test_model_mode_and_proxy_mismatch_is_rejected(self):
        with self.assertRaises(ValidationError): engine(mode='modeled')
        cfg=ExecutionConfig(market_model='modeled_bar',metadata_mode='research_assumption',manual_delay_ms=0)
        e=engine(config=cfg,intents=[intent(expires_ms=START+120000)],mode='modeled'); e.push(bar())
        self.rejected(e,'historical_mark_coverage_unsupported',START+60000)

    def test_checkpoint_every_split_preserves_report(self):
        events=[event('mark'),event('quote',eid=2),event('quote',eid=3,stamp=START+1500,bid='100',ask='100.2')]
        a=engine()
        for e in events: a.push(e)
        want=a.report(START+1500).serialized
        for split in range(4):
            b=engine()
            for e in events[:split]: b.push(e)
            c=ExecutionEngine.restore(b.dataset,b.intents,b.universe,b.versions,b.fees,b.config,b.features,b.decision_ms,json.loads(json.dumps(b.checkpoint())))
            for e in events[split:]: c.push(e)
            self.assertEqual(c.report(START+1500).serialized,want)

    def test_bad_source_and_checkpoint_preserve_failure(self):
        e=engine(); bad=event('quote',bid='101',ask='100')
        with self.assertRaises(ValidationError): e.push(bad)
        self.assertEqual(e.event_count,0)
        cp=e.checkpoint(); cp['run_hash']='wrong'
        with self.assertRaises(ValidationError): ExecutionEngine.restore(e.dataset,e.intents,e.universe,e.versions,e.fees,e.config,e.features,e.decision_ms,cp)

    def test_timer_evaluation_cannot_go_backwards_without_new_events(self):
        e=seeded(); self.evaluate(e,START+2000)
        with self.assertRaises(ValidationError): self.evaluate(e,START+1500)

    def test_entry_close_to_settlement_suppresses_projection(self):
        e=engine(); e.push(event('mark',next_funding_ms=START+16000)); e.push(event('quote',eid=2))
        d=self.evaluate(e); self.assertTrue(d['ready'])
        self.assertEqual(d['funding']['status'],'funding_boundary_ambiguous')
        self.assertIsNone(d['projected_execution_cost_with_next_funding_usdt'])

    def test_zero_after_floor_and_max_quantity_fail_closed(self):
        self.rejected(seeded(intents=[intent(quantity='0.0001')],config=ExecutionConfig(manual_delay_ms=0,quantity_rounding='floor')),'quantity_below_minimum')
        self.rejected(seeded(intents=[intent(quantity='10000')]),'quantity_above_maximum')

    def test_unavailable_and_wrong_dataset_features_cannot_join(self):
        i=intent(required_features=['log_return_1'],feature_timeframe='1m')
        for f in (feature(evaluation_as_of_ms=START+2000),feature(dataset_hash='different'),feature(target_end_ms=START+2000)):
            self.rejected(seeded(intents=[i],features=[f]),'missing_feature_context')

    def test_stale_feature_and_metadata_are_distinct_rejections(self):
        i=intent(required_features=['log_return_1'],feature_timeframe='1m')
        self.rejected(seeded(intents=[i],features=[feature(target_end_ms=START-65000)]),'stale_feature_context')
        self.rejected(seeded(config=ExecutionConfig(manual_delay_ms=0,max_metadata_age_ms=1000)),'metadata_stale')

    def test_optional_unready_feature_does_not_block_required_valid_feature(self):
        i=intent(required_features=['log_return_1'],feature_timeframe='1m')
        f=feature(ready=False,values={'log_return_1':{'status':'valid','value':0,'stable':True},'atr14':{'status':'warming_up','value':None,'stable':False}})
        self.assertTrue(self.evaluate(seeded(intents=[i],features=[f]))['ready'])

    def test_ineligible_metadata_with_no_reason_still_cannot_fill(self):
        _,u,v=metadata(); u['decisions'][0].update(state='ineligible',reasons=[])
        u.pop('snapshot_hash'); u['snapshot_hash']=fingerprint(u)
        e=ExecutionEngine(dataset(),[intent()],u,v,FeeSchedule('0.0005','0','test'),ExecutionConfig(manual_delay_ms=0))
        e.push(event('mark')); e.push(event('quote',eid=2))
        self.rejected(e,'metadata_ineligible')
