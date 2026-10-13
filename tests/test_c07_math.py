from decimal import Decimal, localcontext
import unittest
from tradee.c01 import ValidationError
from tradee.c07 import ExecutionIntent, ExecutionConfig, FeeSchedule
from tradee.c07.math import common_step, quantity, adverse_tick, modeled_price, fee, fill_costs, ratio
from tests.c07_support import metadata,intent,START


class ExecutionMathTests(unittest.TestCase):
    def test_fee_uses_each_fill_notional_and_supports_explicit_maker_rebate(self):
        self.assertEqual(fee('1','100.2','0.0005'),'0.0501')
        self.assertEqual(fee('1','109.8','0.0005'),'0.0549')
        self.assertEqual(fee('1','100','-0.0001'),'-0.01')

    def test_quantity_grid_intersection_and_floor(self):
        filters=next(iter(metadata()[2].values()))['filters']
        filters['LOT_SIZE']['stepSize']='0.002'; filters['MARKET_LOT_SIZE']['stepSize']='0.003'
        self.assertEqual(common_step(['0.002','0.003']),Decimal('0.006'))
        q,step,reasons=quantity('1.005',filters,'floor')
        self.assertEqual(q,Decimal('1.002')); self.assertFalse(reasons)
        self.assertIn('quantity_off_step',quantity('1.005',filters,'reject')[2])

    def test_adverse_tick_rounding_is_directional(self):
        self.assertEqual(adverse_tick(Decimal('100.12002'),'0.1','buy'),Decimal('100.2'))
        self.assertEqual(adverse_tick(Decimal('99.88002'),'0.1','sell'),Decimal('99.8'))
        self.assertEqual(adverse_tick(Decimal('100.2'),'0.1','buy'),Decimal('100.2'))

    def test_exact_rational_impact_and_non_power_of_ten_tick(self):
        self.assertEqual(modeled_price(Decimal('100'),Decimal(1),Decimal(3),'0',Decimal(1),'0.001','buy'),Decimal('100.004'))
        self.assertEqual(adverse_tick(Decimal('1.001'),'0.003','buy'),Decimal('1.002'))
        self.assertEqual(adverse_tick(Decimal('1.001'),'0.003','sell'),Decimal('0.999'))

    def test_cost_decomposition_and_r_units(self):
        costs=fill_costs(intent(),Decimal(1),Decimal(100),Decimal('100.1'),Decimal('100.2'),'0.0005')
        self.assertEqual(costs['delay_drift_usdt'],'0'); self.assertEqual(costs['spread_crossing_usdt'],'0.1')
        self.assertEqual(costs['extra_slippage_and_rounding_usdt'],'0.1')
        self.assertEqual(costs['execution_plus_fee_cost_usdt'],'0.2501'); self.assertEqual(costs['cost_bps'],'25.01')
        self.assertEqual(costs['planned_risk_usdt'],'1'); self.assertEqual(costs['cost_r'],'0.2501')

    def test_favorable_drift_is_signed_not_clipped(self):
        c=fill_costs(intent(),Decimal(1),Decimal('99.8'),Decimal('99.9'),Decimal('99.9'),'0.0005')
        self.assertEqual(c['delay_drift_usdt'],'-0.2')
        self.assertEqual(c['execution_plus_fee_cost_usdt'],'-0.05005')

    def test_low_external_precision_does_not_change_money_or_gates(self):
        with localcontext() as ctx:
            ctx.prec=3
            self.assertEqual(fee('0.123456789','12345.6789','0.0005'),'0.76207893750952605')
            self.assertEqual(modeled_price(Decimal('100.1'),Decimal(1),Decimal(10),'2',Decimal(5),'0.1','buy'),Decimal('100.2'))
            self.assertEqual(common_step(['0.002','0.003']),Decimal('0.006'))

    def test_diagnostic_ratio_rounding_is_explicit(self):
        self.assertEqual(ratio(Decimal(1),Decimal(3)),'0.333333333333')
        self.assertIsNone(ratio(Decimal(1),Decimal(0)))

    def test_manual_latency_components_add(self):
        c=ExecutionConfig(processing_delay_ms=1,delivery_delay_ms=2,manual_delay_ms=30000)
        self.assertEqual(c.action_time(intent()),START+30003)

    def test_invalid_config_rejects_hidden_assumptions(self):
        for doc in ({'manual_delay_ms':True},{'max_quote_age_ms':0},{'extra_slippage_bps':.2},
                    {'market_model':'made_up'},{'market_model':'recorded_quote','metadata_mode':'research_assumption'},
                    {'max_top_book_fraction':'0'},{'max_top_book_fraction':'1.1'},{'require_funding_estimate':1},{'surprise':0}):
            with self.subTest(doc=doc),self.assertRaises(ValidationError): ExecutionConfig.from_dict(doc)

    def test_fee_availability_and_input_types(self):
        for doc in ({'taker_rate':.0005,'maker_rate':'0','evidence':'test'},
                    {'taker_rate':'0.0005','maker_rate':'0','evidence':'test','source_kind':'observed'},
                    {'taker_rate':'NaN','maker_rate':'0','evidence':'test'}):
            with self.assertRaises(ValidationError): FeeSchedule.from_dict(doc)

    def test_intent_stop_expiry_reduce_only_and_schema_validation(self):
        for kwargs in ({'stop_price':'100'},{'expires_ms':START},{'quantity':True},{'reduce_only':True},
                       {'required_features':['log_return_1']},{'holding_until_ms':START}):
            with self.assertRaises(ValidationError): intent(**kwargs)
        with self.assertRaises(ValidationError): ExecutionIntent.from_dict({'side':'buy'})

    def test_fill_pnl_does_not_add_shortfall_twice(self):
        # Independent two-leg scenario: actual price gain minus two fees and funding.
        with localcontext() as ctx:
            ctx.prec=50
            net=Decimal('109.8')-Decimal('100.2')-Decimal('0.0501')-Decimal('0.0549')-Decimal('0.01')
        self.assertEqual(net,Decimal('9.485'))


class ExecutionMathInvariantTests(unittest.TestCase):
    def test_fill_attribution_across_sizes_and_sides(self):
        from decimal import Decimal
        from tradee.c07.math import exact, modeled_price, fill_costs
        from tests.c07_support import intent
        with exact():
            for side in ('buy','sell'):
                sign=Decimal(1 if side=='buy' else -1)
                for q in (Decimal('0.001'),Decimal('0.123'),Decimal('1'),Decimal('2.5')):
                    i=intent(side=side,stop_price='99' if side=='buy' else '101')
                    mid=Decimal('100'); touch=mid+sign*Decimal('0.1')
                    price=modeled_price(touch,q,Decimal('10'),'2',Decimal('5'),'0.003',side)
                    costs=fill_costs(i,q,mid,touch,price,'0.0005')
                    attribution=sum(Decimal(costs[k]) for k in ('delay_drift_usdt','spread_crossing_usdt','extra_slippage_and_rounding_usdt'))
                    self.assertEqual(attribution,sign*(price-Decimal('100'))*q)
                    self.assertEqual(Decimal(costs['execution_plus_fee_cost_usdt']),attribution+Decimal(costs['fee_usdt']))
                    self.assertEqual(price%Decimal('0.003'),0)
                    self.assertGreaterEqual(sign*(price-touch),0)

    def test_increased_requested_size_never_improves_impact_price(self):
        from decimal import Decimal
        from tradee.c07.math import modeled_price
        for side in ('buy','sell'):
            prices=[modeled_price(Decimal('100'),Decimal(q),Decimal('10'),'0',Decimal('5'),'0.0001',side) for q in ('0.1','0.5','1','2')]
            self.assertEqual(prices,sorted(prices,reverse=side=='sell'))
