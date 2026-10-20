from copy import deepcopy
from dataclasses import replace
from decimal import localcontext
import unittest
from tradee.c13 import RiskPolicy,AccountSnapshot,Position,Reservation,Mark
from tradee.c13.risk import inspect
from tests.c07_support import metadata,START


class SharedRiskTests(unittest.TestCase):
    def setUp(self):
        _,u,_=metadata(); self.inst=u['decisions'][0]['instrument_id']; self.policy=RiskPolicy()
    def state(self,**kw):
        p=Position('p','candidate',self.inst,'BTCUSDT','long','1','100','99',START,'intraday','0.0005')
        m=Mark(self.inst,'BTCUSDT','102',START+1000,START+1000,1)
        return AccountSnapshot(**dict(dict(as_of_ms=START+1000,available_ms=START+1000,cash_usdt='999.95',peak_equity_usdt='1000',positions=[p.document()],marks=[m.document()]),**kw))
    def test_hand_calculated_linear_wallet_and_risk(self):
        d=inspect(self.state(),START+1000,self.policy)
        self.assertTrue(d['ready'],d['reasons']); self.assertEqual(d['equity_usdt'],'1001.95')
        self.assertEqual(d['exposure']['gross_notional_usdt'],'102')
        self.assertEqual(d['exposure']['stop_risk_usdt'],'3.357')
        self.assertEqual(d['exposure']['collateral_reserved_usdt'],'102.051')
        self.assertEqual(d['exposure']['worst_stress_loss_usdt'],'20.451')
    def test_short_pnl_and_stop_risk(self):
        p=Position('p','c',self.inst,'BTCUSDT','short','1','100','101',START,'swing','0.0005')
        m=Mark(self.inst,'BTCUSDT','98',START+1000,START+1000,1)
        d=inspect(self.state(positions=[p.document()],marks=[m.document()]),START+1000,self.policy)
        self.assertEqual(d['equity_usdt'],'1001.95'); self.assertEqual(d['exposure']['stop_risk_usdt'],'3.3535')
    def test_missing_stale_future_marks_never_zero_unrealized(self):
        for marks in ([],[Mark(self.inst,'BTCUSDT','102',START,START,1).document()]):
            d=inspect(self.state(marks=marks),START+5000,self.policy)
            self.assertFalse(d['ready']); self.assertIsNone(d['equity_usdt'])
    def test_unknown_funding_and_open_orders_block_admission(self):
        for change,reason in (({'funding_known':False},'account_funding_unknown'),({'external_orders_known':False},'external_open_orders_unknown')):
            d=inspect(self.state(**change),START+1000,self.policy); self.assertIn(reason,d['reasons'])
    def test_snapshot_age_and_future_account_flags(self):
        self.assertIn('account_snapshot_stale',inspect(self.state(),START+6000,self.policy)['reasons'])
        self.assertIn('account_snapshot_not_available',inspect(self.state(),START,self.policy)['reasons'])
    def test_expired_reservations_free_capacity_but_keep_identity(self):
        r=Reservation('c',self.inst,'BTCUSDT','long','1','2','100','101','intraday',START,START+1000).document()
        d=inspect(self.state(positions=[],reservations=[r]),START+1000,self.policy)
        self.assertEqual(d['active_reservations'],[]); self.assertEqual(d['exposure']['gross_notional_usdt'],'0')
    def test_joint_shocks_and_pending_fee_reservation_are_counted(self):
        r=Reservation('c',self.inst,'BTCUSDT','long','1','2','100','101','intraday',START,START+5000,closing_fee_usdt='0.05').document()
        d=inspect(self.state(positions=[],reservations=[r]),START+1000,self.policy)
        self.assertEqual(d['exposure']['worst_stress_loss_usdt'],'20.05')
    def test_unknown_risk_assignment_or_unavailable_map_fails_closed(self):
        p=replace(self.policy,asset_risks={'ETHUSDT':dict(group='c',beta='1')})
        self.assertIsNone(inspect(self.state(),START+1000,p)['equity_usdt'])
        self.assertIn('risk_map_not_yet_available',inspect(self.state(),START+1000,replace(self.policy,risk_map_available_ms=START+2000))['reasons'])
    def test_limits_and_drawdown_pause_new_risk(self):
        d=inspect(self.state(cash_usdt='100',peak_equity_usdt='1000'),START+1000,self.policy)
        self.assertIn('drawdown_pause',d['reasons']); self.assertTrue(d['exposure']['unsupported_margin_breach'])
    def test_opposite_asset_directions_do_not_erase_gross_group_beta_or_adverse_stress(self):
        from tradee.c01.domain import normalize
        raw,_,_=metadata(); eth=next(d['instrument_id'] for d in normalize(raw) if d['symbol']=='ETHUSDT')
        positions=[Position('btc','cb',self.inst,'BTCUSDT','long','1','100','99',START,'intraday','0.0005').document(),
            Position('eth','ce',eth,'ETHUSDT','short','1','100','101',START,'swing','0.0005').document()]
        marks=[Mark(i,s,'100',START+1000,START+1000,k).document() for k,(i,s) in enumerate(((self.inst,'BTCUSDT'),(eth,'ETHUSDT')),1)]
        d=inspect(self.state(positions=positions,marks=marks),START+1000,self.policy)['exposure']
        self.assertEqual(d['gross_notional_usdt'],'200'); self.assertEqual(d['absolute_beta_notional_usdt'],'200')
        self.assertEqual(d['groups']['crypto']['notional'],'200'); self.assertEqual(d['worst_stress_loss_usdt'],'40.1005')
        self.assertEqual(len(d['horizon_risk_usdt']),2)

    def test_caller_decimal_precision_does_not_change_wallet_math(self):
        a=inspect(self.state(),START+1000,self.policy)
        with localcontext() as ctx:
            ctx.prec=3; b=inspect(self.state(),START+1000,self.policy)
        self.assertEqual(a,b)
