import json
import math
import unittest
from copy import deepcopy

from tradee.c01 import ValidationError
from tradee.c03 import FeatureConfig, FeatureEngine
from tests.c03_support import START, IDENTITY, event, dataset, quote


def engine(features=('log_return_1',), **kwargs):
    return FeatureEngine(dataset(), FeatureConfig(features=features,timeframes=('1m',),require_stable=False,**kwargs))


def value(snapshot, name='log_return_1'):
    return snapshot.document()['values'][name]


class EngineTests(unittest.TestCase):
    def test_batch_incremental_checkpoint_parity_every_split(self):
        events=[event(i) for i in range(26)]
        baseline=engine(('ema20','rsi14','log_return_1'))
        expected=[s.serialized for s in baseline.run(events)]
        for split in (0,1,14,19,20,25,26):
            with self.subTest(split=split):
                a=engine(('ema20','rsi14','log_return_1'))
                actual=[s.serialized for s in a.run(events[:split])]
                b=FeatureEngine.restore(a.dataset,a.config,json.loads(json.dumps(a.checkpoint())))
                actual.extend(s.serialized for s in b.run(events[split:]))
                self.assertEqual(actual,expected)
                self.assertEqual(b.prefix_hash,baseline.prefix_hash)

    def test_same_millisecond_correction_preserves_prior_snapshot(self):
        a=engine(); a.advance(event(0,100))
        first=a.advance(event(1,101))[0]; frozen=first.serialized
        correction=event(0,102,event_id=3,available=START+120000)
        second=a.advance(correction)[0]
        self.assertAlmostEqual(value(first)['value'],math.log(101/100))
        self.assertAlmostEqual(value(second)['value'],math.log(101/102))
        self.assertNotEqual(first.digest,second.digest)
        self.assertEqual(first.serialized,frozen)
        self.assertEqual(a.advance(correction),[])
        with self.assertRaises(ValidationError): a.push(event(0))
        with self.assertRaises(ValidationError): a.evaluate(IDENTITY,'1m',START+119999)

    def test_gap_resets_recursive_state_and_late_repair_rejoins(self):
        a=engine(('ema20',)); events=[event(i) for i in range(23) if i!=10]
        outputs=list(a.run(events))
        self.assertEqual(value(outputs[-1],'ema20')['status'],'gap_in_window')
        fixed=a.advance(event(10,event_id=24,available=START+23*60000))[0]
        clean=engine(('ema20',)); reference=list(clean.run([event(i) for i in range(23)]))[-1]
        self.assertEqual(value(fixed,'ema20'),value(reference,'ema20'))
        self.assertEqual(value(outputs[-1],'ema20')['status'],'gap_in_window')

    def test_partial_and_cross_instrument_do_not_supply_history(self):
        a=engine(); self.assertEqual(a.advance(event(0,final=False)),[])
        self.assertEqual(value(a.advance(event(1))[0])['status'],'gap_in_window')
        other=a.advance(event(2,symbol='ETHUSDT'))[0]
        self.assertEqual(value(other)['status'],'gap_in_window')

    def test_full_utc_bucket_only_and_no_future_timeframe(self):
        a=FeatureEngine(dataset(),FeatureConfig(features=('mean_trade_quote_notional',),timeframes=('15m','1h'),require_stable=False))
        for i in range(14): self.assertEqual(a.advance(event(i)),[])
        out=a.advance(event(14)); self.assertEqual([s.document()['timeframe'] for s in out],['15m'])
        self.assertEqual(out[0].document()['target_end_ms'],START+900000)
        self.assertEqual(value(out[0],'mean_trade_quote_notional')['value'],200)
        hourly=a.evaluate(IDENTITY,'1h',START+900000)
        self.assertEqual(value(hourly,'mean_trade_quote_notional')['status'],'missing_source')

    def test_staleness_boundary_and_timer_blocks_older_input(self):
        a=engine(); list(a.run([event(0),event(1)]))
        end=START+120000
        self.assertEqual(value(a.evaluate(IDENTITY,'1m',end+64999))['status'],'valid')
        self.assertEqual(value(a.evaluate(IDENTITY,'1m',end+65000))['status'],'stale_input')
        with self.assertRaises(ValidationError): a.push(event(2))

    def test_optional_quote_and_freshness(self):
        a=engine(('log_return_1','spread_bps','quote_event_age_ms'),required_features=('log_return_1',))
        list(a.run([event(0),event(1)]))
        end=START+120000
        self.assertTrue(a.evaluate(IDENTITY,'1m',end).document()['ready'])
        a.push(quote(3,end))
        self.assertEqual(value(a.evaluate(IDENTITY,'1m',end),'spread_bps')['value'],200)
        stale=a.evaluate(IDENTITY,'1m',end+5000)
        self.assertEqual(value(stale,'spread_bps')['status'],'stale_input')
        self.assertEqual(value(stale,'quote_event_age_ms')['value'],5000)

    def test_delayed_older_quote_does_not_replace_newer_event_time(self):
        a=engine(('mid_price',)); a.push(quote(1,START+100,bid='109',ask='111'))
        a.push(quote(2,START,available=START+200))
        self.assertEqual(value(a.evaluate(IDENTITY,'1m',START+200),'mid_price')['value'],110)

    def test_session_anchor_required_and_midnight_reset(self):
        a=engine(('vwap_utc_session',)); first=a.advance(event(0))[0]
        self.assertEqual(value(first,'vwap_utc_session')['value'],100)
        b=engine(('vwap_utc_session',)); late=b.advance(event(1))[0]
        self.assertEqual(value(late,'vwap_utc_session')['status'],'anchor_incomplete')
        reset=b.advance(event(1440))[0]
        self.assertEqual(value(reset,'vwap_utc_session')['value'],100)

    def test_output_start_does_not_reset_warmup(self):
        a=engine(('ema20',),output_start_ms=START+20*60000,output_end_ms=START+22*60000)
        outputs=list(a.run([event(i) for i in range(24)]))
        self.assertEqual(len(outputs),2)
        self.assertEqual(value(outputs[0],'ema20')['observed_bars'],21)

    def test_mode_and_checkpoint_mismatch_rejected(self):
        a=engine(); bad=event(0); bad['availability_basis']='modeled'
        with self.assertRaises(ValidationError): a.push(bad)
        cp=a.checkpoint(); cp['run_hash']='wrong'
        with self.assertRaises(ValidationError): FeatureEngine.restore(a.dataset,a.config,cp)

    def test_zero_denominators_and_flat_rsi(self):
        a=engine(('rsi14','close_z20_prior','bb20_pct_b'))
        out=list(a.run([event(i,100) for i in range(21)]))[-1]
        self.assertEqual(value(out,'rsi14')['value'],50)
        for name in ('close_z20_prior','bb20_pct_b'):
            self.assertEqual(value(out,name)['status'],'zero_denominator')

    def test_prefix_outputs_unchanged_by_future_data(self):
        a=engine(); short=[s.serialized for s in a.run([event(i) for i in range(10)])]
        b=engine(); longer=[s.serialized for s in b.run([event(i) for i in range(20)])]
        self.assertEqual(short,longer[:10])

    def test_checkpoint_after_repair_and_partial_tail(self):
        a=engine(('ema20',)); events=[event(i) for i in range(26) if i!=10]
        events += [event(10,102,event_id=27,available=START+26*60000),
                   event(26,event_id=28,final=False)]
        list(a.run(events))
        b=FeatureEngine.restore(a.dataset,a.config,json.loads(json.dumps(a.checkpoint())))
        final=event(26,event_id=29)
        self.assertEqual([s.serialized for s in a.advance(final)],[s.serialized for s in b.advance(final)])

    def test_checkpoint_invalid_state_is_rejected(self):
        a=engine(); a.advance(event(0)); original=a.checkpoint()
        for field,invalid in (('cursor',None),('cursor',[START,0]),('event_count',-1),
                              ('prefix_hash','bad'),('last_event_hash','f'*64),('latest',None)):
            cp=deepcopy(original); cp[field]=invalid
            with self.subTest(field=field),self.assertRaises(ValidationError):
                FeatureEngine.restore(a.dataset,a.config,cp)

    def test_calendar_leap_day_session_rollover(self):
        from datetime import datetime,timezone
        start=int(datetime(2024,2,29,23,59,tzinfo=timezone.utc).timestamp()*1000)
        a=FeatureEngine(dataset(start=start,end=start+120000),FeatureConfig(features=('vwap_utc_session',),timeframes=('1m',)))
        old=a.advance(event(0,start=start))[0]
        new=a.advance(event(1,start=start))[0]
        self.assertEqual(value(old,'vwap_utc_session')['status'],'anchor_incomplete')
        self.assertEqual(value(new,'vwap_utc_session')['value'],100)

    def test_early_correction_rebuilds_all_ema_updates(self):
        events=[event(i) for i in range(220)]
        a=engine(('ema20','rsi14')); list(a.run(events))
        out=a.advance(event(0,103,event_id=221,available=START+220*60000))[0]
        clean=engine(('ema20','rsi14')); fixed=[event(0,103)]+events[1:]
        reference=list(clean.run(fixed))[-1]
        self.assertEqual(out.document()['values'],reference.document()['values'])
        self.assertEqual(out.document()['trigger'],'revision')
        self.assertEqual(out.document()['target_open_ms'],START+219*60000)

    def test_quote_state_is_bounded_and_survives_restart(self):
        a=engine(('mid_price',))
        for i in range(100): a.push(quote(i+1,START+i))
        self.assertEqual(len(a.latest),1)
        b=FeatureEngine.restore(a.dataset,a.config,a.checkpoint())
        self.assertEqual(a.evaluate(IDENTITY,'1m',START+100).serialized,
                         b.evaluate(IDENTITY,'1m',START+100).serialized)
