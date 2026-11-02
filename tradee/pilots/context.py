"""Known-time level inventory and current/frozen hourly state are distinct."""
from collections import deque

from tradee.c01.domain import fingerprint
from .contracts import BAR, HOUR, DAY, dec, jsonable
from .indicators import Measurements, pivot


class Context:
    def __init__(self, symbol, tick, config):
        self.symbol, self.tick, self.config = symbol, dec(tick), config
        self.exec, self.hour = Measurements(), Measurements()
        self.rows, self.values = deque(maxlen=720), deque(maxlen=720)
        self.hour_rows, self.hour_pivots = deque(maxlen=50), []
        self.levels, self.hour_parts = [], []
        self.state, self.raw, self.raw_count, self.box = 'TRANSITION', None, 0, None
        self.shock_wait, self.calm = False, 0
        self.prefix = fingerprint(['pilot', symbol, config.digest])
        self.generation = 0

    def reset_gap(self):
        old = self.generation
        self.__init__(self.symbol, self.tick, self.config)
        self.generation = old+1

    def add_level(self, kind, side, price, anchor, confirmed, known, atr):
        if not atr or atr <= 0: return
        identity = dict(instrument_id=self.symbol,kind=kind,side=side,anchor_ms=anchor,interval_ms=BAR)
        if kind == 'swing': identity.update(pivot_left=2,pivot_right=2)
        key=fingerprint(identity)
        z=max(dec('.10')*self.config.scale*atr,2*self.tick)
        self.levels.append(dict(id=key,kind=kind,side=side,price=price,anchor_ms=anchor,
            confirmed_ms=confirmed,known_ms=known,atr=atr,z=z,touches=0,episode=False,outside=0,
            accepted_up=False,accepted_down=False,up=0,down=0,
            expires_ms=confirmed+(DAY if kind=='previous_day' else 96*BAR)))

    def update_behavior(self, row):
        for level in self.levels:
            level['prior_touches']=level['touches']
            level['prior_accepted_up']=level['accepted_up']; level['prior_accepted_down']=level['accepted_down']
            if row['open_ms'] < level['confirmed_ms']: continue
            x,z=level['price'],level['z']
            touches=row['low'] <= x+z and row['high'] >= x-z
            if touches:
                if not level['episode']: level['touches']+=1
                level['episode']=True; level['outside']=0
            else:
                level['outside']+=1
                if level['outside']>=2: level['episode']=False
            b=max(dec('.10')*self.config.scale*level['atr'],2*self.tick)
            level['up']=level['up']+1 if row['close']>=x+b else 0
            level['down']=level['down']+1 if row['close']<=x-b else 0
            level['accepted_up'] |= level['up']>=2
            level['accepted_down'] |= level['down']>=2

    def update_hour(self, row):
        if not self.hour_parts or row['open_ms']//HOUR != self.hour_parts[0]['open_ms']//HOUR:
            self.hour_parts=[]
        self.hour_parts.append(row)
        if row['open_ms']+BAR != (row['open_ms']//HOUR+1)*HOUR: return
        parts=self.hour_parts
        if len(parts)!=4 or parts[0]['open_ms']%HOUR or any(b['open_ms']-a['open_ms']!=BAR for a,b in zip(parts,parts[1:])):
            self.state='TRANSITION'; return
        h=dict(open_ms=parts[0]['open_ms'],open=parts[0]['open'],close=parts[-1]['close'],
               high=max(r['high'] for r in parts),low=min(r['low'] for r in parts),
               quote_volume=sum(r['quote_volume'] for r in parts),available_ms=max(r['available_ms'] for r in parts))
        self.hour_rows.append(h); v=self.hour.push(h)
        for p in pivot(self.hour_rows):
            p['confirmed_ms']+=HOUR; self.hour_pivots.append(p)
        self.hour_pivots=[p for p in self.hour_pivots if p['confirmed_ms']+48*HOUR>h['open_ms']+HOUR]
        self.box=None
        ah=v['atr']; last=list(self.hour_rows)[-24:]
        if ah and len(last)==24:
            lo=min(r['low'] for r in last); hi=max(r['high'] for r in last)
            def edge(side, price):
                anchors=sorted(p['anchor_ms'] for p in self.hour_pivots if p['side']==side and p['anchor_ms']>=last[0]['open_ms'] and abs(p['price']-price)<=dec('.25')*self.config.scale*ah and p['known_ms']<=h['available_ms'])
                return bool(anchors and anchors[-1]-anchors[0]>=3*HOUR)
            if 4*self.config.scale <= (hi-lo)/ah <= 10*self.config.scale and edge('low',lo) and edge('high',hi):
                self.box=dict(low=lo,high=hi,atr=ah,mid=(lo+hi)/2,hour_end_ms=h['open_ms']+HOUR)
        trend_er,range_er,trend_slope,range_slope={
            'base':('.35','.25','.01','.005'),'loose':('.30','.30','.008','.006'),
            'tight':('.40','.20','.012','.004')}[self.config.regime_neighbor]
        raw='TRANSITION'
        if v['stable'] and ah and v['slope'] is not None and v['er'] is not None:
            if h['close']>v['ema200']+dec('.25')*ah and v['ema20']>v['ema50']>v['ema200'] and (v['ema20']-v['ema50'])/ah>=dec('.25') and v['slope']>=dec(trend_slope) and v['er']>=dec(trend_er): raw='TREND_UP'
            elif h['close']<v['ema200']-dec('.25')*ah and v['ema20']<v['ema50']<v['ema200'] and (v['ema50']-v['ema20'])/ah>=dec('.25') and v['slope']<=-dec(trend_slope) and v['er']>=dec(trend_er): raw='TREND_DOWN'
            elif v['er']<=dec(range_er) and abs(v['slope'])<=dec(range_slope) and self.box: raw='HEALTHY_RANGE'
        self.raw_count=self.raw_count+1 if raw==self.raw else 1
        self.raw=raw; self.state=raw if raw!='TRANSITION' and self.raw_count>=2 else 'TRANSITION'

    def push(self, row):
        if self.rows and row['open_ms']!=self.rows[-1]['open_ms']+BAR: self.reset_gap()
        previous=self.values[-1] if self.values else None
        self.rows.append(row); v=self.exec.push(row); self.values.append(v)
        self.update_hour(row)
        end=row['open_ms']+BAR
        self.levels=[x for x in self.levels if x['expires_ms']>end]
        for p in pivot(self.rows):
            self.add_level('swing',p['side'],p['price'],p['anchor_ms'],p['confirmed_ms']+BAR,p['known_ms'],v['atr'])
        if end%DAY==0:
            day=list(self.rows)[-96:]
            if len(day)==96 and day[0]['open_ms']==end-DAY:
                for side in ('high','low'):
                    self.add_level('previous_day',side,(max if side=='high' else min)(r[side] for r in day),end-DAY,end,max(r['available_ms'] for r in day),v['atr'])
        self.update_behavior(row)
        if v['shock']: self.shock_wait=True; self.calm=0
        elif self.shock_wait:
            self.calm=self.calm+1 if v['calm'] else 0
            if self.calm>=8: self.shock_wait=False
        self.prefix=fingerprint([self.prefix,jsonable(row)])
        return previous,v

    def ready(self, end, when):
        if not self.values or not self.values[-1]['stable'] or not self.hour.values or not self.hour.values[-1]['stable']: return 'warmup'
        expected=end//HOUR*HOUR
        if not self.hour_rows or self.hour_rows[-1]['open_ms']+HOUR!=expected or self.hour_rows[-1]['available_ms']>when: return 'missing_context'
        if self.shock_wait: return 'shock_cooldown'
        return None

    def box_valid(self, frozen):
        if self.state!='HEALTHY_RANGE' or not self.box or not frozen: return False
        a=frozen['atr']; close=self.hour_rows[-1]['close']
        return (frozen['low']-dec('.25')*a <= close <= frozen['high']+dec('.25')*a
                and abs(self.box['low']-frozen['low'])<=dec('.50')*a and abs(self.box['high']-frozen['high'])<=dec('.50')*a)
