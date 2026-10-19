from copy import deepcopy
from dataclasses import replace
import unittest
from tradee.c01 import ValidationError
from tradee.c12 import Experiment, EvidencePolicy, Split
from tests.c12_support import plan,split,START,BIN


class ResearchContractTests(unittest.TestCase):
    def test_roundtrip_and_deep_freeze(self):
        d=plan(); e=Experiment.from_dict(d); frozen=e.document(); self.assertEqual(Experiment.from_dict(frozen).document(),frozen)
        d['variants'][0]['parameters']['buffer_r']='99'; self.assertEqual(e.document(),frozen)
        frozen['variants'][0]['estimator']['min_trades']=999; self.assertEqual(e.variants[0].estimator.min_trades,6)

    def test_strict_fields_and_version(self):
        for change in ({'oops':1},{'version':True},{'historical_trials':True},{'family_trial_budget':0},{'holdout_status':'fresh-maybe'},{'policy':False}):
            with self.subTest(change=change),self.assertRaises(ValidationError): Experiment.from_dict(plan(**change))

    def test_chronology_and_outer_ownership(self):
        for mutate in (lambda d:d['folds'][1]['split']['test'].update(start_ms=START+30*BIN),
                       lambda d:d['folds'][0]['split']['train'].update(cutoff_ms=START+25*BIN),
                       lambda d:d['folds'][0]['inner'][0]['test'].update(cutoff_ms=START+25*BIN),
                       lambda d:d['folds'][0]['inner'].append(split('overlap',12,18,22))):
            d=plan(); mutate(d)
            with self.assertRaises(ValidationError): Experiment.from_dict(d)

    def test_tuning_cannot_use_no_inner_folds(self):
        for key in ('folds','holdout'):
            d=plan()
            if key=='folds': d[key][0]['inner']=[]
            else: d[key]['inner']=[]
            with self.assertRaisesRegex(ValidationError,'Tuning'): Experiment.from_dict(d)

    def test_single_fixed_rule_does_not_require_fake_selection(self):
        d=plan(); d['variants']=d['variants'][:1]
        for f in (*d['folds'],d['holdout']): f['inner']=[]
        self.assertEqual(len(Experiment.from_dict(d).variants),1)

    def test_holdout_sources_are_distinct_and_hashes_valid(self):
        for value in (['a'*64],['invalid'],[],['b'*64,'b'*64]):
            d=plan(); d['variants'][0]['holdout_runs']=value
            with self.assertRaises(ValidationError): Experiment.from_dict(d)

    def test_reference_validation(self):
        for field,value in (('stress_of','absent'),('neighbor_of','a')):
            d=plan(); d['variants'][0][field]=value
            with self.assertRaises(ValidationError): Experiment.from_dict(d)

    def test_budget_and_tail_resolution(self):
        for change in ({'family_trial_budget':3},{'historical_trials':1},{'family_trial_budget':1000}):
            with self.assertRaises(ValidationError): Experiment.from_dict(plan(**change))

    def test_policy_validations(self):
        for change in ({'alpha':'0'},{'alpha':'0.5'},{'block_bins':True},{'require_stress':1},{'min_estimated_fraction':'1.1'},{'bootstrap_replicates':99}):
            with self.assertRaises(ValidationError): EvidencePolicy(**change)

    def test_gap_leaves_history(self):
        d=split('gap',12,12,20,gap=12*BIN)
        with self.assertRaises(ValidationError): Split.from_dict(d)

    def test_every_referenced_source_needs_a_frozen_report_digest(self):
        for refs in ({},{'a'*64:'not-a-hash'},{'a'*64:'e'*64}):
            with self.assertRaisesRegex(ValidationError,'report hash'): Experiment.from_dict(plan(source_report_hashes=refs))
