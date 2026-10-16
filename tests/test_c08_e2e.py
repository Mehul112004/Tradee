from pathlib import Path
import tempfile
import unittest
from scripts.verify_c08 import run_e2e


class CandidateEndToEndTests(unittest.TestCase):
    def test_two_15m_families_from_raw_import_through_cli_recovery_and_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            result=run_e2e(folder)
            self.assertTrue(result['passed']); self.assertGreaterEqual(result['commands'],20)
            self.assertEqual(result['range_breakout']['emitted_candidates'],4)
            self.assertEqual(result['trend_continuation']['emitted_candidates'],2)
            self.assertEqual(result['range_breakout']['evaluations'],1616)
            self.assertEqual(result['trend_continuation']['evaluations'],1616)
            self.assertTrue((Path(folder)/'e2e_report.json').is_file())
