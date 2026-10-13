"""Immutable public records, serialized without NaN or mutable aliases."""
from dataclasses import asdict, dataclass
import json
import math
from tradee.c01.domain import canonical, fingerprint

STATUSES = ('valid', 'insufficient_history', 'gap_in_window', 'zero_denominator', 'stale_input',
            'missing_source', 'anchor_incomplete', 'unsupported_coverage', 'numeric_error')


@dataclass(frozen=True)
class FeatureDefinition:
    feature_id: str
    units: str
    min_bars: int
    formula: str
    dependencies: tuple = ()
    inputs: tuple = ('candle',)
    smoothers: tuple = ()  # (period, seed price-bar count, mode, lag)
    version: int = 1
    window_policy: str = 'current-inclusive unless explicitly prior in formula'
    numeric_policy: str = 'float64; centered population variance; exact volume sums'
    gap_policy: str = 'strict-contiguous; recursive reset at segment boundary'
    zero_policy: str = 'null zero_denominator; RSI flat=50; zero standalone volatility valid'
    parameters: tuple = ()
    input_fields: tuple = ('close',)
    timeframes: tuple = ('1m', '15m', '1h', '4h', '1d')
    seed_rule: str = 'none; complete finite window'

    def document(self):
        doc = asdict(self)
        doc['parameters'] = dict(self.parameters)
        return json.loads(canonical(doc))

    @property
    def definition_hash(self):
        return fingerprint(self.document())


@dataclass(frozen=True)
class FeatureValue:
    value: float | None
    status: str
    min_bars: int
    observed_bars: int
    stable: bool = False
    seed_weight: float = 0.0
    flags: tuple = ()

    def __post_init__(self):
        if self.status not in STATUSES or (self.value is not None and not math.isfinite(self.value)):
            raise ValueError('Invalid feature value')
        if (self.status == 'valid') != (self.value is not None):
            raise ValueError('Feature status/value mismatch')

    def document(self):
        return asdict(self)


@dataclass(frozen=True)
class FrozenRecord:
    serialized: str

    @classmethod
    def create(cls, document):
        return cls(canonical(document))

    def document(self):
        return json.loads(self.serialized)

    @property
    def digest(self):
        return fingerprint(self.document())


class FeatureSnapshot(FrozenRecord):
    pass


class RunManifest(FrozenRecord):
    pass
