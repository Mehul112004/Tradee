import tempfile
import unittest
from scripts.verify_c11 import run_e2e


class SimulationE2ETests(unittest.TestCase):
    def test_raw_imports_to_both_families_and_reconciled_simulation_in_real_cli_processes(self):
        with tempfile.TemporaryDirectory(prefix='tradee-c11-e2e-test-') as folder:
            result=run_e2e(folder)
            self.assertTrue(result['passed']); self.assertEqual(result['simulation']['metrics']['mature'],4)
            self.assertGreaterEqual(result['commands'],15)
