"""Accumulate exchange volume fields exactly; no typical-price VWAP proxy."""
from decimal import Decimal, localcontext
from .rolling import finite


def ratio_sums(rows, numerator, denominator):
    with localcontext() as ctx:
        ctx.prec = 120
        top = sum((Decimal(str(r[numerator])) for r in rows), Decimal(0))
        bottom = sum((Decimal(str(r[denominator])) for r in rows), Decimal(0))
        if bottom == 0:
            raise ZeroDivisionError('zero_denominator')
        return finite(top/bottom)


def vwap(rows):
    return ratio_sums(rows, 'quote_volume', 'volume')


def imbalance(rows, quote=False):
    return 2*ratio_sums(rows, 'taker_quote' if quote else 'taker_base', 'quote_volume' if quote else 'volume')-1


def relative_volume(current, prior):
    with localcontext() as ctx:
        ctx.prec = 120
        total = sum((Decimal(str(r['quote_volume'])) for r in prior), Decimal(0))
        if total == 0:
            raise ZeroDivisionError('zero_denominator')
        return finite(Decimal(str(current['quote_volume']))*len(prior)/total)


def mean_trade_notional(row):
    return ratio_sums([row], 'quote_volume', 'trades')
