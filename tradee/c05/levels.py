"""Exact price references and descriptive bar/level relationships.

Levels are reconstructed from a supplied available prefix. A new source vintage
may change the current view; previously emitted snapshots are immutable.
"""
from decimal import Decimal, localcontext

from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c02.domain import MINUTE, integer, number
from .contracts import StructureConfig

DAY = 86400000
WEEK = 7 * DAY


def strict_swing_extreme(value,neighbors,side):
    """Shared exact strict-extremum rule; callers own contiguous confirmation windows."""
    if side not in ('high','low') or not neighbors: raise ValidationError('Swing side and neighbors required')
    return value>max(neighbors) if side=='high' else value<min(neighbors)


def _contiguous(rows, interval):
    return bool(rows) and all(b['open_ms'] == a['open_ms'] + interval for a, b in zip(rows, rows[1:]))


def _rows(rows, interval, as_of_ms):
    result = []
    for row in rows:
        start = integer(row['open_ms'], 'level bar open')
        available = integer(row.get('available_ms', start + interval), 'level bar availability')
        if (start % interval or available < start + interval or available > as_of_ms
                or result and start <= result[-1]['open_ms']):
            raise ValidationError('Level inputs must be sorted, unique, complete and already available')
        d = dict(open_ms=start, available_ms=available,
                 **{k: number(row[k], positive=True) for k in ('high', 'low', 'close')})
        if not Decimal(d['low']) <= Decimal(d['close']) <= Decimal(d['high']):
            raise ValidationError('Invalid level input envelope')
        d['source_hash'] = row.get('source_hash') or fingerprint(d)
        result.append(d)
    return result


def reference_levels(rows, interval, *, as_of_ms=None, instrument_id='display', config=None,
                     period_rows=None, period_interval=None):
    """Return current levels and per-family coverage; never infer orders/stops.

    Periods are anchored at the latest target's exclusive end. Pure display
    callers may supply native bars; replay callers supply C02 one-minute bars
    for complete UTC day/week evidence independently of the output timeframe.
    """
    config = config or StructureConfig()
    if type(interval) is not int or interval < MINUTE or interval % MINUTE or DAY % interval:
        raise ValidationError('Level interval must divide a UTC day')
    if not rows:
        return dict(levels=[], coverage=dict(target='missing_source'))
    as_of_ms = rows[-1]['open_ms'] + interval if as_of_ms is None else integer(as_of_ms, 'level as_of_ms')
    rows = _rows(rows, interval, as_of_ms)
    target_end = rows[-1]['open_ms'] + interval
    source_interval = interval if period_interval is None else period_interval
    if (type(source_interval) is not int or source_interval < MINUTE
            or source_interval % MINUTE or DAY % source_interval):
        raise ValidationError('Period source interval must divide a UTC day')
    periods = rows if period_rows is None else _rows(period_rows, source_interval, as_of_ms)
    result, coverage = [], {}

    def add(kind, side, sources, anchor, confirmed, scope_interval):
        price = (max if side == 'high' else min)((r[side] for r in sources), key=Decimal)
        identity = dict(instrument_id=instrument_id, kind=kind, side=side, anchor_ms=anchor,
                        interval_ms=scope_interval)
        if kind == 'swing':
            identity.update(pivot_left=config.pivot_left, pivot_right=config.pivot_right)
        elif kind == 'prior_range':
            identity['range_bars'] = config.range_bars
        doc = dict(level_id=fingerprint(identity), **identity, price=price,
                   source_start_ms=sources[0]['open_ms'], source_end_ms=sources[-1]['open_ms'] + scope_interval,
                   confirmed_ms=confirmed, known_ms=max(r['available_ms'] for r in sources),
                   source_hash=fingerprint([r['source_hash'] for r in sources]))
        doc['revision_hash'] = fingerprint(doc)
        result.append(doc)

    prior = rows[-config.range_bars-1:-1]
    if len(prior) == config.range_bars and _contiguous(rows[-config.range_bars-1:], interval):
        coverage['prior_range'] = 'valid'
        for side in ('high', 'low'):
            add('prior_range', side, prior, rows[-1]['open_ms'], rows[-1]['open_ms'], interval)
    else:
        coverage['prior_range'] = 'insufficient_or_gapped_history'

    for kind, enabled, duration, end in (
            ('previous_day', config.previous_day, DAY, target_end // DAY * DAY),
            ('previous_week', config.previous_week, WEEK, (target_end - 4 * DAY) // WEEK * WEEK + 4 * DAY)):
        if not enabled:
            coverage[kind] = 'disabled'
            continue
        selected = [r for r in periods if end - duration <= r['open_ms'] < end]
        if (len(selected) == duration // source_interval and selected[0]['open_ms'] == end - duration
                and _contiguous(selected, source_interval)):
            coverage[kind] = 'valid'
            for side in ('high', 'low'):
                add(kind, side, selected, end - duration, end, source_interval)
        else:
            coverage[kind] = 'anchor_incomplete'

    left, right = config.pivot_left, config.pivot_right
    coverage['swings'] = 'valid' if any(
        _contiguous(rows[i-left:i+right+1], interval)
        for i in range(left, len(rows)-right)) else 'insufficient_or_gapped_history'
    for side in ('high', 'low'):
        found = 0
        for i in range(len(rows)-right-1, left-1, -1):
            window = rows[i-left:i+right+1]
            if not _contiguous(window, interval):
                continue
            value = Decimal(rows[i][side])
            neighbors = [Decimal(r[side]) for j, r in enumerate(window) if j != left]
            if strict_swing_extreme(value,neighbors,side):
                # Price belongs to the pivot; all neighbors are confirmation evidence.
                add('swing', side, [rows[i]], rows[i]['open_ms'], rows[i+right]['open_ms'] + interval, interval)
                level = result[-1]
                level.update(source_start_ms=window[0]['open_ms'], source_end_ms=window[-1]['open_ms'] + interval,
                             known_ms=max(r['available_ms'] for r in window),
                             source_hash=fingerprint([r['source_hash'] for r in window]))
                level.pop('revision_hash')
                level['revision_hash'] = fingerprint(level)
                found += 1
                if found == config.max_pivots_per_side:
                    break
    return dict(levels=result, coverage=coverage)


def relationships(levels, current, previous=None, atr=None):
    """Exact relations; intrabar observations require a level known before open."""
    result = []
    for level in levels:
        price = Decimal(level['price'])
        def relation(value):
            return 'above' if Decimal(value) > price else 'below' if Decimal(value) < price else 'equal'
        known = level['known_ms'] <= current['open_ms']
        with localcontext() as ctx:
            ctx.prec = 120
            distance = format(Decimal(current['close']) - price, 'f')
            distance = distance.rstrip('0').rstrip('.') if '.' in distance else distance
            if Decimal(distance) == 0:
                distance = '0'
        normalized = None
        status = 'missing_source' if atr is None else atr['status']
        if atr is not None and status == 'valid':
            if atr['value'] == 0:
                status = 'zero_denominator'
            else:
                from tradee.c03.rolling import divide, finite
                try:
                    normalized = divide(finite(Decimal(distance)), atr['value'])
                except ArithmeticError:
                    status = 'numeric_error'
        result.append(dict(level_id=level['level_id'], revision_hash=level['revision_hash'],
                           close_relation=relation(current['close']), distance_price=distance,
                           distance_atr14=normalized, distance_atr14_status=status,
                           atr14_stable=False if atr is None else atr.get('stable', False),
                           level_known_before_bar=known,
                           touched_in_bar=(Decimal(current['low']) <= price <= Decimal(current['high'])) if known else None,
                           high_relation=relation(current['high']) if known else None,
                           low_relation=relation(current['low']) if known else None,
                           previous_close_relation=relation(previous['close']) if known and previous is not None else None))
    return result
