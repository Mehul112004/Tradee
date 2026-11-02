"""Same-prefix multi-timeframe context, preserving each frame's readiness."""
from tradee.c03.contracts import FrozenRecord
from tradee.observations import ObservationEngine
from .contracts import ContextConfig


class MarketStateSnapshot(FrozenRecord):
    pass


class ContextEngine(ObservationEngine):
    COMPONENT = 'C04'

    def __init__(self, dataset, config=None):
        super().__init__(dataset, config or ContextConfig())

    @staticmethod
    def definitions():
        return dict(version=1, trend='EMA200 distance and five-bar slope in ATR units',
                    volatility='ATR14/close and population standard deviation of 20 log returns',
                    participation='prior-window relative quote volume and candle taker imbalance',
                    liquidity='optional observed spread, quote age and top-of-book notionals; not full depth',
                    frames='latest complete available frame at the identical input prefix; per-frame readiness',
                    interpretation='continuous measurements; no bullish/bearish labels, thresholds or routing')

    def advance(self, event):
        outputs = self.features.advance(event)
        by_frame = {(s.document()['instrument_id'], s.document()['timeframe']): s for s in outputs}
        frames = {}
        for identity, _ in by_frame:
            if identity not in frames:
                frames[identity] = {}
                for tf in self.config.timeframes:
                    feature = by_frame.get((identity, tf))
                    if feature is None:
                        feature = self.features.evaluate(identity, tf, event['available_ms'])
                    frames[identity][tf] = dict(snapshot_hash=feature.digest, **feature.document())
        snapshots = []
        for feature in outputs:
            doc = self.envelope(feature)
            snapshots.append(MarketStateSnapshot.create(dict(
                **doc, frames=frames[doc['instrument_id']], ready=doc['feature_snapshot']['ready'])))
        return snapshots
