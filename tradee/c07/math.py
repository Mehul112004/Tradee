"""Exact monetary calculations; diagnostic ratios have explicit rounding."""
from contextlib import contextmanager
from decimal import Decimal, Inexact, Rounded, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext
from math import lcm
from fractions import Fraction

from tradee.c01 import ValidationError
from tradee.c02.domain import number
from tradee.c06.contracts import decimal_text


@contextmanager
def exact():
    with localcontext() as ctx:
        ctx.prec=400; ctx.traps[Inexact]=ctx.traps[Rounded]=True
        yield


def dec(value): return Decimal(str(value))


def ratio(numerator,denominator):
    if denominator==0: return None
    with localcontext() as ctx:
        ctx.prec=400; ctx.traps[Inexact]=ctx.traps[Rounded]=False
        return decimal_text((numerator/denominator).quantize(Decimal('0.000000000001'),rounding=ROUND_HALF_EVEN))


def common_step(steps):
    values=[Decimal(number(s,positive=True)) for s in steps]
    with exact():
        scale=Decimal(10)**max(0,max(-v.as_tuple().exponent for v in values))
        return Decimal(lcm(*(int(v*scale) for v in values)))/scale


def quantity(requested,filters,mode):
    """Both general and market-lot grids apply; floor never increases exposure."""
    with exact():
        q=dec(requested); step=common_step([filters[k]['stepSize'] for k in ('LOT_SIZE','MARKET_LOT_SIZE')])
        floor=q-(q%step)
        reasons=[]
        if q!=floor and mode=='reject': reasons.append('quantity_off_step')
        effective=floor if mode=='floor' else q
        for k in ('LOT_SIZE','MARKET_LOT_SIZE'):
            lo,hi=(dec(filters[k][key]) for key in ('minQty','maxQty'))
            if effective<lo or effective<=0: reasons.append('quantity_below_minimum')
            if hi and effective>hi: reasons.append('quantity_above_maximum')
        return effective,step,sorted(set(reasons))


def adverse_tick(price,tick,side):
    with exact():
        tick=dec(tick)
        if tick<=0: raise ValidationError('Positive tick required')
        remainder=price%tick
        return price-remainder+(tick if side=='buy' and remainder else 0)


def fee(quantity,price,rate):
    with exact(): return decimal_text(dec(quantity)*dec(price)*dec(rate))


def modeled_price(touch,q,visible,extra,coefficient,tick,side):
    """Round a rational impact price to a tick without an intermediate rounded quotient."""
    if visible<=0: raise ValidationError('Positive liquidity proxy required')
    sign=1 if side=='buy' else -1
    raw=Fraction(touch)*(1+sign*(Fraction(dec(extra))+Fraction(coefficient)*Fraction(q)/Fraction(visible))/10000)
    units=raw/Fraction(dec(tick))
    count=-(-units.numerator//units.denominator) if side=='buy' else units.numerator//units.denominator
    with exact(): return dec(tick)*count


def fill_costs(intent,quantity,mid,touch,fill,rate):
    """Shortfall decomposition is attribution; never add it again to fill-price P&L."""
    with exact():
        sign=Decimal(1 if intent.side=='buy' else -1); ref=dec(intent.reference_price)
        drift=sign*(mid-ref)*quantity; spread=sign*(touch-mid)*quantity; slip=sign*(fill-touch)*quantity
        commission=quantity*fill*dec(rate); shortfall=sign*(fill-ref)*quantity
        risk=None if intent.stop_price is None else abs(ref-dec(intent.stop_price))*quantity
        total=shortfall+commission
        return dict(delay_drift_usdt=decimal_text(drift),spread_crossing_usdt=decimal_text(spread),
            extra_slippage_and_rounding_usdt=decimal_text(slip),implementation_shortfall_usdt=decimal_text(shortfall),
            fee_usdt=decimal_text(commission),execution_plus_fee_cost_usdt=decimal_text(total),
            cost_bps=ratio(total*10000,quantity*ref),planned_risk_usdt=None if risk is None else decimal_text(risk),
            cost_r=None if risk is None else ratio(total,risk),
            attribution='drift + spread + extra slippage = implementation shortfall; fills already contain shortfall, add only fee to realized fill-price P&L')
