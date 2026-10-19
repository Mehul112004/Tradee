from copy import deepcopy
from dataclasses import replace
from decimal import Decimal,localcontext
import unittest
from tradee.c01 import ValidationError
from tradee.c12 import EvidencePolicy
from tradee.c12.statistics import evidence
from tests.c12_support import rows,plan,BIN,START


class ResearchStatisticsTests(unittest.TestCase):
    def cfg(self,**kw): return EvidencePolicy.from_dict({**plan()['policy'],**kw})

    def test_golden_mean_joint_block_identity_and_adjusted_tail(self):
        a=evidence(rows(),self.cfg(),4); b=evidence(list(reversed(rows())),self.cfg(),4)
        self.assertTrue(a['ready']); self.assertEqual(a['utility_r_per_candidate'],'1.5')
        self.assertEqual(a['uncertainty']['tail_probability'],'0.00625'); self.assertEqual(a['uncertainty'],b['uncertainty'])
        self.assertEqual(len(a['leave_group_out']['symbol']),2)

    def test_abstentions_zero_utility_unknown_selected_is_null(self):
        r=rows(); r[0]['prediction']=dict(ready=True,eligible=False)
        a=evidence(r,self.cfg(),4); self.assertEqual(a['utility_r_per_candidate'],'1.333333333333')
        r[1]['outcome_status']='unresolved'; r[1]['net_r']=None
        b=evidence(r,self.cfg(),4); self.assertIsNone(b['utility_r_per_candidate']); self.assertIsNone(b['uncertainty']['lower'])
        self.assertIn('selected_outcomes_unresolved_or_unfilled',b['reasons'])

    def test_no_selected_labels_cannot_pass_as_flat_profit(self):
        r=rows()
        for p in r: p['prediction']['eligible']=False
        d=evidence(r,self.cfg(),4); self.assertFalse(d['ready']); self.assertEqual(d['utility_r_per_candidate'],'0')

    def test_duplicate_opportunity_rejected(self):
        r=rows()
        with self.assertRaisesRegex(ValidationError,'Duplicate'): evidence(r+[r[0]],self.cfg(),4)

    def test_negative_and_degenerate_results_fail(self):
        for value in ('-1','1'):
            r=rows()
            for p in r: p['net_r']=value
            self.assertFalse(evidence(r,self.cfg(),4)['ready'])

    def test_span_and_estimation_coverage(self):
        r=rows()
        for p in r: p['prediction']['ready']=False; p['prediction']['eligible']=False
        d=evidence(r,self.cfg(),4); self.assertIn('insufficient_estimated_coverage',d['reasons'])
        r=rows(); r[0]['label_end_ms']+=2*BIN
        self.assertIn('block_shorter_than_selected_label_span',evidence(r,self.cfg(),4)['reasons'])

    def test_resource_budget_no_silent_truncation(self):
        with self.assertRaisesRegex(ValidationError,'budget'): evidence(rows(),self.cfg(max_work=1),4)
        with self.assertRaisesRegex(ValidationError,'budget'): evidence(rows(),self.cfg(max_bins=1),4)

    def test_leave_asset_out_reveals_concentration(self):
        r=rows()
        for p in r: p['net_r']='10' if p['symbol']=='BTCUSDT' else '-1'
        d=evidence(r,self.cfg(),4)
        self.assertIn('leave_period_or_asset_out_not_positive',d['reasons'])

    def test_empty_inventory_has_no_statistic(self):
        d=evidence([],self.cfg(),4); self.assertFalse(d['ready']); self.assertIsNone(d['utility_r_per_candidate'])

    def test_multiple_assets_in_same_bin_move_together(self):
        r=rows(); more=deepcopy(r)
        for p in more: p['candidate_id']='copy-'+p['candidate_id']; p['symbol']='SOLUSDT'
        a=evidence(r,self.cfg(),4); b=evidence(r+more,self.cfg(),4)
        self.assertEqual(a['uncertainty']['lower'],b['uncertainty']['lower']); self.assertEqual(a['uncertainty']['draw_manifest_hash'],b['uncertainty']['draw_manifest_hash'])

    def test_nonterminating_tail_and_low_decimal_context_are_supported(self):
        a=evidence(rows(),self.cfg(),3)
        with localcontext() as context:
            context.prec=3; b=evidence(rows(),self.cfg(),3)
        self.assertEqual(a,b); self.assertEqual(a['uncertainty']['tail_fraction'],'1/120')

    def test_unresolvable_tail_is_not_pretended_precise(self):
        with self.assertRaisesRegex(ValidationError,'Too few'): evidence(rows(),self.cfg(),1000)

    def test_predeclared_windows_keep_empty_edges_and_do_not_shrink_to_winners(self):
        r=rows(start=START+2*BIN)
        windows=[dict(start_ms=START,end_ms=START+16*BIN)]
        d=evidence(r,self.cfg(),4,windows)
        self.assertEqual(d['uncertainty']['calendar_bins'],16)
        self.assertEqual(d['uncertainty']['declared_windows_ms'],[[START,START+16*BIN]])
        self.assertEqual(d['utility_r_per_candidate'],'1.5')

    def test_window_ownership_and_overlap_are_validated(self):
        for windows in ([],[dict(start_ms=START+BIN,end_ms=START+20*BIN)],
                        [dict(start_ms=START,end_ms=START+20*BIN),dict(start_ms=START+BIN,end_ms=START+30*BIN)]):
            with self.assertRaises(ValidationError): evidence(rows(),self.cfg(),4,windows)
