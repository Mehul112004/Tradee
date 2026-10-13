"""True-range and return-based volatility are distinct measurements."""
import math
from .rolling import smooth, finite
from .price import log_return


def true_ranges(highs, lows, closes):
    return [max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
            for i in range(1, len(closes))]


def atr(highs, lows, closes, n=14):
    return [None] + smooth(true_ranges(highs, lows, closes), n, 'rma') if closes else []


def returns(closes):
    return [log_return(closes[i], closes[i-1]) for i in range(1, len(closes))]


def realized_variance(values):
    return finite(math.fsum(v*v for v in values))
