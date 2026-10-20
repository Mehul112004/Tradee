import os
import tempfile
import unittest
from scripts.verify_c13 import run_e2e


class FundedPortfolioE2ETests(unittest.TestCase):
    def test_raw_production_pipeline_to_shared_capital_research_receipt_and_local_reservations(self):
        with tempfile.TemporaryDirectory(prefix='tradee-c13-e2e-') as temporary:
            r=run_e2e(os.environ.get('TRADEE_C13_E2E_OUTPUT',temporary))
            self.assertTrue(r['passed']); self.assertEqual(r['portfolio']['coverage']['admitted_positions'],6)
            self.assertEqual(r['portfolio']['metrics']['net_pnl_usdt'],'12.7335')
            self.assertTrue(r['compatibility']['ready']); self.assertFalse(r['compatibility']['promotion_authorized'])
            self.assertFalse(r['portfolio']['live_approved'])
