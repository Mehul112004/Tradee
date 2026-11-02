"""Frozen v1 definitions. Performance cannot mutate a running definition."""
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_CEILING
import math

from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint

BAR = 900000
HOUR = 3600000
DAY = 86400000
FAMILIES = ('liquidity_sweep_v1', 'ema200_rejection_v1', 'key_level_retest_v1')
MODES = ('sweep_trend', 'sweep_range', 'ema_trend', 'retest_trend')
PRIORITY = {FAMILIES[0]: 0, FAMILIES[2]: 1, FAMILIES[1]: 2}
WARMUP_BARS = 6800  # >=1587 complete hours, including incomplete boundary margins.


def dec(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite(): raise ValueError()
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError('Finite decimal required') from None


def text(value):
    return format(dec(value), 'f')


def jsonable(value):
    if isinstance(value, Decimal): return text(value)
    if isinstance(value, dict): return {k:jsonable(v) for k,v in value.items()}
    if isinstance(value, (tuple,list)): return [jsonable(v) for v in value]
    return value


def rounded(value, tick, up=False):
    return (dec(value) / dec(tick)).to_integral_value(rounding=ROUND_CEILING if up else ROUND_FLOOR) * dec(tick)


@dataclass(frozen=True)
class PilotConfig:
    version: int = 1
    geometry_scale: str = '1'
    regime_filter: bool = True
    dull_filter: bool = True
    exhaustion_filter: bool = True
    regime_neighbor: str = 'base'
    context_profile: str = 'strict_v1'

    def __post_init__(self):
        if type(self.version) is not int or self.version != 1: raise ValidationError('Unsupported pilot version')
        if dec(self.geometry_scale) not in (dec('.8'), dec('1'), dec('1.2')):
            raise ValidationError('Only preregistered geometry neighbors are supported')
        object.__setattr__(self,'geometry_scale',format(dec(self.geometry_scale).normalize(),'f'))
        for name in ('regime_filter', 'dull_filter', 'exhaustion_filter'):
            if type(getattr(self, name)) is not bool: raise ValidationError('Explicit filter booleans required')
        if self.regime_neighbor not in ('base', 'loose', 'tight'): raise ValidationError('Unsupported regime neighbor')
        if self.context_profile not in ('strict_v1','balanced_v2'): raise ValidationError('Unknown context profile')
        if self.context_profile=='balanced_v2' and (self.geometry_scale!='1' or self.regime_neighbor!='base' or not all((self.regime_filter,self.dull_filter,self.exhaustion_filter))):
            raise ValidationError('Balanced v2 is one fixed research definition, not an extra search grid')

    @property
    def scale(self): return dec(self.geometry_scale)

    def document(self): return asdict(self)

    @property
    def digest(self): return fingerprint(self.document())


def candle(row, interval=BAR):
    if not isinstance(row, dict) or type(row.get('open_ms')) is not int or row['open_ms'] < 0 or row['open_ms'] % interval:
        raise ValidationError('Aligned completed pilot candle required')
    r = dict(row)
    for k in ('open', 'high', 'low', 'close', 'quote_volume'):
        r[k] = dec(row[k])
        if r[k] < 0 or k != 'quote_volume' and r[k] == 0: raise ValidationError('Invalid pilot candle price/volume')
    if not r['low'] <= min(r['open'], r['close']) <= max(r['open'], r['close']) <= r['high']:
        raise ValidationError('Invalid pilot candle envelope')
    values = {float(r[k]): r[k] for k in ('open', 'high', 'low', 'close')}
    if (len(values) != len({r[k] for k in ('open', 'high', 'low', 'close')}) or not all(math.isfinite(v) and v>0 for v in values)):
        raise ValidationError('Source price distinctions lost in float64')
    r['available_ms'] = row.get('available_ms', row['open_ms'] + interval)
    if type(r['available_ms']) is not int or r['available_ms'] < row['open_ms'] + interval:
        raise ValidationError('Completed candle cannot be known before its close')
    return r
