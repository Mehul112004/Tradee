"""Frozen shared-risk inputs. Quantities remain tied to their C10 cost protocol."""
from dataclasses import dataclass, MISSING
from decimal import Decimal
import re
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c02.domain import integer, number
from tradee.c03.contracts import FrozenRecord
from tradee.c06.contracts import identity
from tradee.c10 import EstimateRequest
from tradee.c10.engine import verified_model
from tradee.c09 import TradeIntent
from tradee.c07 import ExecutionIntent


def fields(d,cls):
    required={k for k,v in cls.__dataclass_fields__.items() if v.default is MISSING and v.default_factory is MISSING}
    if not isinstance(d,dict) or set(d)-set(cls.__dataclass_fields__) or required-set(d): raise ValidationError('Invalid portfolio input fields')


def text(s):
    if not isinstance(s,str) or not s.strip() or len(s)>1000: raise ValidationError('Bounded portfolio identity/evidence required')
    return s


def amount(v,positive=False,signed=False): return number(v,positive=positive,signed=signed)


def fraction(v):
    v=amount(v)
    if not Decimal(0)<Decimal(v)<=1: raise ValidationError('Portfolio fractions must lie in (0,1]')
    return v


@dataclass(frozen=True)
class RiskPolicy:
    version: int = 1
    per_trade_risk_fraction: str = '0.005'
    total_risk_fraction: str = '0.02'
    group_risk_fraction: str = '0.015'
    horizon_risk_fraction: str = '0.015'
    gross_notional_fraction: str = '0.5'
    group_notional_fraction: str = '0.5'
    absolute_beta_notional_fraction: str = '0.5'
    collateral_fraction: str = '0.6'
    max_stress_loss_fraction: str = '0.1'
    max_drawdown_fraction: str = '0.1'
    stop_gap_bps: str = '30'
    stress_shock_fraction: str = '0.2'
    max_positions: int = 4
    max_snapshot_age_ms: int = 5000
    max_mark_age_ms: int = 5000
    max_offers: int = 1000
    max_positions_in_state: int = 1000
    max_samples: int = 100000
    max_artifacts: int = 100000
    asset_risks: dict | None = None
    risk_map_available_ms: int = 0
    risk_map_evidence: str = 'assumption: BTC/ETH share one fully correlated crypto bucket; beta magnitude 1'
    leverage: int = 1

    def __post_init__(self):
        if type(self.version) is not int or self.version!=1 or type(self.leverage) is not int or self.leverage!=1:
            raise ValidationError('Only version 1 fully collateralized one-way paper risk is supported')
        for k in ('per_trade_risk_fraction','total_risk_fraction','group_risk_fraction','horizon_risk_fraction','gross_notional_fraction','group_notional_fraction',
                  'absolute_beta_notional_fraction','collateral_fraction','max_stress_loss_fraction','max_drawdown_fraction','stress_shock_fraction'):
            object.__setattr__(self,k,fraction(getattr(self,k)))
        object.__setattr__(self,'stop_gap_bps',amount(self.stop_gap_bps))
        if Decimal(self.stop_gap_bps)>1000: raise ValidationError('Stop gap buffer must be <=1000bps')
        for k in ('max_positions','max_snapshot_age_ms','max_mark_age_ms','max_offers','max_positions_in_state','max_samples','max_artifacts'):
            integer(getattr(self,k),k)
            if not getattr(self,k): raise ValidationError('Positive portfolio limits required')
        integer(self.risk_map_available_ms,'risk map availability'); text(self.risk_map_evidence)
        risks=self.asset_risks if self.asset_risks is not None else {s:dict(group='crypto',beta='1') for s in ('BTCUSDT','ETHUSDT')}
        if isinstance(risks,FrozenRecord): risks=risks.document()
        if not isinstance(risks,dict) or not 1<=len(risks)<=1000: raise ValidationError('Explicit bounded asset risk map required')
        parsed={}
        for symbol,r in risks.items():
            if not isinstance(symbol,str) or not re.fullmatch('[A-Z0-9]{5,30}',symbol) or not isinstance(r,dict) or set(r)!={'group','beta'}: raise ValidationError('Invalid asset risk assignment')
            text(r['group']); beta=amount(r['beta'],signed=True)
            if not Decimal('0.01')<=abs(Decimal(beta))<=10: raise ValidationError('Conservative nonzero bounded beta assumption required')
            parsed[symbol]=dict(group=r['group'],beta=beta)
        object.__setattr__(self,'asset_risks',FrozenRecord.create(parsed))

    def document(self): return {k:(self.asset_risks.document() if k=='asset_risks' else getattr(self,k)) for k in self.__dataclass_fields__}
    @property
    def policy_hash(self): return fingerprint(self.document())
    @classmethod
    def from_dict(cls,d): fields(d,cls); return cls(**d)


@dataclass(frozen=True)
class Position:
    position_id: str
    candidate_id: str
    instrument_id: str
    symbol: str
    side: str
    quantity: str
    entry_price: str
    stop_price: str
    opened_ms: int
    horizon: str
    exit_fee_rate: str

    def __post_init__(self):
        text(self.position_id); text(self.candidate_id); identity(self.instrument_id,self.symbol)
        if self.side not in ('long','short') or self.horizon not in ('intraday','swing'): raise ValidationError('Position side/horizon required')
        for k in ('quantity','entry_price','stop_price'): object.__setattr__(self,k,amount(getattr(self,k),positive=True))
        object.__setattr__(self,'exit_fee_rate',amount(self.exit_fee_rate))
        if Decimal(self.exit_fee_rate)>Decimal('0.01'): raise ValidationError('Unsupported exit fee')
        integer(self.opened_ms,'position opened')

    def document(self): return {k:getattr(self,k) for k in self.__dataclass_fields__}
    @classmethod
    def from_dict(cls,d): fields(d,cls); return cls(**d)


@dataclass(frozen=True)
class Reservation:
    candidate_id: str
    instrument_id: str
    symbol: str
    side: str
    quantity: str
    risk_usdt: str
    notional_usdt: str
    collateral_usdt: str
    horizon: str
    created_ms: int
    expires_ms: int
    closing_fee_usdt: str = '0'

    def __post_init__(self):
        text(self.candidate_id); identity(self.instrument_id,self.symbol)
        if self.side not in ('long','short') or self.horizon not in ('intraday','swing'): raise ValidationError('Reservation side/horizon required')
        for k in ('quantity','risk_usdt','notional_usdt','collateral_usdt'): object.__setattr__(self,k,amount(getattr(self,k),positive=True))
        object.__setattr__(self,'closing_fee_usdt',amount(self.closing_fee_usdt))
        if Decimal(self.collateral_usdt)<Decimal(self.notional_usdt): raise ValidationError('Reservation collateral cannot imply leverage')
        integer(self.created_ms,'reservation created'); integer(self.expires_ms,'reservation expiry')
        if self.created_ms>=self.expires_ms: raise ValidationError('Future reservation expiry required')

    def document(self): return {k:getattr(self,k) for k in self.__dataclass_fields__}
    @classmethod
    def from_dict(cls,d): fields(d,cls); return cls(**d)


@dataclass(frozen=True)
class Mark:
    instrument_id: str
    symbol: str
    price: str
    event_ms: int
    available_ms: int
    event_id: int
    basis: str = 'recorded_mark'

    def __post_init__(self):
        identity(self.instrument_id,self.symbol); object.__setattr__(self,'price',amount(self.price,positive=True))
        for k in ('event_ms','available_ms','event_id'): integer(getattr(self,k),k)
        if self.available_ms<self.event_ms or not self.event_id or self.basis not in ('recorded_mark','explicit_bar_close_proxy'): raise ValidationError('Invalid portfolio mark evidence')

    def document(self): return {k:getattr(self,k) for k in self.__dataclass_fields__}
    @classmethod
    def from_dict(cls,d): fields(d,cls); return cls(**d)


@dataclass(frozen=True)
class AccountSnapshot:
    as_of_ms: int
    available_ms: int
    cash_usdt: str
    peak_equity_usdt: str
    positions: tuple = ()
    reservations: tuple = ()
    marks: tuple = ()
    seen_candidates: tuple = ()
    funding_known: bool = True
    external_orders_known: bool = True
    basis: str = 'paper'
    position_mode: str = 'one_way'

    def __post_init__(self):
        integer(self.as_of_ms,'account as of'); integer(self.available_ms,'account availability')
        if self.available_ms<self.as_of_ms or self.basis not in ('paper','user_snapshot') or self.position_mode!='one_way': raise ValidationError('Explicit one-way paper/user snapshot required')
        object.__setattr__(self,'cash_usdt',amount(self.cash_usdt,signed=True)); object.__setattr__(self,'peak_equity_usdt',amount(self.peak_equity_usdt,positive=True))
        for name,cls in (('positions',Position),('reservations',Reservation),('marks',Mark)):
            values=getattr(self,name)
            if not isinstance(values,(list,tuple)) or len(values)>1000: raise ValidationError('Bounded account evidence lists required')
            object.__setattr__(self,name,tuple(cls.from_dict(v) for v in values))
        for name in ('funding_known','external_orders_known'):
            if type(getattr(self,name)) is not bool: raise ValidationError('Explicit account coverage flags required')
        if (len({p.position_id for p in self.positions})!=len(self.positions) or len({p.instrument_id for p in self.positions})!=len(self.positions)
                or len({r.candidate_id for r in self.reservations})!=len(self.reservations) or len({m.instrument_id for m in self.marks})!=len(self.marks)):
            raise ValidationError('Duplicate/hedged positions, reservations or marks')
        if any(p.opened_ms>self.as_of_ms for p in self.positions) or any(r.created_ms>self.available_ms for r in self.reservations): raise ValidationError('Future account position/reservation')
        if any(m.available_ms>self.available_ms for m in self.marks): raise ValidationError('Mark not available in frozen account snapshot')
        if not isinstance(self.seen_candidates,(list,tuple)) or len(self.seen_candidates)>100000 or len(set(self.seen_candidates))!=len(self.seen_candidates): raise ValidationError('Distinct bounded seen candidates required')
        for value in self.seen_candidates: text(value)
        object.__setattr__(self,'seen_candidates',tuple(sorted(self.seen_candidates)))

    def document(self):
        return {k:([x.document() for x in getattr(self,k)] if k in ('positions','reservations','marks') else list(self.seen_candidates) if k=='seen_candidates' else getattr(self,k)) for k in self.__dataclass_fields__}
    @classmethod
    def from_dict(cls,d): fields(d,cls); return cls(**d)


@dataclass(frozen=True)
class Offer:
    request: dict
    model: dict

    def __post_init__(self):
        q=EstimateRequest.from_dict(self.request); model=verified_model(self.model)
        object.__setattr__(self,'request',q); object.__setattr__(self,'model',model)

    @property
    def intent(self):
        q=self.request.document(); return TradeIntent(q['candidate'],q['feature_snapshot'],q['scenario']['quantity'],q['scenario']['policy'])
    @property
    def execution_intent(self):
        i=self.intent; c=i.candidate.document()
        return ExecutionIntent(i.trade_id+':entry',c['instrument_id'],c['symbol'],'buy' if c['side']=='long' else 'sell',i.quantity,
            c['detected_ms'],c['expires_ms'],c['reference_price'],stop_price=i.levels()['stop'],holding_until_ms=c['expires_ms']+i.policy.max_holding_ms,
            required_features=i.required_features,feature_timeframe=c['timeframe'])
    def document(self): return dict(request=self.request.document(),model=self.model.document())
    @property
    def offer_id(self): return fingerprint([self.intent.trade_id,self.request.document()['scenario']['horizon'],self.model.digest])
    @classmethod
    def from_dict(cls,d): fields(d,cls); return cls(**d)
