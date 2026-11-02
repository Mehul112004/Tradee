"""Reproducible price/cost diagnostics and training-only quarterly selection.

Minute closes are execution proxies. This module cannot produce a strict
qualified observation, C12 promotion, or a recorded-execution profit label.
"""
import argparse
from bisect import bisect_left,bisect_right
from collections import Counter,defaultdict
from datetime import datetime,timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess

from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from .archive import candles,months,rows
from .calendar import reconstructed
from .contracts import BAR,HOUR,DAY,MODES,PRIORITY,PilotConfig,dec,jsonable
from .engine import PilotEngine
from .execution import costs


def ms(date): return int(datetime.fromisoformat(date).replace(tzinfo=timezone.utc).timestamp()*1000)


def add_months(date,n):
    d=datetime.fromisoformat(date); y,m=divmod(d.year*12+d.month-1+n,12)
    return f'{y:04d}-{m+1:02d}-01'


def implementation_hash():
    from tradee.c06.engine import code_hash
    return code_hash()  # Includes C03/C05 primitives and every imported core implementation.


class MinuteBook:
    def __init__(self,directory,end): self.directory=Path(directory); self.end=ms(end)

    @lru_cache(maxsize=4)
    def month(self,symbol,month):
        if ms(month+'-01')>=self.end: raise ValidationError('Reserved archive access denied')
        path=self.directory/f'{symbol}-1m-{month}.zip'
        result=[]; last=None
        for r in rows(path):
            t=int(r[0]); t=t//1000 if t>10**14 else t
            if t%60000 or last is not None and t<=last: raise ValidationError('Invalid minute archive ordering')
            o,h,l,c=map(dec,r[1:5])
            if not 0<l<=min(o,c)<=max(o,c)<=h: raise ValidationError('Invalid minute envelope')
            result.append((t,o,h,l,c)); last=t
        return [r[0] for r in result],result

    def window(self,symbol,start,end):
        if end>self.end: end=self.end
        cursor=start
        while cursor<end:
            d=datetime.fromtimestamp(cursor/1000,timezone.utc); month=d.strftime('%Y-%m')
            times,data=self.month(symbol,month); next_ms=ms(add_months(month+'-01',1))
            a,b=bisect_left(times,cursor),bisect_left(times,min(end,next_ms))
            yield from data[a:b]; cursor=next_ms


def funding(directory,symbol,start,end):
    result=[]
    for month in months(start,end):
        for r in rows(Path(directory)/f'{symbol}-fundingRate-{month}.zip',3):
            result.append((int(r[0]),dec(r[2])))
    if any(b[0]<=a[0] for a,b in zip(result,result[1:])): raise ValidationError('Invalid funding sequence')
    return result


def detect(directory,symbol,config,protocol,mode_scope=None):
    engine=PilotEngine(symbol,'.1' if symbol=='BTCUSDT' else '.01',config,mode_scope=mode_scope)
    plans=[]; states=[]; gaps=[]; previous=None
    start=ms(protocol['development_start']); end=ms(protocol['development_end'])
    for r in candles(directory,symbol,'15m',protocol['warmup_start'],protocol['development_end']):
        if r['open_ms']>=end: raise ValidationError('Reserved candle access denied')
        if previous is not None and r['open_ms']!=previous+BAR: gaps.append([previous+BAR,r['open_ms']])
        previous=r['open_ms']; outputs=engine.advance(r)
        plans.extend(p for p in outputs if p['end_ms']>=start)
        if r['open_ms']+BAR>=start:
            c=engine.context; v=c.values[-1]
            states.append(jsonable(dict(end_ms=r['open_ms']+BAR,state=c.state,dull=v['dull'],shock=c.shock_wait,
                close=r['close'],ema200=v['ema200'],hour_close=c.hour_rows[-1]['close'] if c.hour_rows else None,
                box=c.box,dull_twice=len(c.values)>=2 and v['dull'] and c.values[-2]['dull'])))
    return dict(plans=plans,states=states,gaps=gaps,rejections=dict(engine.reasons),prefix_hash=engine.context.prefix,
                state_counts=dict(Counter('DULL' if s['dull'] else 'SHOCK' if s['shock'] else s['state'] for s in states)))


def state_at(states,times,when):
    i=bisect_right(times,when)-1
    return states[i] if i>=0 else None


def state_exit(plan,state):
    if state is None: return 'missing_context'
    d=1 if plan['side']=='long' else -1
    expected='HEALTHY_RANGE' if plan['mode']=='sweep_range' else 'TREND_UP' if d==1 else 'TREND_DOWN'
    filters=plan.get('filters',{})
    if filters.get('regime_filter',True) and state['state']!=expected: return 'state_exit'
    if state['shock']: return 'shock_exit'
    if filters.get('dull_filter',True) and state['dull_twice']: return 'dull_exit'
    c=dec(state['close']); b=dec(plan['b']); x=dec(plan['trigger_level'])
    if plan['mode']=='ema_trend': x=dec(state['ema200'])
    if d*(c-x)<=-b: return 'thesis_exit'
    if plan['mode']=='sweep_range':
        f=plan['box']; current=state['box']; a=dec(f['atr'])
        if (not current or not dec(f['low'])-dec('.25')*a<=dec(state['hour_close'])<=dec(f['high'])+dec('.25')*a
                or abs(dec(current['low'])-dec(f['low']))>dec('.50')*a or abs(dec(current['high'])-dec(f['high']))>dec('.50')*a): return 'range_exit'
    return None


def model_trade(plan,book,states,settlements,blackouts,execution,*,state_times=None):
    p=plan; d=1 if p['side']=='long' else -1; start=p['end_ms']; a=dec(p['atr']); risk0=dec(p['reference_risk'])
    s,t=dec(p['stop']),dec(p['target']); fee=dec(execution['fee_each_side']); slip=dec(execution['slippage_bps_each_side'])/10000
    stimes=state_times if state_times is not None else [x['end_ms'] for x in states]; ftimes=[f[0] for f in settlements]
    result=dict(plan=p,status='no_entry',reason=None,net_r=None,strict_net_r=None,mature=False,marks=[])
    entered=None; estimate=None; entry_ms=None; mfe=dec(0); expected=start; last_state=None; running=dec(0); funding_value=dec(0)
    for minute in book.window(p['symbol'],start,start+p['max_hold_ms']+240000):
        opened,o,h,l,c=minute; when=opened+60000
        if opened!=expected:
            result.update(status='unresolved' if entered is not None else 'no_entry',reason='minute_gap'); return jsonable(result)
        expected=opened+60000
        state=state_at(states,stimes,when)
        if entered is None:
            if l<=min(s,t) or h>=max(s,t): result['reason']='level_hit_before_entry'; return result
            if when<start+execution['entry_delay_seconds']*1000: continue
            if when>=p['expires_ms']: result['reason']='expired'; return result
            if abs(c-dec(p['price']))>min(dec('.10')*a,dec('.15')*risk0): result['reason']='drift'; return result
            if state_exit(p,state): result['reason']='context_before_entry'; return result
            if any(b['start_ms']<=when+p['max_hold_ms'] and b['end_ms']>when for b in blackouts): result['reason']='event_window'; return result
            j=bisect_left(ftimes,when)
            if j<2: result['reason']='funding_schedule_unknown'; return result
            interval=ftimes[j-1]-ftimes[j-2]; projected=ftimes[j-1]+interval
            if projected<=when+p['max_hold_ms']+300000: result['reason']='funding_window'; return result
            width=c*dec(execution['entry_spread_bps'])/10000
            if width/c>dec('.0005') or width>dec('.05')*a: result['reason']='spread'; return result
            estimate=costs(p,c-width/2,c+width/2,fee=fee,slippage_bps=execution['slippage_bps_each_side'],exit_spread_bps=execution['exit_spread_bps'])
            if estimate['reasons']: result['reason']=';'.join(estimate['reasons']); return result
            if d*(c-dec(p['trigger_level']))<dec(p['entry_level_buffer']): result['reason']='reclaim_lost'; return result
            entered=estimate['entry']; entry_ms=when; actual_risk=estimate['entry_risk']; entry_fee=fee*entered
            running=d*(c-entered)-entry_fee
            result.update(status='open_modeled',entry_ms=when,entry=entered,entry_mid=c,entry_risk=actual_risk,
                expected_stopped_loss=estimate['stopped_loss'],entry_fee=entry_fee)
            result['marks'].append(dict(at_ms=when,pnl=running,price=c,regime='DULL' if state['dull'] else state['state']))
            last_state=state['end_ms']; continue
        stop_hit=l<=s if d==1 else h>=s; target_hit=h>=t if d==1 else l<=t
        if stop_hit and target_hit:
            # Retain ambiguity. Adverse scenario is diagnostic and never a mature label.
            width=max(c*dec(execution['exit_spread_bps'])/10000,dec(execution['entry_spread_bps'])*c/10000)
            adverse=s-d*(width/2+slip*s)
            scenario=(d*(adverse-entered)-fee*(entered+adverse)+funding_value)/actual_risk
            result.update(status='unresolved',reason='stop_and_target_same_minute',scenario_stop_first_r=scenario); return jsonable(result)
        reason='stop' if stop_hit else 'target' if target_hit else None
        mfe=max(mfe,d*((h if d==1 else l)-entered))
        if not reason and state and state['end_ms']!=last_state:
            reason=state_exit(p,state); last_state=state['end_ms']
        if not reason and when>=entry_ms+HOUR and mfe<dec('.5')*actual_risk: reason='stall'
        if not reason and when>=entry_ms+p['max_hold_ms']: reason='time'
        for k in range(bisect_right(ftimes,opened),bisect_right(ftimes,when)):
            if ftimes[k]<=entry_ms: continue
            # Contract-close proxy for settlement mark; explicitly modeled.
            funding_value-=d*c*settlements[k][1]
        running=d*(c-entered)-entry_fee+funding_value
        if reason:
            width=max(c*dec(execution['exit_spread_bps'])/10000,dec(execution['entry_spread_bps'])*c/10000)
            fill=c-d*(width/2+slip*c); net=d*(fill-entered)-fee*(entered+fill)+funding_value
            result.update(status='modeled_closed',reason=reason,exit_ms=when,exit=fill,net=net,net_r=net/actual_risk,
                fees=fee*(entered+fill),funding=funding_value)
            running=net
        result['marks'].append(dict(at_ms=when,pnl=running,price=c,regime='DULL' if state and state['dull'] else 'SHOCK' if state and state['shock'] else state['state'] if state else 'UNKNOWN'))
        if reason: return jsonable(result)
    result.update(status='unresolved' if entered is not None else 'no_entry',reason='data_tail')
    return jsonable(result)


def metrics(trades):
    closed=sorted((t for t in trades if t['status']=='modeled_closed'),key=lambda t:(t['exit_ms'],t['plan'].get('opportunity_id',''))); values=[dec(t['net_r']) for t in closed]
    wins=sum(v>0 for v in values); gain=sum((v for v in values if v>0),dec(0)); loss=-sum((v for v in values if v<0),dec(0))
    total=dec(0); peak=dec(0); dd=dec(0)
    for v in values: total+=v; peak=max(peak,total); dd=max(dd,peak-total)
    regimes=defaultdict(lambda:dec(0))
    for trade in closed:
        previous=dec(0); risk=dec(trade['entry_risk'])
        for mark in trade['marks']:
            current=dec(mark['pnl'])/risk; regimes[mark['regime']]+=current-previous; previous=current
    return jsonable(dict(pattern_plans=len(trades),modeled_entries=sum('entry_ms' in t for t in trades),
        modeled_closed=len(closed),unresolved=sum(t['status']=='unresolved' for t in trades),
        win_rate=wins/len(values) if values else None,net_r=total,mean_r=total/len(values) if values else None,
        profit_factor=gain/loss if loss else None,cumulative_r_drawdown=dd,time_in_regime_net_r=dict(regimes),
        reasons=dict(Counter(t['reason'] for t in trades)),strict_mature_entries=0,live_approved=False))


def choose_training(variants,start,end,purge_ms=DAY):
    """This function receives only training cohorts; no test score is an argument."""
    scores=[]
    for name,trades in sorted(variants.items()):
        selected=[t for t in trades if start<=t['plan']['end_ms'] and t['plan']['end_ms']+t['plan']['max_hold_ms']+180000<end-purge_ms]
        m=metrics(selected); score=None
        if m['modeled_closed']>=30 and m['unresolved']==0 and dec(m['mean_r'])>0:
            score=dec(m['mean_r'])-dec('.10')*dec(m['cumulative_r_drawdown'])
        scores.append(dict(scale=name,metrics=m,score=score))
    viable=[s for s in scores if s['score'] is not None]
    winner=sorted(viable,key=lambda s:(-s['score'],s['scale']))[0]['scale'] if viable else None
    return jsonable(dict(winner=winner,scores=scores,selection='earlier training only; no passing sample means abstain'))


def walk_forward(cohorts,mode,protocol):
    folds=[]; date=protocol['outer_start']; end=protocol['development_end']; selected_all=[]
    while date<end:
        test_end=min(add_months(date,protocol['test_months']),end); train_start=add_months(date,-protocol['train_months'])
        variants={scale:cohorts[scale][mode] for scale in protocol['geometry_scales']}
        training=choose_training(variants,ms(train_start),ms(date),protocol['purge_hours']*HOUR)
        selected=[]
        if training['winner'] is not None:
            selected=[t for t in variants[training['winner']] if ms(date)<=t['plan']['end_ms']<ms(test_end)-3*HOUR-180000]
        fixed={scale:metrics([t for t in variants[scale] if ms(date)<=t['plan']['end_ms']<ms(test_end)-3*HOUR-180000]) for scale in variants}
        folds.append(dict(train_start=train_start,train_end=date,test_start=date,test_end=test_end,training=training,
            selected=metrics(selected),fixed_variants=fixed))
        selected_all+=selected; date=test_end
    return dict(mode=mode,folds=folds,selected_outer=metrics(selected_all),
                status='diagnostic_only_not_promotable',holdout_accessed=False)


def run(args):
    protocol=json.loads(Path(args.protocol).read_text()); out=Path(args.output); out.mkdir(parents=True,exist_ok=True)
    if protocol['development_end']>protocol['reserved_start']: raise ValidationError('Development overlaps reserved evidence')
    code=implementation_hash(); manifest=dict(protocol=protocol,implementation_hash=code,
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        execution_basis='modeled 1m close proxies, assumed fees/spreads/slippage, reconstructed calendars/rules; strict outcomes unavailable',
        holdout_accessed=False,live_approved=False)
    manifest['run_id']=fingerprint(manifest); (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    calendars=json.loads(Path(args.calendar).read_text()); blackouts=reconstructed(calendars)
    book=MinuteBook(args.archives,protocol['development_end']); settlements={s:funding(args.archives,s,protocol['warmup_start'],protocol['development_end']) for s in protocol['symbols']}
    cohorts={}; detection={}; base_execution=protocol['modeled_execution']
    for scale in protocol['geometry_scales']:
        cohorts[scale]={mode:[] for mode in MODES}; detection[scale]={}
        for symbol in protocol['symbols']:
            cache=out/f'detection-{symbol}-{scale}.json'
            if cache.exists():
                saved=json.loads(cache.read_text())
                if saved['implementation_hash']!=code: raise ValidationError('Detection cache belongs to a different implementation; use a new output directory')
                data=saved['data']
            else:
                data=detect(args.archives,symbol,PilotConfig(geometry_scale=scale),protocol)
                cache.write_text(json.dumps(dict(implementation_hash=code,data=data),separators=(',',':'))+'\n')
            detection[scale][symbol]={k:v for k,v in data.items() if k not in ('plans','states')}
            state_times=[s['end_ms'] for s in data['states']]
            for plan in data['plans']:
                trade=model_trade(plan,book,data['states'],settlements[symbol],blackouts,base_execution,state_times=state_times)
                cohorts[scale][plan['mode']].append(trade)
            print(json.dumps(dict(stage='modeled_baseline',scale=scale,symbol=symbol,plans=len(data['plans']))),flush=True)
        for mode in MODES: cohorts[scale][mode].sort(key=lambda t:(t['plan']['end_ms'],t['plan']['symbol'],t['plan']['opportunity_id']))
        (out/f'cohorts-{scale}.json').write_text(json.dumps(cohorts[scale],separators=(',',':'))+'\n')
    summary=dict(manifest=manifest,detection=detection,backtests={s:{m:metrics(v) for m,v in modes.items()} for s,modes in cohorts.items()},
                 walk_forward={m:walk_forward(cohorts,m,protocol) for m in MODES},
                 promotion=dict(accepted=False,reasons=['modeled_execution_only','historical_trial_count_unknown','reserved_evidence_unattested','forward_paper_outstanding']))
    (out/'report.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(report=str(out/'report.json'),run_id=manifest['run_id'])),flush=True)


def main():
    p=argparse.ArgumentParser(); p.add_argument('--protocol',default='configs/pilot_research_v1.json'); p.add_argument('--archives',default='data/pilot-research/archives')
    p.add_argument('--calendar',default='configs/pilot_calendar_reconstructed.json'); p.add_argument('--output',default='data/pilot-research/run-v1')
    run(p.parse_args())


if __name__=='__main__': main()
