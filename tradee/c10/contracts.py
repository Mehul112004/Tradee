"""Versioned cohort estimation, causal fit windows and inference inputs."""
from dataclasses import dataclass,asdict
from decimal import Decimal
import json
from tradee.c01 import ValidationError
from tradee.c01.domain import canonical,fingerprint
from tradee.c02.domain import integer,number
from tradee.c03.contracts import FrozenRecord
from tradee.c06 import FundingConfig
from tradee.c07 import ExecutionConfig,FeeSchedule
from tradee.c08 import CandidateConfig
from tradee.c09 import TradeIntent
from tradee.c11 import Scenario


def fields(doc,cls):
    if not isinstance(doc,dict) or set(doc)-set(cls.__dataclass_fields__): raise ValidationError('Unknown expectancy input fields')


@dataclass(frozen=True)
class TrainingWindow:
    start_ms: int
    end_ms: int
    cutoff_ms: int

    def __post_init__(self):
        for k in ('start_ms','end_ms','cutoff_ms'): integer(getattr(self,k),k)
        if not self.start_ms<self.end_ms<=self.cutoff_ms: raise ValidationError('Training requires start < decision end <= knowledge cutoff')

    def document(self): return asdict(self)
    @classmethod
    def from_dict(cls,d):
        fields(d,cls)
        if set(d)!=set(cls.__dataclass_fields__): raise ValidationError('Complete training window required')
        return cls(**d)


@dataclass(frozen=True)
class EstimatorConfig:
    version: int = 1
    cohort_fields: tuple = ('side','horizon')
    min_trades: int = 30
    min_occupied_bins: int = 20
    min_occupied_spans: int = 10
    min_mature_fraction: str = '0.8'
    min_fill_fraction: str = '0.5'
    bin_ms: int = 86400000
    block_bins: int = 3
    bootstrap_replicates: int = 2000
    confidence_level: str = '0.95'
    max_empty_replicate_fraction: str = '0.05'
    seed: int = 20261019
    max_model_age_ms: int = 604800000
    lower_bound_buffer_r: str = '0'
    max_source_runs: int = 100
    max_cohorts: int = 256
    max_rows: int = 100000
    max_bins: int = 10000
    max_bootstrap_work: int = 20000000

    def __post_init__(self):
        if type(self.version) is not int or self.version!=1: raise ValidationError('Unsupported expectancy version')
        if not isinstance(self.cohort_fields,(tuple,list)) or len(set(self.cohort_fields))!=len(self.cohort_fields) or any(k not in ('side','horizon','symbol') for k in self.cohort_fields):
            raise ValidationError('Supported predeclared cohorts are side, horizon and optional symbol')
        object.__setattr__(self,'cohort_fields',tuple(k for k in ('side','horizon','symbol') if k in self.cohort_fields))
        for k in ('min_trades','min_occupied_bins','min_occupied_spans','bin_ms','block_bins','bootstrap_replicates','max_model_age_ms','max_source_runs','max_cohorts','max_rows','max_bins','max_bootstrap_work'):
            integer(getattr(self,k),k)
            if not getattr(self,k): raise ValidationError('Positive expectancy thresholds/budgets required')
        integer(self.seed,'bootstrap seed')
        if not 100<=self.bootstrap_replicates<=100000: raise ValidationError('Bootstrap replicates must be 100..100000')
        for k in ('min_mature_fraction','min_fill_fraction','confidence_level','max_empty_replicate_fraction'):
            value=number(getattr(self,k)); object.__setattr__(self,k,value)
            if not 0<=Decimal(value)<=1: raise ValidationError('Expectancy fractions must lie in [0,1]')
        if not Decimal('0.5')<Decimal(self.confidence_level)<1: raise ValidationError('Confidence level must lie in (0.5,1)')
        object.__setattr__(self,'lower_bound_buffer_r',number(self.lower_bound_buffer_r))
        if Decimal(self.lower_bound_buffer_r)<0: raise ValidationError('Nonnegative admission buffer required')

    def document(self): return json.loads(canonical(asdict(self)))
    @classmethod
    def from_dict(cls,d): fields(d,cls); return cls(**d)


def protocol(scenario,execution,fees,funding,candidates,mode,definitions):
    """Semantically matched hypotheses/costs; data vintages remain provenance."""
    scenario=scenario if isinstance(scenario,Scenario) else Scenario.from_dict(scenario)
    execution=execution if isinstance(execution,ExecutionConfig) else ExecutionConfig.from_dict(execution)
    fees=fees if isinstance(fees,FeeSchedule) else FeeSchedule.from_dict(fees)
    funding=funding if isinstance(funding,FundingConfig) else FundingConfig.from_dict(funding)
    candidates=candidates if isinstance(candidates,CandidateConfig) else CandidateConfig.from_dict(candidates)
    if mode not in ('recorded','modeled') or not isinstance(definitions,dict): raise ValidationError('Available feature definitions and data mode required')
    if (execution.enabled_symbols!=candidates.enabled_symbols or execution.metadata_mode!=candidates.metadata_mode or execution.max_metadata_age_ms!=candidates.max_metadata_age_ms):
        raise ValidationError('Expectancy candidate/execution metadata policies differ')
    return dict(strategy=scenario.strategy.definition(),policy=scenario.policy.document(),quantity=scenario.quantity,
        execution=execution.document(),fees=fees.document(),funding=funding.document(),candidates=candidates.document(),
        availability_mode=mode,feature_definition_hashes=definitions)


@dataclass(frozen=True)
class EstimateRequest:
    candidate: dict
    feature_snapshot: dict
    scenario: dict
    execution: dict
    fees: dict
    funding: dict
    candidates: dict
    evaluation_ms: int

    def __post_init__(self):
        s=Scenario.from_dict(self.scenario); i=TradeIntent(self.candidate,self.feature_snapshot,s.quantity,s.policy.document())
        c=i.candidate.document(); f=i.feature_snapshot.document(); integer(self.evaluation_ms,'expectancy decision time')
        if c['strategy_hash']!=s.strategy.strategy_hash or c['hypothesis_family']!=s.strategy.family or c['timeframe']!=s.strategy.timeframe or c['side'] not in s.strategy.sides:
            raise ValidationError('Inference scenario differs from candidate strategy')
        if not c['detected_ms']<=self.evaluation_ms<c['expires_ms'] or f['assumed_usable_ms']>self.evaluation_ms:
            raise ValidationError('Inference candidate is not currently available/unexpired')
        for name in i.required_features:
            value=f['values'].get(name,{})
            if value.get('status')!='valid' or value.get('value') is None or value.get('stable') is not True: raise ValidationError('Inference requires stable valid strategy features')
        p=protocol(s,self.execution,self.fees,self.funding,self.candidates,c['availability_basis'],f['definition_hashes'])
        if c['metadata_mode']!=p['candidates']['metadata_mode']: raise ValidationError('Candidate metadata mode differs from inference protocol')
        if c['detected_ms']-c['target_end_ms']>=p['candidates']['max_detection_lag_ms']:
            raise ValidationError('Candidate detection is stale under the declared protocol')
        object.__setattr__(self,'candidate',i.candidate); object.__setattr__(self,'feature_snapshot',i.feature_snapshot)
        object.__setattr__(self,'scenario',FrozenRecord.create(s.document()))
        for k in ('execution','fees','funding','candidates'): object.__setattr__(self,k,FrozenRecord.create(p[k]))

    def document(self):
        return {k:(getattr(self,k).document() if k!='evaluation_ms' else self.evaluation_ms) for k in self.__dataclass_fields__}

    @property
    def protocol(self):
        d=self.document(); return protocol(d['scenario'],d['execution'],d['fees'],d['funding'],d['candidates'],d['candidate']['availability_basis'],d['feature_snapshot']['definition_hashes'])

    @classmethod
    def from_dict(cls,d):
        fields(d,cls)
        if set(d)!=set(cls.__dataclass_fields__): raise ValidationError('Complete expectancy request required')
        return cls(**d)


class ExpectancyRecord(FrozenRecord):
    pass


def cohort_key(protocol_hash,attributes,config):
    return fingerprint([protocol_hash,{k:attributes[k] for k in config.cohort_fields}])
