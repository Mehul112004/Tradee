from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c06.contracts import decimal_text
from tradee.c07.math import ratio
from tradee.c15 import MonitorPolicy,reconcile
from tradee.c15.engine import ForwardMonitor
from tradee.c15.source import outcome_row
from tests.c15_integration_support import isolated
from scripts.verify_c14 import LIVE,BIN
from decimal import Decimal

NOW=LIVE+3*BIN+4


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.m,self.feed,self.result=isolated(self.tmp.name)

    def test_export_is_vintage_pinned_and_does_not_mix_tracks_or_actual_fills(self):
        out=self.m.export('forward'); self.assertEqual(len(out['rows']),9)
        self.assertEqual(len({(r['signal_id'],r['track']) for r in out['rows']}),9)
        self.assertFalse(any(r['actual_user_fill'] for r in out['rows']))
        old=self.m.export('forward',self.result['first_report_hash']); self.assertEqual(old['rows'],[])

    def test_paper_fees_and_funding_scope_reconcile_without_double_counting(self):
        r=self.m.observe('forward',NOW)
        for row in r['rows']:
            if row['track']=='portfolio':
                self.assertTrue(row['decision_recorded_before_outcome']); self.assertEqual(row['economics']['entry_fee_difference_usdt'],'0')
                self.assertEqual(row['net_usdt'],decimal_text(Decimal(row['gross_usdt'])-Decimal(row['fees_usdt'])+Decimal(row['funding_usdt'])))
                self.assertEqual(row['economics']['execution_delay_ms'],1000)
        self.assertEqual(r['telemetry']['delivery_states'],{'sent':1,'suppressed':2})

    def test_downstream_missing_inventory_requests_integrity_pause_even_on_cached_observation(self):
        with self.m.simulations.connection() as db:
            cycle=self.m.signals.session('paper_demo')['cycle']
            db.execute('DELETE FROM artifacts WHERE run_hash=? AND sequence=1',(cycle['simulation']['run_hash'],))
        r=self.m.observe('forward',NOW)
        self.assertIn('source_evidence_verification_failed',r['health']['integrity']); self.assertTrue(r['pause_requested'])
        self.assertEqual(r['rows'],[])

    def test_c14_deleted_outbox_or_signal_index_fails_closed(self):
        with self.m.signals.connection() as db: db.execute('DELETE FROM outbox')
        with self.assertRaisesRegex(ValidationError,'delivery inventory'): self.m.observe('forward',NOW)

    def test_replay_corruption_is_recorded_then_surfaces_as_monitoring_failure(self):
        with self.feed.market.connection() as db:
            # Preserve the shape but change a pinned quote event's content.
            row=db.execute("SELECT id,document FROM events WHERE kind='quote' ORDER BY id DESC LIMIT 1").fetchone()
            import json
            event=json.loads(row['document']); event['data']['bid_price']='99'
            db.execute('UPDATE events SET document=? WHERE id=?',(json.dumps(event),row['id']))
        receipt=reconcile(self.m,'forward',self.feed.market,NOW)
        self.assertFalse(receipt['ready'])
        r=self.m.observe('forward',NOW)
        self.assertIn('deterministic_replay_mismatch',r['health']['integrity'])

    def test_valid_shape_replay_mismatch_also_requests_pause(self):
        with patch('tradee.c15.reconcile._rebuild',return_value=dict(raw_prefix=False)):
            receipt=reconcile(self.m,'forward',self.feed.market,NOW)
        self.assertEqual(receipt['reasons'],['replay_content_mismatch']); self.assertFalse(self.m.observe('forward',NOW)['ready'])

    def test_delivery_audit_change_blocks_pause_without_paper_revision_change(self):
        r=self.m.observe('forward',NOW)
        # A persisted reconciliation check failure causes a new actionable report.
        self.m.store.reconciliation('forward',dict(kind='forward_replay_reconciliation',at_ms=NOW,ready=False,report_hash=r['report_hash']))
        r=self.m.observe('forward',NOW+1)
        with self.m.signals.connection() as db:
            self.m.signals._event(db,'paper_demo','delivery_diagnostic',dict(safe=True),NOW+2)
        with self.assertRaisesRegex(ValidationError,'audit compare-and-swap'): self.m.apply_pause('forward',r['report_hash'],NOW+3)

    def test_old_pause_receipt_does_not_repause_after_explicit_operator_resume(self):
        events=self.m.store.events('forward'); prior=next(e for e in events if e['kind']=='pause_applied')
        self.m.signals.pause('paper_demo',False,'Explicit synthetic recovery',NOW)
        receipt=self.m.apply_pause('forward',prior['payload']['report_hash'],NOW+1)
        self.assertTrue(receipt['paused']); self.assertFalse(self.m.signals.session('paper_demo')['paused'])

    def test_maturity_lag_is_strict_and_same_revision_does_not_restart_lag(self):
        source=self.m.signals.evidence('paper_demo'); last=source['cycles'][-1]; c=last['cycle']
        baselines=[]
        for item in source['cycles']:
            report=self.m.simulations.report(item['cycle']['simulation']['report_hash'])
            baselines.append({t['candidate_id']:t for t in report['trades']})
        p=MonitorPolicy([NOW+100],maturity_lag_ms=10)
        rows=ForwardMonitor._rows(source['cycles'],baselines,c['as_of_ms']+10,p)
        latest=[r for r in rows if r['track']=='portfolio' and r['detected_ms']>=LIVE+2*BIN]
        self.assertEqual(latest[0]['status'],'pending')
        later=ForwardMonitor._rows(source['cycles'],baselines,c['as_of_ms']+11,p)
        self.assertEqual([r for r in later if r['track']=='portfolio' and r['detected_ms']>=LIVE+2*BIN][0]['status'],'mature')

    def test_correction_replaces_current_label_and_revocation_removes_maturity(self):
        c=self.m.signals.session('paper_demo')['cycle']; s=next(x for x in c['signals'] if x['paper_outcome']); t=deepcopy(s['paper_outcome'])
        first=dict(detection=dict(cycle_hash='a'*64,as_of_ms=s['detected_ms']),admission=dict(cycle_hash='b'*64,as_of_ms=s['entry_ms'],decision=s['decision']))
        original=outcome_row(s,t,'portfolio','c'*64,c['as_of_ms'],first,NOW,0)
        t['funding_usdt']='1'; t['net_usdt']=decimal_text(Decimal(t['net_usdt'])+1)
        t['net_r']=ratio(Decimal(t['net_usdt']),Decimal(t['risk_usdt'])); t['outcome_known_ms']=NOW
        t['state']['ledger']['synthetic_revision']=dict(kind='funding',amount_usdt='1')
        t['outcome_revision_hash']=fingerprint(dict(ledger=t['state']['ledger'],status=t['status'],ambiguity=t['ambiguity_flags'],funding=t['funding_usdt']))
        revised=outcome_row(s,t,'portfolio','d'*64,NOW,first,NOW+1,0)
        self.assertEqual(Decimal(revised['net_usdt']),Decimal(original['net_usdt'])+1)
        self.assertNotEqual(original['outcome_revision_hash'],revised['outcome_revision_hash'])
        t.update(ready=False,label_status='unresolved',net_usdt=None,net_r=None)
        revoked=outcome_row(s,t,'portfolio','e'*64,NOW+1,first,NOW+2,0)
        self.assertEqual(revoked['status'],'unresolved'); self.assertIsNone(revoked['net_usdt'])
        self.assertEqual(original['net_usdt'],s['paper_outcome']['net_usdt'])

    def test_mature_ledger_corruption_cannot_be_exported_as_known_net(self):
        c=self.m.signals.session('paper_demo')['cycle']; s=next(x for x in c['signals'] if x['paper_outcome']); t=deepcopy(s['paper_outcome']); t['net_usdt']='99999'
        first=dict(detection=dict(cycle_hash='a'*64,as_of_ms=s['detected_ms']),admission=None)
        with self.assertRaisesRegex(ValidationError,'monetary'): outcome_row(s,t,'portfolio','b'*64,c['as_of_ms'],first,NOW,0)

    def test_expired_and_cancelled_entries_remain_unfilled_without_zero_return(self):
        c=self.m.signals.session('paper_demo')['cycle']; s=next(x for x in c['signals'] if x['paper_outcome'])
        first=dict(detection=dict(cycle_hash='a'*64,as_of_ms=s['detected_ms']),admission=None)
        for state in ('expired','cancelled'):
            t=deepcopy(s['paper_outcome']); t.update(ready=False,status=state,label_status='unfilled',net_r=None,net_usdt=None)
            row=outcome_row(s,t,'independent','b'*64,c['as_of_ms'],first,NOW,0)
            self.assertEqual(row['status'],'unfilled'); self.assertIsNone(row['net_r'])

    def test_open_tail_is_pending_but_an_ambiguous_open_path_is_unresolved(self):
        c=self.m.signals.session('paper_demo')['cycle']; s=next(x for x in c['signals'] if x['paper_outcome'])
        first=dict(detection=dict(cycle_hash='a'*64,as_of_ms=s['detected_ms']),admission=None)
        t=deepcopy(s['paper_outcome']); t.update(ready=False,status='open',label_status='unresolved',net_r=None,net_usdt=None,ambiguity_flags=['unresolved_data_tail'])
        self.assertEqual(outcome_row(s,t,'independent','b'*64,c['as_of_ms'],first,NOW,0)['status'],'pending')
        t['ambiguity_flags'].append('unresolved_source_gap')
        self.assertEqual(outcome_row(s,t,'independent','b'*64,c['as_of_ms'],first,NOW,0)['status'],'unresolved')
