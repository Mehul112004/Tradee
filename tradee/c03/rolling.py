"""Small, explicit numerical primitives. No data access or implicit imputation."""
from collections import deque
from decimal import Decimal
import math

from tradee.c01 import ValidationError


def period(n):
    if type(n) is not int or not 1 <= n <= 10000:
        raise ValidationError('Period must be an integer from 1 to 10000')
    return n


def finite(value):
    result = float(value)
    if not math.isfinite(result):
        raise ArithmeticError('Nonfinite analytical result')
    if result == 0 and value != 0 and Decimal(str(value)) != 0:
        raise ArithmeticError('Float conversion underflow')
    return result


def exact_floats(values):
    """Detect distinct exact source prices collapsing to the same binary float."""
    result, seen = [], {}
    for value in values:
        dec = Decimal(str(value))
        number = finite(dec)
        if number in seen and seen[number] != dec:
            raise ArithmeticError('Source distinctions lost during float conversion')
        seen[number] = dec
        result.append(number)
    return result


def mean(values):
    if not values:
        raise ValueError('Empty window')
    return finite(math.fsum(values)/len(values))


def sd0(values):
    # Shift before centering to preserve small differences at a large price scale.
    shifted = [v-values[0] for v in values]
    m = mean(shifted)
    return finite(math.sqrt(math.fsum((v-m)**2 for v in shifted)/len(values)))


def divide(numerator, denominator):
    if denominator == 0:
        raise ZeroDivisionError('zero_denominator')
    return finite(numerator/denominator)


class Window:
    def __init__(self, n, values=()):
        self.n = period(n)
        self.values = deque((finite(v) for v in values), maxlen=n)

    def push(self, value):
        self.values.append(finite(value))
        return tuple(self.values) if len(self.values) == self.n else None

    def document(self):
        return {'n': self.n, 'values': list(self.values)}


class Smoother:
    """SMA seed followed by EMA or Wilder recurrence; restartable without pickle."""
    def __init__(self, n, mode='ema'):
        self.n = period(n)
        if mode not in ('ema', 'rma'):
            raise ValidationError('Unknown smoother')
        self.mode, self.seed, self.value, self.updates = mode, [], None, 0

    @property
    def alpha(self):
        return 2/(self.n+1) if self.mode == 'ema' else 1/self.n

    @property
    def seed_weight(self):
        return 1.0 if self.value is None else (1-self.alpha)**self.updates

    def push(self, value):
        value = finite(value)
        if self.value is None:
            self.seed.append(value)
            if len(self.seed) == self.n:
                self.value = mean(self.seed)
                self.seed.clear()
        else:
            self.value = finite(self.value+self.alpha*(value-self.value))
            self.updates += 1
        return self.value

    def document(self):
        return dict(n=self.n, mode=self.mode, seed=list(self.seed), value=self.value, updates=self.updates)

    @classmethod
    def restore(cls, doc):
        obj = cls(doc['n'], doc['mode'])
        if type(doc['updates']) is not int or doc['updates'] < 0 or len(doc['seed']) >= obj.n:
            raise ValidationError('Invalid smoother checkpoint')
        obj.seed = [finite(v) for v in doc['seed']]
        obj.value = None if doc['value'] is None else finite(doc['value'])
        obj.updates = doc['updates']
        if (obj.value is None and obj.updates) or (obj.value is not None and obj.seed):
            raise ValidationError('Inconsistent smoother state')
        return obj


def smooth(values, n, mode='ema'):
    smoother = Smoother(n, mode)
    return [smoother.push(v) for v in values]
