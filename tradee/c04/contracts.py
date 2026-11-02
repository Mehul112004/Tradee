"""Continuous context measurements; no fitted regimes or strategy gates."""
from dataclasses import dataclass

from tradee.c03 import FeatureConfig
from tradee.observations import ConfigDocument, timeframes


CONTEXT_FEATURES = (
    'ema200', 'ema200_prior', 'ema200_distance_atr14', 'ema200_slope5_atr14',
    'atr14', 'atr14_fraction', 'return_sd20', 'log_return_1',
    'relative_quote_volume20_prior', 'taker_base_imbalance20',
    'spread_bps', 'quote_event_age_ms', 'top_bid_quote_notional', 'top_ask_quote_notional')
REQUIRED = ('ema200', 'ema200_distance_atr14', 'ema200_slope5_atr14', 'atr14_fraction', 'return_sd20')


@dataclass(frozen=True)
class ContextConfig(ConfigDocument):
    timeframes: tuple = ('15m', '1h', '4h')
    seed_threshold: float = 1e-6
    max_quote_age_ms: int = 5000
    candle_grace_ms: int = 5000
    output_start_ms: int | None = None
    output_end_ms: int | None = None

    def __post_init__(self):
        object.__setattr__(self, 'timeframes', timeframes(self.timeframes))
        self.feature_config()

    def feature_config(self):
        return FeatureConfig(features=CONTEXT_FEATURES, required_features=REQUIRED,
                             timeframes=self.timeframes, seed_threshold=self.seed_threshold,
                             max_quote_age_ms=self.max_quote_age_ms, candle_grace_ms=self.candle_grace_ms,
                             output_start_ms=self.output_start_ms, output_end_ms=self.output_end_ms)
