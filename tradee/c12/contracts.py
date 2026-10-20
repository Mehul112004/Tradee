"""Predeclared chronological experiments; hashes freeze every research choice."""
from dataclasses import dataclass, MISSING
from decimal import Decimal
import re
from fractions import Fraction
from tradee.c01 import ValidationError
from tradee.c02.domain import integer, number
from tradee.c03.contracts import FrozenRecord
from tradee.c10 import TrainingWindow, EstimatorConfig


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('[a-z][a-z0-9_-]{0,63}', value):
        raise ValidationError('Short lowercase research identifier required')
    return value


def text(value):
    if not isinstance(value, str) or not value.strip() or len(value)>10000:
        raise ValidationError('Nonempty bounded research disclosure required')
    return value


def fields(d, cls):
    required={k for k,f in cls.__dataclass_fields__.items() if f.default is MISSING and f.default_factory is MISSING}
    if not isinstance(d, dict) or set(d)-set(cls.__dataclass_fields__) or required-set(d):
        raise ValidationError('Unknown research input fields')


def hashes(values):
    if not isinstance(values, (list, tuple)) or not values or len(values)>100 or len(set(values))!=len(values):
        raise ValidationError('Distinct bounded pinned C11 run hashes required')
    if any(not isinstance(v, str) or not re.fullmatch('[a-f0-9]{64}', v) for v in values):
        raise ValidationError('C11 SHA256 run hashes required')
    return tuple(sorted(values))


@dataclass(frozen=True)
class Split:
    name: str
    train: dict
    test: dict
    purge_gap_ms: int = 0

    def __post_init__(self):
        identifier(self.name)
        object.__setattr__(self, 'train', TrainingWindow.from_dict(self.train))
        object.__setattr__(self, 'test', TrainingWindow.from_dict(self.test))
        integer(self.purge_gap_ms, 'label purge gap')
        if self.train.cutoff_ms>self.test.start_ms or self.train.start_ms>=self.test.start_ms-self.purge_gap_ms:
            raise ValidationError('Training knowledge must precede test decisions; purge gap must leave training history')

    def document(self):
        return dict(name=self.name, train=self.train.document(), test=self.test.document(), purge_gap_ms=self.purge_gap_ms)

    @classmethod
    def from_dict(cls, d):
        fields(d, cls)
        return cls(**d)


@dataclass(frozen=True)
class Fold:
    split: dict
    inner: tuple = ()

    def __post_init__(self):
        s=Split.from_dict(self.split); object.__setattr__(self, 'split', s)
        if not isinstance(self.inner, (tuple, list)): raise ValidationError('Inner chronological splits required')
        items=tuple(Split.from_dict(i) for i in self.inner)
        if len(items)>20 or len({i.name for i in items})!=len(items): raise ValidationError('Distinct bounded inner splits required')
        previous=None
        for i in items:
            if (i.train.start_ms<s.train.start_ms or i.test.end_ms>s.train.end_ms or i.test.cutoff_ms>s.train.cutoff_ms or
                    (previous is not None and i.test.start_ms<previous)):
                raise ValidationError('Inner tests must be disjoint, chronological and known within outer training')
            previous=i.test.end_ms
        object.__setattr__(self, 'inner', items)

    def document(self): return dict(split=self.split.document(), inner=[i.document() for i in self.inner])
    @classmethod
    def from_dict(cls, d): fields(d, cls); return cls(**d)


@dataclass(frozen=True)
class Variant:
    name: str
    hypothesis: str
    development_runs: tuple
    holdout_runs: tuple
    estimator: dict
    rationale: str
    parameters: dict
    stress_of: str | None = None
    neighbor_of: str | None = None

    def __post_init__(self):
        identifier(self.name); text(self.hypothesis); text(self.rationale)
        object.__setattr__(self, 'development_runs', hashes(self.development_runs))
        object.__setattr__(self, 'holdout_runs', hashes(self.holdout_runs))
        if set(self.development_runs)&set(self.holdout_runs): raise ValidationError('Holdout requires separate C11 artifacts from development')
        object.__setattr__(self, 'estimator', EstimatorConfig.from_dict(self.estimator))
        if not isinstance(self.parameters, dict): raise ValidationError('Explicit parameter description required')
        object.__setattr__(self, 'parameters', FrozenRecord.create(self.parameters))
        for k in ('stress_of', 'neighbor_of'):
            if getattr(self, k) is not None: identifier(getattr(self, k))
        if self.stress_of is not None and self.neighbor_of is not None: raise ValidationError('Stress and neighborhood roles must be distinct')

    def document(self):
        return dict(name=self.name, hypothesis=self.hypothesis, development_runs=list(self.development_runs), holdout_runs=list(self.holdout_runs),
                    estimator=self.estimator.document(), rationale=self.rationale, parameters=self.parameters.document(), stress_of=self.stress_of, neighbor_of=self.neighbor_of)

    @classmethod
    def from_dict(cls, d): fields(d, cls); return cls(**d)


@dataclass(frozen=True)
class EvidencePolicy:
    version: int = 1
    bin_ms: int = 86400000
    block_bins: int = 3
    bootstrap_replicates: int = 2000
    alpha: str = '0.05'
    seed: int = 20261019
    min_candidates: int = 30
    min_eligible_mature: int = 20
    min_occupied_spans: int = 10
    min_estimated_fraction: str = '0.8'
    lower_bound_buffer_r: str = '0'
    require_stress: bool = True
    require_neighbors: bool = True
    require_leave_group_positive: bool = True
    max_bins: int = 10000
    max_work: int = 20000000

    def __post_init__(self):
        if type(self.version) is not int or self.version!=1: raise ValidationError('Unsupported research policy')
        for k in ('bin_ms','block_bins','bootstrap_replicates','min_candidates','min_eligible_mature','min_occupied_spans','max_bins','max_work'):
            integer(getattr(self,k),k)
            if not getattr(self,k): raise ValidationError('Positive research thresholds and budgets required')
        integer(self.seed, 'research bootstrap seed')
        if not 100<=self.bootstrap_replicates<=100000: raise ValidationError('Research bootstrap replicates must be 100..100000')
        for k in ('alpha','min_estimated_fraction','lower_bound_buffer_r'):
            value=number(getattr(self,k)); object.__setattr__(self,k,value)
            if Decimal(value)<0: raise ValidationError('Nonnegative research thresholds required')
        if not 0<Decimal(self.alpha)<Decimal('0.5') or Decimal(self.min_estimated_fraction)>1: raise ValidationError('Invalid research fractions')
        for k in ('require_stress','require_neighbors','require_leave_group_positive'):
            if type(getattr(self,k)) is not bool: raise ValidationError('Explicit research gate booleans required')

    def document(self): return {k:getattr(self,k) for k in self.__dataclass_fields__}
    @classmethod
    def from_dict(cls,d): fields(d,cls); return cls(**d)


@dataclass(frozen=True)
class Experiment:
    name: str
    family: str
    thesis: str
    prior_research: str
    historical_trials: int
    family_trial_budget: int
    variants: tuple
    folds: tuple
    holdout: dict
    holdout_attestation: str
    source_report_hashes: dict | None = None
    portfolio_recipe_hashes: tuple = ()
    holdout_status: str = 'development_only'
    policy: dict | None = None
    version: int = 1

    def __post_init__(self):
        identifier(self.name); identifier(self.family); text(self.thesis); text(self.prior_research); text(self.holdout_attestation)
        if type(self.version) is not int or self.version!=1: raise ValidationError('Unsupported experiment version')
        integer(self.historical_trials, 'historical/manual trial count'); integer(self.family_trial_budget, 'family trial budget')
        if not 1<=self.family_trial_budget<=10000: raise ValidationError('Bounded positive family trial budget required')
        if self.holdout_status not in ('uninspected','development_only'): raise ValidationError('Disclose holdout inspection status')
        if not isinstance(self.variants,(list,tuple)) or not 1<=len(self.variants)<=32: raise ValidationError('One to 32 predeclared variants required')
        vs=tuple(Variant.from_dict(v) for v in self.variants); names={v.name for v in vs}; bases={v.name for v in vs if v.stress_of is None}
        if len(names)!=len(vs) or not bases: raise ValidationError('Distinct variants and at least one base required')
        if any(v.stress_of is not None and v.stress_of not in bases or v.neighbor_of is not None and (v.neighbor_of not in bases or v.neighbor_of==v.name) for v in vs):
            raise ValidationError('Stress/neighborhood references must name a different base variant')
        recipes=self.portfolio_recipe_hashes
        if not isinstance(recipes,(list,tuple)) or len(recipes)>32 or any(not isinstance(h,str) or not re.fullmatch('[a-f0-9]{64}',h) for h in recipes) or len(set(recipes))!=len(recipes):
            raise ValidationError('Distinct bounded predeclared portfolio recipe hashes required')
        object.__setattr__(self,'portfolio_recipe_hashes',tuple(sorted(recipes)))
        if self.historical_trials+len(vs)+len(recipes)>self.family_trial_budget: raise ValidationError('Declared family trial budget exceeded')
        if not isinstance(self.folds,(list,tuple)) or not 1<=len(self.folds)<=20: raise ValidationError('One to 20 chronological outer folds required')
        fs=tuple(Fold.from_dict(f) for f in self.folds); h=Fold.from_dict(self.holdout)
        if len({f.split.name for f in (*fs,h)})!=len(fs)+1: raise ValidationError('Distinct outer/holdout names required')
        previous=None
        for f in (*fs,h):
            if previous is not None and f.split.test.start_ms<previous: raise ValidationError('Outer test ownership must be disjoint and chronological')
            previous=f.split.test.end_ms
            if len(bases)>1 and not f.inner: raise ValidationError('Tuning requires earlier inner validation in every outer/final fold')
        if any(f.split.test.cutoff_ms>h.split.test.start_ms for f in fs): raise ValidationError('Development outcome cutoffs must precede holdout')
        if h.split.train.cutoff_ms>h.split.test.start_ms: raise ValidationError('Final training must precede sealed decisions')
        if self.policy is not None and not isinstance(self.policy,dict): raise ValidationError('Research policy must be an object')
        p=EvidencePolicy.from_dict({} if self.policy is None else self.policy)
        # A percentile estimate needs enough draws to resolve the declared tail.
        if p.bootstrap_replicates*Fraction(p.alpha)/(2*self.family_trial_budget)<1:
            raise ValidationError('Too few bootstrap draws for family-adjusted tail probability')
        refs=self.source_report_hashes
        all_runs={h for v in vs for h in (*v.development_runs,*v.holdout_runs)}
        if (not isinstance(refs,dict) or not all_runs<=set(refs) or len(refs)>6400 or
                any(not isinstance(k,str) or not re.fullmatch('[a-f0-9]{64}',k) or not isinstance(v,str) or not re.fullmatch('[a-f0-9]{64}',v) for k,v in refs.items())):
            raise ValidationError('Every C11 run requires its pinned content-addressed report hash')
        object.__setattr__(self,'source_report_hashes',FrozenRecord.create(refs))
        object.__setattr__(self,'variants',vs); object.__setattr__(self,'folds',fs); object.__setattr__(self,'holdout',h); object.__setattr__(self,'policy',p)

    def document(self):
        return dict(version=self.version,name=self.name,family=self.family,thesis=self.thesis,prior_research=self.prior_research,
                    historical_trials=self.historical_trials,family_trial_budget=self.family_trial_budget,source_report_hashes=self.source_report_hashes.document(),variants=[v.document() for v in self.variants],
                    folds=[f.document() for f in self.folds],holdout=self.holdout.document(),holdout_status=self.holdout_status,
                    holdout_attestation=self.holdout_attestation,portfolio_recipe_hashes=list(self.portfolio_recipe_hashes),policy=self.policy.document())

    @classmethod
    def from_dict(cls,d): fields(d,cls); return cls(**d)
