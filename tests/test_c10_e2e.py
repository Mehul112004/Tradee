import tempfile
import unittest
from scripts.verify_c10 import run_e2e


class ExpectancyE2ETests(unittest.TestCase):
    def test_raw_inputs_default_fit_atomic_retry_and_later_inference_and_evaluation(self):
        with tempfile.TemporaryDirectory(prefix='tradee-c10-e2e-test-') as folder:
            d=run_e2e(folder); self.assertTrue(d['passed']); self.assertTrue(d['model']['ready'])
            self.assertEqual(d['evaluation']['coverage']['matched_eligible_mature'],4)
