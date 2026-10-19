from copy import deepcopy
from decimal import Decimal,localcontext
import json
import unittest
from tradee.c01 import ValidationError
from tradee.c09 import LifecycleEngine,TradePolicy
from tests.c09_support import *


class LifecycleEngineTests(unittest.TestCase):
    def test_long_target_books_fill_price_pnl_fees_and_declared_zero_funding_once(self):
        e,i,events=prepared(calendars=[calendar()]); s=open_trade(e,events); self.assertEqual(s['entry_price'],'102.2')
        s=close_trade(e); self.assertEqual(s['status'],'closed')
        r=e.report(DETECT+30000,True).document()['trades'][0]
        self.assertEqual(r['gross_realized_usdt'],'2.6'); self.assertEqual(r['fees_usdt'],'0.1035')
        self.assertEqual(r['net_usdt'],'2.4965'); self.assertTrue(r['profitable']); self.assertTrue(r['target_before_stop'])
        self.assertEqual(r['state']['remaining_quantity'],'0'); self.assertEqual(len(r['state']['ledger']),2)
        self.assertEqual(e.report(DETECT+30000,True).document()['trades'][0]['net_usdt'],'2.4965')

    def test_short_target_has_reverse_cashflow_and_taker_fees(self):
        e,i,events=prepared('short',calendars=[calendar()]); s=open_trade(e,events,'98'); self.assertEqual(s['entry_price'],'97.8')
        close_trade(e,'95'); r=e.report(DETECT+30000,True).document()['trades'][0]
        self.assertEqual(r['gross_realized_usdt'],'2.6'); self.assertEqual(r['fees_usdt'],'0.0965'); self.assertEqual(r['net_usdt'],'2.5035')

    def test_stop_gap_fills_at_available_quote_not_threshold(self):
        e,i,events=prepared(calendars=[calendar()]); open_trade(e,events); close_trade(e,'99')
        r=e.report(DETECT+30000,True).document()['trades'][0]
        self.assertEqual(r['reason'],'stop'); self.assertEqual(r['gross_realized_usdt'],'-3.4'); self.assertEqual(r['net_usdt'],'-3.5005')
        self.assertFalse(r['target_before_stop']); self.assertFalse(r['profitable'])

    def test_partial_exit_then_full_target_updates_quantity_timeline(self):
        e,i,events=prepared(partial_target_r='1',calendars=[calendar()]); s=open_trade(e,events)
        s=close_trade(e,'103.5'); self.assertEqual(s['status'],'open'); self.assertEqual(s['remaining_quantity'],'0.5')
        close_trade(e,'105',DETECT+50000,9); r=e.report(DETECT+50000,True).document()['trades'][0]
        self.assertEqual([c['quantity'] for c in r['state']['quantity_changes']],['1','0.5','0'])
        self.assertEqual(r['gross_realized_usdt'],'1.85'); self.assertEqual(r['fees_usdt'],'0.103125'); self.assertEqual(r['net_usdt'],'1.746875')

    def test_partial_exit_then_stop_does_not_reopen_or_double_book(self):
        e,i,events=prepared(partial_target_r='1'); open_trade(e,events); close_trade(e,'103.5'); close_trade(e,'100',DETECT+50000,9)
        s=e.states[i.trade_id]; self.assertEqual(s['status'],'closed'); self.assertEqual(s['exit_reason'],'stop')
        self.assertEqual(sum(Decimal(v['quantity']) for v in s['ledger'].values() if v['kind']=='exit'),Decimal('1'))

    def test_manual_delay_and_exclusive_expiry(self):
        e,i,events=prepared(execution=ExecutionConfig(manual_delay_ms=30000)); s=open_trade(e,events)
        self.assertEqual(s['status'],'pending_entry')
        e.tick(DETECT+60000); self.assertEqual(e.states[i.trade_id]['status'],'expired'); self.assertEqual(s['remaining_quantity'],'0')

    def test_future_candidate_never_enters_before_its_exact_known_prefix(self):
        e,i,events=prepared(); e.advance(events[0]); self.assertEqual(e.states[i.trade_id]['status'],'waiting')
        bad=deepcopy(events[1]); bad['data']['quote_volume']='100001'; bad['raw_sha256']=fingerprint(bad['data'])
        e.advance(bad)
        with self.assertRaises(ValidationError): e.advance(events[2])

    def test_pending_entry_thesis_invalidation_cancels(self):
        e,i,events=prepared(execution=ExecutionConfig(manual_delay_ms=30000)); open_trade(e,events)
        later=candle_event(3,'100',eid=6); e.advance(later)
        self.assertEqual(e.states[i.trade_id]['status'],'expired') # expiry takes precedence
        e,i,events=prepared(execution=ExecutionConfig(manual_delay_ms=1000));
        for x in events: e.advance(x)
        revision=candle_event(2,'100',eid=4,available=DETECT+2000); e.advance(revision)
        self.assertEqual(e.states[i.trade_id]['exit_reason'],'setup_invalidated')

    def test_entry_stop_or_beyond_target_does_not_create_position(self):
        e,i,events=prepared(execution=ExecutionConfig(manual_delay_ms=0,max_adverse_drift_bps='1000')); s=open_trade(e,events,'105')
        self.assertEqual(s['status'],'cancelled'); self.assertEqual(s['exit_reason'],'entry_beyond_target'); self.assertFalse(s['ledger'])

    def test_missing_mark_or_liquidity_rejection_leaves_pending(self):
        e,i,events=prepared()
        for x in events: e.advance(x)
        e.advance(observation('quote',4,DETECT+1000))
        s=e.states[i.trade_id]; self.assertEqual(s['status'],'pending_entry'); self.assertIn('missing_or_stale_mark',s['attempts'][-1]['estimate']['reasons'])

    def test_time_exit_uses_configured_holding_time_and_next_executable_quote(self):
        e,i,events=prepared(max_holding_ms=10000,calendars=[calendar()]); open_trade(e,events)
        e.tick(DETECT+11000); self.assertEqual(e.states[i.trade_id]['status'],'exit_pending')
        e.advance(observation('mark',6,DETECT+12000)); e.advance(observation('quote',7,DETECT+12000))
        self.assertEqual(e.states[i.trade_id]['exit_reason'],'time_exit'); self.assertEqual(e.states[i.trade_id]['remaining_quantity'],'0')

    def test_exit_delay_latches_stop_and_does_not_fill_at_trigger(self):
        e,i,events=prepared(exit_delay_ms=10000); open_trade(e,events); close_trade(e,'100')
        self.assertEqual(e.states[i.trade_id]['status'],'exit_pending')
        e.advance(observation('mark',9,DETECT+41000,'101')); e.advance(observation('quote',10,DETECT+41000,'101'))
        self.assertEqual(e.states[i.trade_id]['exit_reason'],'stop')

    def test_exit_block_timeout_does_not_fabricate_a_flat_position(self):
        e,i,events=prepared(); open_trade(e,events)
        e.advance(observation('trade',6,DETECT+30000,'100')); e.tick(DETECT+90000)
        s=e.states[i.trade_id]; self.assertEqual(s['status'],'unresolved'); self.assertEqual(s['remaining_quantity'],'1'); self.assertEqual(s['exit_reason'],'exit_liquidity_timeout')

    def test_explicit_invalidation_cancels_pending_or_requests_market_close(self):
        e,i,events=prepared(); s=open_trade(e,events); e.cancel(i.trade_id,DETECT+5000)
        e.advance(observation('mark',6,DETECT+6000)); e.advance(observation('quote',7,DETECT+6000))
        self.assertEqual(s['exit_reason'],'invalidation'); self.assertEqual(s['status'],'closed')

    def test_same_millisecond_quote_does_not_allow_entry_and_exit_at_once(self):
        e,i,events=prepared(); s=open_trade(e,events)
        e.advance(observation('trade',6,DETECT+1000,'99')); e.advance(observation('quote',7,DETECT+1000,'99'))
        self.assertEqual(s['status'],'exit_pending'); self.assertEqual(len(s['quantity_changes']),1)

    def test_trigger_source_mark_and_contract_trade_are_distinct(self):
        e,i,events=prepared(policy=TradePolicy(trigger_source='mark')); s=open_trade(e,events)
        e.advance(observation('trade',6,DETECT+5000,'99')); self.assertEqual(s['status'],'open')
        e.advance(observation('mark',7,DETECT+6000,'99')); e.advance(observation('quote',8,DETECT+6000,'99'))
        self.assertEqual(s['exit_reason'],'stop')

    def test_late_revised_trigger_does_not_rewrite_fill_and_flags_label(self):
        e,i,events=prepared(calendars=[calendar()]); s=open_trade(e,events)
        e.advance(observation('trade',6,DETECT+20000,'103'))
        e.advance(observation('trade',7,DETECT+10000,'99',available=DETECT+21000)); close_trade(e,stamp=DETECT+30000,eid=8)
        r=e.report(DETECT+30000,True).document()['trades'][0]
        self.assertIn('late_or_revised_trigger_path',r['ambiguity_flags']); self.assertFalse(r['ready']); self.assertIsNone(r['profitable'])

    def test_missing_calendar_keeps_net_and_profitability_unknown(self):
        e,i,events=prepared(); open_trade(e,events); close_trade(e)
        r=e.report(DETECT+30000,True).document()['trades'][0]
        self.assertIsNone(r['net_usdt']); self.assertEqual(r['funding']['coverage_status'],'unknown_schedule'); self.assertIsNone(r['profitable'])

    def test_funding_revisions_replace_one_cashflow_and_do_not_change_fill_prices(self):
        at=DETECT+30000
        e,i,events=prepared(calendars=[calendar([at])]); s=open_trade(e,events)
        e.advance(observation('funding',6,at,'102')); close_trade(e,'105',DETECT+60000,7)
        first=e.report(DETECT+60000,True).document()['trades'][0]
        self.assertEqual(first['funding_usdt'],'-0.102'); self.assertEqual(first['net_usdt'],'2.3945')
        e.advance(observation('funding',10,at,'102',available=DETECT+70000,funding_rate='0.002'))
        second=e.report(DETECT+70000,True).document()['trades'][0]
        self.assertEqual(second['net_usdt'],'2.2925'); self.assertEqual(len(second['state']['ledger']),3)
        self.assertEqual(first['net_usdt'],'2.3945')

    def test_partial_quantity_at_funding_is_used(self):
        at=DETECT+50000
        e,i,events=prepared(partial_target_r='1',calendars=[calendar([at])]); open_trade(e,events); close_trade(e,'103.5',DETECT+20000)
        e.advance(observation('funding',9,at,'104')); close_trade(e,'105',DETECT+80000,10)
        r=e.report(DETECT+80000,True).document()['trades'][0]
        self.assertEqual(r['funding_usdt'],'-0.052'); self.assertEqual(r['net_usdt'],'1.694875')

    def test_settlement_boundary_ambiguity_suppresses_net_label(self):
        at=DETECT+10000
        e,i,events=prepared(calendars=[calendar([at])]); open_trade(e,events); e.advance(observation('funding',6,at)); close_trade(e,stamp=DETECT+40000,eid=7)
        r=e.report(DETECT+40000,True).document()['trades'][0]
        self.assertIsNone(r['net_usdt']); self.assertEqual(r['funding']['cashflows'][0]['status'],'boundary_ambiguous')

    def test_modeled_next_bar_entry_and_later_close_trigger_not_intrabar_fills(self):
        e,i,events=prepared(mode='modeled')
        for x in events: e.advance(x)
        self.assertEqual(e.states[i.trade_id]['status'],'pending_entry')
        e.advance(candle_event(45,'102',mode='modeled')); self.assertEqual(e.states[i.trade_id]['entry_ms'],START+46*MINUTE)
        e.advance(candle_event(46,'105',mode='modeled')); r=e.report(START+47*MINUTE,True).document()['trades'][0]
        self.assertEqual(r['status'],'closed'); self.assertIsNone(r['funding_usdt']); self.assertIsNone(r['net_usdt'])

    def test_bar_range_stop_target_conflict_is_unresolved_without_fake_fill(self):
        e,i,events=prepared(mode='modeled',policy=TradePolicy(trigger_source='bar_range'))
        for x in events: e.advance(x)
        e.advance(candle_event(45,'102',mode='modeled')); e.advance(candle_event(46,'102',high='106',low='99',mode='modeled'))
        s=e.states[i.trade_id]; self.assertEqual(s['status'],'unresolved'); self.assertEqual(s['remaining_quantity'],'1')
        self.assertEqual(len(s['ledger']),1); self.assertIn('stop_and_target_same_bar',s['ambiguity_flags'])

    def test_unresolved_tail_is_visible_and_does_not_turn_into_loss(self):
        e,i,events=prepared(); open_trade(e,events)
        _,r=e.finish(DETECT+2000); t=r.document()['trades'][0]
        self.assertIn('unresolved_data_tail',t['ambiguity_flags']); self.assertIsNone(t['net_usdt']); self.assertIsNone(t['outcome_known_ms'])

    def test_checkpoint_every_split_matches_final_fill_and_ledger(self):
        e,i,events=prepared(calendars=[calendar()])
        inputs=events+[observation('mark',4,DETECT+1000),observation('quote',5,DETECT+1000),observation('mark',6,DETECT+30000,'105'),observation('trade',7,DETECT+30000,'105'),observation('quote',8,DETECT+30000,'105')]
        for x in inputs: e.advance(x)
        want=e.report(DETECT+30000,True).serialized
        for split in range(len(inputs)+1):
            a,_,_=prepared(calendars=[calendar()])
            for x in inputs[:split]: a.advance(x)
            b=LifecycleEngine.restore(a.dataset,a.intents,a.book.snapshots,a.book.versions,a.fees,a.execution,a.funding_config,a.calendars,json.loads(json.dumps(a.checkpoint())))
            for x in inputs[split:]: b.advance(x)
            self.assertEqual(b.report(DETECT+30000,True).serialized,want)

    def test_duplicate_backward_clock_and_checkpoint_fail(self):
        e,i,events=prepared(); e.advance(events[0]); cp=e.checkpoint(); self.assertEqual(e.advance(events[0]),[])
        self.assertEqual(e.checkpoint(),cp)
        with self.assertRaises(ValidationError): e.tick(START)
        cp['run_hash']='bad'
        with self.assertRaises(ValidationError): LifecycleEngine.restore(e.dataset,e.intents,e.book.snapshots,e.book.versions,e.fees,e.execution,e.funding_config,e.calendars,cp)

    def test_target_before_stop_is_not_a_net_profit_label(self):
        e,i,events=prepared(target_r='1',calendars=[calendar()])
        e=LifecycleEngine(e.dataset,[i],e.book.snapshots,e.book.versions,FeeSchedule('0.01','0','explicit stress fee assumption'),e.execution,calendars=e.calendars)
        open_trade(e,events); close_trade(e,'103.1')
        r=e.report(DETECT+30000,True).document()['trades'][0]
        self.assertTrue(r['target_before_stop']); self.assertFalse(r['profitable']); self.assertLess(Decimal(r['net_usdt']),0)

    def test_mfe_mae_are_sampled_diagnostics_not_future_inputs(self):
        e,i,events=prepared(calendars=[calendar()]); open_trade(e,events)
        e.advance(observation('trade',6,DETECT+5000,'103')); e.advance(observation('trade',7,DETECT+10000,'101.5'))
        close_trade(e,stamp=DETECT+30000,eid=8)
        r=e.report(DETECT+30000,True).document()['trades'][0]
        self.assertEqual(r['mfe_price'],'105'); self.assertEqual(r['mae_price'],'101.5'); self.assertGreater(Decimal(r['mfe_r']),0); self.assertLess(Decimal(r['mae_r']),0)

    def test_unknown_gap_or_stale_trigger_prevents_mature_label(self):
        e,i,events=prepared(calendars=[calendar()]); open_trade(e,events)
        close_trade(e,stamp=DETECT+70000)
        r=e.report(DETECT+70000,True).document()['trades'][0]
        self.assertIn('gap_in_trigger_path',r['ambiguity_flags']); self.assertFalse(r['ready'])

    def test_invalid_trade_source_or_unpinned_metadata_leaves_prefix_unchanged(self):
        e,i,events=prepared(); open_trade(e,events); cp=e.checkpoint()
        for event in (observation('trade',6,DETECT+5000),observation('trade',6,DETECT+5000)):
            event['data']['price']='NaN'
            with self.assertRaises(ValidationError): e.advance(event)
        self.assertEqual(e.checkpoint(),cp)
        event=observation('trade',6,DETECT+5000); event['metadata_version']='not-known'
        with self.assertRaises(ValidationError): e.advance(event)
        self.assertEqual(e.checkpoint(),cp)

    def test_tiny_partial_quantity_is_not_silently_rounded_up(self):
        e,i,events=prepared(quantity='0.05',partial_target_r='1',partial_fraction='0.001')
        open_trade(e,events); close_trade(e,'103.5')
        s=e.states[i.trade_id]; self.assertEqual(s['remaining_quantity'],'0.05')
        self.assertIn('partial_quantity_unexecutable',s['ambiguity_flags']); self.assertEqual(len(s['quantity_changes']),1)

    def test_corrupt_quantity_ledger_and_feature_checkpoint_are_rejected(self):
        e,i,events=prepared(); open_trade(e,events)
        for mutate in ('quantity','ledger','feature'):
            cp=json.loads(json.dumps(e.checkpoint()))
            if mutate=='quantity': cp['states'][i.trade_id]['remaining_quantity']='0'
            elif mutate=='ledger': next(iter(cp['states'][i.trade_id]['ledger'].values()))['amount_usdt']='0'
            else: cp['latest_features'][0]['values']['log_return_1']['value']=123
            with self.assertRaises(ValidationError): LifecycleEngine.restore(e.dataset,e.intents,e.book.snapshots,e.book.versions,e.fees,e.execution,e.funding_config,e.calendars,cp)

    def test_empty_prefix_tail_does_not_emit_an_entry_or_crash(self):
        e,i,_=prepared(); _,r=e.finish()
        s=r.document()['trades'][0]; self.assertEqual(s['status'],'waiting'); self.assertIsNone(s['net_usdt']); self.assertIn('unresolved_data_tail',s['ambiguity_flags'])

    def test_missed_settlement_and_post_entry_boundary_are_not_zero_funding(self):
        at=DETECT+30000
        e,i,events=prepared(calendars=[calendar([at])]); open_trade(e,events); close_trade(e,stamp=DETECT+60000)
        r=e.report(DETECT+60000,True).document()['trades'][0]
        self.assertIsNone(r['net_usdt']); self.assertEqual(r['funding']['cashflows'][0]['status'],'missing_settlement')
        # Settlement just before the entry still needs the strict timing guard.
        at=DETECT-1000
        e,i,events=prepared(calendars=[calendar([at])]); open_trade(e,events)
        e.advance(observation('funding',6,at,available=DETECT+2000)); close_trade(e,stamp=DETECT+30000,eid=7)
        r=e.report(DETECT+30000,True).document()['trades'][0]
        self.assertIsNone(r['net_usdt']); self.assertEqual(r['funding']['cashflows'][0]['status'],'boundary_ambiguous')

    def test_mature_outcome_recognition_time_is_stable_until_ledger_revision(self):
        e,i,events=prepared(calendars=[calendar()]); open_trade(e,events); close_trade(e)
        first=e.report(DETECT+30000,True).document()['trades'][0]
        later=e.report(DETECT+40000,True).document()['trades'][0]
        self.assertEqual(first['outcome_revision_hash'],later['outcome_revision_hash'])
        self.assertEqual(later['outcome_known_ms'],DETECT+30000)

    def test_distinct_same_millisecond_trades_follow_aggregate_id_order(self):
        e,i,events=prepared(); s=open_trade(e,events)
        e.advance(observation('trade',6,DETECT+5000,'103'))
        e.advance(observation('trade',7,DETECT+5000,'99'))
        self.assertEqual(s['status'],'exit_pending'); self.assertEqual(s['target_before_stop'],False)
        self.assertNotIn('late_or_revised_trigger_path',s['ambiguity_flags'])
        e.advance(observation('mark',8,DETECT+5001,'99')); e.advance(observation('quote',9,DETECT+5001,'99'))
        self.assertEqual(s['status'],'closed')
