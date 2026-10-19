"""Frozen independent-scenario simulation inputs; no implicit size or capital."""
from dataclasses import dataclass, asdict
import json
import re

from tradee.c01 import ValidationError
from tradee.c01.domain import canonical
from tradee.c02.domain import integer, number
from tradee.c03.contracts import FrozenRecord
from tradee.c08 import StrategySpec
from tradee.c09 import TradePolicy


def fields(doc, cls):
    if not isinstance(doc, dict) or set(doc)-set(cls.__dataclass_fields__):
        raise ValidationError('Unknown simulation input fields or invalid object')


@dataclass(frozen=True)
class Scenario:
    name: str
    strategy: dict
    policy: dict
    quantity: str
    horizon: str = 'intraday'

    def __post_init__(self):
        if not isinstance(self.name, str) or not re.fullmatch('[a-z][a-z0-9_-]{0,63}', self.name):
            raise ValidationError('Scenario name must be a short lowercase identifier')
        if self.horizon not in ('intraday', 'swing'):
            raise ValidationError('Explicit intraday/swing horizon required')
        object.__setattr__(self, 'strategy', StrategySpec.from_dict(self.strategy))
        object.__setattr__(self, 'policy', TradePolicy.from_dict(self.policy))
        object.__setattr__(self, 'quantity', number(self.quantity, positive=True))

    def document(self):
        return dict(name=self.name, strategy=self.strategy.document(), policy=self.policy.document(), quantity=self.quantity, horizon=self.horizon)

    @classmethod
    def from_dict(cls, doc):
        fields(doc, cls)
        if not {'name', 'strategy', 'policy', 'quantity'}<=set(doc): raise ValidationError('Incomplete simulation scenario')
        return cls(**doc)


@dataclass(frozen=True)
class SimulationConfig:
    version: int = 1
    decision_start_ms: int | None = None
    decision_end_ms: int | None = None
    sample_interval_ms: int = 60000
    max_valuation_age_ms: int = 5000
    max_candidates: int = 10000
    max_samples: int = 100000
    max_artifacts: int = 500000

    def __post_init__(self):
        if type(self.version) is not int or self.version!=1: raise ValidationError('Unsupported simulation version')
        for k in ('decision_start_ms', 'decision_end_ms'):
            if getattr(self, k) is not None: integer(getattr(self, k), k)
        if self.decision_start_ms is not None and self.decision_end_ms is not None and self.decision_start_ms>=self.decision_end_ms:
            raise ValidationError('Simulation decision interval must be nonempty')
        for k in ('sample_interval_ms', 'max_valuation_age_ms', 'max_candidates', 'max_samples', 'max_artifacts'):
            integer(getattr(self, k), k)
            if not getattr(self, k): raise ValidationError('Positive simulation budgets required')

    def window(self, dataset):
        start=dataset['start_ms'] if self.decision_start_ms is None else self.decision_start_ms
        end=min(dataset['end_ms'], dataset['as_of_ms']+1) if self.decision_end_ms is None else self.decision_end_ms
        if not dataset['start_ms']<=start<end<=min(dataset['end_ms'], dataset['as_of_ms']+1):
            raise ValidationError('Decision interval outside pinned dataset')
        if (dataset['as_of_ms']-start)//self.sample_interval_ms+1>self.max_samples:
            raise ValidationError('Regular sample budget exceeded; narrow the dataset or increase explicit budget')
        return start, end

    def document(self): return json.loads(canonical(asdict(self)))

    @classmethod
    def from_dict(cls, doc): fields(doc, cls); return cls(**doc)


class SimulationRecord(FrozenRecord):
    pass
