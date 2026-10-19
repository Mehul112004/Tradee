from copy import deepcopy
from dataclasses import replace
import unittest
from tradee.c01 import ValidationError
from tradee.c08 import CandidateConfig
from tradee.c11 import Scenario, SimulationConfig, Simulator
from tests.c11_support import fixture
from tests.c08_support import spec, START


class SimulationContractsTests(unittest.TestCase):
    def test_configuration_round_trip_and_strict_fields(self):
        c=SimulationConfig(); self.assertEqual(c,SimulationConfig.from_dict(c.document()))
        s=Scenario('range',spec().document(),{},'1'); self.assertEqual(s,Scenario.from_dict(s.document()))
        for doc in ({'version':True},{'version':2},{'sample_interval_ms':0},{'max_candidates':True},{'max_samples':-1},{'extra':1},[],{'decision_start_ms':4,'decision_end_ms':4}):
            with self.subTest(doc=doc),self.assertRaises(ValidationError): SimulationConfig.from_dict(doc)

    def test_explicit_valid_size_horizon_and_policy(self):
        base=Scenario('range',spec().document(),{},'1').document()
        for field,value in (('quantity','0'),('quantity','NaN'),('name','Bad name'),('horizon','hourly'),('policy',{'extra':1}),('strategy',{'timeframe':'2m'})):
            with self.subTest(field=field,value=value),self.assertRaises(ValidationError): Scenario.from_dict({**base,field:value})
        for key in ('quantity','strategy','policy','name'):
            doc=deepcopy(base); del doc[key]
            with self.assertRaises(ValidationError): Scenario.from_dict(doc)

    def test_window_and_budgets_are_bounded_by_snapshot(self):
        s,_=fixture(); d=s.dataset
        for c in (SimulationConfig(decision_start_ms=START-1),SimulationConfig(decision_end_ms=d['end_ms']),SimulationConfig(max_samples=1)):
            with self.assertRaises(ValidationError): c.window(d)

    def test_duplicate_scenarios_and_metadata_conflicts_rejected(self):
        s,_=fixture(); a=s.scenarios[0]
        for scenarios in ([],[a,a],[a,Scenario('duplicate',a.strategy.document(),a.policy.document(),a.quantity)]):
            with self.assertRaises(ValidationError): fixture(scenarios=scenarios)
        with self.assertRaises(ValidationError): fixture(candidates=CandidateConfig(metadata_mode='research_assumption'))

    def test_recorded_and_modeled_source_contracts_fail_closed(self):
        from tradee.c09 import TradePolicy
        for policy in (TradePolicy(trigger_source='mark'),TradePolicy(trigger_source='contract_trade')):
            s,_=fixture(policy=policy); d=deepcopy(s.dataset); d['kinds']=['candle']
            with self.assertRaises(ValidationError): Simulator(d,s.scenarios,s.snapshots,s.versions,s.fees,s.execution)
        s,_=fixture()
        with self.assertRaises(ValidationError): fixture(execution=replace(s.execution,market_model='modeled_bar',bar_mark_proxy='bar_close'))

    def test_missing_event_count_and_fees_rejected_even_with_no_candidates(self):
        s,_=fixture()
        for count in (None,True,-1):
            d={**s.dataset,'event_count':count}
            with self.assertRaises(ValidationError): Simulator(d,s.scenarios,s.snapshots,s.versions,s.fees,s.execution)
        with self.assertRaises(ValidationError): Simulator(s.dataset,s.scenarios,s.snapshots,s.versions,None,s.execution)
