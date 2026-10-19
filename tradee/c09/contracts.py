"""Frozen outcome policy, setup evidence and exact trade intent contracts."""
from copy import deepcopy
from dataclasses import dataclass,asdict
from decimal import Decimal
import json
from tradee.c01 import ValidationError
from tradee.c01.domain import canonical,fingerprint
from tradee.c02.domain import integer,number
from tradee.c03.contracts import FrozenRecord
from tradee.c07.engine import verified_feature
from tradee.c07.math import exact
from tradee.c06.contracts import decimal_text
from tradee.c08 import CandidateSpec
from tradee.c08.contracts import FAMILY


def fields(doc,cls):
    if not isinstance(doc,dict) or set(doc)-set(cls.__dataclass_fields__): raise ValidationError('Invalid lifecycle input fields')


@dataclass(frozen=True)
class TradePolicy:
    version: int = 1
    stop_fraction: str = '0.01'
    target_r: str = '2'
    max_holding_ms: int = 14400000
    trigger_source: str = 'contract_trade'
    partial_target_r: str | None = None
    partial_fraction: str = '0.5'
    exit_delay_ms: int = 0
    max_exit_wait_ms: int = 60000
    max_trigger_age_ms: int = 5000
    max_path_gap_ms: int = 60000

    def __post_init__(self):
        if type(self.version) is not int or self.version!=1: raise ValidationError('Unsupported lifecycle policy version')
        for k in ('stop_fraction','target_r','partial_fraction'):
            object.__setattr__(self,k,number(getattr(self,k),positive=True))
        if not Decimal('0')<Decimal(self.stop_fraction)<1 or not Decimal('0')<Decimal(self.partial_fraction)<1 or Decimal(self.target_r)>100:
            raise ValidationError('Invalid stop/target/partial fraction')
        if self.partial_target_r is not None:
            object.__setattr__(self,'partial_target_r',number(self.partial_target_r,positive=True))
            if Decimal(self.partial_target_r)>=Decimal(self.target_r): raise ValidationError('Partial target must precede final target')
        if self.trigger_source not in ('contract_trade','mark','bar_close','bar_range'):
            raise ValidationError('Unsupported lifecycle trigger source')
        for k in ('max_holding_ms','exit_delay_ms','max_exit_wait_ms','max_trigger_age_ms','max_path_gap_ms'):
            integer(getattr(self,k),k)
            if k!='exit_delay_ms' and not getattr(self,k): raise ValidationError('Positive lifecycle time budgets required')

    def document(self): return json.loads(canonical(asdict(self)))
    @property
    def policy_hash(self): return fingerprint(self.document())
    @classmethod
    def from_dict(cls,doc): fields(doc,cls); return cls(**doc)


@dataclass(frozen=True)
class TradeIntent:
    candidate: dict
    feature_snapshot: dict
    quantity: str
    policy: dict

    def __post_init__(self):
        c=CandidateSpec.from_dict(self.candidate).document()
        f=deepcopy(verified_feature(self.feature_snapshot)); p=TradePolicy.from_dict(self.policy)
        if (f['snapshot_hash']!=c['feature_snapshot_hash'] or f['instrument_id']!=c['instrument_id']
                or f['timeframe']!=c['timeframe'] or f['target_open_ms']!=c['target_open_ms']
                or f['target_end_ms']!=c['target_end_ms'] or f['input_cursor']!=c['input_cursor']
                or f['input_prefix_hash']!=c['input_prefix_hash'] or f['evaluation_as_of_ms']!=c['detected_ms']
                or f['assumed_usable_ms']>c['detected_ms']):
            raise ValidationError('Candidate and feature evidence do not share an available prefix')
        q=number(self.quantity,positive=True)
        with exact():
            sign=1 if c['side']=='long' else -1; ref=Decimal(c['reference_price']); risk=ref*Decimal(p.stop_fraction)
            stop=ref-sign*risk
            if stop<=0 or ref+sign*risk*Decimal(p.target_r)<=0: raise ValidationError('Nonpositive trade level')
        object.__setattr__(self,'candidate',FrozenRecord.create(c))
        object.__setattr__(self,'feature_snapshot',FrozenRecord.create(f))
        object.__setattr__(self,'policy',p)
        object.__setattr__(self,'quantity',q)

    def document(self):
        return dict(candidate=self.candidate.document(),feature_snapshot=self.feature_snapshot.document(),quantity=self.quantity,policy=self.policy.document())

    @property
    def trade_id(self): return fingerprint([self.candidate.document()['candidate_id'],self.policy.policy_hash,self.quantity])

    def levels(self):
        c=self.candidate.document(); sign=1 if c['side']=='long' else -1
        with exact():
            ref=Decimal(c['reference_price']); risk=ref*Decimal(self.policy.stop_fraction)
            return dict(stop=decimal_text(ref-sign*risk),target=decimal_text(ref+sign*risk*Decimal(self.policy.target_r)),
                partial=None if self.policy.partial_target_r is None else decimal_text(ref+sign*risk*Decimal(self.policy.partial_target_r)),
                reference_risk_per_unit=decimal_text(risk))

    @property
    def required_features(self):
        return ('log_return_1',) if self.candidate.document()['hypothesis_family']==FAMILY else ('ema20','ema50','ema20_prior','ema50_prior')

    @classmethod
    def from_dict(cls,doc):
        if not isinstance(doc,dict) or set(doc)!=set(cls.__dataclass_fields__): raise ValidationError('Invalid trade-intent schema')
        return cls(**doc)


class LifecycleRecord(FrozenRecord):
    pass
