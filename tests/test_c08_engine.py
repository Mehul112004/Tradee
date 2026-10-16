from copy import deepcopy
from dataclasses import replace
import json
import unittest
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c08 import CandidateEngine, CandidateConfig
from tradee.c08.contracts import TREND_FAMILY
from tests.c08_support import *


class CandidateEngineTests(unittest.TestCase):
    def outputs(self,events,**kw): return docs(engine(**kw).run(events))

    def test_complete_inventory_includes_warmup_nontriggers_long_and_short(self):
        a=engine(); out=docs(a.run([event(0),event(1),event(2,'102'),event(3,'98')]))
        self.assertEqual(len(out),8); self.assertEqual([r['candidate']['side'] for r in out if r['candidate']],['long','short'])
        self.assertIn('insufficient_range_history',out[0]['reasons']); self.assertEqual(out[5]['status'],'not_triggered')

    def test_reference_and_expiry_are_fixed_to_detection_and_bar_end(self):
        e=engine(); list(e.run([event(0),event(1)])); r=docs(e.advance(event(2,'102',available=START+3*MINUTE+1000)))[0]
        c=r['candidate']; self.assertEqual(c['reference_price'],'102'); self.assertEqual(c['detected_ms'],START+181000)
        self.assertEqual(c['expires_ms'],START+240000); self.assertEqual(c['context_end_ms'],START+120000)

    def test_default_15m_aggregation_waits_for_final_minute(self):
        a=engine(strategy=StrategySpec(),config=CandidateConfig(max_metadata_age_ms=86400000))
        allout=[]
        for i in range(21*15-1): allout.extend(a.advance(event(i,'102' if i>=300 else '100')))
        self.assertEqual(len(allout),40)
        out=docs(a.advance(event(314,'102'))); self.assertEqual(out[0]['status'],'emitted')
        self.assertEqual(out[0]['candidate']['breakout_level'],'101')

    def test_partial_candle_and_non_candle_do_not_trigger(self):
        a=engine(); self.assertEqual(a.advance(event(0,final=False)),[])
        final=event(0,eid=2,available=START+MINUTE+1); self.assertEqual(len(a.advance(final)),2)

    def test_identical_duplicate_is_idempotent_and_conflicting_or_reverse_rejected(self):
        a=engine(); a.advance(event(0)); before=a.checkpoint(); self.assertEqual(a.advance(event(0)),[])
        self.assertEqual(a.checkpoint(),before)
        with self.assertRaises(ValidationError): a.advance(event(0,'101'))

    def test_late_old_correction_is_diagnostic_only_and_old_candidate_frozen(self):
        a=engine(); old=docs(a.run([event(0),event(1),event(2,'102')]))[-2]
        serialized=json.dumps(old,sort_keys=True)
        revision=docs(a.advance(event(1,high='110',eid=4,available=START+181000)))
        self.assertEqual({r['status'] for r in revision},{'revision_only'}); self.assertTrue(all(r['candidate'] is None for r in revision))
        self.assertEqual(json.dumps(old,sort_keys=True),serialized)
        later=docs(a.advance(event(3,'105'))); self.assertFalse(later[0]['triggered'])

    def test_correction_cannot_invent_a_candidate_at_an_old_bar(self):
        a=engine(); list(a.run([event(0),event(1),event(2)]))
        revised=docs(a.advance(event(2,'102',eid=4,available=START+181000)))
        self.assertTrue(revised[0]['triggered']); self.assertIsNone(revised[0]['candidate']); self.assertEqual(a.emitted_count,0)

    def test_cooldown_is_per_direction_only_emissions_consume_it(self):
        a=engine(strategy=spec(cooldown_bars=2))
        out=docs(a.run([event(0),event(1),event(2,'102'),event(3,'104'),event(4,'106')]))
        long=[r for r in out if r['side']=='long']
        self.assertEqual([r['status'] for r in long[-3:]],['emitted','rejected','emitted'])
        self.assertIn('cooldown_active',long[-2]['reasons'])

    def test_gap_suppresses_then_window_recovers(self):
        out=self.outputs([event(i,'102' if i>=4 else '100') for i in (0,1,3,4,5)])
        self.assertIn('gap_in_range_window',out[4]['reasons']); self.assertIn('gap_in_range_window',out[6]['reasons'])
        self.assertNotIn('gap_in_range_window',out[8]['reasons'])

    def test_stale_and_expired_detection_never_emits(self):
        for late in (60000,120000):
            out=self.outputs([event(0),event(1),event(2,'102',available=START+180000+late)])[-2]
            self.assertTrue(out['triggered']); self.assertIsNone(out['candidate']); self.assertIn('stale_detection',out['reasons']); self.assertIn('candidate_window_expired',out['reasons'])

    def test_current_metadata_cannot_become_historical_observed_evidence(self):
        _,u,v=metadata(); u.pop('snapshot_hash'); u['as_of_ms']=START+500000; u['decisions'][0]['last_observed_ms']=START+500000; u['snapshot_hash']=fingerprint(u)
        out=self.outputs([event(0),event(1),event(2,'102')],snapshots=[u])[-2]
        self.assertIn('metadata_not_available',out['reasons']); self.assertIsNone(out['candidate'])
        out=self.outputs([event(0),event(1),event(2,'102')],snapshots=[u],config=CandidateConfig(metadata_mode='research_assumption'))[-2]
        self.assertEqual(out['status'],'emitted'); self.assertEqual(out['candidate']['metadata_mode'],'research_assumption')

    def test_metadata_refresh_status_and_missing_membership_are_time_ordered(self):
        _,u,v=metadata(); newer=deepcopy(u); newer.pop('snapshot_hash'); newer['as_of_ms']=START+181000
        newer['decisions'][0].update(state='ineligible',reasons=['not_trading'],last_observed_ms=START+181000); newer['snapshot_hash']=fingerprint(newer)
        out=self.outputs([event(0),event(1),event(2,'102'),event(3,'104')],snapshots=[u,newer])
        self.assertEqual(out[4]['status'],'emitted'); self.assertIn('metadata_ineligible',out[6]['reasons'])

    def test_symbol_allowlist_identity_and_metadata_freshness_are_checked(self):
        out=self.outputs([event(0),event(1),event(2,'102')],config=CandidateConfig(enabled_symbols=['ETHUSDT']))[-2]
        self.assertIn('symbol_not_enabled',out['reasons'])
        out=self.outputs([event(0),event(1),event(2,'102')],config=CandidateConfig(max_metadata_age_ms=180000))[-2]
        self.assertIn('metadata_stale',out['reasons'])

    def test_strategy_side_filter_declares_inventory_scope(self):
        out=self.outputs([event(0),event(1),event(2,'102')],strategy=spec(sides=['long']))
        self.assertEqual(len(out),3); self.assertEqual({r['side'] for r in out},{'long'})

    def test_modeled_data_is_labeled_and_requires_explicit_metadata_assumption_when_needed(self):
        out=self.outputs([event(0,mode='modeled'),event(1,mode='modeled'),event(2,'102',mode='modeled')],ds=dataset(mode='modeled'),config=CandidateConfig(metadata_mode='research_assumption'))
        self.assertEqual(out[-2]['candidate']['availability_basis'],'modeled')
        with self.assertRaises(ValidationError): engine(ds=dataset(mode='modeled')).advance(event(0))

    def test_input_beyond_horizon_and_bad_provenance_leave_state_unchanged(self):
        a=engine(); bad=event(0); bad['raw_sha256']='bad'
        with self.assertRaises(ValidationError): a.advance(bad)
        self.assertIsNone(a.cursor)
        with self.assertRaises(ValidationError): engine(ds=dataset(bars=2)).advance(event(2))

    def test_lookahead_suffix_does_not_change_prior_serialized_outputs(self):
        prefix=[event(0),event(1),event(2,'102')]; a=engine(); first=list(a.run(prefix)); frozen=[r.serialized for r in first]
        list(a.run([event(3,'104'),event(4,'98')]))
        self.assertEqual([r.serialized for r in first],frozen); self.assertEqual([r.serialized for r in engine().run(prefix)],frozen)

    def test_checkpoint_resume_every_split_including_correction(self):
        inputs=[event(0),event(1),event(2,'102'),event(0,high='110',eid=4,available=START+181000),event(3,'105')]
        full=engine(); want=[r.serialized for r in full.run(inputs)]
        for split in range(len(inputs)+1):
            a=engine(); got=[r.serialized for r in a.run(inputs[:split])]
            b=CandidateEngine.restore(a.dataset,a.strategy,a.book.snapshots,a.book.versions,a.config,json.loads(json.dumps(a.checkpoint())))
            got += [r.serialized for r in b.run(inputs[split:])]; self.assertEqual(got,want)

    def test_corrupt_metadata_and_checkpoint_fail_closed(self):
        _,u,v=metadata(); u['as_of_ms']+=1
        with self.assertRaises(ValidationError): engine(snapshots=[u])
        a=engine(); cp=a.checkpoint(); cp['run_hash']='wrong'
        with self.assertRaises(ValidationError): CandidateEngine.restore(a.dataset,a.strategy,a.book.snapshots,a.book.versions,a.config,cp)

    def test_trend_long_and_short_use_real_stabilized_c03_emas(self):
        for short in (False,True):
            a=engine(strategy=spec(TREND_FAMILY)); out=docs(a.run(trend_events(short)))
            candidates=[r['candidate'] for r in out if r['candidate']]
            self.assertEqual(len(candidates),1); self.assertEqual(candidates[0]['side'],'short' if short else 'long')
            self.assertEqual(candidates[0]['target_open_ms'],START+401*MINUTE)
            self.assertEqual(candidates[0]['reference_price'],'160' if short else '140')
            self.assertNotEqual(a.strategy.strategy_hash,spec().strategy_hash)

    def test_nominal_ema_validity_does_not_bypass_stability(self):
        out=self.outputs(trend_events()[:60],strategy=spec(TREND_FAMILY))
        self.assertTrue(all(r['candidate'] is None for r in out)); self.assertIn('unstable_feature:ema50',out[-1]['reasons'])

    def test_trend_checkpoint_has_same_recovery_and_cooldown(self):
        inputs=trend_events(); a=engine(strategy=spec(TREND_FAMILY)); list(a.run(inputs[:-1]))
        b=CandidateEngine.restore(a.dataset,a.strategy,a.book.snapshots,a.book.versions,a.config,json.loads(json.dumps(a.checkpoint())))
        self.assertEqual([r.serialized for r in a.advance(inputs[-1])],[r.serialized for r in b.advance(inputs[-1])])
