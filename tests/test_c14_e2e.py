import unittest
from tests.c14_integration_support import baseline


class SignalE2ETests(unittest.TestCase):
    def test_raw_research_release_to_prospective_pipeline_delivery_recovery_and_close(self):
        _,r=baseline(); self.assertTrue(r['passed']); self.assertEqual(r['commands'],23); self.assertEqual(r['prior_research_commands'],32)
        self.assertEqual(r['paper_account']['cash_usdt'],'328.489'); self.assertEqual(r['paper_account']['positions'],[])
        self.assertEqual(set(r['delivery_states'].values()),{'resolved_sent','expired','suppressed'})
