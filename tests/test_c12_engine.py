from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tradee.c01 import ValidationError
from tradee.c03.contracts import FrozenRecord
from tradee.c12 import ResearchStore,Split,Experiment
from tradee.c12.engine import purged_snapshot,stress_protocol
from tests.c12_support import sources,split,START,BIN


class WalkForwardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared=tempfile.TemporaryDirectory(); cls.ss,cls.plan=sources(cls.shared.name)
        from tests.c10_support import simulation
        from tests.c12_support import stress
        cls.extra={}
        for name,kwargs in (('negative',dict(positive=False)),('unknown',dict(unknown_funding=True))):
            r,events=simulation(n=12,start=START+48*BIN,**kwargs)
            cls.extra[name]=(cls.ss.commit(r)['run_hash'],cls.ss.commit(stress(r,events))['run_hash'])
    @classmethod
    def tearDownClass(cls): cls.shared.cleanup()
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store=ResearchStore(Path(self.tmp.name)/'research.db'); self.h=self.store.register(self.plan)['experiment_hash']

    def test_nested_development_and_sealed_holdout_have_disjoint_frozen_predictions(self):
        d=self.store.run(self.h,self.ss); self.assertTrue(d['ready'],d['reasons'])
        self.assertEqual([f['winner'] for f in d['folds']],['a','a']); self.assertFalse(d['holdout_accessed'])
        self.assertEqual(d['evidence']['coverage']['eligible_mature'],16)
        self.assertEqual(d['evidence']['utility_r_per_candidate'],'2.455942622951')
        self.assertEqual(self.store.decision(self.h)['status'],'awaiting_holdout')
        before=self.store.jobs(self.h); self.assertFalse(any(x['key'].startswith('holdout/') for x in before))
        h=self.store.open_holdout(self.h,self.ss,'Synthetic explicit first access')
        self.assertTrue(h['ready'],h['reasons']); self.assertFalse(h['live_approved'])
        self.assertEqual(h['result']['model_hash'],d['final_training']['model_hash'])
        self.assertEqual(self.store.decision(self.h)['status'],'research_candidate')
        self.assertEqual(self.store.open_holdout(self.h,self.ss,'Idempotent retry'),h)
        self.assertEqual(len([e for e in self.store.events(self.h) if e['kind']=='holdout_opened']),1)
        self.assertEqual(self.store.run(self.h,self.ss),d)

    def test_no_holdout_source_is_even_inspected_in_development(self):
        forbidden={h for v in self.plan['variants'] for h in v['holdout_runs']}; original=self.ss.manifest
        def guard(h):
            if h in forbidden: raise AssertionError('Holdout touched during development')
            return original(h)
        with patch.object(self.ss,'manifest',side_effect=guard): self.assertTrue(self.store.run(self.h,self.ss)['ready'])

    def test_selection_journal_precedes_outer_labels_and_stress_preserves_predictions(self):
        d=self.store.run(self.h,self.ss); events=self.store.events(self.h)
        for name in ('outer1','outer2'):
            selected=next(e['sequence'] for e in events if e['kind']=='job_completed' and e['payload']['key']=='selection/'+name)
            outer=next(e['sequence'] for e in events if e['kind']=='job_started' and e['payload']['key']=='outer/'+name+'/a')
            self.assertLess(selected,outer)
        f=d['folds'][0]; stress=f['stresses'][0]
        self.assertEqual([r['prediction'] for r in f['rows']],[r['prediction'] for r in stress['rows']])
        self.assertLess(float(stress['evidence']['utility_r_per_candidate']),float(d['evidence']['utility_r_per_candidate']))

    def test_no_holdout_open_before_passed_development(self):
        with self.assertRaisesRegex(ValidationError,'Passing'): self.store.open_holdout(self.h,self.ss,'Too soon')
        self.assertFalse(any(e['kind']=='holdout_opened' for e in self.store.events(self.h)))

    def test_failed_job_resume_does_not_change_completed_selection(self):
        from tradee.c12 import engine
        original=engine.testing
        def fail(sim,v,s,m,stage,holdout_start):
            if s.name=='outer2': raise RuntimeError('injected source interruption')
            return original(sim,v,s,m,stage,holdout_start)
        with patch.object(engine,'testing',side_effect=fail),self.assertRaisesRegex(RuntimeError,'injected'): self.store.run(self.h,self.ss)
        jobs=self.store.jobs(self.h); selected=next(j for j in jobs if j['key']=='selection/outer2'); self.assertEqual(selected['status'],'completed')
        self.assertTrue(any(j['status']=='failed' for j in jobs)); self.assertTrue(self.store.run(self.h,self.ss)['ready'])
        again=next(j for j in self.store.jobs(self.h) if j['key']=='selection/outer2')
        self.assertEqual(again['artifact'],selected['artifact']); self.assertEqual(again['attempts'],1)
        self.assertTrue(any(e['kind']=='job_failed' for e in self.store.events(self.h)))

    def test_holdout_failure_stays_consumed_and_same_job_resumes(self):
        self.store.run(self.h,self.ss)
        with patch('tradee.c12.engine.testing',side_effect=RuntimeError('holdout failure')):
            with self.assertRaises(RuntimeError): self.store.open_holdout(self.h,self.ss,'Consume access before execution')
        self.assertEqual(len([e for e in self.store.events(self.h) if e['kind']=='holdout_opened']),1)
        self.assertTrue(self.store.open_holdout(self.h,self.ss,'Resume unchanged job')['ready'])

    def test_source_failure_is_failure_not_empty_performance(self):
        with patch.object(self.ss,'summary',side_effect=ValidationError('corrupt source')):
            with self.assertRaisesRegex(ValidationError,'corrupt'): self.store.run(self.h,self.ss)
        self.assertEqual(self.store.decision(self.h)['status'],'not_evaluated')

    def test_code_change_requires_new_counted_trial(self):
        with patch('tradee.c12.store.code_hash',return_value='different'):
            with self.assertRaisesRegex(ValidationError,'code/runtime'): self.store.run(self.h,self.ss)

    def test_previously_inspected_holdout_can_only_yield_research_rejection(self):
        s=ResearchStore(Path(self.tmp.name)/'contaminated.db'); d=deepcopy(self.plan); d['holdout_status']='development_only'; h=s.register(d)['experiment_hash']
        self.assertTrue(s.run(h,self.ss)['ready']); final=s.open_holdout(h,self.ss,'Disclosed development diagnostic')
        self.assertFalse(final['ready']); self.assertIn('holdout_previously_inspected_or_unattested',final['reasons'])
        self.assertEqual(s.decision(h)['status'],'rejected')

    def test_purge_endpoint_and_decision_gap_preserve_unknown_coverage(self):
        boundary=START+11*BIN
        rows=[dict(candidate_id='touch',protocol_hash='p',detected_ms=START,label_start_ms=START,label_end_ms=boundary,status='mature'),
              dict(candidate_id='before',protocol_hash='p',detected_ms=START,label_start_ms=START,label_end_ms=boundary-1,status='mature'),
              dict(candidate_id='gap',protocol_hash='p',detected_ms=boundary,label_start_ms=None,label_end_ms=None,status='unfilled'),
              dict(candidate_id='unknown',protocol_hash='p',detected_ms=START,label_start_ms=START,label_end_ms=None,status='unresolved')]
        s=Split.from_dict(split('purge',12,12,20,gap=BIN))
        d=purged_snapshot(FrozenRecord.create(dict(rows=rows)),s).document()
        self.assertEqual([r['candidate_id'] for r in d['rows']],['before','unknown']); self.assertEqual(d['c12_purge']['unresolved_retained'],1)

    def test_missing_stress_and_neighborhood_are_explicit_gates(self):
        d=deepcopy(self.plan); d['variants']=d['variants'][:1]
        s=ResearchStore(Path(self.tmp.name)/'fixed.db'); h=s.register(d)['experiment_hash']; r=s.run(h,self.ss)
        self.assertFalse(r['ready']); self.assertIn('missing_predeclared_stress',r['reasons']); self.assertIn('missing_predeclared_neighborhood',r['reasons'])
        self.assertEqual(s.decision(h)['status'],'rejected_development')

    def test_wrong_stress_hypothesis_or_beneficial_cost_is_rejected(self):
        d=self.ss.manifest(self.plan['variants'][0]['development_runs'][0])
        from tradee.c10.contracts import protocol
        from tradee.c11 import Scenario
        sc=Scenario.from_dict(d['scenarios'][0]); definitions={k:v for k,v in d['detectors']['range']['feature_manifest']['definitions'].items() if k in sc.strategy.feature_config().features}
        p=protocol(sc,d['execution'],d['fees'],d['funding'],d['candidates'],d['dataset']['mode'],definitions)
        for mutate in (lambda q:q['fees'].update(taker_rate='0'),lambda q:q['policy'].update(target_r='3'),lambda q:None):
            q=deepcopy(p); mutate(q)
            with self.assertRaises(ValidationError): stress_protocol(p,q)

    def test_negative_or_unknown_holdout_cannot_change_frozen_winner_or_pass(self):
        for label,(baseline,stressed) in self.extra.items():
            with self.subTest(label=label):
                d=deepcopy(self.plan)
                for v in d['variants']: v['holdout_runs']=[stressed if v.get('stress_of') else baseline]
                d['source_report_hashes'].update({r:self.ss.summary(r)['report_hash'] for r in (baseline,stressed)})
                s=ResearchStore(Path(self.tmp.name)/(label+'.db')); h=s.register(d)['experiment_hash']; dev=s.run(h,self.ss)
                self.assertTrue(dev['ready']); self.assertEqual(dev['final_selection']['winner'],'a')
                result=s.open_holdout(h,self.ss,'Controlled negative/unknown holdout test')
                self.assertFalse(result['ready']); self.assertEqual(s.decision(h)['status'],'rejected')
                self.assertEqual(result['result']['model_hash'],dev['final_training']['model_hash'])
                if label=='unknown':
                    self.assertIsNone(result['result']['evidence']['utility_r_per_candidate'])
                    self.assertIn('selected_outcomes_unresolved_or_unfilled',result['reasons'])
                else: self.assertLess(float(result['result']['evidence']['utility_r_per_candidate']),0)

    def test_final_release_failure_cannot_publish_a_completed_research_approval(self):
        self.store.run(self.h,self.ss)
        with patch.object(self.store,'_release',side_effect=RuntimeError('release interrupted')):
            with self.assertRaises(RuntimeError): self.store.open_holdout(self.h,self.ss,'Controlled release interruption')
        self.assertEqual(self.store.decision(self.h)['status'],'incomplete_release'); self.assertFalse(self.store.decision(self.h)['ready'])
        self.store.open_holdout(self.h,self.ss,'Resume release publication')
        release=self.store.release(self.h)
        self.assertEqual(release['release_hash'],self.store.decision(self.h)['release_hash']); self.assertFalse(release['live_approved'])

    def test_development_source_with_future_revisions_is_rejected_before_outcome_read(self):
        original=self.ss.manifest
        def future(h):
            m=original(h); m['dataset']['as_of_ms']=START+61*BIN; return m
        with patch.object(self.ss,'manifest',side_effect=future),patch.object(self.ss,'summary',side_effect=AssertionError('must reject before reading results')):
            with self.assertRaisesRegex(ValidationError,'sealed-period'): self.store.run(self.h,self.ss)

    def test_insufficient_inner_evidence_rejects_without_selecting_an_outer_winner(self):
        d=deepcopy(self.plan)
        for v in d['variants']: v['estimator']['min_trades']=1000
        s=ResearchStore(Path(self.tmp.name)/'insufficient.db'); h=s.register(d)['experiment_hash']; result=s.run(h,self.ss)
        self.assertFalse(result['ready']); self.assertTrue(all(f['winner'] is None for f in result['folds']))
        self.assertIsNone(result['final_training'])
        with self.assertRaisesRegex(ValidationError,'Passing'): s.open_holdout(h,self.ss,'Must remain sealed')
