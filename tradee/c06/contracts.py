"""Exact, versioned funding inputs. Currency quantities never pass through float."""
from dataclasses import asdict, dataclass
from decimal import Decimal, Inexact, Rounded, localcontext
import json

from tradee.c01 import ValidationError
from tradee.c01.domain import canonical, fingerprint, symbol_name
from tradee.c02.domain import integer, number


def strict_object(value, allowed, required):
    if not isinstance(value, dict) or set(value)-set(allowed) or set(required)-set(value):
        raise ValidationError('Invalid funding object fields')


def text_id(value, name):
    if not isinstance(value, str) or not value.strip() or len(value)>250:
        raise ValidationError(f'{name} must be a nonempty identifier')
    return value


def identity(value, symbol):
    text_id(value, 'instrument_id')
    symbol_name(symbol)
    if not symbol.endswith('USDT') or not value.startswith(f'binance:usds_futures:{symbol}:'):
        raise ValidationError('C06 supports identified Binance crypto USDT perpetual instruments')
    return value


def decimal_text(value):
    if not value.is_finite():
        raise ValidationError('Nonfinite funding arithmetic')
    if not value:
        return '0'
    result=format(value,'f')
    return result.rstrip('0').rstrip('.') if '.' in result else result


def cashflow(side, quantity, mark_price, rate):
    """USDT received is positive, paid is negative; no wallet rounding or leverage."""
    if side not in ('long','short'):
        raise ValidationError('Side must be long or short')
    q=Decimal(number(quantity)); p=Decimal(number(mark_price,positive=True)); r=Decimal(number(rate,signed=True))
    with localcontext() as ctx:
        ctx.prec=400
        ctx.traps[Inexact]=ctx.traps[Rounded]=True
        return decimal_text((-1 if side=='long' else 1)*q*p*r)


def total_amounts(values):
    with localcontext() as ctx:
        ctx.prec=400
        ctx.traps[Inexact]=ctx.traps[Rounded]=True
        return decimal_text(sum((Decimal(v) for v in values),Decimal(0)))


@dataclass(frozen=True)
class QuantityChange:
    at_ms: int
    quantity: str

    def __post_init__(self):
        integer(self.at_ms,'quantity change time')
        object.__setattr__(self,'quantity',number(self.quantity))

    @classmethod
    def from_dict(cls, doc):
        strict_object(doc,cls.__dataclass_fields__,cls.__dataclass_fields__)
        return cls(**doc)


@dataclass(frozen=True)
class PositionTimeline:
    position_id: str
    instrument_id: str
    symbol: str
    side: str
    changes: tuple

    def __post_init__(self):
        text_id(self.position_id,'position_id'); identity(self.instrument_id,self.symbol)
        if self.side not in ('long','short') or not isinstance(self.changes,(list,tuple)) or not self.changes:
            raise ValidationError('Position requires a side and nonempty quantity timeline')
        changes=tuple(c if isinstance(c,QuantityChange) else QuantityChange.from_dict(c) for c in self.changes)
        if any(b.at_ms<=a.at_ms or b.quantity==a.quantity for a,b in zip(changes,changes[1:])):
            raise ValidationError('Quantity changes must be unique, ordered and change exposure')
        object.__setattr__(self,'changes',changes)

    def quantity_at(self, stamp):
        integer(stamp,'quantity query time')
        result='0'
        for change in self.changes:
            if change.at_ms>stamp:
                break
            result=change.quantity
        return result

    def boundary_ambiguous(self, stamp, guard):
        return any(abs(c.at_ms-stamp)<=guard for c in self.changes)

    def document(self):
        return json.loads(canonical(asdict(self)))

    @classmethod
    def from_dict(cls, doc):
        strict_object(doc,cls.__dataclass_fields__,cls.__dataclass_fields__)
        return cls(**doc)


@dataclass(frozen=True)
class SettlementCalendar:
    instrument_id: str
    symbol: str
    start_ms: int
    end_ms: int
    settlement_times_ms: tuple
    evidence: str  # Named audit artifact or explicit operator assumption, never inferred.

    def __post_init__(self):
        identity(self.instrument_id,self.symbol)
        integer(self.start_ms,'calendar start'); integer(self.end_ms,'calendar end')
        text_id(self.evidence,'calendar evidence')
        if self.start_ms>=self.end_ms or not isinstance(self.settlement_times_ms,(list,tuple)):
            raise ValidationError('Invalid settlement calendar range')
        times=tuple(integer(t,'settlement time') for t in self.settlement_times_ms)
        if times!=tuple(sorted(set(times))) or any(not self.start_ms<=t<self.end_ms for t in times):
            raise ValidationError('Calendar timestamps must be ordered, unique and in range')
        object.__setattr__(self,'settlement_times_ms',times)

    def document(self):
        return json.loads(canonical(asdict(self)))

    @classmethod
    def from_dict(cls, doc):
        strict_object(doc,cls.__dataclass_fields__,cls.__dataclass_fields__)
        return cls(**doc)


@dataclass(frozen=True)
class FundingConfig:
    boundary_policy: str = 'strict'
    boundary_guard_ms: int = 15000
    max_mark_age_ms: int = 5000

    def __post_init__(self):
        if self.boundary_policy not in ('strict','nominal'):
            raise ValidationError('Funding boundary policy must be strict or nominal')
        integer(self.boundary_guard_ms,'boundary guard'); integer(self.max_mark_age_ms,'mark freshness')
        if not self.max_mark_age_ms or (self.boundary_policy=='strict' and self.boundary_guard_ms<15000):
            raise ValidationError('Strict boundary guard must be >=15000 ms; freshness must be positive')

    def document(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, doc):
        strict_object(doc,cls.__dataclass_fields__,())
        return cls(**doc)


@dataclass(frozen=True)
class FundingRecord:
    serialized: str

    @classmethod
    def create(cls, doc):
        return cls(canonical(doc))

    def document(self):
        return json.loads(self.serialized)

    @property
    def digest(self):
        return fingerprint(self.document())
