from pathlib import Path
import tempfile
import unittest

from scripts.verify_structure_prerequisites import run_e2e


class PrerequisitesEndToEndTests(unittest.TestCase):
    def test_raw_inputs_actual_cli_independent_math_and_crash_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            result = run_e2e(folder)
            self.assertTrue(result['passed'])
            self.assertTrue(result['context']['completed'])
            self.assertTrue(result['structure']['completed'])
            self.assertGreaterEqual(result['commands'], 15)
            self.assertEqual(result['previous_day_high']['price'], '102')
            self.assertTrue((Path(folder)/'e2e_report.json').is_file())
