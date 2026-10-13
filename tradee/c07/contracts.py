"""Versioned paper-execution inputs. Financial values are decimal strings."""
from dataclasses import dataclass, asdict
from decimal import Decimal
import json

from tradee.c01 import ValidationError
from tradee.c01.domain import canonical, symbol_name
from tradee.c02.domain import integer, number
from tradee.c03.catalog import TIMEFRAMES, definition
from tradee.c03.contracts import FrozenRecord
from tradee.c06.contracts import identity, text_id


def fields(doc, cls, required=()):
    if not isinstance(doc,dict) or set(doc)-set(cls.__dataclass_fields__) or set(required)-set(doc):
        raise ValidationError('Invalid execution input fields')


def bounded(value, name, low='0', high='1', positive=False):
    value=number(value,signed=Decimal(low)<0)
    d=Decimal(value)
    if not Decimal(low)<=d<=Decimal(high) or (positive and d==0):
        raise ValidationError(f'Invalid execution {name}')
    return value


@dataclass(frozen=True)
class ExecutionIntent:
    intent_id: str
    instrument_id: str
    symbol: str
    side: str
    quantity: str
    detected_ms: int
    expires_ms: int
    reference_price: str
    purpose: str = 'entry'
    order_type: str = 'MARKET'
    stop_price: str | None = None
    holding_until_ms: int | None = None
    required_features: tuple = ()
    feature_timeframe: str | None = None
    reduce_only: bool = False
    position_quantity: str | None = None

    def __post_init__(self):
        text_id(self.intent_id,'intent_id'); identity(self.instrument_id,self.symbol)
        if self.side not in ('buy','sell') or self.purpose not in ('entry','exit') or self.order_type not in ('MARKET','LIMIT'):
            raise ValidationError('Unsupported execution side/purpose/type')
        if type(self.reduce_only) is not bool or (self.reduce_only and (self.purpose!='exit' or self.position_quantity is None)):
            raise ValidationError('Reduce-only requires an exit and caller-supplied position quantity')
        if self.position_quantity is not None:
            if self.purpose!='exit': raise ValidationError('Position quantity belongs to exit requests')
            object.__setattr__(self,'position_quantity',number(self.position_quantity,positive=True))
        object.__setattr__(self,'quantity',number(self.quantity,positive=True))
        object.__setattr__(self,'reference_price',number(self.reference_price,positive=True))
        integer(self.detected_ms,'detection'); integer(self.expires_ms,'expiry')
        if self.detected_ms>=self.expires_ms:
            raise ValidationError('Execution expiry must follow detection')
        if self.stop_price is not None:
            stop=number(self.stop_price,positive=True); object.__setattr__(self,'stop_price',stop)
            ref=Decimal(self.reference_price); value=Decimal(stop)
            if ref==value or (self.purpose=='entry' and (value>=ref if self.side=='buy' else value<=ref)):
                raise ValidationError('Execution stop must define positive directional entry risk')
        if self.holding_until_ms is not None:
            integer(self.holding_until_ms,'holding horizon')
            if self.holding_until_ms<=self.detected_ms or self.purpose!='entry':
                raise ValidationError('Holding horizon is for a future entry position')
        if not isinstance(self.required_features,(list,tuple)):
            raise ValidationError('Required execution features must be a list')
        required=tuple(dict.fromkeys(self.required_features))
        for name in required: definition(name)
        if (required and self.feature_timeframe not in TIMEFRAMES) or (self.feature_timeframe is not None and self.feature_timeframe not in TIMEFRAMES):
            raise ValidationError('Required execution features need a supported timeframe')
        object.__setattr__(self,'required_features',required)

    def document(self): return json.loads(canonical(asdict(self)))

    @classmethod
    def from_dict(cls,doc):
        required=('intent_id','instrument_id','symbol','side','quantity','detected_ms','expires_ms','reference_price')
        fields(doc,cls,required); return cls(**doc)


@dataclass(frozen=True)
class FeeSchedule:
    taker_rate: str
    maker_rate: str
    evidence: str
    source_kind: str = 'assumption'
    available_ms: int | None = None
    effective_from_ms: int | None = None
    effective_until_ms: int | None = None

    def __post_init__(self):
        object.__setattr__(self,'taker_rate',bounded(self.taker_rate,'taker fee','0','0.01'))
        object.__setattr__(self,'maker_rate',bounded(self.maker_rate,'maker fee','-0.01','0.01'))
        text_id(self.evidence,'fee evidence')
        if self.source_kind not in ('assumption','observed'):
            raise ValidationError('Fees require assumption or observed source kind')
        for name in ('available_ms','effective_from_ms','effective_until_ms'):
            if getattr(self,name) is not None: integer(getattr(self,name),name)
        if self.source_kind=='observed' and (self.available_ms is None or self.effective_from_ms is None):
            raise ValidationError('Observed fee schedules require availability and effective start')
        if self.effective_until_ms is not None and (self.effective_from_ms is None or self.effective_until_ms<=self.effective_from_ms):
            raise ValidationError('Invalid fee validity interval')

    def document(self): return asdict(self)

    @classmethod
    def from_dict(cls,doc):
        fields(doc,cls,('taker_rate','maker_rate','evidence')); return cls(**doc)


@dataclass(frozen=True)
class ExecutionConfig:
    market_model: str = 'recorded_quote'
    metadata_mode: str = 'observed'
    bar_mark_proxy: str | None = None
    enabled_symbols: tuple = ('BTCUSDT','ETHUSDT')
    quantity_rounding: str = 'reject'
    processing_delay_ms: int = 0
    delivery_delay_ms: int = 0
    manual_delay_ms: int = 30000
    max_quote_age_ms: int = 5000
    max_mark_age_ms: int = 5000
    max_metadata_age_ms: int = 1800000
    candle_grace_ms: int = 5000
    max_spread_bps: str = '20'
    max_adverse_drift_bps: str = '50'
    extra_slippage_bps: str = '2'
    impact_bps_per_participation: str = '5'
    max_top_book_fraction: str = '0.25'
    synthetic_spread_bps: str = '10'
    max_bar_volume_fraction: str = '0.001'
    bar_impact_bps_per_participation: str = '100'
    max_cost_r: str | None = None
    require_stable_features: bool = True
    require_funding_estimate: bool = False

    def __post_init__(self):
        if self.market_model not in ('recorded_quote','modeled_bar') or self.metadata_mode not in ('observed','research_assumption'):
            raise ValidationError('Unsupported execution market/metadata model')
        if self.market_model=='recorded_quote' and (self.metadata_mode!='observed' or self.bar_mark_proxy is not None):
            raise ValidationError('Recorded execution requires observed metadata without a candle mark proxy')
        if self.bar_mark_proxy not in (None,'bar_close') or (self.bar_mark_proxy is not None and self.market_model!='modeled_bar'):
            raise ValidationError('Invalid modeled mark-price proxy')
        if self.quantity_rounding not in ('reject','floor'):
            raise ValidationError('Quantity rounding must be reject or floor')
        if not isinstance(self.enabled_symbols,(tuple,list)) or not self.enabled_symbols:
            raise ValidationError('Explicit enabled execution universe is required')
        object.__setattr__(self,'enabled_symbols',tuple(sorted({symbol_name(s) for s in self.enabled_symbols})))
        for name in ('processing_delay_ms','delivery_delay_ms','manual_delay_ms','max_quote_age_ms','max_mark_age_ms','max_metadata_age_ms','candle_grace_ms'):
            integer(getattr(self,name),name)
            if name.startswith('max_') and not getattr(self,name): raise ValidationError('Execution age budgets must be positive')
        for name in ('max_spread_bps','max_adverse_drift_bps','extra_slippage_bps','impact_bps_per_participation','synthetic_spread_bps','bar_impact_bps_per_participation'):
            object.__setattr__(self,name,bounded(getattr(self,name),name,'0','1000'))
        for name in ('max_top_book_fraction','max_bar_volume_fraction'):
            object.__setattr__(self,name,bounded(getattr(self,name),name,positive=True))
        if self.max_cost_r is not None: object.__setattr__(self,'max_cost_r',bounded(self.max_cost_r,'cost/R','0','100'))
        for name in ('require_stable_features','require_funding_estimate'):
            if type(getattr(self,name)) is not bool: raise ValidationError('Execution readiness flags must be booleans')

    def action_time(self,intent):
        return integer(intent.detected_ms+self.processing_delay_ms+self.delivery_delay_ms+self.manual_delay_ms,'action time')

    def document(self): return json.loads(canonical(asdict(self)))

    @classmethod
    def from_dict(cls,doc): fields(doc,cls); return cls(**doc)


class ExecutionRecord(FrozenRecord):
    pass
