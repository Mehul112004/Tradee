from copy import deepcopy
from dataclasses import replace
import unittest
from tradee.c01 import ValidationError
from tradee.c13 import *
from tradee.c01.domain import fingerprint
from tests.c07_support import metadata,START


class PortfolioContractTests(unittest.TestCase):
    def test_policy_roundtrip_and_immutable_risk_map(self):
        d=RiskPolicy().document(); p=RiskPolicy.from_dict(d); self.assertEqual(p.document(),d)
        d['asset_risks']['BTCUSDT']['beta']='9'; self.assertEqual(p.asset_risks.document()['BTCUSDT']['beta'],'1')
        self.assertEqual(p.policy_hash,fingerprint(p.document()))

    def test_invalid_risk_configuration(self):
        for d in ({'leverage':2},{'leverage':True},{'version':True},{'total_risk_fraction':'0'},{'gross_notional_fraction':'1.1'},
                  {'per_trade_risk_fraction':0.01},{'max_positions':0},{'max_samples':True},{'stop_gap_bps':'1001'},
                  {'asset_risks':{}},{'asset_risks':{'BTCUSDT':{'group':'c','beta':'0'}}},{'max_quote_age':1}):
            with self.subTest(d=d),self.assertRaises(ValidationError): RiskPolicy.from_dict(d)

    def test_state_roundtrip_freezes_all_lists(self):
        s=AccountSnapshot(START,START,'1000','1000'); d=s.document(); self.assertEqual(AccountSnapshot.from_dict(d).document(),d)
        d['seen_candidates'].append('changed'); self.assertEqual(s.seen_candidates,())

    def test_unknown_coverage_is_explicit_and_not_boolean_coercion(self):
        self.assertFalse(AccountSnapshot(START,START,'1000','1000',funding_known=False).funding_known)
        for d in ({'funding_known':1},{'external_orders_known':'yes'},{'position_mode':'hedge'},{'basis':'binance_confirmed'},{'cash_usdt':'NaN'},{'seen_candidates':[{}]}):
            with self.assertRaises(ValidationError): AccountSnapshot.from_dict({**AccountSnapshot(START,START,'1000','1000').document(),**d})

    def test_mark_and_position_identity_clock_validation(self):
        _,u,_=metadata(); inst=u['decisions'][0]['instrument_id']
        for d in (dict(instrument_id=inst,symbol='ETHUSDT',price='100',event_ms=START,available_ms=START,event_id=1),
                  dict(instrument_id=inst,symbol='BTCUSDT',price='100',event_ms=START,available_ms=START-1,event_id=1)):
            with self.assertRaises(ValidationError): Mark.from_dict(d)
        m=Mark(inst,'BTCUSDT','100',START,START,1)
        with self.assertRaises(ValidationError): AccountSnapshot(START-1,START-1,'1000','1000',marks=[m.document()])

    def test_future_positions_and_duplicate_reservations_rejected(self):
        _,u,_=metadata(); inst=u['decisions'][0]['instrument_id']
        p=Position('p','c',inst,'BTCUSDT','long','1','100','99',START,'intraday','0.0005').document()
        with self.assertRaises(ValidationError): AccountSnapshot(START-1,START,'1000','1000',positions=[p])
        with self.assertRaises(ValidationError): AccountSnapshot(START,START,'1000','1000',positions=[p,p])
        r=Reservation('c',inst,'BTCUSDT','long','1','2','100','101','intraday',START,START+1000).document()
        with self.assertRaises(ValidationError): AccountSnapshot(START,START,'1000','1000',reservations=[r,r])

    def test_reservations_are_not_leveraged_or_permanent(self):
        _,u,_=metadata(); inst=u['decisions'][0]['instrument_id']
        for collateral,expiry in (('99',START+1),('101',START)):
            with self.assertRaises(ValidationError): Reservation('c',inst,'BTCUSDT','long','1','2','100',collateral,'swing',START,expiry)

    def test_negative_cash_can_be_represented_without_assuming_solvency(self):
        self.assertEqual(AccountSnapshot(START,START,'-2','1000').cash_usdt,'-2')

    def test_replay_config_strict_inputs(self):
        for d in ({'initial_cash_usdt':'0'},{'sample_interval_ms':0},{'max_events':True},{'unknown':1}):
            with self.assertRaises(ValidationError): ReplayConfig.from_dict(d)
