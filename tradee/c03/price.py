"""Price movement and location, with explicit window endpoints."""
import math
from .rolling import divide, finite, mean, sd0


def log_return(current, previous):
    if current <= 0 or previous <= 0:
        raise ArithmeticError('Log returns require positive prices')
    change = (current-previous)/previous
    # log1p preserves small changes; log subtraction avoids ratio under/overflow.
    return finite(math.log1p(change) if abs(change) < 0.5 else math.log(current)-math.log(previous))


def prior_z(current, prior):
    shifted = [v-prior[0] for v in prior]
    return divide((current-prior[0])-mean(shifted), sd0(prior))


def shape(o, h, l, c):
    span = h-l
    return dict(body_fraction=divide(c-o, span), upper_wick_fraction=divide(h-max(o,c), span),
                lower_wick_fraction=divide(min(o,c)-l, span), close_location=divide((c-l)-(h-c), span))
