"""Closed-bar state machines. No outcomes, quotes or future bars enter detection."""
from collections import Counter
from copy import deepcopy

from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from .contracts import BAR, HOUR, DAY, FAMILIES, PRIORITY, PilotConfig, candle, dec, jsonable, rounded
from .context import Context


class PilotEngine:
    def __init__(self, symbol, tick_size, config=None, *, start_seed_ms=0, families=FAMILIES):
        if symbol not in ('BTCUSDT','ETHUSDT'): raise ValidationError('Pilot v1 supports BTCUSDT/ETHUSDT only')
        self.config=config or PilotConfig(); self.symbol=symbol; self.tick=dec(tick_size)
        if self.tick<=0 or any(f not in FAMILIES for f in families): raise ValidationError('Invalid pilot tick/family')
        self.families=tuple(families); self.context=Context(symbol,self.tick,self.config)
        self.start_seed_ms=start_seed_ms; self.pending=[]; self.attempts=set(); self.attempt_log=[]
        self.ema_after={'long':0,'short':0}; self.reasons=Counter(); self.snapshots=[]
        self.last_open=None; self.last_source=None; self.last_generation=0
        self.latest_available=0

    def g(self, factor, atr): return dec(factor)*self.config.scale*atr

    def buffer(self, atr): return max(self.g('.10',atr),2*self.tick)

    def allowed(self, side, mode):
        if not self.config.regime_filter: return mode!='sweep_range' or self.context.box is not None
        return self.context.state==('HEALTHY_RANGE' if mode=='sweep_range' else 'TREND_UP' if side=='long' else 'TREND_DOWN')

    def health(self, row, current, previous=None):
        when=max(row['available_ms'],self.context.hour_rows[-1]['available_ms'] if self.context.hour_rows else 0)
        reason=self.context.ready(row['open_ms']+BAR,when)
        if reason: return reason
        if when>row['open_ms']+BAR+30000: return 'late_detection'
        if self.config.dull_filter and (current['dull'] or previous is not None and previous['dull']): return 'dull'
        return None

    def trend_execution(self, side, values, b, price):
        d=1 if side=='long' else -1
        return values['crosses']<=2 and d*(price-values['ema200'])>=b

    def confirmation(self, row, v, side, atr):
        if row['high']<=row['low'] or v['rv'] is None or v['rv']<1 or v['tr']>self.g('2.5',atr): return False
        body=row['close']-row['open']; clv=(row['close']-row['low'])/(row['high']-row['low'])
        return (body>=self.g('.25',atr) and clv>=dec('.75')) if side=='long' else (-body>=self.g('.25',atr) and clv<=dec('.25'))

    def eligible(self, level, side, family, row, atr):
        if not dec('.5')<=atr/level['atr']<=2 or level['known_ms']>row['open_ms']-3*BAR: return False
        if self.config.exhaustion_filter and level['prior_touches']>2: return False
        key=(level['id'],side,row['open_ms']//DAY)
        if key in self.attempts or any(p.get('level',{}).get('id')==level['id'] and p['side']==side for p in self.pending): return False
        if family==FAMILIES[0] and level['prior_accepted_down' if side=='long' else 'prior_accepted_up']: return False
        if family==FAMILIES[2] and level['prior_accepted_up' if side=='long' else 'prior_accepted_down']: return False
        return True

    def consume(self, levels, side, row, family):
        for level in levels:
            key=(level['id'],side,row['open_ms']//DAY); self.attempts.add(key)
            self.attempt_log.append(dict(level_id=level['id'],side=side,day=key[2],seed_ms=row['open_ms'],family=family))

    def select(self, levels):
        return sorted(levels,key=lambda l:(l['kind']!='previous_day',-l['confirmed_ms'],l['id']))[0]

    def base(self, family, mode, side, row, atr, level=None):
        return dict(family=family,mode=mode,side=side,seed_ms=row['open_ms'],atr=atr,b=self.buffer(atr),
                    low=row['low'],high=row['high'],level=deepcopy(level),box=deepcopy(self.context.box),
                    generation=self.context.generation,state=self.context.state)

    def sweep_seeds(self, row, v, prior):
        atr=prior['atr']; b=self.buffer(atr); before=list(self.context.rows)[-4:-1]
        found={'long':[],'short':[]}
        for side in ('long','short'):
            d=1 if side=='long' else -1
            for l in self.context.levels:
                if l['side']!=('low' if side=='long' else 'high') or not self.eligible(l,side,FAMILIES[0],row,atr): continue
                x=l['price']
                if len(before)!=3 or any(d*(r['close']-x)<=b or r['open_ms']<l['known_ms'] for r in before): continue
                depth=x-row['low'] if side=='long' else row['high']-x
                span=row['high']-row['low']
                wick=min(row['open'],row['close'])-row['low'] if side=='long' else row['high']-max(row['open'],row['close'])
                if not (d*(row['open']-x)>=b and b<=depth<=self.g('.75',atr) and span>0 and wick/span>=dec('.30') and v['tr']<=self.g('2.5',atr)): continue
                mode='sweep_range' if self.context.state=='HEALTHY_RANGE' else 'sweep_trend'
                if not self.allowed(side,mode): continue
                if mode=='sweep_range':
                    box=self.context.box; ah=box['atr']; edge=box['low' if side=='long' else 'high']
                    if abs(x-edge)>self.g('.25',ah) or d*(x-(box['low']+dec('.20')*(box['high']-box['low']) if side=='long' else box['high']-dec('.20')*(box['high']-box['low'])))>0: continue
                elif v['crosses']>2: continue
                found[side].append((l,mode))
        if found['long'] and found['short']:
            self.reasons['dual_sweep']+=1
            for side,items in found.items(): self.consume([l for l,_ in items],side,row,FAMILIES[0])
            return []
        result=[]
        for side,items in found.items():
            if not items: continue
            chosen=self.select([l for l,_ in items]); mode=next(m for l,m in items if l['id']==chosen['id'])
            self.consume([l for l,_ in items],side,row,FAMILIES[0])
            result.append(self.base(FAMILIES[0],mode,side,row,atr,chosen))
        return result

    def ema_seeds(self, row, v, prior):
        history=list(self.context.rows); values=list(self.context.values)
        if len(history)<10 or prior['ema200'] is None: return []
        result=[]; atr=prior['atr']; e=prior['ema200']; band=max(self.g('.15',atr),2*self.tick)
        for side in ('long','short'):
            d=1 if side=='long' else -1
            if not self.allowed(side,'ema_trend') or v['crosses']>2 or v['slope'] is None or d*v['slope']<dec('.01'): continue
            separated=True; far=False
            for i in range(len(history)-9,len(history)-1):
                r,a,p=history[i],values[i],values[i-1]
                if not a['stable'] or not p['atr'] or r['open_ms']<self.ema_after[side]: separated=False; break
                width=max(self.g('.15',p['atr']),2*self.tick)
                extreme=r['low'] if side=='long' else r['high']
                if d*(extreme-a['ema200'])<=width or d*(r['close']-a['ema200'])<self.g('.10',a['atr']): separated=False; break
                far |= d*(r['close']-a['ema200'])>=self.g('.75',a['atr'])
            if not separated or not far or row['low']>e+band or row['high']<e-band: continue
            # Every first intersection consumes the episode, even a weak/deep candle.
            self.ema_after[side]=row['open_ms']+BAR
            span=row['high']-row['low']; wick=min(row['open'],row['close'])-row['low'] if side=='long' else row['high']-max(row['open'],row['close'])
            depth=e-row['low'] if side=='long' else row['high']-e
            if depth>self.g('.35',atr) or span<=0 or wick/span<dec('.30') or v['tr']>self.g('2.5',atr):
                self.reasons['ema_first_touch_failed']+=1; continue
            p=self.base(FAMILIES[1],'ema_trend',side,row,atr); p.update(ema=e,band=band)
            result.append(p)
        return result

    def retest_seeds(self, row, v, prior):
        atr=prior['atr']; b=self.buffer(atr); before=list(self.context.rows)[-4:-1]; result=[]
        for side in ('long','short'):
            if not self.allowed(side,'retest_trend') or v['crosses']>2: continue
            d=1 if side=='long' else -1; found=[]
            for l in self.context.levels:
                if l['side']!=('high' if side=='long' else 'low') or not self.eligible(l,side,FAMILIES[2],row,atr): continue
                x=l['price']; span=row['high']-row['low']
                if len(before)!=3 or any(d*(r['close']-x)>=-b or r['open_ms']<l['known_ms'] for r in before): continue
                clv=(row['close']-row['low'])/span if span else dec('.5')
                if (d*(row['close']-x)>=max(self.g('.25',atr),b) and d*(row['close']-row['open'])>=self.g('.50',atr)
                        and (clv>=dec('.75') if side=='long' else clv<=dec('.25')) and v['rv'] is not None and v['rv']>=dec('1.20') and v['tr']<=self.g('2.5',atr)):
                    found.append(l)
            if found:
                chosen=self.select(found); self.consume(found,side,row,FAMILIES[2])
                p=self.base(FAMILIES[2],'retest_trend',side,row,atr,chosen); p['stage']='acceptance'; result.append(p)
        return result

    def state_failure(self, p, row, v):
        if p['generation']!=self.context.generation: return 'missing_context'
        if not self.allowed(p['side'],p['mode']): return 'transition'
        if p['level'] and row['open_ms']+BAR>=p['level']['expires_ms']: return 'level_rollover'
        if p['mode']=='sweep_range' and not self.context.box_valid(p['box']): return 'range_moved'
        if p['mode']!='sweep_range' and v['crosses']>2: return 'crossing_chop'
        return self.health(row,v)

    def progress(self, p, row, v):
        """Return (action,reason): wait / confirm / reject. No later-bar rescue."""
        failure=self.state_failure(p,row,v)
        if failure: return 'reject',failure
        atr,b,d=p['atr'],p['b'],1 if p['side']=='long' else -1
        age=(row['open_ms']-p['seed_ms'])//BAR; family=p['family']; x=p['level']['price'] if p['level'] else p.get('ema')
        if family==FAMILIES[2]:
            if p['stage']=='acceptance':
                if age==0:
                    return ('reject','extended_before_retest') if d*(row['close']-x)>self.g('2',atr) else ('wait',None)
                if age!=1 or d*(row['close']-x)<b or (row['low']<=x+p['level']['z'] if d==1 else row['high']>=x-p['level']['z']): return 'reject','early_retest'
                if d*(row['close']-x)>self.g('2',atr): return 'reject','extended_before_retest'
                p['stage']='waiting'; return 'wait',None
            if p['stage']=='waiting':
                if age>6: return 'reject','late_retest'
                touch=row['low']<=x+p['level']['z'] and row['high']>=x-p['level']['z']
                if not touch:
                    if d*(row['close']-x)<b: return 'reject','lost_acceptance'
                    if d*(row['close']-x)>self.g('2',atr): return 'reject','extended_before_retest'
                    return 'wait',None
                p.update(stage='retest',touch_ms=row['open_ms'],touch_high=row['high'],touch_low=row['low'],low=row['low'],high=row['high'])
            p['low']=min(p['low'],row['low']); p['high']=max(p['high'],row['high'])
            depth=x-p['low'] if d==1 else p['high']-x
            if depth>self.g('.50',atr) or d*(row['close']-x)<=-b: return 'reject','retest_failed'
            strength=d*(row['close']-x)>=max(self.g('.20',atr),b)
            touch_age=(row['open_ms']-p['touch_ms'])//BAR
            extra=touch_age==0 or d*(row['close']-(p['touch_high'] if d==1 else p['touch_low']))>b
            if self.confirmation(row,v,p['side'],atr) and strength and extra and self.trend_execution(p['side'],v,b,row['close']): return 'confirm',None
            return ('wait',None) if touch_age==0 else ('reject','retest_confirmation_expired')
        p['low']=min(p['low'],row['low']); p['high']=max(p['high'],row['high'])
        if family==FAMILIES[0]:
            depth=x-p['low'] if d==1 else p['high']-x
            if depth>self.g('.75',atr): return 'reject','deep_sweep'
            strength=d*(row['close']-x)>=b
        else:
            depth=x-p['low'] if d==1 else p['high']-x
            if depth>self.g('.35',atr) or d*(row['close']-x)<=-b or abs(v['ema200']-x)>self.g('.15',atr): return 'reject','ema_failed'
            if v['slope'] is None or d*v['slope']<dec('.01'): return 'reject','ema_slope_failed'
            strength=d*(row['close']-x)>=p['band'] and d*(row['close']-v['ema200'])>=b
        extra=age==0 or d*(row['close']-(p['seed_high'] if d==1 else p['seed_low']))>b
        aligned=p['mode']=='sweep_range' or self.trend_execution(p['side'],v,b,row['close'])
        if strength and extra and aligned and self.confirmation(row,v,p['side'],atr): return 'confirm',None
        return ('wait',None) if age==0 else ('reject','confirmation_expired')

    def plan(self, p, row):
        d=1 if p['side']=='long' else -1; a=p['atr']; price=row['close']; pad=max(self.g('.15',a),2*self.tick)
        stop=rounded(p['low']-pad if d==1 else p['high']+pad,self.tick,up=d==-1)
        risk=d*(price-stop)
        if not self.g('.75',a)<=risk<=self.g('2.5',a) or risk<10*self.tick: return None,'stop_distance'
        distance=dec('2.5')*risk
        if p['mode']=='sweep_range': distance=min(distance,d*(p['box']['mid']-price))
        barriers=[]
        for l in self.context.levels+self.context.hour_pivots:
            if l['side']!=('high' if d==1 else 'low') or l['anchor_ms']>=p['seed_ms'] or l['known_ms']>row['available_ms']: continue
            gap=d*(l['price']-price)
            if gap>=0 and gap<=distance:
                distance=min(distance,gap-self.g('.10',a)); barriers.append(l.get('id') or fingerprint(jsonable(l)))
        target=rounded(price+d*distance,self.tick,up=d==-1)
        if d*(target-price)<=0: return None,'no_room'
        end=row['open_ms']+BAR
        output=dict(schema_version=1,symbol=self.symbol,strategy=p['family'],strategy_hash=self.config.digest,geometry_scale=self.config.geometry_scale,
            mode=p['mode'],side=p['side'],open_ms=row['open_ms'],end_ms=end,seed_ms=p['seed_ms'],detected_ms=row['available_ms'],
            price=price,stop=stop,target=target,reference_risk=risk,atr=a,b=p['b'],tick_size=self.tick,
            entry_level_buffer=max(self.g('.20',a),p['b']) if p['family']==FAMILIES[2] else p['band'] if p['family']==FAMILIES[1] else p['b'],
            trigger_level=p['level']['price'] if p['level'] else p['ema'],level_id=p['level']['id'] if p['level'] else None,
            level_known_ms=p['level']['known_ms'] if p['level'] else None,level_expires_ms=p['level']['expires_ms'] if p['level'] else None,
            box=p['box'] if p['mode']=='sweep_range' else None,barriers=barriers,regime=self.context.state,
            expires_ms=end+180000,max_hold_ms=2*HOUR if p['mode']=='sweep_range' else 3*HOUR,
            input_prefix_hash=self.context.prefix,live_approved=False,qualification='execution_unchecked',
            reasons=['missing_execution_evidence'])
        output['opportunity_id']=fingerprint([self.symbol,self.config.digest,p['family'],p['seed_ms'],row['open_ms'],p['side']])
        return jsonable(output),None

    def advance(self, document):
        row=candle(document); source=fingerprint(jsonable(row))
        if self.last_open is not None and row['open_ms']<=self.last_open:
            if row['open_ms']==self.last_open and source==self.last_source: return []
            raise ValidationError('Pilot corrections require a pinned-prefix rebuild; no retroactive emission')
        self.last_open,self.last_source=row['open_ms'],source
        self.latest_available=max(self.latest_available,row['available_ms'])
        row['available_ms']=self.latest_available
        prior,v=self.context.push(row)
        if self.context.generation!=self.last_generation:
            self.pending=[]; self.ema_after={'long':row['open_ms']+BAR,'short':row['open_ms']+BAR}; self.last_generation=self.context.generation
        self.snapshots.append(dict(end_ms=row['open_ms']+BAR,state=self.context.state,dull=v['dull'],shock=self.context.shock_wait))
        self.snapshots=self.snapshots[-720:]
        if row['open_ms']<self.start_seed_ms: return []
        existing=list(self.pending); plans=[]
        failure=self.health(row,v,prior)
        if not failure and prior and prior['atr']:
            if FAMILIES[0] in self.families: existing+=self.sweep_seeds(row,v,prior)
            if FAMILIES[1] in self.families and not any(p['family']==FAMILIES[1] for p in existing): existing+=self.ema_seeds(row,v,prior)
            if FAMILIES[2] in self.families: existing+=self.retest_seeds(row,v,prior)
        elif failure: self.reasons[failure]+=1
        self.pending=[]
        for p in existing:
            if 'seed_high' not in p: p.update(seed_high=p['high'],seed_low=p['low'])
            action,reason=self.progress(p,row,v)
            if action=='wait': self.pending.append(p)
            elif action=='reject': self.reasons[reason]+=1
            else:
                result,reason=self.plan(p,row)
                if result: plans.append(result)
                else: self.reasons[reason]+=1
        return sorted(plans,key=lambda p:(PRIORITY[p['strategy']],p['opportunity_id']))

    def run(self, rows):
        for row in rows: yield from self.advance(row)
