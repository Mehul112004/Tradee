"""Predeclared prospective monitoring: one deployment, one immutable rule set."""
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from tradee.c01 import ValidationError
from tradee.c02.domain import integer,number
from tradee.c13.contracts import fields


@dataclass(frozen=True)
class MonitorPolicy:
    review_times_ms: tuple
    version: int = 1
    maturity_lag_ms: int = 60000
    max_cycle_age_ms: int = 30000
    min_mature: int = 30
    min_occupied_spans: int = 4
    bin_ms: int = 3600000
    block_bins: int = 24
    bootstrap_replicates: int = 2000
    alpha: str = '0.05'
    residual_tolerance_r: str = '0.5'
    net_mean_floor_r: str = '0'
    seed: int = 20261020
    pause_on_operational_failure: bool = True
    pause_on_statistical_degradation: bool = True
    max_cycles: int = 10000
    max_observations: int = 10000
    max_report_bytes: int = 50000000
    max_bins: int = 10000
    max_work: int = 2000000

    def __post_init__(self):
        if type(self.version) is not int or self.version!=1: raise ValidationError('Unsupported C15 policy version')
        times=self.review_times_ms
        if not isinstance(times,(tuple,list)) or not 1<=len(times)<=32: raise ValidationError('One to 32 predeclared review times required')
        for value in times: integer(value,'review time')
        if list(times)!=sorted(set(times)): raise ValidationError('Strictly increasing distinct review times required')
        object.__setattr__(self,'review_times_ms',tuple(times))
        for key in ('pause_on_operational_failure','pause_on_statistical_degradation'):
            if type(getattr(self,key)) is not bool: raise ValidationError('Explicit boolean pause policy required')
        limits=dict(maturity_lag_ms=604800000,max_cycle_age_ms=30000,min_mature=100000,min_occupied_spans=10000,
                    bin_ms=86400000,block_bins=1000,bootstrap_replicates=100000,seed=2**32-1,max_cycles=100000,
                    max_report_bytes=50000000,max_bins=10000,max_work=10000000,max_observations=100000)
        for key,cap in limits.items():
            value=getattr(self,key); integer(value,key)
            if value>cap or (key not in ('maturity_lag_ms','seed') and value==0): raise ValidationError('C15 bounded positive settings required')
        if self.min_mature<2 or self.min_occupied_spans<2: raise ValidationError('Multiple observations and time spans required')
        for key in ('alpha','residual_tolerance_r'):
            object.__setattr__(self,key,number(getattr(self,key)))
        object.__setattr__(self,'net_mean_floor_r',number(self.net_mean_floor_r,signed=True))
        if not Decimal(0)<Decimal(self.alpha)<1: raise ValidationError('Alpha must lie strictly between zero and one')
        if self.bootstrap_replicates*Fraction(self.alpha)/(4*len(times))<1: raise ValidationError('Insufficient draws for the predeclared family tail')

    def document(self):
        return {k:list(self.review_times_ms) if k=='review_times_ms' else getattr(self,k) for k in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls,d):
        fields(d,cls); return cls(**d)
