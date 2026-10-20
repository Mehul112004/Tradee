import unittest
from tradee.c01 import ValidationError
from tradee.c15 import MonitorPolicy
from tradee.c15.statistics import review


def policy(**kw):
    return MonitorPolicy(**dict(dict(review_times_ms=[100,200],min_mature=4,min_occupied_spans=3,bin_ms=10,block_bins=2,bootstrap_replicates=400,alpha='0.1'),**kw))


def rows(offset=-3):
    return [dict(signal_id=str(i),track='portfolio',detected_ms=i*10,status='mature',decision_recorded_before_outcome=True,
        predicted_mean_net_r='2',net_r=str(2+offset+(i%3)/10),label_start_ms=i*10,label_end_ms=i*10+5) for i in range(10)]


class StatisticsTests(unittest.TestCase):
    def test_degradation_and_reproducible_resampling(self):
        r=review(rows(),policy(),0,100)
        self.assertTrue(r['degraded']); self.assertEqual(r['tail_fraction'],'1/80'); self.assertEqual(r,review(rows(),policy(),0,100))
        self.assertLess(float(r['upper']),-.5)

    def test_no_degradation_is_not_profitability(self):
        r=review(rows(0),policy(),0,100); self.assertEqual(r['status'],'no_degradation_detected')
        self.assertFalse(r['degraded']); self.assertIn('No profitability',r['limitations'])

    def test_unknown_admission_blocks_complete_case_bias(self):
        data=rows(); data[-1]['status']='unresolved'; data[-1]['net_r']=None
        r=review(data,policy(),0,100); self.assertEqual(r['status'],'insufficient_evidence'); self.assertIsNone(r['upper'])
        self.assertIn('incomplete_or_nonprospective_admitted_cohort',r['reasons'])

    def test_retrospective_decision_cannot_enter_review(self):
        data=rows(); data[0]['decision_recorded_before_outcome']=False
        self.assertFalse(review(data,policy(),0,100)['degraded'])

    def test_independent_outcomes_do_not_inflate_evidence(self):
        data=rows()
        for row in data: row['track']='independent'
        self.assertEqual(review(data,policy(),0,100)['usable_mature'],0)

    def test_long_overlapping_labels_require_longer_blocks(self):
        data=rows(); data[0]['label_end_ms']=25
        self.assertIn('block_shorter_than_label_span',review(data,policy(),0,100)['reasons'])

    def test_degenerate_returns_and_single_time_span_abstain(self):
        data=rows()
        for row in data: row.update(net_r='-1',detected_ms=0)
        r=review(data,policy(),0,100)
        self.assertIn('degenerate_residuals_or_net_outcomes',r['reasons']); self.assertIn('insufficient_occupied_time_spans',r['reasons'])

    def test_negative_net_is_detected_even_when_the_forecast_is_more_pessimistic(self):
        data=rows()
        for r in data: r['predicted_mean_net_r']='-5'
        result=review(data,policy(),0,100)
        self.assertEqual(result['degradation_reasons'],['mean_net_r_below_floor'])

    def test_budget_exhaustion_and_outside_window(self):
        with self.assertRaises(ValidationError): review(rows(),policy(max_work=1),0,100)
        data=rows(); data[0]['detected_ms']=-10
        with self.assertRaises(ValidationError): review(data,policy(),0,100)
