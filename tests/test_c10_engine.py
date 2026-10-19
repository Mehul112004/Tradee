from copy import deepcopy
from dataclasses import replace
from decimal import localcontext
from pathlib import Path
import tempfile
import unittest
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c10 import *
from tradee.c10.engine import verified_model
from tradee.c11 import SimulationStore
from tests.c10_support import *


class FrozenEstimatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.ss=SimulationStore(Path(cls.tmp.name)/'s.db')
        r,_=simulation(); cls.training=cls.ss.commit(r)['run_hash']
        cls.data=snapshot(cls.ss,[cls.training],window(),config()); cls.fitted=fit(cls.data,config()); cls.model=publish(cls.fitted,window().cutoff_ms,'modeled')
        r,_=simulation(start=START+13*BIN); cls.later=cls.ss.commit(r)['run_hash']; cls.q=request(cls.ss,cls.later)

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_ready_frozen_mean_bounds_and_eligibility(self):
        d=estimate(self.model,self.q).document(); self.assertEqual(d['status'],'estimated'); self.assertTrue(d['ready']); self.assertTrue(d['eligible'])
        self.assertEqual(d['statistics']['mean_net_r'],'2.455942622951'); self.assertIsNotNone(d['uncertainty']['lower_mean_net_r'])
        self.assertEqual(d['model_availability_basis'],'modeled'); self.assertEqual(d['feature_snapshot_hash'],self.q.candidate.document()['feature_snapshot_hash'])

    def test_inference_never_imports_source_or_current_outcomes(self):
        from unittest.mock import patch
        with patch('tradee.c10.source.snapshot',side_effect=AssertionError('inference must not train')):
            self.assertTrue(estimate(self.model,self.q).document()['ready'])
        self.assertNotIn('net_r',self.q.document()); self.assertNotIn('outcome',self.q.document())

    def test_future_publication_training_equality_and_staleness_abstain(self):
        future=publish(self.fitted,self.q.evaluation_ms+1,'modeled')
        self.assertIn('estimator_not_yet_available',estimate(future,self.q).document()['reasons'])
        f=self.fitted.document(); f['window']['cutoff_ms']=self.q.evaluation_ms
        model=publish(ExpectancyRecord.create(f),self.q.evaluation_ms,'modeled')
        self.assertIn('training_not_strictly_earlier',estimate(model,self.q).document()['reasons'])
        f=self.fitted.document(); f['config']['max_model_age_ms']=1
        model=publish(ExpectancyRecord.create(f),self.q.evaluation_ms,'modeled')
        self.assertIn('stale_estimator',estimate(model,self.q).document()['reasons'])

    def test_already_trained_candidate_is_never_scored_as_new(self):
        q=request(self.ss,self.training)
        d=estimate(self.model,q).document(); self.assertFalse(d['ready']); self.assertIn('candidate_seen_in_training',d['reasons'])
        self.assertIsNone(d['statistics'])

    def test_different_fees_policy_quantity_features_or_execution_abstain(self):
        original=self.q.document()
        variants=[]
        for field,part in (('fees',{'taker_rate':'0.001'}),('execution',{'manual_delay_ms':1})):
            q=deepcopy(original); q[field].update(part); variants.append(q)
        for field,value in (('quantity','0.5'),('policy',{'target_r':'3'})):
            q=deepcopy(original); q['scenario'][field]=value; variants.append(q)
        for q in variants:
            d=estimate(self.model,EstimateRequest.from_dict(q)).document(); self.assertFalse(d['ready'])
            self.assertIn('incompatible_strategy_policy_cost_or_feature_protocol',d['reasons'])

    def test_insufficient_and_negative_bound_models_abstain_without_fallback(self):
        f=fit(self.data,replace(config(),min_trades=30)); d=estimate(publish(f,window().cutoff_ms,'modeled'),self.q).document()
        self.assertEqual(d['status'],'abstained'); self.assertIn('insufficient_mature_trades',d['reasons']); self.assertIsNone(d['statistics'])
        f=fit(self.data,replace(config(),lower_bound_buffer_r='100')); d=estimate(publish(f,window().cutoff_ms,'modeled'),self.q).document()
        self.assertTrue(d['ready']); self.assertFalse(d['eligible']); self.assertEqual(d['reasons'],['lower_bound_not_above_buffer'])

    def test_empty_declared_cohort_remains_visible_instead_of_silent_pooling(self):
        f=self.fitted.document(); c=next(iter(f['cohorts'].values())); c['observed_mature_symbols']=[]
        d=estimate(publish(ExpectancyRecord.create(f),window().cutoff_ms,'modeled'),self.q).document()
        self.assertIn('unseen_mature_symbol',d['reasons']); self.assertFalse(d['ready'])

    def test_publication_validation_and_corrupt_model_hash(self):
        for available,basis in ((window().cutoff_ms-1,'modeled'),(True,'modeled'),(window().cutoff_ms,'guess')):
            with self.assertRaises(ValidationError): publish(self.fitted,available,basis)
        d={'model_hash':'0'*64,**self.model.document()}
        with self.assertRaises(ValidationError): verified_model(d)
        d=self.model.document(); d['fit']['ready']=False
        with self.assertRaises(ValidationError): verified_model(d)

    def test_exact_repeated_fit_is_independent_of_decimal_context(self):
        a=fit(self.data,config())
        with localcontext() as ctx:
            ctx.prec=3; b=fit(self.data,config())
        self.assertEqual(a,b)

    def test_frozen_later_evaluation_has_predictions_coverage_and_reliability(self):
        start=START+13*BIN; w=window(start=start)
        r=evaluate(self.model,self.ss,[self.later],w).document()
        self.assertTrue(r['ready']); self.assertEqual(r['coverage']['matched_estimated_mature'],12); self.assertEqual(r['coverage']['matched_eligible_mature'],12)
        self.assertEqual(r['metrics']['empirical_frequency_brier_score'],'0')
        self.assertEqual(r['metrics']['all_mature_mean_net_r'],'2.455942622951')
        self.assertTrue(r['metrics']['reliability_bins'])
        with self.assertRaises(ValidationError): evaluate(self.model,self.ss,[self.training],window())

    def test_future_labels_do_not_change_frozen_predictions(self):
        r,_=simulation(start=START+13*BIN,positive=False); h=self.ss.commit(r)['run_hash']
        a=evaluate(self.model,self.ss,[self.later],window(start=START+13*BIN)).document()
        b=evaluate(self.model,self.ss,[h],window(start=START+13*BIN)).document()
        self.assertEqual([p['prediction']['statistics'] for p in a['predictions']],[p['prediction']['statistics'] for p in b['predictions']])
        self.assertNotEqual(a['metrics']['all_mature_mean_net_r'],b['metrics']['all_mature_mean_net_r'])

    def test_cohort_configuration_cannot_change_after_snapshot_selection(self):
        with self.assertRaises(ValidationError): fit(self.data,replace(config(),cohort_fields=('side','horizon','symbol')))

    def test_feature_definition_changes_abstain_and_unstable_values_are_invalid(self):
        from tradee.c01.domain import fingerprint
        q=self.q.document(); f=q['feature_snapshot']; f.pop('snapshot_hash'); f['definition_hashes']['log_return_1']='1'*64
        f['snapshot_hash']=fingerprint(f); q['candidate']['feature_snapshot_hash']=f['snapshot_hash']
        d=estimate(self.model,EstimateRequest.from_dict(q)).document()
        self.assertFalse(d['ready']); self.assertIn('incompatible_strategy_policy_cost_or_feature_protocol',d['reasons'])
        q=self.q.document(); f=q['feature_snapshot']; f.pop('snapshot_hash'); f['values']['log_return_1']['stable']=False
        f['snapshot_hash']=fingerprint(f); q['candidate']['feature_snapshot_hash']=f['snapshot_hash']
        with self.assertRaises(ValidationError): EstimateRequest.from_dict(q)

    def test_frozen_unfilled_and_unresolved_evaluation_keeps_coverage(self):
        r,_=simulation(start=START+13*BIN,unknown_funding=True); h=self.ss.commit(r)['run_hash']
        e=evaluate(self.model,self.ss,[h],window(start=START+13*BIN)).document()
        self.assertFalse(e['ready']); self.assertEqual(e['coverage']['estimated'],12)
        self.assertEqual(e['coverage']['matched_estimated_mature'],0); self.assertIsNone(e['metrics']['empirical_frequency_brier_score'])

    def test_fit_cohort_and_source_run_budgets_fail_without_truncation(self):
        with self.assertRaises(ValidationError): snapshot(self.ss,[self.training,self.later],window(),replace(config(),max_source_runs=1))
        # Declare a second separate cohort rather than silently collapsing it.
        d=self.data.document(); key=next(iter(d['cohorts'])); decl=d['cohorts'][key]
        from tradee.c10.contracts import cohort_key
        attributes={**decl['attributes'],'side':'short'}
        d['cohorts'][cohort_key(decl['protocol_hash'],attributes,config())]=dict(protocol_hash=decl['protocol_hash'],attributes=attributes)
        with self.assertRaises(ValidationError): fit(ExpectancyRecord.create(d),replace(config(),max_cohorts=1))

    def test_global_work_budget_counts_empty_draws_across_cohorts(self):
        from tradee.c10.contracts import cohort_key
        cfg=config(min_trades=3,min_occupied_bins=3,min_occupied_spans=3,max_empty_replicate_fraction='1',max_bootstrap_work=39000)
        d=self.data.document(); d['rows']=d['rows'][:3]
        d['window']=TrainingWindow(START,START+100*BIN,START+100*BIN+1).document()
        old_key=next(iter(d['cohorts'])); decl=d['cohorts'][old_key]
        attrs={**decl['attributes'],'horizon':'swing'}; key=cohort_key(decl['protocol_hash'],attrs,cfg)
        d['cohorts'][key]=dict(protocol_hash=decl['protocol_hash'],attributes=attrs)
        copies=deepcopy(d['rows'])
        for r in copies: r['cohort_hash']=key; r['attributes']['horizon']='swing'; r['candidate_id']='second-'+r['candidate_id']
        d['rows']+=copies
        # Two 100-bin x 200-draw cohorts cost 40,000 index visits, including
        # empty draws; 39,000 must fail rather than counting only usable draws.
        with self.assertRaisesRegex(ValidationError,'Total cohort bootstrap'): fit(ExpectancyRecord.create(d),cfg)
