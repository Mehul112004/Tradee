import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tradee.c01 import ValidationError
from tradee.c12 import ResearchStore
from tradee.c14 import load_release,SessionSpec
from tests.c14_integration_support import isolated,baseline
from scripts.verify_c14 import LIVE


class FrozenDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name); self.feed,self.s,self.r=isolated(self.root)
        _,prior=baseline(); self.research=ResearchStore(self.root/'research/c12.sqlite3'); self.experiment=prior['deployment_hash']
        self.original=self.s.session('paper_demo')['manifest']; self.refs=self.original['research']; self.spec=SessionSpec.from_dict(self.original['spec']); self.cals=self.original['calendars']
    def load(self,spec=None,calendars=None):
        return load_release(self.research,self.r.portfolios,self.r.simulations,self.refs['experiment_hash'],self.refs['portfolio_run_hash'],spec or self.spec,self.cals if calendars is None else calendars)
    def test_real_release_and_recipe_match_frozen_deployment_without_live_promotion(self):
        d=self.load().document(); self.assertEqual(d,self.original); self.assertFalse(d['live_approved']); self.assertFalse(d['promotion_authorized'])
    def test_session_cannot_reuse_final_test_as_prospective_evidence(self):
        d=self.spec.document(); d.update(start_ms=LIVE-2*240000,warmup_start_ms=LIVE-2*240000-60000)
        with self.assertRaisesRegex(ValidationError,'after frozen'): self.load(SessionSpec.from_dict(d))
    def test_tail_and_calendar_coverage_cannot_be_silently_shortened(self):
        d=self.spec.document(); d['tail_ms']=60000
        with self.assertRaisesRegex(ValidationError,'tail'): self.load(SessionSpec.from_dict(d))
        calendars=[dict(c,end_ms=self.spec.end_ms) for c in self.cals]
        with self.assertRaisesRegex(ValidationError,'cover'): self.load(calendars=calendars)
    def test_duplicate_settlement_calendars_rejected(self):
        with self.assertRaisesRegex(ValidationError,'Duplicate'): self.load(calendars=self.cals+self.cals[:1])
    def test_runtime_change_requires_new_counted_research(self):
        with patch('tradee.c14.release.code_hash',return_value='0'*64):
            with self.assertRaisesRegex(ValidationError,'runtime'): self.load()
    def test_corrupt_training_report_refuses_deployment(self):
        source=self.original['model']['fit']['sources'][0]
        with self.r.simulations.connection() as db: db.execute("UPDATE reports SET document='{}' WHERE hash=?",(source['report_hash'],))
        with self.assertRaisesRegex(ValidationError,'Corrupt'): self.load()
    def test_missing_calendars_remain_explicit_unknown_instead_of_assumed_zero(self):
        self.assertEqual(self.load(calendars=[]).document()['calendars'],[])
