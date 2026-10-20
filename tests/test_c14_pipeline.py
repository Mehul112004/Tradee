from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c03.contracts import FrozenRecord
from tradee.c14 import SignalRuntime,SignalStore
from tests.c14_integration_support import isolated,trim_future
from scripts.verify_c14 import LIVE


class ProspectivePipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.feed,self.s,self.r=isolated(self.tmp.name)
    def tick(self,at=LIVE+181000): self.feed.clock[0]=at; return self.r.tick('paper_demo',at)
    def pending(self): return next(x['signal'] for x in self.s.signals('paper_demo') if x['delivery'] and x['delivery']['state']=='pending')
    def test_raw_prefix_first_paper_entry_matches_independent_funded_engine(self):
        h=self.tick(); c=h['cycle']; report=self.r.portfolios.report(c['portfolio']['report_hash'])
        self.assertEqual(c['paper_account'],report['terminal_account']); self.assertEqual(c['paper_account']['cash_usdt'],'319.9489')
        self.assertEqual([x['phase'] for x in c['signals']].count('paper_open'),1)
        self.assertEqual(c['source_prefix_hash'],report['input_prefix_hash']); self.assertFalse(c['live_approved'])
    def test_tick_reopen_and_retry_do_not_duplicate_notices(self):
        a=self.tick(); self.assertEqual(self.tick(),a)
        other=SignalRuntime(SignalStore(self.s.path),self.feed.market,self.r.simulations,self.r.portfolios)
        self.assertEqual(other.tick('paper_demo',LIVE+181000),a); self.assertEqual(len([x for x in self.s.signals('paper_demo') if x['delivery']]),1)
    def test_pre_send_rebuilds_current_feature_vintage_without_rebinding_candidate(self):
        h=self.tick(); signal=self.pending(); old=fingerprint(signal['request']); self.feed.clock[0]+=1000
        g=self.r.preflight(h,signal,self.feed.clock[0]); self.assertTrue(g['ready'],g['reasons']); self.assertEqual(fingerprint(signal['request']),old)
        self.assertEqual(g['execution']['evaluation_as_of_ms'],self.feed.clock[0])
    def test_backdated_new_source_under_closed_watermark_is_rejected(self):
        trim_future(self.feed,LIVE+181000); self.tick(); self.feed.price(LIVE+181000,'102.1')
        with self.assertRaisesRegex(ValidationError,'watermark'): self.tick(LIVE+181001)
    def test_backward_cutoff_and_hot_code_reload_fail_before_publishing(self):
        self.tick()
        with self.assertRaisesRegex(ValidationError,'backward'): self.tick(LIVE+180999)
        with patch('tradee.c14.pipeline.code_hash',return_value='0'*64):
            with self.assertRaisesRegex(ValidationError,'code/runtime'): self.tick(LIVE+181001)
    def test_stale_marks_or_cycle_expiry_block_send(self):
        h=self.tick(); signal=self.pending()
        for offset in (5000,10000):
            self.feed.clock[0]=LIVE+181000+offset; g=self.r.preflight(h,signal,self.feed.clock[0]); self.assertFalse(g['ready'])
    def test_new_trades_require_a_fresh_paper_book_before_send(self):
        trim_future(self.feed,LIVE+181000); h=self.tick(); signal=self.pending(); self.feed.price(LIVE+182000,'105',True)
        g=self.r.preflight(h,signal,self.feed.clock[0]); self.assertFalse(g['ready']); self.assertTrue(g['deferred']); self.assertIn('position_or_thesis_prefix_requires_tick',g['reasons'])
    def test_new_quote_with_changed_economics_suppresses_notice(self):
        import json
        trim_future(self.feed,LIVE+181000); h=self.tick(); signal=self.pending(); self.feed.clock[0]=LIVE+182000
        symbol=signal['candidate']['symbol']; stamp=self.feed.clock[0]
        self.feed.market.ingest_ws(json.dumps(dict(e='bookTicker',E=stamp,T=stamp,s=symbol,u=stamp,b='102',a='102.2',B='10',A='10')))
        g=self.r.preflight(h,signal,stamp); self.assertFalse(g['ready']); self.assertIn('tested_entry_economics_changed',g['reasons'])
    def test_closed_paper_entry_cannot_be_sent_after_catch_up(self):
        h=self.tick(LIVE+240000); self.assertEqual(len(h['cycle']['paper_account']['positions']),0)
        for x in self.s.signals('paper_demo'):
            if x['delivery']: self.assertEqual(x['delivery']['state'],'suppressed')
    def test_absent_calendar_gives_unknown_funding_and_no_notice(self):
        m=self.s.session('paper_demo')['manifest']; m['calendars']=[]; m['spec']['name']='unknown'
        self.s.create(FrozenRecord.create(m)); h=self.r.tick('unknown',LIVE+181000)
        self.assertEqual(h['cycle']['paper_account']['cash_usdt'],'320'); self.assertFalse(any(x['delivery'] for x in self.s.signals('unknown')))
    def test_read_budget_fails_instead_of_truncating_paper_history(self):
        m=self.s.session('paper_demo')['manifest']; m['spec']['runtime']['max_events']=1; m['spec']['name']='bounded'; self.s.create(FrozenRecord.create(m))
        with self.assertRaisesRegex(ValidationError,'event budget'): self.r.tick('bounded',LIVE+181000)
    def test_live_window_and_tail_are_enforced(self):
        for stamp in (LIVE-1,LIVE+3*240000+180001):
            with self.assertRaisesRegex(ValidationError,'session/tail'): self.tick(stamp)

    def test_benign_high_rate_trades_do_not_starve_delivery_checks(self):
        trim_future(self.feed,LIVE+181000); h=self.tick(); signal=self.pending()
        for ms in (181100,181200,181300): self.feed.price(LIVE+ms,'102',True)
        g=self.r.preflight(h,signal,self.feed.clock[0]); self.assertTrue(g['ready'],g['reasons'])
    def test_mark_trigger_crossing_cannot_be_treated_as_a_benign_quote_refresh(self):
        from tradee.c14.pipeline import position_prefix_requires_tick
        h=self.tick(); c=deepcopy(h['cycle']); signal=next(s for s in c['signals'] if s['phase']=='paper_open')
        signal['trade_intent']['policy']['trigger_source']='mark'
        event=next(e for e in self.feed.market.replay(c['dataset']['dataset_hash']) if e['kind']=='mark' and e['instrument_id']==signal['candidate']['instrument_id'])
        event=deepcopy(event); event['data']['mark_price']='105'; event['event_ms']=event['available_ms']=LIVE+182000
        self.assertTrue(position_prefix_requires_tick([event],c,LIVE+182000))

    def test_changed_mark_path_requires_full_peak_and_drawdown_replay(self):
        trim_future(self.feed,LIVE+181000); h=self.tick(); signal=self.pending()
        self.feed.price(LIVE+182000,'103'); self.feed.price(LIVE+182100,'102')
        g=self.r.preflight(h,signal,self.feed.clock[0]); self.assertFalse(g['ready']); self.assertTrue(g['deferred'])
