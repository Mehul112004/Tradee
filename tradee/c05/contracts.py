"""Explicit level-construction choices, independent of trading rules."""
from dataclasses import dataclass

from tradee.c01 import ValidationError
from tradee.c03 import FeatureConfig
from tradee.observations import ConfigDocument, timeframes


@dataclass(frozen=True)
class StructureConfig(ConfigDocument):
    timeframes: tuple = ('15m', '1h', '4h')
    range_bars: int = 20
    pivot_left: int = 2
    pivot_right: int = 2
    max_pivots_per_side: int = 20
    previous_day: bool = True
    previous_week: bool = True
    candle_grace_ms: int = 5000
    output_start_ms: int | None = None
    output_end_ms: int | None = None

    def __post_init__(self):
        object.__setattr__(self, 'timeframes', timeframes(self.timeframes))
        for name, low, high in (('range_bars', 2, 1000), ('pivot_left', 1, 100),
                                ('pivot_right', 1, 100), ('max_pivots_per_side', 1, 100)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValidationError(f'Invalid {name}: expected integer {low}..{high}')
        if type(self.previous_day) is not bool or type(self.previous_week) is not bool:
            raise ValidationError('Period-level switches must be booleans')
        self.feature_config()

    def feature_config(self):
        return FeatureConfig(features=('atr14',), timeframes=self.timeframes,
                             required_features=(), candle_grace_ms=self.candle_grace_ms,
                             output_start_ms=self.output_start_ms, output_end_ms=self.output_end_ms)
