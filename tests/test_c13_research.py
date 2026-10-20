from pathlib import Path
import tempfile
import unittest
from tradee.c01 import ValidationError
from tradee.c12 import Experiment,ResearchStore
from tests.c12_support import plan


class PortfolioResearchBoundaryTests(unittest.TestCase):
    def test_recipe_is_frozen_counted_and_cannot_reset_family_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=ResearchStore(Path(tmp)/'r.db'); d=plan(family_trial_budget=5,portfolio_recipe_hashes=['1'*64]); d['policy']['bootstrap_replicates']=400
            h=s.register(d)['experiment_hash']; ledger=s.ledger(d['family'])
            self.assertEqual(ledger['used_trials'],5); self.assertEqual(s.manifest(h)['experiment']['portfolio_recipe_hashes'],['1'*64])
            self.assertEqual(ledger['experiments'][0]['portfolio_recipe_hashes'],['1'*64])
            self.assertEqual(s.events(h)[0]['payload']['trials_reserved'],5)
    def test_recipe_fields_and_count_are_strict(self):
        for recipes in (['bad'],['a'*64]*2,[1],[{}],['a'*64]):
            with self.subTest(recipes=recipes),self.assertRaises(ValidationError): Experiment.from_dict(plan(portfolio_recipe_hashes=recipes))
    def test_sealed_access_rejected_before_external_portfolio_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=ResearchStore(Path(tmp)/'r.db'); h=s.register(plan())['experiment_hash']
            class Sealed:
                def manifest(self,h): raise AssertionError('Sealed portfolio was inspected')
            with self.assertRaisesRegex(ValidationError,'holdout access'): s.check_portfolio(h,Sealed(),'x')

    def test_subset_of_frozen_holdout_assets_cannot_get_compatibility_receipt(self):
        from unittest.mock import patch
        from tradee.c06.engine import code_hash
        import platform
        with tempfile.TemporaryDirectory() as tmp:
            s=ResearchStore(Path(tmp)/'r.db'); d=plan(family_trial_budget=5,portfolio_recipe_hashes=['1'*64]); d['policy']['bootstrap_replicates']=400
            d['variants'][0]['holdout_runs'].append('d'*64); d['source_report_hashes']['d'*64]='e'*64
            h=s.register(d)['experiment_hash']; variant=d['variants'][0]
            with s.connection() as db: s._event(db,h,'holdout_opened',dict(reason='unit boundary fixture'))
            test=d['holdout']['split']['test']
            p=dict(code_hash=code_hash(),python=platform.python_version(),recipe_hash='1'*64,
                decision_window_ms=[test['start_ms'],test['end_ms']],dataset=dict(as_of_ms=test['cutoff_ms']),
                sources=[dict(run_hash=variant['holdout_runs'][0],report_hash=d['source_report_hashes'][variant['holdout_runs'][0]])],models=[dict(model_hash='m')])
            class Subset:
                def manifest(self,run): return p
                def summary(self,run): raise AssertionError('Subset reached funded economics')
            with patch.object(s,'release',return_value=dict(variant=variant,model_hash='m')):
                with self.assertRaisesRegex(ValidationError,'source/model/window'): s.check_portfolio(h,Subset(),'run')
