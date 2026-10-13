"""Current platform boundary: raw data through actual production CLI processes."""
from pathlib import Path
import tempfile
import unittest
from scripts.verify_c06 import run_e2e


class FundingEndToEndTests(unittest.TestCase):
    def test_raw_import_to_feature_and_funding_reports_with_recovery_cases(self):
        with tempfile.TemporaryDirectory() as folder:
            result=run_e2e(folder)
            self.assertTrue(result['passed'])
            self.assertEqual([p['total_cashflow_usdt'] for p in result['funding']['positions']],['0.04','-0.42'])
            self.assertEqual([p['total_cashflow_usdt'] for p in result['corrected_funding']['positions']],['-0.06','-0.27'])
            self.assertGreaterEqual(result['commands'],20)
            self.assertTrue((Path(folder)/'e2e_report.json').is_file())
            self.assertTrue((Path(folder)/'c06.sqlite3').is_file())
