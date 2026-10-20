import unittest
from tests.c15_integration_support import baseline


class E2ETests(unittest.TestCase):
    def test_raw_prospective_pipeline_delivery_pause_maturity_and_replay(self):
        _,r=baseline(); self.assertTrue(r['passed']); self.assertEqual(r['prior_research_commands'],32)
        self.assertGreaterEqual(r['commands'],25); self.assertEqual(r['paper_account']['cash_usdt'],'328.489')
        self.assertEqual(r['paper_account']['positions'],[])
        self.assertEqual(r['summary']['portfolio']['statuses'],{'mature':3}); self.assertEqual(r['summary']['independent']['statuses'],{'mature':6})
        self.assertTrue(r['reconciliation']['ready']); self.assertEqual(r['reviews'][0]['status'],'insufficient_evidence')
        self.assertEqual(r['reviews'][1]['status'],'insufficient_evidence')
        self.assertIn('empty_or_degenerate_resampling',r['reviews'][1]['reasons'])
