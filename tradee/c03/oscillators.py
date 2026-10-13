"""Wilder RSI and population-variance Bollinger bands."""
from .rolling import smooth, mean, sd0, divide


def rsi(closes, n=14):
    changes = [closes[i]-closes[i-1] for i in range(1, len(closes))]
    gains = smooth([max(v, 0) for v in changes], n, 'rma')
    losses = smooth([max(-v, 0) for v in changes], n, 'rma')
    values = [None] if closes else []
    flat = [False] if closes else []
    for gain, loss in zip(gains, losses):
        values.append(None if gain is None else 50.0 if gain+loss == 0 else 100*gain/(gain+loss))
        flat.append(gain is not None and gain+loss == 0)
    return values, flat


def bands(closes, k=2):
    middle, deviation = mean(closes), sd0(closes)
    # Compute width directly to avoid subtracting nearby price-level endpoints.
    width = 2*k*deviation
    return dict(middle=middle, upper=middle+k*deviation, lower=middle-k*deviation,
                width=divide(width, middle),
                pct_b=None if width == 0 else 0.5+divide(closes[-1]-middle, width))
