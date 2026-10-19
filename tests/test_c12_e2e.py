import tempfile
import os
import unittest
from scripts.verify_c12 import run_e2e


class ResearchE2ETests(unittest.TestCase):
    def test_raw_ingestion_to_nested_validation_stress_holdout_and_registry_cli(self):
        with tempfile.TemporaryDirectory(prefix='tradee-c12-e2e-') as temporary:
            r=run_e2e(os.environ.get('TRADEE_C12_E2E_OUTPUT',temporary))
            self.assertTrue(r['passed']); self.assertEqual(r['decision']['status'],'research_candidate'); self.assertFalse(r['decision']['live_approved'])
            self.assertEqual(r['holdout']['result']['evidence']['coverage']['eligible_mature'],12)
