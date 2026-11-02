"""Strict qualification and explicit modeled costs; no alert is a fill."""
from .contracts import BAR, DAY, HOUR, FAMILIES, dec, jsonable


def costs(plan, bid, ask, *, fee='.0005', slippage_bps='2', exit_spread_bps='5'):
    bid,ask,f=dec(bid),dec(ask),dec(fee); p=dec(slippage_bps)/10000
    s,t=dec(plan['stop']),dec(plan['target']); d=1 if plan['side']=='long' else -1
    if bid<=0 or ask<bid or f<0 or p<0: return dict(reasons=['invalid_quote_or_cost'])
    mid=(bid+ask)/2; width=max(ask-bid,dec(exit_spread_bps)*mid/10000)
    entry=ask*(1+p) if d==1 else bid*(1-p)
    stop=s-d*(width/2+p*s); target=t-d*(width/2+p*t)
    dm=d*(mid-s); loss=d*(entry-stop)+f*(entry+stop); gain=d*(target-entry)-f*(entry+target)
    reasons=[]
    if min(entry,stop,target,dm,loss,gain)<=0: reasons.append('invalid_price_geometry')
    else:
        if gain/loss<dec('1.8'): reasons.append('net_rr_low')
        if max(loss-dm,d*(t-mid)-gain)>dec('.25')*dm: reasons.append('cost_too_large')
    a=dec(plan['atr']); scale=dec(plan.get('geometry_scale','1')); tick=dec(plan['tick_size'])
    if not dec('.75')*scale*a<=dm<=dec('2.5')*scale*a or dm<10*tick: reasons.append('stop_distance')
    actual_risk=d*(entry-s)
    if not dec('.75')*scale*a<=actual_risk<=dec('2.5')*scale*a or actual_risk<10*tick: reasons.append('fill_stop_distance')
    return dict(mid=mid,entry=entry,stop_exit=stop,target_exit=target,stopped_loss=loss,target_gain=gain,
                net_rr=gain/loss if loss>0 else None,planning_risk=dm,entry_risk=actual_risk,
                fee=f,slippage=p,exit_width=width,reasons=sorted(set(reasons)))


def qualify(plan, evidence, now_ms, *, context=None, purpose='entry'):
    """Evidence is normalized by source adapters, never supplied by strategy outcomes."""
    reasons=[]; estimate=None
    if purpose not in ('entry','notification'): raise ValueError('Unknown assessment purpose')
    if now_ms>=plan['expires_ms']: reasons.append('expired')
    if purpose=='notification' and now_ms>=plan['end_ms']+60000: reasons.append('late_notification')
    if purpose=='entry' and now_ms<plan['detected_ms']+30000: reasons.append('reaction_delay')
    if plan['detected_ms']>plan['end_ms']+30000: reasons.append('late_detection')
    if not evidence: evidence={}
    q=evidence.get('quote'); mark=evidence.get('mark'); meta=evidence.get('metadata'); path=evidence.get('path'); calendar=evidence.get('calendar')
    if evidence.get('stream_state')!='connected': reasons.append('stream_not_connected')
    offset=evidence.get('clock_offset_ms')
    if type(offset) is not int or abs(offset)>1000: reasons.append('clock_unknown_or_skewed')
    def fresh(row,age):
        return bool(row and all(type(row.get(k)) is int and 0<=now_ms-row[k]<age for k in ('event_ms','received_ms')))
    if not fresh(q,2000): reasons.append('quote_stale')
    else:
        if q.get('symbol')!=plan['symbol']: reasons.append('wrong_instrument')
        bid,ask=dec(q['bid']),dec(q['ask']); mid=(bid+ask)/2; a=dec(plan['atr']); d0=dec(plan['reference_risk'])
        if bid<=0 or ask<bid or mid<=0: reasons.append('invalid_quote')
        else:
            if (ask-bid)/mid>dec('.0005') or ask-bid>dec('.05')*a: reasons.append('spread')
            if abs(mid-dec(plan['price']))>min(dec('.10')*a,dec('.15')*d0): reasons.append('drift')
            d=1 if plan['side']=='long' else -1
            if d*(mid-dec(plan['trigger_level']))<dec(plan.get('entry_level_buffer',plan['b'])): reasons.append('reclaim_lost')
            estimate=costs(plan,bid,ask,fee=max(dec('.0005'),dec(evidence.get('fee_each_side','.0005'))))
            reasons+=estimate['reasons']
    if not fresh(mark,5000): reasons.append('mark_stale')
    elif mark.get('symbol')!=plan['symbol']: reasons.append('wrong_instrument')
    elif type(mark.get('next_funding_ms')) is not int or mark['next_funding_ms']<=now_ms+plan['max_hold_ms']+300000: reasons.append('funding_window')
    if not meta or type(meta.get('observed_ms')) is not int or not 0<=now_ms-meta['observed_ms']<=900000: reasons.append('metadata_stale')
    else:
        if meta.get('symbol')!=plan['symbol'] or meta.get('status')!='TRADING' or dec(meta.get('tick_size','0'))!=dec(plan['tick_size']): reasons.append('instrument_rules')
        for k in ('step_size','min_quantity','min_notional'):
            if dec(meta.get(k,'0'))<=0: reasons.append('instrument_rules')
        halt=meta.get('halt_ms')
        if halt is not None and halt<=now_ms+plan['max_hold_ms']+300000: reasons.append('instrument_halt')
    if (not path or path.get('source')!='recorded_contract_trades' or path.get('continuous') is not True
            or path.get('symbol')!=plan['symbol'] or path.get('start_ms',now_ms)>plan['end_ms'] or path.get('end_ms',0)<now_ms-2000): reasons.append('path_unknown')
    else:
        d=1 if plan['side']=='long' else -1
        if (dec(path['low'])<=dec(plan['stop']) or dec(path['high'])>=dec(plan['target'])) if d==1 else (dec(path['high'])>=dec(plan['stop']) or dec(path['low'])<=dec(plan['target'])):
            reasons.append('level_hit_before_entry')
    if (not calendar or calendar.get('sources')!=['bls_cpi','bls_employment','fomc']
            or type(calendar.get('refreshed_ms')) is not int or not 0<=now_ms-calendar['refreshed_ms']<=DAY
            or calendar.get('coverage_start_ms',now_ms+1)>now_ms or calendar.get('coverage_end_ms',0)<now_ms+plan['max_hold_ms']): reasons.append('calendar_unknown')
    else:
        for event in calendar.get('blackouts',[]):
            if event['known_ms']>now_ms: continue
            if event['start_ms']<=now_ms+plan['max_hold_ms'] and event['end_ms']>now_ms: reasons.append('event_window')
    if context is None: reasons.append('missing_context')
    else:
        allowed='HEALTHY_RANGE' if plan['mode']=='sweep_range' else 'TREND_UP' if plan['side']=='long' else 'TREND_DOWN'
        if context.state!=allowed: reasons.append('transition')
        if context.shock_wait or context.values[-1]['dull']: reasons.append('market_veto')
        if plan['mode']=='sweep_range' and not context.box_valid({k:dec(v) if k!='hour_end_ms' else v for k,v in plan['box'].items()}): reasons.append('range_moved')
        if plan['level_expires_ms'] is not None and now_ms>=plan['level_expires_ms']: reasons.append('level_rollover')
        if plan['strategy']==FAMILIES[1] and q and fresh(q,2000):
            d=1 if plan['side']=='long' else -1; mid=(dec(q['ask'])+dec(q['bid']))/2
            if d*(mid-context.values[-1]['ema200'])<dec(plan['b']): reasons.append('ema_reclaim_lost')
    return jsonable(dict(qualified=not reasons,reasons=sorted(set(reasons)),estimate=estimate,
                        assessed_ms=now_ms,entry_not_before_ms=plan['detected_ms']+30000,live_approved=False))
