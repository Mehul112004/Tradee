import unittest
from tradee.c01 import ValidationError
from tradee.c15 import MonitorPolicy


class ContractsTests(unittest.TestCase):
    def test_roundtrip_and_no_mutable_time_alias(self):
        times=[100,200]; p=MonitorPolicy(times); times.append(300)
        self.assertEqual(p.review_times_ms,(100,200)); self.assertEqual(MonitorPolicy.from_dict(p.document()),p)

    def test_invalid_times(self):
        for v in ([],[1,1],[2,1],[True],[1.2],list(range(33)),None):
            with self.subTest(v=v),self.assertRaises(ValidationError): MonitorPolicy(v)

    def test_invalid_bounded_settings(self):
        for k,v in (('version',True),('min_mature',1),('min_occupied_spans',1),('max_cycle_age_ms',30001),('alpha','0'),('alpha','1'),
                    ('alpha','NaN'),('alpha',.1),('residual_tolerance_r','-1'),('bootstrap_replicates',1),('block_bins',0),
                    ('pause_on_operational_failure',1),('maturity_lag_ms',-1),('max_work',10000001)):
            with self.subTest(k=k,v=v),self.assertRaises(ValidationError): MonitorPolicy([100],**{k:v})

    def test_strict_fields_and_tail_resolution(self):
        with self.assertRaises(ValidationError): MonitorPolicy.from_dict(dict(review_times_ms=[1],unknown=True))
        with self.assertRaises(ValidationError): MonitorPolicy(list(range(1,33)),bootstrap_replicates=200)

