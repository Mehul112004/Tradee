from copy import deepcopy
from decimal import Decimal as D
import calendar
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tradee.pilots.calendar import CalendarCache,blackout,parse_bls,parse_fed,reconstructed,timestamp
from tradee.pilots.contracts import BAR,HOUR,DAY,dec
from tradee.pilots.research import choose_training,metrics,model_trade,ms,walk_forward
from tradee.pilots.comparisons import observation_controls

T=2*DAY+HOUR


class Book:
    def __init__(self,rows): self.rows=rows
    def window(self,symbol,start,end): return iter(self.rows)


def plan():
    return dict(symbol='BTCUSDT',side='long',mode='sweep_trend',strategy='liquidity_sweep_v1',price='100',
        stop='98',target='105',atr='1',reference_risk='2',entry_level_buffer='.1',trigger_level='99',b='.1',
        tick_size='.01',geometry_scale='1',end_ms=T,detected_ms=T,expires_ms=T+180000,max_hold_ms=3*HOUR,
        opportunity_id='fixture')


def states():
    return [dict(end_ms=T+i*BAR,state='TREND_UP',dull=False,dull_twice=False,shock=False,close='100',ema200='90',box=None,hour_close='106') for i in range(13)]


EXEC=dict(entry_delay_seconds=30,fee_each_side='.0005',slippage_bps_each_side='2',entry_spread_bps='1',exit_spread_bps='5')
FUND=[(T-12*HOUR,D('.0001')),(T-4*HOUR,D('.0001'))]


def minute(t,o,h,l,c): return (t,*map(D,(o,h,l,c)))


class ModeledExecution(unittest.TestCase):
    def test_after_delay_close_fill_and_independent_net(self):
        rows=[minute(T,'100','100.1','99.9','100'),minute(T+60000,'100','105.2','99.9','105.1')]
        r=model_trade(plan(),Book(rows),states(),FUND,[],EXEC)
        self.assertEqual(r['status'],'modeled_closed'); self.assertEqual(r['entry_ms'],T+60000)
        self.assertEqual(D(r['entry']),D('100.025001')); self.assertEqual(D(r['exit']),D('105.052705'))
        self.assertEqual(D(r['net']),D('4.925165147')); self.assertEqual(D(r['entry_risk']),D('2.025001'))
        self.assertIsNone(r['strict_net_r']); self.assertFalse(r['mature'])
        self.assertEqual(sum((D(m['pnl'])-D(r['marks'][i-1]['pnl']) if i else D(m['pnl']) for i,m in enumerate(r['marks'])),D(0)),D(r['net']))

    def test_ambiguity_is_not_dropped_into_winning_sample(self):
        rows=[minute(T,'100','100.1','99.9','100'),minute(T+60000,'100','106','97','101')]
        r=model_trade(plan(),Book(rows),states(),FUND,[],EXEC)
        self.assertEqual(r['status'],'unresolved'); self.assertIsNone(r['net_r']); self.assertIn('scenario_stop_first_r',r)
        m=metrics([r]); self.assertEqual(m['unresolved'],1); self.assertIsNone(m['win_rate'])

    def test_entry_band_expiry_pretouch_gap_event_and_funding(self):
        first=minute(T,'100','100.1','99.9','100'); cases=[
            ([minute(T,'100','100.3','99.9','100.2')],[],FUND,'drift'),
            ([minute(T,'100','105.1','99.9','100')],[],FUND,'level_hit_before_entry'),
            ([minute(T+60000,'100','100.1','99.9','100')],[],FUND,'minute_gap'),
            ([first],[dict(start_ms=T+HOUR,end_ms=T+2*HOUR)],FUND,'event_window'),
            ([first],[],[(T-2*HOUR,D(0)),(T-HOUR,D(0))],'funding_window')]
        for rows,events,fund,reason in cases:
            with self.subTest(reason=reason): self.assertEqual(model_trade(plan(),Book(rows),states(),fund,events,EXEC)['reason'],reason)
        self.assertEqual(model_trade(plan(),Book([first]),states(),FUND,[],dict(EXEC,entry_delay_seconds=180))['reason'],'data_tail')

    def test_gap_after_entry_retains_unresolved_risk(self):
        r=model_trade(plan(),Book([minute(T,'100','100.1','99.9','100'),minute(T+120000,'100','100.1','99.9','100')]),states(),FUND,[],EXEC)
        self.assertEqual(r['status'],'unresolved'); self.assertEqual(r['reason'],'minute_gap'); self.assertIn('entry_ms',r)


class TemporalSelection(unittest.TestCase):
    def trade(self,end,net,status='modeled_closed'):
        p=plan(); p['end_ms']=end; p['max_hold_ms']=HOUR
        return dict(plan=p,status=status,net_r=str(net) if status=='modeled_closed' else None,
            entry_ms=end+60000,entry_risk='1',exit_ms=end+HOUR if status=='modeled_closed' else None,
            marks=[],reason='fixture')

    def test_outer_winners_cannot_enter_training_choice(self):
        start=ms('2023-01-01'); split=ms('2024-01-01')
        a=[self.trade(start+i*DAY,1) for i in range(35)]; b=[self.trade(start+i*DAY,-1) for i in range(35)]
        variants={'1':a,'0.8':b}
        self.assertEqual(choose_training(variants,start,split)['winner'],'1')
        # Poisoned later outcomes cannot change the earlier choice.
        variants['0.8'] += [self.trade(split+i*DAY,1000) for i in range(100)]
        self.assertEqual(choose_training(variants,start,split)['winner'],'1')

    def test_small_samples_negative_mean_and_unresolved_cohorts_abstain(self):
        start=ms('2023-01-01'); end=ms('2024-01-01')
        for count,net,status in [(29,1,'modeled_closed'),(35,-1,'modeled_closed'),(35,1,'unresolved')]:
            trades=[self.trade(start+i*DAY,net,status) for i in range(count)]
            self.assertIsNone(choose_training({'1':trades},start,end)['winner'])
        trades=[self.trade(start+i*DAY,1) for i in range(35)]+[self.trade(start+50*DAY,1,'unresolved')]
        self.assertIsNone(choose_training({'1':trades},start,end)['winner'])

    def test_observation_caps_ignore_future_profit_and_remove_unadmitted_fill_fields(self):
        trades=[]
        for i in range(4):
            t=self.trade(2*DAY+i*4*BAR,1); t['plan']['opportunity_id']=str(i); t['fees']='1'; trades.append(t)
        result=observation_controls(trades)
        self.assertEqual(sum(t['status']=='modeled_closed' for t in result),3)
        self.assertEqual(result[-1]['reason'],'observation_family_cap'); self.assertNotIn('entry_ms',result[-1]); self.assertNotIn('fees',result[-1])
        changed=deepcopy(trades); changed[0]['net_r']='-1000'
        self.assertEqual([t['status'] for t in observation_controls(changed)],[t['status'] for t in result])


class Calendars(unittest.TestCase):
    def test_dst_and_local_date_blackout(self):
        self.assertEqual(timestamp('2024-01-11','08:30'),ms('2024-01-11')+13*HOUR+30*60000)
        self.assertEqual(timestamp('2024-07-11','08:30'),ms('2024-07-11')+12*HOUR+30*60000)
        b=blackout('2024-03-10','fomc',0); self.assertEqual(b['end_ms']-b['start_ms'],23*HOUR)

    def test_unverified_calendar_markup_cannot_claim_empty_coverage(self):
        for fn in (parse_bls,parse_fed):
            with self.assertRaises(Exception): fn('<html>no supported events</html>',2024,0)

    def test_calendar_knowledge_uses_final_receipt_and_retains_raw_sources(self):
        now=ms('2024-01-01'); clock=[now]
        bls=''.join(f'Monday, {calendar.month_name[m]} 01, 2024 08:30 AM {title} for fixture ' for m in range(1,11) for title in ('Consumer Price Index','Employment Situation'))
        fed='2024 FOMC Meetings'+''.join(f'<div class="fomc-meeting__month">{calendar.month_name[m]}</div><div class="fomc-meeting__date">1-2</div>' for m in range(1,9))
        def get(url,limit):
            clock[0]+=1000; return (bls if 'bls.gov' in url else fed).encode()
        with tempfile.TemporaryDirectory() as root,patch('tradee.pilots.calendar.get',side_effect=get) as fetch:
            cache=CalendarCache(Path(root)/'latest.json',clock=lambda:clock[0]/1000)
            result=cache.view(now)
            self.assertEqual(result['refreshed_ms'],now+2000)
            self.assertTrue(all(e['known_ms']==now+2000 for e in result['blackouts']))
            self.assertEqual(len(list(Path(root).glob('calendar-source-*.html'))),2)
            self.assertEqual(cache.view(now+3000),result); self.assertEqual(fetch.call_count,2)


if __name__=='__main__': unittest.main()
