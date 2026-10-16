"""Exact strategy-specific range boundaries over C03 aggregated candle data."""
from decimal import Decimal
from tradee.c01 import ValidationError
from tradee.c02.domain import number


def prior_range(rows,lookback,interval):
    if type(lookback) is not int or lookback<2 or type(interval) is not int or interval<=0:
        raise ValidationError('Invalid range window')
    if len(rows)<lookback+1: return None
    window=rows[-lookback-1:]
    if any(b['open_ms']!=a['open_ms']+interval for a,b in zip(window,window[1:])):
        return None
    prior,current=window[:-1],window[-1]
    high=max((number(r['high'],positive=True) for r in prior),key=Decimal)
    low=min((number(r['low'],positive=True) for r in prior),key=Decimal)
    close=number(current['close'],positive=True)
    return dict(upper=high,lower=low,reference_price=close,start_ms=prior[0]['open_ms'],end_ms=current['open_ms'],
                long=Decimal(close)>Decimal(high),short=Decimal(close)<Decimal(low))


def trend_recovery(previous,current,previous_values,current_values):
    """EMA inputs and comparisons follow C03 float64; exact source prices retained."""
    from tradee.c03.rolling import exact_floats
    import math
    vals=[previous_values[k]['value'] for k in ('ema20','ema50')]+[current_values[k]['value'] for k in ('ema20','ema50')]
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in vals):
        raise ValidationError('Invalid EMA recovery measurements')
    old,close=exact_floats([previous['close'],current['close']])
    p20,p50,e20,e50=vals
    return dict(reference_price=current['close'],start_ms=previous['open_ms'],end_ms=current['open_ms'],
        level=number(repr(float(e20)),positive=True),
        context=dict(previous_close=previous['close'],previous_ema20=number(repr(float(p20)),positive=True),
                     previous_ema50=number(repr(float(p50)),positive=True),ema20=number(repr(float(e20)),positive=True),
                     ema50=number(repr(float(e50)),positive=True)),
        long=e20>e50 and old<=p20 and close>e20,short=e20<e50 and old>=p20 and close<e20)
