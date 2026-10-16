"""Versioned feature definitions and strict run configuration."""
from dataclasses import dataclass, asdict
import json
import math
import re

from tradee.c01 import ValidationError
from tradee.c01.domain import canonical, fingerprint
from .contracts import FeatureDefinition

TIMEFRAMES = {'1m': 60000, '15m': 900000, '1h': 3600000, '4h': 14400000, '1d': 86400000}
BASELINE = ('log_return_1', 'log_return_4', 'log_return_12', 'ema20_distance_atr14',
            'ema20_50_spread_atr14', 'ema20_slope5_atr14', 'return_sd20', 'atr14_fraction',
            'return_surprise20_prior', 'close_z20_prior', 'vwap20_distance_atr14',
            'relative_quote_volume20_prior', 'taker_base_imbalance20', 'rsi14')
CATALOG = {}


def add(name, units, bars, formula, dependencies=(), smoothers=(), inputs=('candle',)):
    params = {}
    if name.startswith('log_return_'):
        params['horizon'] = int(name.rsplit('_', 1)[1])
    if '20' in name:
        params['period'] = 20
    if '14' in name:
        params['wilder_period'] = 14
    if '50' in name:
        params['slow_period'] = 50
    if 'slope5' in name:
        params['lag'] = 5
    if name == 'range_atr14_prior':
        params['lag'] = 1
    if name.startswith('bb20_'):
        params.update(multiplier=2, ddof=0)
    if name in ('return_sd20', 'return_surprise20_prior', 'close_z20_prior'):
        params['ddof'] = 0
    fields = ('close',)
    if inputs == ('quote',):
        fields = ('bid', 'ask', 'bid_qty', 'ask_qty', 'event_ms', 'received_ms')
    elif 'vwap' in name:
        fields = ('volume', 'quote_volume', 'close')
    elif name == 'relative_quote_volume20_prior':
        fields = ('quote_volume',)
    elif name.startswith('taker_'):
        fields = ('quote_volume', 'taker_quote') if 'quote' in name else ('volume', 'taker_base')
    elif name == 'mean_trade_quote_notional':
        fields = ('quote_volume', 'trades')
    elif name in ('tr', 'atr14', 'body_fraction', 'upper_wick_fraction', 'lower_wick_fraction', 'close_location', 'range_atr14_prior'):
        fields = ('open', 'high', 'low', 'close')
    CATALOG[name] = FeatureDefinition(name, units, bars, formula, tuple(dependencies), tuple(inputs), tuple(smoothers),
        parameters=tuple(params.items()), input_fields=fields,
        seed_rule=('SMA seed; recursive coefficients in smoothers; dependencies inherit their seed rules' if smoothers
                   else 'none locally; inherit dependency seed rules' if dependencies else 'none; complete finite window'),
        window_policy='prior baseline excludes current observation' if 'prior' in name else 'current-inclusive; exact offsets in formula')


for horizon in (1, 4, 12):
    add(f'log_return_{horizon}', 'log_return_fraction', horizon+1, f'ln(C[t]/C[t-{horizon}])')
add('sma20', 'price', 20, 'mean(C[t-19:t+1])')
for n in (20, 50):
    add(f'ema{n}', 'price', n, f'SMA seed over {n} closes, then alpha=2/({n}+1)', smoothers=((n,n,'ema',0),))
    add(f'ema{n}_prior', 'price', n+1, f'EMA{n}[t-1]; current close excluded', (f'ema{n}',), ((n,n,'ema',1),))
add('tr', 'price', 2, 'max(H-L, abs(H-Cprev), abs(L-Cprev)); no TR0')
add('atr14', 'price', 15, 'SMA(TR[1:15]) seed then RMA alpha=1/14', ('tr',), ((14,15,'rma',0),))
add('atr14_fraction', 'fraction', 15, 'ATR14/C', ('atr14',))
add('ema20_distance_atr14', 'atr_multiples', 20, '(C-EMA20)/ATR14', ('ema20','atr14'))
add('ema20_50_spread_atr14', 'atr_multiples', 50, '(EMA20-EMA50)/ATR14', ('ema20','ema50','atr14'))
add('ema20_slope5_atr14', 'atr_multiples_per_bar', 25, '(EMA20[t]-EMA20[t-5])/(5*ATR14[t])',
    ('ema20','atr14'), ((20,20,'ema',5),))
add('return_sd20', 'log_return_fraction', 21, 'population_sd(last 20 one-bar log returns)', ('log_return_1',))
add('realized_variance20', 'squared_log_return', 21, 'sum(r*r over last 20 returns)', ('log_return_1',))
add('realized_vol20', 'log_return_fraction', 21, 'sqrt(realized_variance20)', ('realized_variance20',))
add('return_surprise20_prior', 'standardized_return', 22, '(r[t]-mean(r[t-20:t]))/population_sd(r[t-20:t])', ('log_return_1',))
add('close_z20_prior', 'standardized_price', 21, '(C[t]-mean(C[t-20:t]))/population_sd(C[t-20:t])')
add('vwap20', 'price', 20, 'sum(Q[t-19:t+1])/sum(V[t-19:t+1])')
add('vwap20_distance_atr14', 'atr_multiples', 20, '(C-VWAP20)/ATR14', ('vwap20','atr14'))
add('vwap_utc_session', 'price', 1, 'sum(one-minute Q)/sum(one-minute V), complete UTC session through target close')
add('vwap_utc_session_distance_atr14', 'atr_multiples', 15, '(C-session_VWAP)/ATR14', ('vwap_utc_session','atr14'))
add('relative_quote_volume20_prior', 'ratio', 21, 'Q[t]/mean(Q[t-20:t])')
add('taker_base_imbalance20', 'signed_fraction', 20, '(2*sum(TB)-sum(V))/sum(V), last 20 bars')
add('taker_quote_imbalance20', 'signed_fraction', 20, '(2*sum(TQ)-sum(Q))/sum(Q), last 20 bars')
add('mean_trade_quote_notional', 'quote_currency', 1, 'Q/trade_count')
add('rsi14', 'index_0_100', 15, '100*RMA(gain)/(RMA(gain)+RMA(loss)); both zero=50', smoothers=((14,15,'rma',0),))
for name, formula, units in (
    ('middle','SMA20','price'), ('upper','SMA20+2*population_sd(C20)','price'),
    ('lower','SMA20-2*population_sd(C20)','price'), ('width_fraction','4*population_sd(C20)/SMA20','fraction'),
    ('pct_b','0.5+(C-SMA20)/(4*population_sd(C20))','fraction')):
    add('bb20_'+name, units, 20, formula, ('sma20',))
for name, formula in (('body_fraction','(C-O)/(H-L)'), ('upper_wick_fraction','(H-max(O,C))/(H-L)'),
                       ('lower_wick_fraction','(min(O,C)-L)/(H-L)'), ('close_location','(2*C-H-L)/(H-L)')):
    add(name, 'fraction', 1, formula)
add('range_atr14_prior', 'atr_multiples', 16, '(H[t]-L[t])/ATR14[t-1]', ('atr14',), ((14,15,'rma',1),))
for name, formula, units in (
    ('mid_price','(ask+bid)/2','price'), ('spread_bps','10000*(ask-bid)/mid','bps'),
    ('top_bid_quote_notional','bid*bid_qty','quote_currency'), ('top_ask_quote_notional','ask*ask_qty','quote_currency'),
    ('top_base_imbalance','(bid_qty-ask_qty)/(bid_qty+ask_qty)','signed_fraction'),
    ('quote_event_age_ms','decision_ms-event_ms','milliseconds'),
    ('quote_receipt_age_ms','decision_ms-received_ms; recorded only','milliseconds')):
    add(name, units, 0, formula, inputs=('quote',))


def definition(name):
    if not isinstance(name, str):
        raise ValidationError('Feature IDs must be strings')
    if name in CATALOG:
        return CATALOG[name]
    match = re.fullmatch(r'simple_return_([1-9][0-9]{0,3})', name)
    if match:
        n = int(match[1])
        return FeatureDefinition(name, 'fraction', n+1, f'C[t]/C[t-{n}]-1', parameters=(('horizon', n),))
    raise ValidationError(f'Unknown feature: {name}')


def resolve(names, lookup=definition):
    ordered, visiting, done = [], set(), set()
    def visit(name):
        if name in visiting:
            raise ValidationError('Feature dependency cycle')
        if name in done:
            return
        visiting.add(name)
        for dependency in lookup(name).dependencies:
            visit(dependency)
        visiting.remove(name)
        done.add(name)
        ordered.append(name)
    for name in names:
        visit(name)
    return tuple(ordered)


def seed_weight(name, count):
    terms = set()
    for dependency in resolve((name,)):
        terms.update(definition(dependency).smoothers)
    return max(((1-(2/(n+1) if mode == 'ema' else 1/n))**max(0, count-seed-lag)
                for n, seed, mode, lag in terms), default=0.0)


@dataclass(frozen=True)
class FeatureConfig:
    features: tuple = BASELINE
    timeframes: tuple = ('15m', '1h', '4h', '1d')
    required_features: tuple | None = None
    require_stable: bool = True
    seed_threshold: float = 1e-6
    max_quote_age_ms: int = 5000
    candle_grace_ms: int = 5000
    processing_delay_ms: int = 0
    output_start_ms: int | None = None
    output_end_ms: int | None = None

    def __post_init__(self):
        for field in ('features', 'timeframes'):
            values = getattr(self, field)
            if not isinstance(values, (tuple,list)) or not values or not all(isinstance(v,str) for v in values):
                raise ValidationError(f'{field} must be a nonempty list')
            object.__setattr__(self, field, tuple(dict.fromkeys(values)))
        resolve(self.features)
        if set(self.timeframes)-set(TIMEFRAMES):
            raise ValidationError('Unsupported timeframe')
        required = self.features if self.required_features is None else self.required_features
        if not isinstance(required, (tuple,list)) or not all(isinstance(v,str) for v in required) or set(required)-set(self.features):
            raise ValidationError('Required features must be selected features')
        object.__setattr__(self, 'required_features', tuple(dict.fromkeys(required)))
        if type(self.require_stable) is not bool or type(self.seed_threshold) not in (int,float) or not math.isfinite(self.seed_threshold) or not 0 < self.seed_threshold <= 1:
            raise ValidationError('Invalid stabilization policy')
        for key in ('max_quote_age_ms','candle_grace_ms','processing_delay_ms','output_start_ms','output_end_ms'):
            val = getattr(self,key)
            if val is None and key.startswith('output_'):
                continue
            if type(val) is not int or val < 0 or (key == 'max_quote_age_ms' and val == 0):
                raise ValidationError(f'Invalid {key}')
        if self.output_start_ms is not None and self.output_end_ms is not None and self.output_start_ms >= self.output_end_ms:
            raise ValidationError('Output range must be nonempty [start,end)')

    def document(self):
        return json.loads(canonical(asdict(self)))

    @property
    def config_hash(self):
        return fingerprint(self.document())

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict) or set(value)-set(cls.__dataclass_fields__):
            raise ValidationError('Unknown configuration fields or invalid object')
        return cls(**value)
