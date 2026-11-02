"""Independent published geometry, exact boundaries, causal state and cost oracles."""
from collections import deque
from copy import deepcopy
from decimal import Decimal as D
from types import SimpleNamespace
import math
import unittest

from tradee.c01 import ValidationError
from tradee.c03.evaluator import Evaluator
from tradee.pilots.contracts import BAR,HOUR,DAY,FAMILIES,PilotConfig,candle,dec,jsonable
from tradee.pilots.context import Context
from tradee.pilots.engine import PilotEngine
from tradee.pilots.execution import costs,qualify
from tradee.pilots.indicators import Measurements,pivot

T=2*DAY+HOUR


def row(o='100.6',h='101',l='99.6',c='100.95',t=T):
    return candle(dict(open_ms=t,open=o,high=h,low=l,close=c,quote_volume='120',available_ms=t+BAR))


def values(**kw):
    return dict(dict(stable=True,atr=D('1'),ema200=D('90'),ema20=D('105'),ema50=D('100'),
        rv=D('1.2'),tr=D('1.4'),slope=D('.02'),crosses=0,dull=False,shock=False,calm=True),**kw)


def level(side='low'):
    return dict(id='test-level',kind='previous_day',side=side,price=D('100'),atr=D('1'),z=D('.1'),
        anchor_ms=T-DAY,confirmed_ms=T-5*BAR,known_ms=T-4*BAR,expires_ms=T+DAY,
        prior_touches=0,touches=0,prior_accepted_up=False,prior_accepted_down=False,
        accepted_up=False,accepted_down=False,up=0,down=0,episode=False,outside=0)


def engine(state='TREND_UP'):
    e=PilotEngine('BTCUSDT','.01'); c=e.context
    c.state=state; c.values.append(values()); c.hour.values.append(dict(stable=True))
    c.hour_rows.append(dict(open_ms=T-HOUR,available_ms=T,close=D('106')))
    c.box=dict(low=D('100'),high=D('112'),atr=D('1.5'),mid=D('106'),hour_end_ms=T)
    return e


def set_hour(e,r):
    expected=(r['open_ms']+BAR)//HOUR*HOUR
    e.context.hour_rows[-1].update(open_ms=expected-HOUR,available_ms=expected)


class PublishedGeometry(unittest.TestCase):
    def test_range_sweep_exact_published_long_and_short(self):
        for side in ('long','short'):
            e=engine('HEALTHY_RANGE'); l=level('low' if side=='long' else 'high')
            r=row() if side=='long' else row('99.4','100.4','99','99.05')
            if side=='short': e.context.box.update(low=D('88'),high=D('100'),mid=D('94')); e.context.hour_rows[-1]['close']=D('94')
            e.context.rows=deque([row('101','102','100.5','101',T-i*BAR) if side=='long' else row('99','99.5','98','99',T-i*BAR) for i in (3,2,1)]+[r],maxlen=720)
            e.context.levels=[l]
            seeds=e.sweep_seeds(r,values(),values()); self.assertEqual(len(seeds),1)
            p=seeds[0]; p.update(seed_high=r['high'],seed_low=r['low'])
            self.assertEqual(e.progress(p,r,values())[0],'confirm')
            plan,reason=e.plan(p,r); self.assertIsNone(reason)
            self.assertEqual(D(plan['stop']),D('99.45' if side=='long' else '100.55'))
            self.assertEqual(D(plan['target']),D('104.70' if side=='long' else '95.30'))

    def test_ema_exact_published_geometry(self):
        for side in ('long','short'):
            e=engine('TREND_UP' if side=='long' else 'TREND_DOWN')
            r=row('100.5','101','99.85','100.9') if side=='long' else row('99.5','100.15','99','99.1')
            prior=values(ema200=D('100')); current=values(ema200=D('100.02') if side=='long' else D('99.98'),slope=D('.02') if side=='long' else D('-.02'))
            e.context.rows=deque([row('101','101.5','100.5','101',T-i*BAR) if side=='long' else row('99','99.5','98.5','99',T-i*BAR) for i in range(9,0,-1)]+[r],maxlen=720)
            e.context.values=deque([deepcopy(prior) for _ in range(9)]+[current],maxlen=720)
            seeds=e.ema_seeds(r,current,prior); self.assertEqual(len(seeds),1)
            p=seeds[0]; p.update(seed_high=r['high'],seed_low=r['low'])
            self.assertEqual(e.progress(p,r,current)[0],'confirm')
            plan,reason=e.plan(p,r); self.assertIsNone(reason)
            self.assertEqual(D(plan['stop']),D('99.70' if side=='long' else '100.30'))
            self.assertEqual(D(plan['target']),D('103.90' if side=='long' else '96.10'))

    def test_retest_three_distinct_stages_and_short_mirror(self):
        for side in ('long','short'):
            e=engine('TREND_UP' if side=='long' else 'TREND_DOWN'); l=level('high' if side=='long' else 'low')
            b0=row('99.7','101','99.6','100.8') if side=='long' else row('100.3','100.4','99','99.2')
            b1=row('100.8','101.3','100.3','101',T+BAR) if side=='long' else row('99.2','99.7','98.7','99',T+BAR)
            r=row('100.7','101.1','99.9','100.95',T+2*BAR) if side=='long' else row('99.3','100.1','98.9','99.05',T+2*BAR)
            v=values(ema200=D('90') if side=='long' else D('110'),rv=D('1.3'))
            e.context.rows=deque([row('99','99.5','98','99',T-i*BAR) if side=='long' else row('101','102','100.5','101',T-i*BAR) for i in (3,2,1)]+[b0],maxlen=720)
            e.context.levels=[l]; p=e.retest_seeds(b0,v,values())[0]
            self.assertEqual(e.progress(p,b0,v)[0],'wait')
            set_hour(e,b1); self.assertEqual(e.progress(p,b1,v)[0],'wait')
            set_hour(e,r); self.assertEqual(e.progress(p,r,v)[0],'confirm')
            plan,reason=e.plan(p,r); self.assertIsNone(reason)
            self.assertEqual(D(plan['stop']),D('99.75' if side=='long' else '100.25'))
            self.assertEqual(D(plan['target']),D('103.95' if side=='long' else '96.05'))

    def test_second_candle_confirmation_cannot_extend_to_third(self):
        e=engine(); r=row('100.6','101','99.6','100.4'); p=e.base(FAMILIES[0],'sweep_trend','long',r,D('1'),level())
        p.update(seed_high=r['high'],seed_low=r['low'])
        self.assertEqual(e.progress(p,r,values())[0],'wait')
        second=row('100.4','101','100','100.5',T+BAR); set_hour(e,second)
        self.assertEqual(e.progress(p,second,values())[0],'reject')

    def test_wrong_side_ema_and_deep_sweep_fail(self):
        e=engine(); r=row('100.5','101','99.85','100.9'); p=e.base(FAMILIES[1],'ema_trend','long',r,D('1'))
        p.update(ema=D('100'),band=D('.15'),seed_high=r['high'],seed_low=r['low'])
        bad=row('100','100.2','99.8','99.9'); self.assertEqual(e.progress(p,bad,values(ema200=D('100'))),('reject','ema_failed'))
        p=e.base(FAMILIES[0],'sweep_trend','long',r,D('1'),level()); p.update(seed_high=r['high'],seed_low=r['low'])
        self.assertEqual(e.progress(p,row('100.6','101','99.24','100.95'),values()),('reject','deep_sweep'))

    def test_retest_early_late_and_extension(self):
        for scenario in ('early','late','extended'):
            e=engine(); r=row('99.7','101','99.6','100.8'); p=e.base(FAMILIES[2],'retest_trend','long',r,D('1'),level('high')); p['stage']='acceptance'
            e.progress(p,r,values())
            if scenario=='early':
                b=row('100.8','101.3','100.1','101',T+BAR); set_hour(e,b)
                self.assertEqual(e.progress(p,b,values()),('reject','early_retest'))
            else:
                b=row('100.8','101.3','100.3','101',T+BAR); set_hour(e,b); e.progress(p,b,values())
                b=row('101','103','100.4','102.01',T+2*BAR) if scenario=='extended' else row('100.7','101.1','99.9','100.95',T+7*BAR)
                set_hour(e,b); self.assertEqual(e.progress(p,b,values())[1],'extended_before_retest' if scenario=='extended' else 'late_retest')


class CausalContext(unittest.TestCase):
    def test_known_time_exhaustion_displacement_and_consumption(self):
        e=engine(); l=level(); r=row()
        self.assertTrue(e.eligible(l,'long',FAMILIES[0],r,D('1')))
        for update in ({'known_ms':T-3*BAR+1},{'prior_touches':3},{'prior_accepted_down':True}):
            changed=dict(l,**update); self.assertFalse(e.eligible(changed,'long',FAMILIES[0],r,D('1')))
        e.consume([l],'long',r,FAMILIES[0]); self.assertFalse(e.eligible(l,'long',FAMILIES[0],r,D('1')))

    def test_pending_ema_and_level_attempt_can_coexist_without_a_fake_level(self):
        e=engine(); r=row(); e.pending=[e.base(FAMILIES[1],'ema_trend','long',r,D('1'))]
        self.assertIsNone(e.pending[0]['level'])
        self.assertTrue(e.eligible(level(),'long',FAMILIES[0],r,D('1')))
        e.pending.append(e.base(FAMILIES[0],'sweep_trend','long',r,D('1'),level()))
        self.assertFalse(e.eligible(level(),'long',FAMILIES[0],r,D('1')))

    def test_immutable_birth_scale_and_two_outside_episode_reset(self):
        c=Context('BTCUSDT','.01',PilotConfig()); l=level(); c.levels=[l]
        for i,lo in enumerate(('99.9','100.5','99.9')): c.update_behavior(row('100.6','101',lo,'100.8',T+i*BAR))
        self.assertEqual(l['touches'],1)
        for i,lo in enumerate(('100.5','100.5','99.9')): c.update_behavior(row('100.6','101',lo,'100.8',T+(3+i)*BAR))
        self.assertEqual(l['touches'],2)
        for i in (6,7): c.update_behavior(row('99.5','99.8','99','99.7',T+i*BAR))
        self.assertTrue(l['accepted_down']); c.update_behavior(row(t=T+8*BAR)); self.assertTrue(l['accepted_down'])

    def test_strict_pivot_requires_right_bars_and_excludes_ties(self):
        rows=[row('100',h,'99','100',T+i*BAR) for i,h in enumerate(('101','102','103','102','101'))]
        self.assertEqual(pivot(rows[:4]),[]); self.assertEqual(pivot(rows)[0]['anchor_ms'],T+2*BAR)
        rows[-1]['high']=D('103'); self.assertEqual(pivot(rows),[])

    def test_native_pivot_matches_c05_confirmation_and_receipt_oracle(self):
        from tradee.c05 import reference_levels,StructureConfig
        rows=[row('100',h,'99','100',T+i*BAR) for i,h in enumerate(('101','102','103','102','101'))]
        rows[-1]['available_ms']+=1000
        actual=pivot(rows)[0]
        expected=next(l for l in reference_levels([jsonable(r) for r in rows],BAR,as_of_ms=rows[-1]['available_ms'],
            config=StructureConfig(previous_week=False))['levels'] if l['kind']=='swing' and l['side']=='high')
        self.assertEqual(actual['price'],D(expected['price'])); self.assertEqual(actual['anchor_ms'],expected['anchor_ms'])
        self.assertEqual(actual['confirmed_ms']+BAR,expected['confirmed_ms']); self.assertEqual(actual['known_ms'],expected['known_ms'])

    def test_c03_incremental_sma_seed_and_slope_match_independent_batch(self):
        m=Measurements(); rows=[]
        for i in range(1590):
            c=100+math.sin(i/7)+i*.005
            r=row(str(c),str(c+.5),str(c-.5),str(c),i*BAR); rows.append(r); v=m.push(r)
            if i==1585: self.assertFalse(v['stable'])
            if i==1586: self.assertTrue(v['stable'])
        source=[jsonable(r) for r in rows]; oracle=Evaluator(source)
        self.assertAlmostEqual(float(v['ema200']),oracle.get('ema200').value,places=12)
        self.assertAlmostEqual(float(v['atr']),oracle.get('atr14').value,places=12)
        self.assertAlmostEqual(float(v['slope']),oracle.get('ema200_slope5_atr14').value,places=12)

    def test_regime_direction_and_range_routing(self):
        e=engine()
        self.assertTrue(e.allowed('long','ema_trend')); self.assertFalse(e.allowed('short','ema_trend'))
        e.context.state='HEALTHY_RANGE'
        self.assertFalse(e.allowed('long','ema_trend')); self.assertFalse(e.allowed('long','retest_trend')); self.assertTrue(e.allowed('long','sweep_range'))
        for state in ('TRANSITION','UNKNOWN'):
            e.context.state=state
            self.assertFalse(e.allowed('long','sweep_range')); self.assertFalse(e.allowed('long','ema_trend'))

    def test_gap_reset_duplicate_and_revision_policy(self):
        e=PilotEngine('BTCUSDT','.01'); r=row(); self.assertEqual(e.advance(jsonable(r)),[])
        count=e.context.exec.count; self.assertEqual(e.advance(jsonable(r)),[]); self.assertEqual(e.context.exec.count,count)
        revised=dict(jsonable(r),quote_volume='121')
        with self.assertRaises(ValidationError): e.advance(revised)
        e.advance(jsonable(row(t=T+2*BAR))); self.assertEqual(e.context.generation,1); self.assertEqual(e.context.exec.count,1)

    def test_warmup_cannot_emit_and_bad_inputs_fail(self):
        e=PilotEngine('BTCUSDT','.01')
        self.assertEqual(list(e.run([jsonable(row(t=T+i*BAR)) for i in range(50)])),[])
        for change in ({'close':'NaN'},{'open_ms':T+1},{'high':'98'},{'available_ms':T+BAR-1},dict.fromkeys(('open','high','low','close'),'1e-1000')):
            with self.assertRaises(ValidationError): candle(dict(jsonable(row()),**change))


class CostQualification(unittest.TestCase):
    def plan(self):
        return dict(symbol='BTCUSDT',side='long',mode='sweep_trend',strategy=FAMILIES[0],geometry_scale='1',
            price='100',stop='98',target='105',atr='1',tick_size='.01',reference_risk='2',trigger_level='99',b='.1',
            detected_ms=T+BAR,end_ms=T+BAR,expires_ms=T+BAR+180000,max_hold_ms=3*HOUR,level_expires_ms=T+DAY)

    def evidence(self,now):
        return dict(stream_state='connected',clock_offset_ms=0,
            quote=dict(symbol='BTCUSDT',bid='99.99',ask='100.01',event_ms=now,received_ms=now),
            mark=dict(symbol='BTCUSDT',next_funding_ms=now+8*HOUR,event_ms=now,received_ms=now),
            metadata=dict(symbol='BTCUSDT',observed_ms=now,status='TRADING',tick_size='.01',step_size='.001',min_quantity='.001',min_notional='5'),
            path=dict(symbol='BTCUSDT',source='recorded_contract_trades',continuous=True,start_ms=T+BAR,end_ms=now,low='99.9',high='100.1'),
            calendar=dict(sources=['bls_cpi','bls_employment','fomc'],refreshed_ms=now,coverage_start_ms=now-DAY,coverage_end_ms=now+DAY,blackouts=[]))

    def test_independent_published_cost_oracle_and_short_symmetry(self):
        plan=self.plan(); c=costs(plan,'99.99','100.01')
        self.assertEqual(c['entry'],D('100.030002')); self.assertEqual(c['stop_exit'],D('97.9554'))
        self.assertEqual(c['stopped_loss'],D('2.173594701')); self.assertEqual(c['target_gain'],D('4.821505999'))
        self.assertEqual(c['entry_risk'],D('2.030002')); self.assertEqual(c['reasons'],[])
        self.assertIn('net_rr_low',costs(dict(plan,target='102'),'99.99','100.01')['reasons'])

    def test_valid_evidence_and_each_missing_source(self):
        p=self.plan(); now=T+BAR+30000; e=engine(); evidence=self.evidence(now)
        self.assertTrue(qualify(p,evidence,now,context=e.context)['qualified'])
        for key,reason in [('quote','quote_stale'),('mark','mark_stale'),('metadata','metadata_stale'),('path','path_unknown'),('calendar','calendar_unknown')]:
            bad=deepcopy(evidence); bad.pop(key)
            self.assertIn(reason,qualify(p,bad,now,context=e.context)['reasons'])

    def test_exclusive_deadlines_drift_staleness_funding_event_and_path(self):
        p=self.plan(); now=T+BAR+30000; e=engine(); ev=self.evidence(now)
        self.assertIn('expired',qualify(p,ev,p['expires_ms'],context=e.context)['reasons'])
        self.assertIn('late_notification',qualify(p,ev,p['end_ms']+60000,context=e.context,purpose='notification')['reasons'])
        for change,reason in [({'quote':dict(ev['quote'],event_ms=now-2000)},'quote_stale'),
                              ({'quote':dict(ev['quote'],bid='100.20',ask='100.22')},'drift'),
                              ({'mark':dict(ev['mark'],next_funding_ms=now+3*HOUR+300000)},'funding_window'),
                              ({'path':dict(ev['path'],low='98')},'level_hit_before_entry'),
                              ({'calendar':dict(ev['calendar'],blackouts=[dict(start_ms=now+HOUR,end_ms=now+2*HOUR,known_ms=now)])},'event_window')]:
            self.assertIn(reason,qualify(p,dict(ev,**change),now,context=e.context)['reasons'])


if __name__=='__main__': unittest.main()
