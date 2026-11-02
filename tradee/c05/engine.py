"""Causal level snapshots from the canonical C02/C03 prefix."""
from tradee.c01.domain import fingerprint
from tradee.c03.catalog import TIMEFRAMES
from tradee.c03.contracts import FrozenRecord
from tradee.observations import ObservationEngine
from .contracts import StructureConfig
from .levels import reference_levels, relationships


class LevelSnapshot(FrozenRecord):
    pass


class StructureEngine(ObservationEngine):
    COMPONENT = 'C05'

    def __init__(self, dataset, config=None):
        super().__init__(dataset, config or StructureConfig())

    @staticmethod
    def definitions():
        return dict(version=1, periods='complete previous UTC day and Monday-based UTC week at target end',
                    range='N contiguous prior bars, excluding current',
                    swings='strictly greater/less than all left/right neighbors; ties excluded; right-bar confirmation lag',
                    revisions='new current snapshot from corrected prefix; never rewrite prior records',
                    relationships='exact close/high/low relations; intrabar observations only for levels known before bar open',
                    lifecycle='retain bounded recent confirmed pivots; no automatic trade invalidation or level ranking',
                    interpretation='price references only; no actual stop liquidity, sweep/retest labels or trading decisions')

    def advance(self, event):
        outputs = self.features.advance(event)
        snapshots = []
        for feature in outputs:
            doc = self.envelope(feature)
            identity, tf = doc['instrument_id'], doc['timeframe']
            interval = TIMEFRAMES[tf]
            bars = self.features.bars[(identity, tf)]
            rows = [dict(**bar['data'], available_ms=bar['available_ms'], source_hash=fingerprint(bar))
                    for _, bar in sorted(bars.items())]
            minutes = [dict(**e['data'], available_ms=e['available_ms'], source_hash=fingerprint(e))
                       for (instrument, kind, _), e in self.features.latest.items()
                       if instrument == identity and kind == 'candle']
            minutes.sort(key=lambda r: r['open_ms'])
            levels = reference_levels(rows, interval, as_of_ms=doc['evaluation_as_of_ms'],
                                      instrument_id=identity, config=self.config,
                                      period_rows=minutes, period_interval=60000)
            current = rows[-1]
            previous = rows[-2] if len(rows) > 1 and rows[-2]['open_ms'] + interval == current['open_ms'] else None
            atr = doc['feature_snapshot']['values']['atr14']
            stale = doc['evaluation_as_of_ms'] - doc['target_end_ms'] >= interval + self.config.candle_grace_ms
            snapshots.append(LevelSnapshot.create(dict(
                **doc, **levels, anchor_basis='target_end_ms', session_timezone='UTC',
                source_status='stale_input' if stale else 'valid',
                ready=not stale and bool(levels['levels']),
                relationships=relationships(levels['levels'], current, previous, atr))))
        return snapshots
