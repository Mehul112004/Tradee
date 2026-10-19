from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import unittest
from tradee.c01 import ValidationError
from tradee.c09 import TradePolicy
from tradee.c11 import SimulationConfig, Scenario, Simulator
from tests.c11_support import fixture,run,payloads
from tests.c09_support import DETECT,observation,prepared
from tests.c08_support import START,event,spec,metadata,trend_events


class SimulatorTests(unittest.TestCase):
    def test_actual_long_and_short_golden_ledgers(self):
        for side,net,fee in (('long','2.4965','0.1035'),('short','2.5035','0.0965')):
            with self.subTest(side=side):
                r=run(side=side); d=r.report.document(); t=d['trades'][0]
                self.assertEqual((t['gross_realized_usdt'],t['fees_usdt'],t['net_usdt']),('2.6',fee,net))
                self.assertTrue(d['ready']); self.assertTrue(d['attribution']['reconciled'])
                self.assertEqual(t['remaining_quantity'],'0'); self.assertEqual(len(t['state']['ledger']),2)
                self.assertEqual(t['outcome_known_ms'],DETECT+30000)
                self.assertEqual(d['candidate_coverage']['range']['evaluations'],6)

    def test_known_outcomes_are_prefix_available_not_only_final_horizon(self):
        r=run(end=DETECT+120000); revisions=payloads(r,'outcome_revision')
        mature=[v for v in revisions if v['outcome']['ready']]
        self.assertEqual(len(mature),1); self.assertEqual(mature[0]['observed_ms'],DETECT+30000)
        self.assertEqual(mature[0]['outcome']['outcome_known_ms'],DETECT+30000)

    def test_warmup_window_excludes_detection_but_preserves_context(self):
        a=run(config=SimulationConfig(decision_start_ms=DETECT,decision_end_ms=DETECT+1))
        self.assertEqual(a.report.document()['metrics']['candidates'],1)
        b=run(config=SimulationConfig(decision_start_ms=DETECT+1,decision_end_ms=DETECT+2))
        d=b.report.document(); self.assertEqual(d['metrics']['candidates'],0)
        self.assertEqual(d['candidate_coverage']['range']['outside_decision_window'],1)
        self.assertFalse(d['ready']); self.assertFalse(d['has_mature_evidence'])
        self.assertEqual(d['regular_pnl']['combined']['max_pnl_drawdown_usdt'],'0')

    def test_no_future_entry_or_outcome_before_exact_detection_prefix(self):
        r=run(config=SimulationConfig(sample_interval_ms=1000))
        early=[a.document()['payload'] for a in r.artifacts if a.document()['kind']=='sample' and a.document()['scenario']=='range' and a.document()['payload']['at_ms']<=DETECT]
        self.assertTrue(early); self.assertTrue(all(p['open_trades']==0 and p['pnl_usdt']=='0' for p in early))
        self.assertTrue(all(v['observed_ms']>=DETECT for v in payloads(r,'outcome_revision')))

    def test_same_timestamp_sources_precede_regular_valuation(self):
        r=run(config=SimulationConfig(sample_interval_ms=1000))
        p=next(a.document()['payload'] for a in r.artifacts if a.document()['kind']=='sample' and a.document()['scenario']=='range' and a.document()['payload']['at_ms']==DETECT+30000)
        self.assertEqual(p['input_cursor'],[DETECT+30000,8]); self.assertEqual(p['pnl_usdt'],'2.4965')

    def test_regular_mtm_marks_open_exposure_and_staleness_without_forward_fill(self):
        r=run(config=SimulationConfig(sample_interval_ms=1000,max_valuation_age_ms=5000))
        points={a.document()['payload']['at_ms']:a.document()['payload'] for a in r.artifacts if a.document()['kind']=='sample' and a.document()['scenario']=='range'}
        self.assertEqual(points[DETECT+1000]['pnl_usdt'],'-0.2511')
        self.assertIsNone(points[DETECT+6000]['pnl_usdt'])
        stats=r.report.document()['regular_pnl']['combined']; self.assertFalse(stats['complete']); self.assertIsNone(stats['max_pnl_drawdown_usdt'])
        self.assertIsNone(stats['sharpe']); self.assertIsNone(stats['annualized_return'])

    def test_time_exit_is_scheduled_during_feed_gap_and_does_not_fill_old_quote(self):
        policy=TradePolicy(max_holding_ms=10000,max_exit_wait_ms=5000)
        r=run(policy=policy); t=r.report.document()['trades'][0]
        self.assertEqual(t['status'],'unresolved'); self.assertEqual(t['reason'],'exit_liquidity_timeout')
        transitions=payloads(r,'transition')
        queued=next(p for p in transitions if p['state']['exit_pending'])
        self.assertEqual(queued['evaluation_as_of_ms'],DETECT+11000)
        timed=next(p for p in transitions if p['state']['status']=='unresolved')
        self.assertEqual(timed['evaluation_as_of_ms'],DETECT+16000)
        self.assertEqual(t['remaining_quantity'],'1'); self.assertIsNone(t['net_usdt'])

    def test_entry_expiry_is_exact_and_manual_delay_has_no_early_fill(self):
        s,events=fixture(); e=replace(s.execution,manual_delay_ms=120000)
        r=run(execution=e,end=DETECT+120000); t=r.report.document()['trades'][0]
        self.assertEqual(t['status'],'expired'); self.assertIsNone(t['entry_ms'])
        timed=next(p for p in payloads(r,'transition') if p['state']['status']=='expired')
        self.assertEqual(timed['evaluation_as_of_ms'],DETECT+60000)

    def test_unknown_funding_and_open_tail_are_never_certified_zero_loss(self):
        r=run(calendars=False); t=r.report.document()['trades'][0]
        self.assertEqual(t['status'],'closed'); self.assertIsNone(t['net_usdt']); self.assertFalse(t['ready'])
        self.assertIsNone(r.report.document()['metrics']['net_usdt'])
        s,events=fixture(); r=run(events=events[:5]); t=r.report.document()['trades'][0]
        self.assertEqual(t['status'],'open'); self.assertEqual(t['remaining_quantity'],'1')
        self.assertIn('unresolved_data_tail',t['ambiguity_flags']); self.assertIsNone(t['net_usdt'])

    def test_late_funding_revision_replaces_cashflow_and_known_time(self):
        from tradee.c06 import SettlementCalendar
        s,events=fixture(); inst=s.snapshots[0]['decisions'][0]['instrument_id']; settle=DETECT+20000
        events[5:]=[observation('mark',6,DETECT+40000,'105'),observation('trade',7,DETECT+40000,'105'),observation('quote',8,DETECT+40000,'105')]
        events+= [observation('funding',9,settle,mark_price='102',available=DETECT+50000),observation('funding',10,settle,mark_price='102',funding_rate='0.002',available=DETECT+60000)]
        s.dataset['event_count']=len(events)
        calendar=SettlementCalendar(inst,'BTCUSDT',START,s.dataset['end_ms'],[settle],'operator_assumption:synthetic')
        sim=Simulator(s.dataset,s.scenarios,s.snapshots,s.versions,s.fees,s.execution,calendars=[calendar])
        r=sim.run(lambda:iter(events)); t=r.report.document()['trades'][0]
        self.assertEqual(t['net_usdt'],'2.2925'); self.assertEqual(t['funding_usdt'],'-0.204')
        self.assertEqual(t['outcome_known_ms'],DETECT+60000); self.assertEqual(len(t['state']['ledger']),3)
        rev=[p for p in payloads(r,'outcome_revision') if p['outcome']['ready']]
        self.assertEqual([(p['observed_ms'],p['outcome']['net_usdt']) for p in rev],[(DETECT+50000,'2.3945'),(DETECT+60000,'2.2925')])

    def test_unexpected_boundary_funding_can_revoke_an_earlier_mature_label(self):
        s,events=fixture()
        events.append(observation('funding',9,DETECT+2000,available=DETECT+50000))
        r=run(events=events); t=r.report.document()['trades'][0]
        self.assertIsNone(t['outcome_known_ms']); self.assertFalse(t['ready']); self.assertEqual(len(t['state']['ledger']),3)
        rev=payloads(r,'outcome_revision')
        self.assertTrue(any(p['outcome']['ready'] for p in rev))
        self.assertFalse(rev[-1]['outcome']['ready']); self.assertEqual(rev[-1]['observed_ms'],DETECT+50000)

    def test_future_price_changes_do_not_change_earlier_candidate_decisions(self):
        a=run(); s,events=fixture()
        events[5]=observation('mark',6,DETECT+30000,'101')
        events[6]=observation('trade',7,DETECT+30000,'101')
        events[7]=observation('quote',8,DETECT+30000,'101')
        b=run(events=events)
        self.assertEqual(payloads(a,'candidate_decision'),payloads(b,'candidate_decision'))
        self.assertNotEqual(a.report.document()['trades'][0]['net_usdt'],b.report.document()['trades'][0]['net_usdt'])

    def test_streaming_factory_and_chunked_iterator_produce_identical_artifacts(self):
        a=run(); s,events=fixture()
        def chunked():
            for i in range(0,len(events),3): yield from events[i:i+3]
        b=s.run(chunked)
        self.assertEqual(a.report,b.report); self.assertEqual(a.artifacts,b.artifacts)

    def test_changed_second_pass_and_missing_prefix_fail_without_results(self):
        for change in ('price','missing'):
            s,events=fixture(); calls=[]
            def factory():
                calls.append(1); rows=deepcopy(events)
                if len(calls)>1:
                    if change=='missing': rows.pop()
                    else: rows[-1]=observation('quote',8,DETECT+30000,'106')
                return iter(rows)
            with self.subTest(change=change),self.assertRaises(ValidationError): s.run(factory)
        s,events=fixture(); s.dataset['event_count']+=1
        with self.assertRaises(ValidationError): s.run(lambda:iter(events))

    def test_resource_budget_exhaustion_is_not_silent_truncation(self):
        s,events=fixture(scenarios=[Scenario('a',spec().document(),{},'1'),Scenario('b',spec().document(),{'target_r':'3'},'1')],config=SimulationConfig(max_candidates=1))
        with self.assertRaisesRegex(ValidationError,'candidate budget'): s.run(lambda:iter(events))
        s,events=fixture(config=SimulationConfig(max_artifacts=1))
        with self.assertRaisesRegex(ValidationError,'artifact budget'): s.run(lambda:iter(events))

    def test_simulator_is_single_use(self):
        s,events=fixture(); s.run(lambda:iter(events))
        with self.assertRaises(ValidationError): s.run(lambda:iter(events))

    def test_both_families_have_separate_context_and_outcome_inventories(self):
        from tradee.c08 import CandidateConfig
        from tradee.c07 import ExecutionConfig,FeeSchedule
        from tradee.c06 import SettlementCalendar
        events=trend_events()+[event(402,'144'),event(403,'144')]
        end=START+405*60000; ds=dict(schema_version=1,dataset_hash='both',mode='recorded',start_ms=START,end_ms=end,as_of_ms=end,symbols=['BTCUSDT'],kinds=['candle','quote','mark','trade','funding'],event_count=len(events))
        _,u,v=metadata(); inst=u['decisions'][0]['instrument_id']
        scenarios=[Scenario('range',spec().document(),{},'1'),Scenario('trend',spec('ema_pullback_continuation').document(),{},'1','swing')]
        ex=ExecutionConfig(manual_delay_ms=0,max_metadata_age_ms=86400000)
        r=Simulator(ds,scenarios,[u],v,FeeSchedule('0.0005','0.0002','fixture'),ex,calendars=[SettlementCalendar(inst,'BTCUSDT',START,end,[],'operator_assumption:fixture')]).run(lambda:iter(events))
        d=r.report.document(); self.assertEqual(d['candidate_coverage']['trend']['selected'],1)
        self.assertEqual(d['candidate_coverage']['range']['selected'],2)
        self.assertEqual(set(d['groups']['family']),{'prior_range_breakout','ema_pullback_continuation'})
        self.assertEqual(set(d['groups']['horizon']),{'intraday','swing'})
        self.assertEqual(len(payloads(r,'lifecycle_manifest')),2)

    def test_partial_exits_reconcile_original_quantity_and_one_fee_per_fill(self):
        s,events=fixture(policy=TradePolicy(partial_target_r='1'))
        events[5:]=[observation('mark',6,DETECT+20000,'103.5'),observation('trade',7,DETECT+20000,'103.5'),observation('quote',8,DETECT+20000,'103.5'),
                    observation('mark',9,DETECT+40000,'105'),observation('trade',10,DETECT+40000,'105'),observation('quote',11,DETECT+40000,'105')]
        r=run(events=events,policy=TradePolicy(partial_target_r='1')); t=r.report.document()['trades'][0]
        self.assertEqual(t['net_usdt'],'1.746875'); self.assertEqual(t['fees_usdt'],'0.103125')
        self.assertEqual(t['remaining_quantity'],'0'); self.assertEqual(len(t['state']['ledger']),3)
        self.assertEqual([p['quantity'] for p in t['state']['quantity_changes']],['1','0.5','0'])

    def test_modeled_close_and_conflicting_range_have_explicit_unknown_labels(self):
        from tradee.c08 import StrategySpec
        for source in ('bar_close','bar_range'):
            with self.subTest(source=source):
                base,intent,events=prepared(mode='modeled',policy=TradePolicy(trigger_source=source,max_holding_ms=60000))
                events=events+[event(45,'102',mode='modeled'),event(46,'105' if source=='bar_close' else '103',high='106',low='100' if source=='bar_range' else '104',mode='modeled')]
                ds={**base.dataset,'as_of_ms':START+48*60000,'event_count':len(events)}
                _,u,v=metadata(); scenario=Scenario('bar',StrategySpec(lookback_bars=2).document(),intent.policy.document(),'1')
                result=Simulator(ds,[scenario],[u],v,base.fees,base.execution).run(lambda:iter(events))
                t=result.report.document()['trades'][0]
                self.assertIsNone(t['net_usdt']); self.assertIsNone(t['funding_usdt'])
                if source=='bar_close': self.assertEqual(t['status'],'closed')
                else:
                    self.assertEqual(t['status'],'unresolved'); self.assertIn('stop_and_target_same_bar',t['ambiguity_flags']); self.assertEqual(t['remaining_quantity'],'1')
