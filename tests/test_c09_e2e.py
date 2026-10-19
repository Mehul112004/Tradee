from pathlib import Path
import tempfile
import unittest
from scripts.verify_c09 import run_e2e


class LifecycleEndToEndTests(unittest.TestCase):
    def test_raw_inputs_to_candidates_fills_and_exact_trade_outcomes_with_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            result=run_e2e(folder)
            self.assertTrue(result['passed']); self.assertGreaterEqual(result['commands'],20)
            self.assertEqual([t['net_usdt'] for t in result['lifecycle']['trades']],['2.4965','2.5035'])
            self.assertTrue((Path(folder)/'e2e_report.json').is_file())
