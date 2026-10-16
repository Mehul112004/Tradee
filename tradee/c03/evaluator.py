"""Evaluate selected features on one contiguous segment; shared lazy dependencies."""
import math

from .catalog import definition, seed_weight
from .contracts import FeatureValue
from .rolling import exact_floats, smooth, divide, mean, sd0, finite
from .price import log_return, prior_z, shape
from .volatility import atr, returns, true_ranges, realized_variance
from .oscillators import rsi, bands
from .participation import vwap, relative_volume, imbalance, mean_trade_notional


class Evaluator:
    def __init__(self, rows, threshold=1e-6, gap=False, session_rows=None):
        self.rows, self.threshold, self.gap, self.session_rows = rows, threshold, gap, session_rows
        self.results, self.arrays, self.price_arrays = {}, {}, {}

    def prices(self, fields=('close',), window=None):
        key = (fields, window)
        if key not in self.price_arrays:
            rows = self.rows if window is None else self.rows[-window:]
            flat = exact_floats([r[k] for r in rows for k in fields])
            self.price_arrays[key] = {field: flat[offset::len(fields)] for offset,field in enumerate(fields)}
        return self.price_arrays[key]

    def series(self, key):
        if key not in self.arrays:
            if key.startswith('ema'):
                value = smooth(self.prices()['close'], int(key[3:]))
            elif key == 'atr':
                p = self.prices(('high','low','close'))
                value = atr(p['high'], p['low'], p['close'])
            elif key == 'returns':
                value = returns(self.prices(window=22)['close'])
            elif key == 'rsi':
                value = rsi(self.prices()['close'])
            elif key == 'bands':
                value = bands(self.prices(window=20)['close'])
            else:
                raise ValueError('Unknown internal series')
            self.arrays[key] = value
        return self.arrays[key]

    def get(self, name):
        if name in self.results:
            return self.results[name]
        spec = definition(name)
        count = len(self.rows)
        weight = seed_weight(name, count)
        status, value, flags = 'valid', None, ()
        if count < spec.min_bars:
            status = 'gap_in_window' if self.gap else 'insufficient_history'
        else:
            try:
                for dependency in spec.dependencies:
                    dep = self.get(dependency)
                    if dep.status != 'valid':
                        status = dep.status
                        break
                if status == 'valid':
                    value = finite(self.calculate(name))
                    if name == 'rsi14' and self.series('rsi')[1][-1]:
                        flags = ('flat_series',)
            except ZeroDivisionError:
                status = 'zero_denominator'
            except (ArithmeticError, ValueError):
                status = 'numeric_error'
        result = FeatureValue(value, status, spec.min_bars, count,
                              status == 'valid' and weight <= self.threshold, weight, flags)
        self.results[name] = result
        return result

    def calculate(self, name):
        rows = self.rows
        if name == 'vwap20':
            return vwap(rows[-20:])
        if name == 'vwap_utc_session':
            if self.session_rows is None:
                # Handled separately so absence isn't a numeric error.
                raise ValueError('Session input must be supplied')
            return vwap(self.session_rows)
        if name == 'relative_quote_volume20_prior':
            return relative_volume(rows[-1], rows[-21:-1])
        if name in ('taker_base_imbalance20','taker_quote_imbalance20'):
            return imbalance(rows[-20:], quote=name.startswith('taker_quote'))
        if name == 'mean_trade_quote_notional':
            return mean_trade_notional(rows[-1])
        if name in ('ema20','ema50'):
            return self.series(name)[-1]
        if name in ('ema20_prior','ema50_prior'):
            return self.series(name.removesuffix('_prior'))[-2]
        if name == 'atr14':
            return self.series('atr')[-1]
        if name == 'rsi14':
            return self.series('rsi')[0][-1]
        fields = ('close',)
        if name in ('tr', 'range_atr14_prior'):
            fields = ('high','low','close')
        if name in ('body_fraction','upper_wick_fraction','lower_wick_fraction','close_location'):
            fields = ('open','high','low','close')
        p = self.prices(fields, definition(name).min_bars)
        c = p['close'][-1]
        def dep(key):
            return self.results[key].value
        if name.startswith('log_return_'):
            n = int(name.rsplit('_',1)[1])
            return log_return(c, p['close'][-n-1])
        if name.startswith('simple_return_'):
            n = int(name.rsplit('_',1)[1])
            return divide(c-p['close'][-n-1], p['close'][-n-1])
        if name == 'sma20':
            return mean(p['close'][-20:])
        if name == 'tr':
            return true_ranges(p['high'][-2:],p['low'][-2:],p['close'][-2:])[0]
        if name == 'atr14_fraction':
            return divide(dep('atr14'),c)
        if name == 'ema20_distance_atr14':
            return divide(c-dep('ema20'),dep('atr14'))
        if name == 'ema20_50_spread_atr14':
            return divide(dep('ema20')-dep('ema50'),dep('atr14'))
        if name == 'ema20_slope5_atr14':
            return divide(dep('ema20')-self.series('ema20')[-6],5*dep('atr14'))
        if name == 'return_sd20':
            return sd0(self.series('returns')[-20:])
        if name == 'realized_variance20':
            return realized_variance(self.series('returns')[-20:])
        if name == 'realized_vol20':
            return math.sqrt(dep('realized_variance20'))
        if name == 'return_surprise20_prior':
            rs = self.series('returns')
            return prior_z(rs[-1],rs[-21:-1])
        if name == 'close_z20_prior':
            return prior_z(c,p['close'][-21:-1])
        if name in ('vwap20_distance_atr14','vwap_utc_session_distance_atr14'):
            return divide(c-dep('vwap20' if name.startswith('vwap20') else 'vwap_utc_session'),dep('atr14'))
        if name.startswith('bb20_'):
            key = name[5:].replace('width_fraction','width')
            value = self.series('bands')[key]
            if value is None:
                raise ZeroDivisionError
            return value
        if name == 'range_atr14_prior':
            return divide(p['high'][-1]-p['low'][-1],self.series('atr')[-2])
        return shape(p['open'][-1],p['high'][-1],p['low'][-1],c)[name]
