from copy import deepcopy
from decimal import Decimal,localcontext
import unittest
from tradee.c01 import ValidationError
from tradee.c11.analysis import metrics,attribution,regular_diagnostics
from tests.c11_support import run


class SimulationAnalysisTests(unittest.TestCase):
    def test_empty_and_unresolved_denominators_are_not_fabricated(self):
        d=metrics([]); self.assertEqual(d['candidates'],0); self.assertIsNone(d['mean_net_r']); self.assertIsNone(d['win_fraction']); self.assertIsNone(d['profit_factor'])
        t=run(calendars=False).report.document()['trades'][0]; d=metrics([t])
        self.assertIsNone(d['net_usdt']); self.assertIsNone(d['mean_net_usdt']); self.assertEqual(d['mature'],0); self.assertEqual(d['unresolved'],1)

    def test_mature_only_statistics_have_explicit_unresolved_coverage(self):
        t=run().report.document()['trades'][0]; loss=deepcopy(t)
        loss.update(net_usdt='-1',net_r='-0.5',profitable=False)
        d=metrics([t,loss]); self.assertEqual(d['mean_net_usdt'],'0.74825'); self.assertEqual(d['win_fraction'],'0.5')
        self.assertEqual(d['profit_factor'],'2.4965'); self.assertEqual(d['net_r_order_statistics']['p05'],'-0.5')
        unresolved=run(calendars=False).report.document()['trades'][0]
        d=metrics([t,loss,unresolved]); self.assertEqual(d['mature'],2); self.assertIsNone(d['net_usdt']); self.assertEqual(d['mature_net_subtotal_usdt'],'1.4965')

    def test_shortfall_attribution_is_not_double_charged(self):
        d=run().report.document(); a=d['attribution']
        self.assertEqual(a['execution']['implementation_shortfall_usdt'],'0.3')
        self.assertEqual(d['metrics']['net_usdt'],'2.4965')
        self.assertEqual(a['fees_usdt'],'0.1035'); self.assertEqual(a['gross_realized_usdt'],'2.6')

    def test_reconciliation_rejects_corrupted_quantity_gross_net_and_costs(self):
        base=run().report.document()['trades'][0]
        variants=[]
        for field,value in (('net_usdt','99'),('fees_usdt','99'),('gross_realized_usdt','99')):
            t=deepcopy(base); t[field]=value; variants.append(t)
        t=deepcopy(base); t['state']['remaining_quantity']='0.5'; variants.append(t)
        t=deepcopy(base); t['state']['attempts'][0]['estimate']['costs']['spread_crossing_usdt']='99'; variants.append(t)
        t=deepcopy(base); t['state']['attempts']=[]; variants.append(t)
        for t in variants:
            with self.assertRaises(ValidationError): attribution([t])

    def test_drawdown_uses_regular_marks_and_missing_samples_are_unknown(self):
        rows=[{'pnl_usdt':v} for v in ('0','2','1','4','-2','3')]
        d=regular_diagnostics(rows); self.assertEqual(d['max_pnl_drawdown_usdt'],'6')
        d=regular_diagnostics([{'pnl_usdt':'-1'},{'pnl_usdt':'-3'}]); self.assertEqual(d['max_pnl_drawdown_usdt'],'3')
        rows.insert(2,{'pnl_usdt':None}); d=regular_diagnostics(rows)
        self.assertIsNone(d['max_pnl_drawdown_usdt']); self.assertEqual(d['available_sample_drawdown_lower_bound_usdt'],'6')
        self.assertEqual(d['missing_samples'],1); self.assertIsNone(d['portfolio_equity'])

    def test_decimal_context_cannot_change_reports(self):
        from tests.c11_support import fixture
        from tradee.c11 import Simulator
        s,events=fixture(); a=s.run(lambda:iter(events))
        with localcontext() as ctx:
            ctx.prec=3
            b=Simulator(s.dataset,s.scenarios,s.snapshots,s.versions,s.fees,s.execution,calendars=s.calendars).run(lambda:iter(events))
        self.assertEqual(a.report,b.report)

    def test_immutable_record_digest_is_cached_without_mutable_document_aliases(self):
        from dataclasses import FrozenInstanceError
        from unittest.mock import patch
        from tradee.c01.domain import fingerprint
        from tradee.c11 import SimulationRecord
        record=SimulationRecord.create({'nested':{'value':1}})
        with patch('tradee.c03.contracts.fingerprint',wraps=fingerprint) as hashed:
            first=record.digest; doc=record.document(); doc['nested']['value']=99
            self.assertEqual(record.digest,first); self.assertEqual(hashed.call_count,1)
        self.assertEqual(record.document(),{'nested':{'value':1}})
        with self.assertRaises(FrozenInstanceError): record.serialized='{}'
        with self.assertRaises(AttributeError): record.digest='invalid'
