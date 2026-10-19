from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from tradee.c01 import ValidationError
from tradee.c10 import TrainingWindow,EstimatorConfig,EstimateRequest
from tradee.c11 import SimulationStore
from tests.c10_support import *


class ExpectancyContractsTests(unittest.TestCase):
    def test_window_round_trip_and_strict_order(self):
        w=window(); self.assertEqual(TrainingWindow.from_dict(w.document()),w)
        for d in ({'start_ms':True,'end_ms':2,'cutoff_ms':3},{'start_ms':2,'end_ms':2,'cutoff_ms':3},{'start_ms':1,'end_ms':4,'cutoff_ms':3},{'start_ms':1,'end_ms':2},{**w.document(),'future':1}):
            with self.subTest(d=d),self.assertRaises(ValidationError): TrainingWindow.from_dict(d)

    def test_configuration_round_trip_and_invalid_fields(self):
        c=EstimatorConfig(); self.assertEqual(EstimatorConfig.from_dict(c.document()),c)
        for d in ({'version':True},{'version':2},{'cohort_fields':['side','side']},{'cohort_fields':['funding_bucket']},{'min_trades':0},{'seed':True},{'bin_ms':-1},{'bootstrap_replicates':99},{'confidence_level':'1'},{'min_fill_fraction':'1.1'},{'lower_bound_buffer_r':'-1'},{'extra':1}):
            with self.subTest(d=d),self.assertRaises(ValidationError): EstimatorConfig.from_dict(d)

    def test_shipped_defaults_are_defensive_and_prespecified(self):
        root=Path(__file__).resolve().parents[1]; c=EstimatorConfig.from_dict(json.loads((root/'configs/c10_estimator.json').read_text()))
        self.assertEqual(c.min_trades,30); self.assertEqual(c.cohort_fields,('side','horizon')); self.assertEqual(c.block_bins,3)
        self.assertEqual(EstimatorConfig(cohort_fields=['horizon','side']).cohort_fields,c.cohort_fields)

    def test_request_round_trip_requires_current_matching_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            ss=SimulationStore(Path(folder)/'s.db'); r,_=simulation(n=2); h=ss.commit(r)['run_hash']; q=request(ss,h)
            self.assertEqual(q,EstimateRequest.from_dict(q.document()))
            for kw in ({'evaluation_ms':q.candidate.document()['detected_ms']-1},{'evaluation_ms':q.candidate.document()['expires_ms']},{'scenario':{**q.scenario.document(),'strategy':{'timeframe':'15m'}}}):
                with self.assertRaises(ValidationError): EstimateRequest.from_dict({**q.document(),**kw})
            with self.assertRaises(ValidationError): EstimateRequest.from_dict({**q.document(),'net_r':'100'})

    def test_request_rejects_direction_excluded_by_strategy(self):
        from tradee.c01.domain import fingerprint
        from tests.c09_support import prepared
        e,intent,_=prepared(side='short'); c=intent.candidate.document(); f=intent.feature_snapshot.document()
        s=Scenario('short_only',spec(sides=('long',)).document(),intent.policy.document(),'1')
        c['strategy_hash']=s.strategy.strategy_hash
        c['candidate_id']=fingerprint([c['strategy_hash'],c['instrument_id'],c['timeframe'],c['target_open_ms'],c['side']])
        with self.assertRaises(ValidationError): EstimateRequest(c,f,s.document(),e.execution.document(),e.fees.document(),e.funding_config.document(),e.meta_config.document(),c['detected_ms'])
