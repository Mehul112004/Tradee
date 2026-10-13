from pathlib import Path
import tempfile
import unittest
from scripts.verify_c07 import run_e2e


class ExecutionEndToEndTests(unittest.TestCase):
    def test_raw_import_to_features_funding_and_execution_with_process_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            result=run_e2e(folder)
            self.assertTrue(result['passed']); self.assertGreaterEqual(result['commands'],27)
            self.assertEqual([e['fill']['price'] for e in result['execution']['estimates']],['100.2','99.8'])
            self.assertEqual([e['projected_execution_cost_with_next_funding_usdt'] for e in result['execution']['estimates']],['0.3501','0.1499'])
            self.assertTrue((Path(folder)/'e2e_report.json').is_file()); self.assertTrue((Path(folder)/'c07.sqlite3').is_file())
