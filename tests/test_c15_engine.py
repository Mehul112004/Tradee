"""Fault injection of monitoring/control paths; real evidence is tested by E2E."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from tradee.c01 import ValidationError
from tradee.c03.contracts import FrozenRecord
from tradee.c11 import SimulationStore
from tradee.c13 import PortfolioStore
from tradee.c14 import SignalStore
from tradee.c14 import Dispatcher,DeliveryResult
from tests.c14_support import ready,Clock
from scripts.verify_c14 import ScriptedTelegram
from tradee.c15 import ForwardMonitor,MonitorStore,MonitorPolicy
from tests.c14_support import deployment,cycle,START,STAMP


class EngineTests(unittest.TestCase):
    def setUp(self):
        recorded=patch('time.time',return_value=START/1000); recorded.start(); self.addCleanup(recorded.stop)
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); root=Path(self.tmp.name)
        self.signals=SignalStore(root/'s'); self.signals.create(deployment())
        self.store=MonitorStore(root/'m'); self.monitor=ForwardMonitor(self.store,self.signals,SimulationStore(root/'sim'),PortfolioStore(root/'p'))
        self.p=MonitorPolicy([START+720000],maturity_lag_ms=0)
        self.monitor.register('forward','paper',self.p,START)
        self.mock=patch('tradee.c15.engine.verified_cycle',return_value={}); self.mock.start(); self.addCleanup(self.mock.stop)

    def publish(self,when=STAMP,health=True):
        c=cycle(self.signals,when=when,health=health).document(); c['signals']=[]
        return self.signals.publish('paper',self.signals.session('paper')['revision'],FrozenRecord.create(c),0)

    def test_rules_must_precede_first_cycle_and_review_deadlines(self):
        self.publish()
        with self.assertRaisesRegex(ValidationError,'Freeze'): self.monitor.register('late','paper',self.p,STAMP)
        with self.assertRaises(ValidationError): self.monitor.register('bad','paper',MonitorPolicy([START]),START)

    def test_registration_before_future_start_waits_without_an_operational_pause(self):
        d=deployment().document(); d['spec']['name']='early_paper'; self.signals.create(FrozenRecord.create(d))
        with patch('time.time',return_value=(START-1000)/1000):
            # Recreate the new deployment with its true pre-start recording time.
            other=SignalStore(Path(self.tmp.name)/'early'); other.create(FrozenRecord.create(d))
        m=ForwardMonitor(MonitorStore(Path(self.tmp.name)/'early_monitor'),other,self.monitor.simulations,self.monitor.portfolios)
        m.register('early','early_paper',self.p,START-1000)
        r=m.observe('early',START-500)
        self.assertTrue(r['health']['awaiting_session_start']); self.assertFalse(r['pause_requested']); self.assertFalse(r['ready'])

    def test_observation_is_idempotent_and_does_not_rewrite_history(self):
        self.publish(); r=self.monitor.observe('forward',STAMP+1)
        self.assertTrue(r['ready']); self.assertEqual(self.monitor.observe('forward',STAMP+1),r)
        self.monitor.observe('forward',STAMP+30001)
        self.assertEqual(self.store.artifact(r['report_hash'])['observed_ms'],STAMP+1)

    def test_future_source_and_backward_observation_rejected(self):
        self.publish()
        with self.assertRaisesRegex(ValidationError,'future'): self.monitor.observe('forward',STAMP-1)
        self.monitor.observe('forward',STAMP+2)
        with self.assertRaisesRegex(ValidationError,'backward'): self.monitor.observe('forward',STAMP+1)

    def test_no_cycle_and_stale_cycle_request_operational_pause(self):
        a=self.monitor.observe('forward',START); self.assertIn('no_paper_cycle',a['health']['operational'])
        self.publish(); b=self.monitor.observe('forward',STAMP+30001)
        self.assertIn('stale_paper_cycle',b['health']['operational']); self.assertTrue(b['pause_requested'])

    def test_unhealthy_paper_path_and_fault_are_distinct_from_statistics(self):
        self.publish(health=False); r=self.monitor.observe('forward',STAMP+1)
        self.assertIn('paper_data_or_risk_unready',r['health']['operational']); self.assertEqual(r['health']['statistical'],[])

    def test_downstream_integrity_failure_is_a_redacted_pause_request(self):
        self.publish()
        with patch('tradee.c15.engine.verified_cycle',side_effect=ValidationError('private provider payload')):
            r=self.monitor.observe('forward',STAMP+1)
        self.assertTrue(r['pause_requested']); self.assertEqual(r['health']['integrity'],['source_evidence_verification_failed'])
        self.assertNotIn('private',str(r))

    def test_pause_cas_refuses_new_c14_revision(self):
        self.publish(); r=self.monitor.observe('forward',STAMP+30001); self.publish(when=STAMP+30002)
        with self.assertRaisesRegex(ValidationError,'compare-and-swap'): self.monitor.apply_pause('forward',r['report_hash'],STAMP+30003)
        self.assertFalse(self.signals.session('paper')['paused'])

    def test_pause_is_durable_idempotent_and_never_auto_resumes(self):
        self.publish(); r=self.monitor.observe('forward',STAMP+30001)
        a=self.monitor.apply_pause('forward',r['report_hash'],STAMP+30001)
        self.assertEqual(self.monitor.apply_pause('forward',r['report_hash'],STAMP+30002),a)
        self.publish(when=STAMP+30003); self.monitor.observe('forward',STAMP+30004)
        self.assertTrue(self.signals.session('paper')['paused'])

    def test_cross_store_receipt_failure_recovers_existing_pause_without_duplicate(self):
        self.publish(); r=self.monitor.observe('forward',STAMP+30001)
        with patch.object(self.store,'receipt',side_effect=sqlite3.OperationalError('disk full')):
            with self.assertRaises(sqlite3.OperationalError): self.monitor.apply_pause('forward',r['report_hash'],STAMP+30001)
        self.assertTrue(self.signals.session('paper')['paused'])
        self.monitor.apply_pause('forward',r['report_hash'],STAMP+30002)
        self.assertEqual(len([e for e in self.signals.events('paper') if e['kind']=='paused']),1)

    def test_stale_report_cannot_pause_after_recovery_observation(self):
        self.publish(); r=self.monitor.observe('forward',STAMP+30001); self.publish(when=STAMP+30002); self.monitor.observe('forward',STAMP+30003)
        with self.assertRaisesRegex(ValidationError,'Stale'): self.monitor.apply_pause('forward',r['report_hash'],STAMP+30004)

    def test_healthy_report_has_no_pause_authority(self):
        self.publish(); r=self.monitor.observe('forward',STAMP+1)
        with self.assertRaisesRegex(ValidationError,'no pause request'): self.monitor.apply_pause('forward',r['report_hash'],STAMP+1)

    def test_policy_opt_out_does_not_mark_failure_healthy(self):
        # A different prospective deployment would freeze this choice. Exercise
        # the evaluator with that explicit rule, rather than mutating a store.
        self.publish()
        p=MonitorPolicy([START+720000],pause_on_operational_failure=False)
        real=self.monitor._source
        with patch.object(self.monitor,'_source',side_effect=lambda n,w:(*real(n,w)[:2],p)):
            r=self.monitor.observe('forward',STAMP+30001)
        self.assertFalse(r['ready']); self.assertFalse(r['pause_requested'])

    def test_report_byte_budget_is_enforced_without_publication(self):
        self.publish(); p=MonitorPolicy([START+720000],max_report_bytes=1); real=self.monitor._source
        with patch.object(self.monitor,'_source',side_effect=lambda n,w:(*real(n,w)[:2],p)):
            with self.assertRaisesRegex(ValidationError,'byte budget'): self.monitor.observe('forward',STAMP+1)
        self.assertIsNone(self.store.head('forward')['report_hash'])

    def test_no_retroactive_review_edits(self):
        self.publish(); r=self.monitor.observe('forward',START+720001)
        self.assertEqual(r['reviews'][0]['status'],'insufficient_evidence')
        later=self.monitor.observe('forward',START+720002); self.assertEqual(later['reviews'],r['reviews'])

    def test_failed_delivery_requests_pause(self):
        self.signals.publish('paper',0,cycle(self.signals),0)
        Dispatcher(self.signals,clock=Clock()).send_one('paper',ready,ScriptedTelegram([DeliveryResult('failed','telegram_rejected')]))
        with patch.object(self.monitor,'_rows',return_value=[]): r=self.monitor.observe('forward',STAMP+1)
        self.assertIn('delivery_failed',r['health']['operational']); self.assertTrue(r['pause_requested'])

    def test_unknown_delivery_is_not_assumed_sent_or_failed(self):
        self.signals.publish('paper',0,cycle(self.signals),0)
        Dispatcher(self.signals,clock=Clock()).send_one('paper',ready,ScriptedTelegram([DeliveryResult('ambiguous','network_outcome_unknown')]))
        with patch.object(self.monitor,'_rows',return_value=[]): r=self.monitor.observe('forward',STAMP+1)
        self.assertIn('delivery_reconciliation_required',r['health']['operational']); self.assertEqual(r['telemetry']['delivery_states'],{'ambiguous':1})

    def test_expired_inflight_lease_requests_recovery_without_guessing_receipt(self):
        self.signals.publish('paper',0,cycle(self.signals),0)
        with self.assertRaises(KeyboardInterrupt): Dispatcher(self.signals,clock=Clock()).send_one('paper',ready,ScriptedTelegram([KeyboardInterrupt()]))
        with patch.object(self.monitor,'_rows',return_value=[]): r=self.monitor.observe('forward',STAMP+15001)
        self.assertIn('delivery_lease_elapsed',r['health']['operational']); self.assertEqual(r['telemetry']['delivery_states'],{'in_flight':1})

    def test_expired_pending_notice_is_operational_evidence(self):
        self.signals.publish('paper',0,cycle(self.signals),0)
        with patch.object(self.monitor,'_rows',return_value=[]): r=self.monitor.observe('forward',STAMP+10001)
        self.assertIn('delivery_expiry_unrecovered',r['health']['operational'])

    def test_statistical_pause_is_separate_from_operational_failure(self):
        self.publish(when=START+720000)
        with patch('tradee.c15.engine.review',return_value=dict(status='degraded',degraded=True,degradation_reasons=['mean_net_r_below_floor'])):
            r=self.monitor.observe('forward',START+720001)
        self.assertEqual(r['health']['operational'],[]); self.assertEqual(r['health']['statistical'],['mean_net_r_below_floor'])
        self.assertTrue(r['pause_requested'])

    def test_count_budget_stops_new_reports_but_allows_cached_retry(self):
        self.publish(); p=MonitorPolicy([START+720000],max_observations=1); real=self.monitor._source
        with patch.object(self.monitor,'_source',side_effect=lambda n,w:(*real(n,w)[:2],p)):
            r=self.monitor.observe('forward',STAMP+1)
            self.assertEqual(self.monitor.observe('forward',STAMP+1),r)
            with self.assertRaisesRegex(ValidationError,'count budget'): self.monitor.observe('forward',STAMP+2)

