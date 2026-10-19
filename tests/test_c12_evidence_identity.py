"""Store-local C02/C11 manifest IDs cannot substitute different outcome bytes."""
from pathlib import Path
import tempfile
import unittest
from tradee.c01 import ValidationError
from tradee.c06 import FundingConfig
from tradee.c07 import ExecutionConfig,FeeSchedule
from tradee.c08 import CandidateConfig
from tradee.c11 import Simulator,SimulationStore,SimulationConfig
from tradee.c12 import ResearchStore
from tests.c10_support import simulation
from tests.c12_support import plan


class ContentQualifiedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=tempfile.TemporaryDirectory(); root=Path(cls.root.name)
        positive,_=simulation(n=6); _,events=simulation(n=6,positive=False); m=positive.manifest.document()
        # C02 manifests currently qualify event IDs within one store. Reuse that
        # header in an isolated counterfactual store, exactly as the raw E2Es do.
        negative=Simulator(m['dataset'],m['scenarios'],m['metadata_snapshots'],m['metadata_versions'],FeeSchedule.from_dict(m['fees']),ExecutionConfig.from_dict(m['execution']),
            CandidateConfig.from_dict(m['candidates']),FundingConfig.from_dict(m['funding']),m['calendars'],SimulationConfig.from_dict(m['config'])).run(lambda:iter(events))
        cls.a=SimulationStore(root/'a.db'); cls.b=SimulationStore(root/'b.db')
        cls.positive=cls.a.commit(positive); cls.negative=cls.b.commit(negative)
    @classmethod
    def tearDownClass(cls): cls.root.cleanup()

    def test_same_run_manifest_id_different_content_cannot_replace_frozen_source(self):
        self.assertEqual(self.positive['run_hash'],self.negative['run_hash'])
        self.assertNotEqual(self.positive['report_hash'],self.negative['report_hash'])
        d=plan(); d['variants']=d['variants'][:1]; d['variants'][0]['development_runs']=[self.positive['run_hash']]
        d['source_report_hashes'][self.positive['run_hash']]=self.positive['report_hash']
        with tempfile.TemporaryDirectory() as folder:
            store=ResearchStore(Path(folder)/'r.db'); h=store.register(d)['experiment_hash']
            store._runner(h,self.a)
            with self.assertRaisesRegex(ValidationError,'differs from frozen evidence'): store.run(h,self.b)
            self.assertEqual(store.jobs(h),[])

    def test_report_digest_changes_registered_experiment_identity_before_any_scoring(self):
        with tempfile.TemporaryDirectory() as folder:
            d=plan(); d['source_report_hashes']['b'*64]=self.positive['report_hash']
            a=ResearchStore(Path(folder)/'a.db').register(d)['experiment_hash']
            d['source_report_hashes']['b'*64]=self.negative['report_hash']
            b=ResearchStore(Path(folder)/'b.db').register(d)['experiment_hash']
            self.assertNotEqual(a,b)
