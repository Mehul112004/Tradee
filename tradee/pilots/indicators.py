"""Incremental C03 recurrences, prefix-only ranks and causal 2/2 pivots."""
from collections import deque
from statistics import median

from tradee.c03.rolling import Smoother
from tradee.c05.levels import strict_swing_extreme
from .contracts import dec


class Measurements:
    def __init__(self):
        self.ema = {n: Smoother(n) for n in (20, 50, 200)}
        self.atr = Smoother(14, 'rma')
        self.rows, self.values = deque(maxlen=720), deque(maxlen=720)
        self.ranks = deque(maxlen=672)
        self.sign, self.crosses = 0, deque(maxlen=32)
        self.count = 0

    def push(self, row):
        previous = self.rows[-1] if self.rows else None
        tr = None if previous is None else max(row['high']-row['low'], abs(row['high']-previous['close']), abs(row['low']-previous['close']))
        atr = self.atr.push(float(tr)) if tr is not None else None
        e = {n: self.ema[n].push(float(row['close'])) for n in self.ema}
        stable = (all(s.value is not None and s.seed_weight <= 1e-6 for s in (*self.ema.values(), self.atr))
                  and self.ema[200].updates >= 5 and self.ema[200].seed_weight/(1-self.ema[200].alpha)**5 <= 1e-6)
        fraction = dec(atr)/row['close'] if atr is not None else None
        percentile = None
        if fraction is not None and len(self.ranks) == 672:
            percentile = dec(100)*(sum(v < fraction for v in self.ranks)+dec('.5')*sum(v == fraction for v in self.ranks))/672
        volume = sum(r['quote_volume'] for r in list(self.rows)[-20:]) if len(self.rows) >= 20 else None
        rv = row['quote_volume']*20/volume if volume else None
        slope = (dec(e[200])-self.values[-5]['ema200'])/(5*dec(atr)) if len(self.values) >= 5 and self.values[-5]['ema200'] is not None and e[200] is not None and atr else None
        sign = (row['close'] > dec(e[200]))-(row['close'] < dec(e[200])) if e[200] is not None else 0
        self.crosses.append(int(bool(sign and self.sign and sign != self.sign)))
        if sign: self.sign = sign
        er = None
        if len(self.rows) >= 24:
            path = [r['close'] for r in list(self.rows)[-24:]]+[row['close']]
            total = sum(abs(b-a) for a,b in zip(path,path[1:]))
            er = abs(path[-1]-path[0])/total if total else dec(0)
        prior_atr = self.values[-1]['atr'] if self.values else None
        gap = abs(row['open']-previous['close'])/prior_atr if previous and prior_atr else None
        v = dict(atr=None if atr is None else dec(atr), tr=tr, rv=rv, fraction=fraction,
                 percentile=percentile, slope=slope, er=er, crosses=sum(self.crosses),
                 stable=stable, gap=gap, count=self.count+1,
                 **{'ema'+str(n): None if x is None else dec(x) for n,x in e.items()})
        recent = list(self.values)[-7:]+[v]
        span = max(r['high'] for r in list(self.rows)[-15:]+[row])-min(r['low'] for r in list(self.rows)[-15:]+[row])
        v['dull'] = (not stable or not atr or fraction < dec('.001') or percentile is None or percentile < 20
                     or len(recent) < 8 or any(x['rv'] is None for x in recent)
                     or median([x['rv'] for x in recent if x['rv'] is not None]) < dec('.70') or span < 2*dec(atr))
        v['shock'] = bool(prior_atr and (tr > 3*prior_atr or gap > dec('.75')) or percentile is not None and percentile > dec('97.5') or fraction is not None and fraction > dec('.02'))
        v['calm'] = bool(prior_atr and tr <= 2*prior_atr and gap <= dec('.75') and percentile is not None and percentile <= 95 and fraction <= dec('.02'))
        self.rows.append(row); self.values.append(v); self.count += 1
        if fraction is not None: self.ranks.append(fraction)
        return v


def pivot(rows):
    if len(rows) < 5: return []
    w = list(rows)[-5:]; result=[]
    for side in ('high','low'):
        x=w[2][side]; others=[r[side] for i,r in enumerate(w) if i != 2]
        if strict_swing_extreme(x,others,side):
            result.append(dict(side=side, price=x, anchor_ms=w[2]['open_ms'],
                               confirmed_ms=w[-1]['open_ms'], known_ms=max(r['available_ms'] for r in w)))
    return result
