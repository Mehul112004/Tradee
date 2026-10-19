from copy import deepcopy
from decimal import Decimal,localcontext
from random import Random
import unittest
from tradee.c01 import ValidationError
from tradee.c10 import TrainingWindow,EstimatorConfig
from tradee.c10.statistics import summarize,circular_indices,quantile
from tests.c10_support import config,START,BIN


def rows(values):
    return [dict(status='mature',net_r=str(v),net_usdt=str(Decimal(str(v))*10),filled=True,detected_ms=START+i*BIN+1000,
                 label_start_ms=START+i*BIN+1100,label_end_ms=START+i*BIN+2100) for i,v in enumerate(values)]


class CohortStatisticsTests(unittest.TestCase):
    def calc(self,values,**kw):
        return summarize(rows(values),TrainingWindow(START,START+len(values)*BIN,START+len(values)*BIN),config(**kw))

    def test_exact_empirical_mean_payoff_tails_and_positive_frequency(self):
        d=self.calc([1,2,3,4,-1,-3,1,2,3,4,-1,-3]); s=d['statistics']
        self.assertEqual(s['mean_net_r'],'1'); self.assertEqual(s['mean_positive_r'],'2.5'); self.assertEqual(s['mean_negative_r'],'-2')
        self.assertEqual(s['empirical_positive_net_fraction'],'0.666666666667')
        self.assertEqual(s['net_r_quantiles'],{'p05':'-3','p50':'1','p95':'4'}); self.assertEqual(s['downside_mean_r'],'-3')
        self.assertEqual(d['status'],'ready')

    def test_literal_seeded_bootstrap_oracle_and_common_draws(self):
        d=self.calc([1,2,3,4,5,6]); u=d['uncertainty']
        rng=Random(config().seed); expected=[]
        for _ in range(200): expected.append(sum([1,2,3,4,5,6][rng.randrange(6)] for _ in range(6))/6)
        expected.sort()
        self.assertAlmostEqual(float(u['lower_mean_net_r']),expected[4],places=10)
        self.assertAlmostEqual(float(u['upper_mean_net_r']),expected[194],places=10)
        e=self.calc([2,4,6,8,10,12]); self.assertEqual(u['draw_manifest_hash'],e['uncertainty']['draw_manifest_hash'])
        self.assertEqual(u['replicates_used'],200)

    def test_circular_indices_wrap_preserve_block_order_and_length(self):
        class Fixed:
            def randrange(self,n): return n-1
        self.assertEqual(circular_indices(7,3,Fixed()),[6,0,1,6,0,1,6])

    def test_cross_symbol_contemporaneous_rows_move_together_and_trade_weighting(self):
        base=rows([1,2,3,4,5,6]); extra=deepcopy(base[0]); extra.update(net_r='7',net_usdt='70')
        d=summarize(base+[extra],TrainingWindow(START,START+6*BIN,START+6*BIN),config())
        self.assertEqual(d['statistics']['mean_net_r'],'4'); self.assertEqual(d['statistics']['max_simultaneous_exposures'],2)
        self.assertEqual(d['coverage']['occupied_bins'],6); self.assertEqual(d['coverage']['mature'],7)

    def test_small_single_day_and_degenerate_evidence_abstains(self):
        d=self.calc([1,2]); self.assertIn('insufficient_mature_trades',d['reasons']); self.assertIsNone(d['uncertainty']['lower_mean_net_r'])
        d=self.calc([1]*12); self.assertIn('degenerate_outcome_distribution',d['reasons']); self.assertFalse(d['positive_lower_bound'])
        r=rows(list(range(1,13)))
        for row in r: row['detected_ms']=START+1000
        d=summarize(r,TrainingWindow(START,START+12*BIN,START+12*BIN),config())
        self.assertIn('insufficient_occupied_time_bins',d['reasons'])

    def test_missing_unfilled_and_coverage_are_not_zero_training_returns(self):
        r=rows([1,2,3,4,5,6]); r+= [dict(status='unfilled',filled=False),dict(status='unresolved',filled=True),dict(status='not_observed',filled=False)]
        d=summarize(r,TrainingWindow(START,START+6*BIN,START+6*BIN),config())
        self.assertEqual(d['statistics']['mean_net_r'],'3.5'); self.assertEqual(d['coverage']['unresolved'],2)
        self.assertIn('insufficient_mature_coverage',d['reasons'])

    def test_empty_and_sparse_calendar_spans_have_no_fake_uncertainty(self):
        d=summarize([],TrainingWindow(START,START+20*BIN,START+20*BIN),config())
        self.assertIsNone(d['statistics']['mean_net_r']); self.assertIsNone(d['uncertainty']['lower_mean_net_r'])
        d=self.calc([1,2,3,4,5,6],block_bins=6); self.assertIn('resampling_block_covers_training_span',d['reasons'])

    def test_block_must_cover_observed_exposure_and_resources_fail_explicitly(self):
        r=rows([1,2,3,4,5,6]); r[0]['label_end_ms']=START+BIN*2
        d=summarize(r,TrainingWindow(START,START+6*BIN,START+6*BIN),config())
        self.assertIn('resampling_block_shorter_than_label_span',d['reasons'])
        for kw in ({'max_bins':2},{'max_bootstrap_work':100}):
            with self.assertRaises(ValidationError): self.calc([1,2,3,4,5,6],**kw)

    def test_decimal_context_and_seed_reproducibility(self):
        a=self.calc([1,2,3,4,5,6])
        with localcontext() as ctx:
            ctx.prec=3; b=self.calc([1,2,3,4,5,6])
        self.assertEqual(a,b); self.assertNotEqual(a['uncertainty']['draw_manifest_hash'],self.calc([1,2,3,4,5,6],seed=21)['uncertainty']['draw_manifest_hash'])

    def test_quantile_nearest_rank_edges(self):
        self.assertIsNone(quantile([],'0.5')); self.assertEqual(quantile([Decimal(1),Decimal(3)],'0.5'),'1')
        self.assertEqual(quantile([Decimal(1),Decimal(3)],'1'),'3'); self.assertEqual(quantile([Decimal(1)],'0'),'1')

    def test_positive_frequency_has_no_zero_width_interval_when_no_losses_observed(self):
        d=self.calc([1,2,3,4,5,6]); u=d['uncertainty']
        self.assertEqual(d['status'],'ready'); self.assertIsNotNone(u['lower_mean_net_r'])
        self.assertIsNone(u['lower_positive_fraction']); self.assertIsNone(u['upper_positive_fraction'])
        self.assertEqual(u['positive_fraction_uncertainty_status'],'unobserved_positive_or_nonpositive_class')

    def test_zero_mean_block_bootstrap_degeneracy_abstains(self):
        d=self.calc([1,-1]*6,block_bins=2,min_occupied_spans=3)
        self.assertIn('degenerate_bootstrap_distribution',d['reasons']); self.assertFalse(d['positive_lower_bound'])

    def test_empty_resamples_are_reported_and_can_block_uncertainty(self):
        r=rows([1,2,3]); d=summarize(r,TrainingWindow(START,START+100*BIN,START+100*BIN),config(min_trades=3,min_occupied_bins=3,min_occupied_spans=3,max_empty_replicate_fraction='0'))
        self.assertGreater(d['uncertainty']['empty_replicates'],0)
        self.assertIn('excessive_empty_bootstrap_replicates',d['reasons']); self.assertIsNone(d['uncertainty']['lower_mean_net_r'])
