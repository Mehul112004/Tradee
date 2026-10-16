"""Versioned hypothesis and eligibility policies; no fitted or outcome inputs."""
from dataclasses import asdict, dataclass
import json
import re

from tradee.c01 import ValidationError
from tradee.c01.domain import canonical, fingerprint, symbol_name
from tradee.c02.domain import integer, number
from tradee.c03 import FeatureConfig
from tradee.c03.catalog import TIMEFRAMES
from tradee.c03.contracts import FrozenRecord
from tradee.c06.contracts import identity

FAMILY='prior_range_breakout'
TREND_FAMILY='ema_pullback_continuation'
FAMILIES=(FAMILY,TREND_FAMILY)


def fields(doc,cls):
    if not isinstance(doc,dict) or set(doc)-set(cls.__dataclass_fields__):
        raise ValidationError('Unknown candidate input fields or invalid object')


def digest(value,name):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):
        raise ValidationError('Invalid '+name+' hash')
    return value


@dataclass(frozen=True)
class StrategySpec:
    family: str = FAMILY
    version: int = 1
    timeframe: str = '15m'
    lookback_bars: int = 20
    sides: tuple = ('long','short')
    entry_window_ms: int = 300000
    cooldown_bars: int = 0

    def __post_init__(self):
        if self.family not in FAMILIES or type(self.version) is not int or self.version!=1:
            raise ValidationError('Unsupported strategy family/version')
        if self.timeframe not in TIMEFRAMES: raise ValidationError('Unsupported strategy timeframe')
        if type(self.lookback_bars) is not int or not 2<=self.lookback_bars<=1000:
            raise ValidationError('Lookback must be 2..1000 completed bars')
        if not isinstance(self.sides,(list,tuple)) or not self.sides or any(s not in ('long','short') for s in self.sides):
            raise ValidationError('Strategy needs explicit long/short directions')
        object.__setattr__(self,'sides',tuple(s for s in ('long','short') if s in self.sides))
        integer(self.entry_window_ms,'entry window'); integer(self.cooldown_bars,'cooldown bars')
        if not self.entry_window_ms or self.entry_window_ms>TIMEFRAMES[self.timeframe] or self.cooldown_bars>10000:
            raise ValidationError('Entry window must be positive and no longer than one bar; cooldown must be <=10000 bars')
        if self.family==TREND_FAMILY and self.lookback_bars!=20:
            raise ValidationError('Trend v1 uses fixed EMA20/EMA50 periods; range lookback is not a trend tuning parameter')

    def document(self): return json.loads(canonical(asdict(self)))

    @property
    def strategy_hash(self): return fingerprint(self.definition())

    def definition(self):
        doc=dict(schema_version=1,spec=self.document(),
            hypothesis='A close outside the previously completed high/low range may identify continuation after costs.',
            alternative='Random excursions, reversals, market exposure or data selection can explain apparent performance; costs can remove any gross advantage.',
            trigger='long: C[t] > max(H[t-N:t]); short: C[t] < min(L[t-N:t]); equality and wick-only touch do not trigger',
            window='N contiguous prior completed bars, excluding current; no crossing or position-state requirement',
            expiry='exclusive target_bar_end_ms + entry_window_ms; late receipt never extends this window',
            cooldown='same instrument/direction; target-bar separation >= cooldown_bars; only emitted candidates consume cooldown',
            revisions='diagnostic only; preserve earlier decisions and update source context for subsequent bars',
            required_features=['log_return_1'],diagnostic_features=['atr14'],
            downstream='C09 owns entry/stop/target/holding/cancellation; C12 owns trials, holdouts, exposure/no-trade baselines and promotion')
        if self.family==TREND_FAMILY:
            doc.update(hypothesis='Recovery across the fast EMA in the direction of the fast/slow EMA trend may identify continuation after a pullback and costs.',
                alternative='Lagging trend filters, serial dependence, generic market exposure, repeated testing or reversals may explain apparent performance.',
                trigger='long: EMA20[t]>EMA50[t] and C[t-1]<=EMA20[t-1] and C[t]>EMA20[t]; short: reverse strict comparisons with C[t-1]>=EMA20[t-1]',
                window='current and previous contiguous completed bars; current and one-bar-prior EMA20/EMA50 valid and stabilized in the current known prefix',
                required_features=['ema20','ema50','ema20_prior','ema50_prior'],diagnostic_features=['log_return_1','atr14'])
        return doc

    def feature_config(self):
        required=tuple(self.definition()['required_features'])
        return FeatureConfig(features=tuple(dict.fromkeys((*required,'log_return_1','atr14'))),required_features=required,
                             timeframes=(self.timeframe,),require_stable=True)

    @classmethod
    def from_dict(cls,doc): fields(doc,cls); return cls(**doc)


@dataclass(frozen=True)
class CandidateConfig:
    enabled_symbols: tuple = ('BTCUSDT','ETHUSDT')
    metadata_mode: str = 'observed'
    max_metadata_age_ms: int = 1800000
    max_detection_lag_ms: int = 60000

    def __post_init__(self):
        if not isinstance(self.enabled_symbols,(tuple,list)) or not self.enabled_symbols:
            raise ValidationError('Explicit candidate universe required')
        object.__setattr__(self,'enabled_symbols',tuple(sorted({symbol_name(s) for s in self.enabled_symbols})))
        if self.metadata_mode not in ('observed','research_assumption'):
            raise ValidationError('Unsupported metadata availability policy')
        for name in ('max_metadata_age_ms','max_detection_lag_ms'):
            integer(getattr(self,name),name)
            if not getattr(self,name): raise ValidationError('Candidate age budgets must be positive')

    def document(self): return json.loads(canonical(asdict(self)))

    @classmethod
    def from_dict(cls,doc): fields(doc,cls); return cls(**doc)


class CandidateRecord(FrozenRecord):
    pass


class CandidateSpec(FrozenRecord):
    """Validated immutable setup; executable order/position policy belongs to C09."""
    @classmethod
    def create(cls,doc):
        required={'schema_version','candidate_id','strategy_hash','hypothesis_family','instrument_id','symbol','side','timeframe',
                  'target_open_ms','target_end_ms','detected_ms','expires_ms','reference_price','breakout_level',
                  'trigger_context','context_start_ms','context_end_ms','feature_snapshot_hash','metadata_snapshot_hash',
                  'metadata_mode','input_cursor','input_prefix_hash','availability_basis'}
        if not isinstance(doc,dict) or set(doc)!=required or type(doc['schema_version']) is not int or doc['schema_version']!=1:
            raise ValidationError('Unsupported candidate schema')
        if doc['hypothesis_family'] not in FAMILIES or doc['side'] not in ('long','short') or doc['timeframe'] not in TIMEFRAMES:
            raise ValidationError('Unsupported candidate hypothesis/direction/timeframe')
        identity(doc['instrument_id'],doc['symbol'])
        for name in ('candidate_id','strategy_hash','feature_snapshot_hash','metadata_snapshot_hash','input_prefix_hash'): digest(doc[name],name)
        for name in ('target_open_ms','target_end_ms','detected_ms','expires_ms','context_start_ms','context_end_ms'): integer(doc[name],name)
        interval=TIMEFRAMES[doc['timeframe']]
        if (doc['target_open_ms']%interval or doc['target_end_ms']!=doc['target_open_ms']+interval
                or doc['context_end_ms']!=doc['target_open_ms'] or doc['context_start_ms']>=doc['context_end_ms']
                or doc['context_start_ms']%interval or doc['detected_ms']<doc['target_end_ms'] or doc['expires_ms']<=doc['detected_ms']):
            raise ValidationError('Invalid candidate range/detection/expiry times')
        from decimal import Decimal
        for name in ('reference_price','breakout_level'):
            if number(doc[name],positive=True)!=doc[name]: raise ValidationError('Noncanonical candidate price')
        ctx=doc['trigger_context']
        if not isinstance(ctx,dict): raise ValidationError('Candidate needs trigger context')
        if doc['hypothesis_family']==FAMILY:
            if set(ctx)!={'upper','lower'}: raise ValidationError('Invalid range context')
            for value in ctx.values():
                if number(value,positive=True)!=value: raise ValidationError('Invalid range price')
            upper,lower,ref=(Decimal(v) for v in (ctx['upper'],ctx['lower'],doc['reference_price']))
            level=ctx['upper'] if doc['side']=='long' else ctx['lower']
            valid=upper>=lower and doc['breakout_level']==level and (ref>upper if doc['side']=='long' else ref<lower)
        else:
            if set(ctx)!={'previous_close','previous_ema20','previous_ema50','ema20','ema50'}:
                raise ValidationError('Invalid EMA recovery context')
            for value in ctx.values():
                if number(value,positive=True)!=value: raise ValidationError('Invalid trend context price')
            a,b,c,d,e=(float(ctx[k]) for k in ('previous_close','previous_ema20','previous_ema50','ema20','ema50'))
            ref=float(doc['reference_price'])
            valid=(d>e and a<=b and ref>d) if doc['side']=='long' else (d<e and a>=b and ref<d)
            valid=valid and doc['breakout_level']==ctx['ema20']
        if not valid: raise ValidationError('Candidate does not satisfy its strict trigger')
        cursor=doc['input_cursor']
        if not isinstance(cursor,(tuple,list)) or len(cursor)!=2: raise ValidationError('Candidate needs a source cursor')
        integer(cursor[0],'cursor availability'); integer(cursor[1],'cursor ID')
        if not cursor[1] or cursor[0]>doc['detected_ms']: raise ValidationError('Candidate references future/invalid cursor')
        if doc['metadata_mode'] not in ('observed','research_assumption') or doc['availability_basis'] not in ('recorded','modeled'):
            raise ValidationError('Invalid candidate evidence mode')
        expected=fingerprint([doc['strategy_hash'],doc['instrument_id'],doc['timeframe'],doc['target_open_ms'],doc['side']])
        if doc['candidate_id']!=expected: raise ValidationError('Candidate identity does not match opportunity')
        return super().create(doc)

    @classmethod
    def from_dict(cls,doc): return cls.create(doc)
