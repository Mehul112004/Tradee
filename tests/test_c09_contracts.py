from copy import deepcopy
from dataclasses import replace
import unittest
from tradee.c01 import ValidationError
from tradee.c09 import TradeIntent,TradePolicy
from tests.c09_support import *


class LifecycleContractTests(unittest.TestCase):
    def test_fixed_levels_long_and_short_and_optional_partial(self):
        _,a,_=prepared(partial_target_r='1'); _,b,_=prepared('short',partial_target_r='1')
        self.assertEqual(a.levels(),dict(stop='100.98',target='104.04',partial='103.02',reference_risk_per_unit='1.02'))
        self.assertEqual(b.levels()['stop'],'98.98'); self.assertEqual(b.levels()['target'],'96.04')

    def test_policy_changes_and_size_change_trade_identity(self):
        _,a,_=prepared(); _,b,_=prepared(quantity='2'); _,c,_=prepared(target_r='3')
        self.assertNotEqual(a.trade_id,b.trade_id); self.assertNotEqual(a.trade_id,c.trade_id)
        self.assertEqual(a.trade_id,TradeIntent.from_dict(a.document()).trade_id)

    def test_defensive_immutable_evidence(self):
        _,a,_=prepared(); doc=a.document(); b=TradeIntent.from_dict(doc)
        doc['candidate']['reference_price']='900'
        self.assertEqual(a.candidate.document()['reference_price'],'102'); self.assertEqual(b.candidate.document()['reference_price'],'102')

    def test_missing_mismatched_and_future_feature_evidence_rejected(self):
        _,a,_=prepared(); doc=a.document()
        for key,value in (('instrument_id','wrong'),('input_prefix_hash','0'*64),('target_open_ms',START),('assumed_usable_ms',DETECT+1)):
            bad=deepcopy(doc); bad['feature_snapshot'].pop('snapshot_hash'); bad['feature_snapshot'][key]=value
            bad['feature_snapshot']['snapshot_hash']=fingerprint(bad['feature_snapshot'])
            with self.assertRaises(ValidationError): TradeIntent.from_dict(bad)

    def test_invalid_policy_fields_and_numeric_types(self):
        for bad in ({'version':True},{'stop_fraction':'1'},{'stop_fraction':.01},{'target_r':'0'},{'max_holding_ms':0},
                    {'trigger_source':'index'},{'partial_target_r':'2'},{'partial_fraction':'1'},{'max_trigger_age_ms':True},{'exit_delay_ms':-1}):
            with self.subTest(bad=bad),self.assertRaises(ValidationError): TradePolicy(**bad)
        with self.assertRaises(ValidationError): TradePolicy.from_dict({'surprise':True})
        _,a,_=prepared(); doc=a.document(); doc['surprise']=1
        with self.assertRaises(ValidationError): TradeIntent.from_dict(doc)

    def test_unsupported_modeled_trigger_and_dataset_mismatch_fail_closed(self):
        with self.assertRaises(ValidationError): prepared(mode='modeled',policy=TradePolicy())
        e,i,_=prepared(); ds={**e.dataset,'dataset_hash':'other'}
        with self.assertRaises(ValidationError): LifecycleEngine(ds,[i],e.book.snapshots,e.book.versions,e.fees,e.execution)
