"""Finite-capital modeled replay. Unknown exits retain positions and reserves."""
from collections import Counter,defaultdict
from decimal import ROUND_FLOOR

from .contracts import DAY,dec,jsonable


class RiskBook:
    def __init__(self,capital='10000'):
        self.cash=dec(capital)
        if self.cash<=0: raise ValueError('Positive predeclared capital required')
        self.initial=self.cash; self.positions={}; self.peak=self.cash; self.max_dd=dec(0)
        self.day,self.week=None,None; self.day_start,self.week_start=self.cash,self.cash
        self.pause_day,self.pause_week=None,None; self.halted=False; self.streak=0
        self.losses=Counter(); self.rejections=Counter(); self.closed=[]; self.regimes=defaultdict(lambda:dec(0))

    @property
    def equity(self): return self.cash+sum((p['quantity']*p['pnl'] for p in self.positions.values()),dec(0))

    def circuits(self):
        equity=self.equity; self.peak=max(self.peak,equity)
        drawdown=(self.peak-equity)/self.peak; self.max_dd=max(self.max_dd,drawdown)
        if equity<=self.day_start*dec('.99'): self.pause_day=max(self.pause_day if self.pause_day is not None else -1,self.day)
        if equity<=self.week_start*dec('.97'): self.pause_week=max(self.pause_week if self.pause_week is not None else -1,self.week)
        if drawdown>=dec('.06'): self.halted=True

    def roll(self,now):
        day=now//DAY; week=(day+3)//7
        if self.day!=day: self.day=day; self.day_start=self.equity
        if self.week!=week: self.week=week; self.week_start=self.equity

    def advance(self,now,updates=(),closures=()):
        # One clock group: all already-known marks/exits precede new admissions.
        if self.day is None: self.roll(now)
        for update in updates:
            trade_id,pnl,regime=update[:3]
            p=self.positions.get(trade_id)
            if p is None: continue
            value=dec(pnl); self.regimes[regime]+=p['quantity']*(value-p['pnl'])
            p['pnl']=value; p['mark_ms']=now
            if len(update)>3: p['mark_price']=dec(update[3])
        for trade_id in closures:
            p=self.positions.pop(trade_id,None)
            if p is None: continue
            net=p['quantity']*p['pnl']; self.cash+=net
            self.closed.append(dict(id=trade_id,at_ms=now,net=net,quantity=p['quantity'],symbol=p['symbol'],family=p['family']))
            if net<0:
                self.streak+=1; self.losses[(now//DAY,p['family'],p['symbol'])]+=1
                if self.streak>=3: self.pause_day=now//DAY
            else: self.streak=0
        self.circuits(); self.roll(now)

    def admit(self,trade,now,*,step='.001',minimum='.001',min_notional='5'):
        self.roll(now); self.circuits(); plan=trade['plan']; symbol=plan['symbol']; family=plan['strategy']; reason=None
        if self.halted: reason='campaign_drawdown'
        elif self.pause_day==self.day or self.pause_week==self.week: reason='risk_pause'
        elif self.losses[(self.day,family,symbol)]>=2: reason='family_loss_pause'
        elif any(p['symbol']==symbol for p in self.positions.values()): reason='instrument_occupied'
        elif len(self.positions)>=2: reason='position_cap'
        elif any(now-p['mark_ms']>60000 for p in self.positions.values()): reason='mark_unknown'
        equity=self.equity; unit=dec(trade['expected_stopped_loss']); entry=dec(trade['entry'])
        if equity<=0 or unit<=0 or entry<=0: reason='invalid_risk'
        quantity=dec(0)
        if reason is None:
            reserved=sum((p['quantity']*p['unit_risk'] for p in self.positions.values()),dec(0))
            gross=sum((p['quantity']*p['mark_price'] for p in self.positions.values()),dec(0))
            notional=dec(trade.get('entry_mid',entry))
            capacity=min(dec('.0025')*equity/unit,(dec('.005')*equity-reserved)/unit,(equity-gross)/notional)
            quantity=(capacity/dec(step)).to_integral_value(rounding=ROUND_FLOOR)*dec(step)
            if quantity<dec(minimum) or quantity*entry<dec(min_notional): reason='quantity_below_minimum'
        if reason:
            self.rejections[reason]+=1; return dict(admitted=False,reason=reason)
        key=plan['opportunity_id']
        if key in self.positions: raise ValueError('Duplicate capital admission')
        self.positions[key]=dict(symbol=symbol,family=family,quantity=quantity,entry=entry,mark_price=dec(trade.get('entry_mid',entry)),unit_risk=unit,
            pnl=dec(0),mark_ms=now)
        return jsonable(dict(admitted=True,quantity=quantity,reserved_risk=quantity*unit))

    def report(self):
        return jsonable(dict(initial_capital=self.initial,marked_equity=self.equity,cash=self.cash,
            valuation_basis='last available modeled contract closes; unresolved/stale exposure is retained',
            max_marked_drawdown=self.max_dd,halted=self.halted,open_unresolved_positions=len(self.positions),
            reserved_risk=sum((p['quantity']*p['unit_risk'] for p in self.positions.values()),dec(0)),
            admissions=len(self.closed)+len(self.positions),closed=self.closed,rejections=dict(self.rejections),
            time_in_regime_pnl=dict(self.regimes),positions=self.positions,live_approved=False))


def replay_capital(trades,capital='10000'):
    events=defaultdict(lambda:dict(entries=[],marks=[],closures=[])); book=RiskBook(capital)
    for t in trades:
        if 'entry_ms' not in t: continue
        key=t['plan']['opportunity_id']; events[t['entry_ms']]['entries'].append(t)
        for m in t['marks']: events[m['at_ms']]['marks'].append((key,m['pnl'],m['regime'],m.get('price',t['entry'])))
        if t['status']=='modeled_closed': events[t['exit_ms']]['closures'].append(key)
    for now,event in sorted(events.items()):
        # Update/close existing positions first; marks for newly admitted positions follow admission.
        book.advance(now,event['marks'],sorted(event['closures']))
        for trade in sorted(event['entries'],key=lambda t:(t['plan']['symbol'],t['plan']['strategy'],t['plan']['opportunity_id'])):
            admission=book.admit(trade,now)
            if admission['admitted']:
                key=trade['plan']['opportunity_id']
                initial=[m for m in event['marks'] if m[0]==key]
                book.advance(now,initial)
    return book.report()
