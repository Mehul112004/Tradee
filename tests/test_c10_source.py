from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from tradee.c01 import ValidationError
from tradee.c10 import snapshot,TrainingWindow
from tradee.c11 import SimulationStore,Simulator,SimulationConfig
from tests.c10_support import *


class CausalSelectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.store=SimulationStore(Path(self.tmp.name)/'s.db')

    def save(self,**kw):
        r,_=simulation(**kw); return self.store.commit(r)['run_hash']

    def test_all_mature_rows_have_exact_source_feature_revision_provenance(self):
        h=self.save(); d=snapshot(self.store,[h],window(),config()).document()
        self.assertEqual(d['coverage'],{'mature':12}); self.assertEqual(len(d['rows']),12)
        for r in d['rows']:
            self.assertLess(r['outcome_known_ms'],window().cutoff_ms)
            self.assertIsNotNone(r['candidate_artifact_hash']); self.assertIsNotNone(r['revision_artifact_hash']); self.assertIsNotNone(r['feature_snapshot_hash'])
            self.assertEqual(r['risk_usdt'],'1.22')

    def test_same_source_repeated_or_reordered_does_not_inflate_sample(self):
        h=self.save(); self.assertEqual(snapshot(self.store,[h,h],window(),config()),snapshot(self.store,[h],window(),config()))

    def test_future_final_outcome_is_not_an_earlier_training_label_and_cutoff_is_strict(self):
        h=self.save(); detected=START+180000; known=detected+40000
        for cutoff,status in ((known,'unresolved'),(known+1,'mature')):
            w=TrainingWindow(START,detected+1,cutoff); d=snapshot(self.store,[h],w,config()).document()
            self.assertEqual(d['rows'][0]['status'],status)
            if status=='unresolved': self.assertIsNone(d['rows'][0]['net_r'])

    def test_future_pricing_does_not_change_earlier_selected_statistics(self):
        from tradee.c10 import fit
        h=self.save(); other=self.save(positive=False)
        w=TrainingWindow(START,START+180001,START+190000)
        a=snapshot(self.store,[h],w,config()).document(); b=snapshot(self.store,[other],w,config()).document()
        self.assertEqual(a['coverage'],b['coverage']); self.assertIsNone(a['rows'][0]['net_r']); self.assertIsNone(b['rows'][0]['net_r'])
        self.assertEqual(fit(snapshot(self.store,[h],w,config()),config()).document()['cohorts'],fit(snapshot(self.store,[other],w,config()),config()).document()['cohorts'])

    def test_disjoint_runs_cover_window_and_overlaps_are_rejected(self):
        a=self.save(n=6); b=self.save(n=6,start=START+6*BIN)
        d=snapshot(self.store,[b,a],window(),config()).document(); self.assertEqual(d['coverage']['mature'],12)
        overlap=self.save(n=8)
        with self.assertRaisesRegex(ValidationError,'Overlapping'): snapshot(self.store,[a,overlap],window(n=6),config())

    def test_missing_declared_source_scope_is_not_filled_with_empty_bins(self):
        a=self.save(n=6); b=self.save(n=6,start=START+7*BIN)
        for runs,w in (([],window()),([a],window()),([a,b],window(n=13))):
            with self.assertRaises(ValidationError): snapshot(self.store,runs,w,config())

    def test_unknown_funding_stays_unresolved_in_snapshot_and_fit(self):
        from tradee.c10 import fit
        h=self.save(unknown_funding=True); d=snapshot(self.store,[h],window(),config())
        self.assertEqual(d.document()['coverage'],{'unresolved':12}); self.assertFalse(fit(d,config()).document()['ready'])
        self.assertTrue(all(r['net_r'] is None for r in d.document()['rows']))

    def test_revisions_replace_then_can_revoke_instead_of_double_count(self):
        from tradee.c06 import FundingConfig
        from tests.c11_support import fixture
        from tests.c09_support import DETECT,observation,calendar
        s,events=fixture(); settle=DETECT+10000
        events += [observation('funding',9,settle,available=DETECT+40000),observation('funding',10,settle,funding_rate='0.002',available=DETECT+50000)]
        ds={**s.dataset,'event_count':len(events)}
        result=Simulator(ds,s.scenarios,s.snapshots,s.versions,s.fees,s.execution,funding=FundingConfig(boundary_policy='nominal'),calendars=[calendar([settle])]).run(lambda:iter(events))
        h=self.store.commit(result)['run_hash']
        for cutoff,net,known in ((DETECT+45000,'2.3945',DETECT+40000),(DETECT+55000,'2.2925',DETECT+50000)):
            r=snapshot(self.store,[h],TrainingWindow(START,DETECT+1,cutoff),config()).document()['rows'][0]
            self.assertEqual(r['net_usdt'],net); self.assertEqual(r['outcome_known_ms'],known)
        # A late observation that conflicts with an assumed empty calendar revokes maturity.
        s,events=fixture(); events.append(observation('funding',9,DETECT+2000,available=DETECT+50000)); ds={**s.dataset,'event_count':len(events)}
        result=Simulator(ds,s.scenarios,s.snapshots,s.versions,s.fees,s.execution,calendars=s.calendars).run(lambda:iter(events)); h=self.store.commit(result)['run_hash']
        before=snapshot(self.store,[h],TrainingWindow(START,DETECT+1,DETECT+45000),config()).document()['rows'][0]
        after=snapshot(self.store,[h],TrainingWindow(START,DETECT+1,DETECT+55000),config()).document()['rows'][0]
        self.assertEqual(before['status'],'mature'); self.assertEqual(after['status'],'unresolved'); self.assertIsNone(after['net_r'])

    def test_row_resource_limit_and_corrupt_source_fail_closed(self):
        h=self.save()
        with self.assertRaisesRegex(ValidationError,'row budget'): snapshot(self.store,[h],window(),config(max_rows=2))
        with self.store.connection() as db: db.execute("UPDATE artifacts SET document='{}' WHERE sequence=1")
        with self.assertRaises(ValidationError): snapshot(self.store,[h],window(),config())

    def test_funding_assumptions_and_dataset_vintage_remain_in_model_provenance(self):
        h=self.save(n=2); d=snapshot(self.store,[h],window(n=2),config()).document()
        evidence=d['sources'][0]
        self.assertEqual(evidence['dataset']['mode'],'recorded')
        self.assertEqual(evidence['decision_window_ms'],[START,START+2*BIN])
        self.assertIn('synthetic',evidence['funding_calendar_evidence'][0]['evidence'])
        self.assertEqual(len(evidence['funding_calendar_evidence'][0]['calendar_hash']),64)
