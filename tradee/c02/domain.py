"""Versioned market-event normalization. All timestamps are UTC milliseconds."""
from decimal import Decimal, InvalidOperation, localcontext
import json

from tradee.c01.domain import ValidationError, canonical, symbol_name

MINUTE = 60_000
KINDS = ('candle', 'trade', 'quote', 'mark', 'funding', 'open_interest')


def integer(value, name, csv=False):
    if csv and isinstance(value, str) and value.isascii() and value.isdigit():
        value = int(value)
    if type(value) is not int or not 0 <= value < 10**14:
        raise ValidationError(f'{name} must be a nonnegative millisecond timestamp or integer (not microseconds)')
    return value


def number(value, positive=False, signed=False):
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValidationError('Numbers require exact decimal strings or integers')
    try:
        n = Decimal(value)
    except InvalidOperation as exc:
        raise ValidationError('Invalid decimal') from exc
    if not n.is_finite() or (not signed and n < 0) or (positive and n <= 0):
        raise ValidationError('Invalid price, quantity or rate')
    if len(n.as_tuple().digits) > 50 or abs(n.as_tuple().exponent) > 50:
        raise ValidationError('Decimal exceeds supported precision')
    if n == 0:
        return '0'
    text = format(n, 'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def event(symbol, kind, key, event_ms, data, final=True):
    return dict(schema_version=1, symbol=symbol_name(symbol), kind=kind, key=str(key),
                event_ms=integer(event_ms, 'event_ms'), final=final, data=data)


def candle(symbol, row, final=True, csv=False):
    if not isinstance(row, (list, tuple)) or len(row) != 12 or type(final) is not bool:
        raise ValidationError('Expected a 12-field Binance candle and boolean finality')
    start = integer(row[0], 'open_ms', csv)
    close = integer(row[6], 'close_ms', csv)
    if start % MINUTE or close != start + MINUTE - 1:
        raise ValidationError('Only aligned one-minute candles are accepted')
    fields = ('open', 'high', 'low', 'close', 'volume', 'quote_volume', 'taker_base', 'taker_quote')
    d = {k: number(row[i], positive=k in fields[:4]) for k, i in zip(fields, (1, 2, 3, 4, 5, 7, 9, 10))}
    n = {k: Decimal(v) for k, v in d.items()}
    if not n['low'] <= min(n['open'], n['close']) <= max(n['open'], n['close']) <= n['high']:
        raise ValidationError('Invalid OHLC bounds')
    if n['taker_base'] > n['volume'] or n['taker_quote'] > n['quote_volume']:
        raise ValidationError('Taker volume exceeds total volume')
    d.update(open_ms=start, close_ms=close, interval_ms=MINUTE, trades=integer(row[8], 'trades', csv))
    return event(symbol, 'candle', start, close, d, final)


def parse_ws(raw):
    message = json.loads(raw)
    canonical(message)
    if not isinstance(message, dict):
        raise ValidationError('Expected a WebSocket object')
    p = message.get('data', message)
    if not isinstance(p, dict):
        raise ValidationError('Invalid combined stream envelope')
    symbol = symbol_name(p.get('s'))
    emitted = integer(p.get('E'), 'exchange_event_ms')
    kind = p.get('e')
    if kind == 'kline':
        k = p.get('k')
        if not isinstance(k, dict) or k.get('s') != symbol or k.get('i') != '1m':
            raise ValidationError('Invalid or unsupported kline identity/interval')
        row = [k.get(f) for f in ('t', 'o', 'h', 'l', 'c', 'v', 'T', 'q', 'n', 'V', 'Q')] + ['0']
        result = candle(symbol, row, k.get('x'))
        if emitted < result['data']['open_ms']:
            raise ValidationError('Candle update emitted before its open')
        if result['final'] and emitted < result['event_ms']:
            raise ValidationError('Final candle emitted before its close')
    elif kind == 'aggTrade':
        first, last = integer(p.get('f'), 'first_trade_id'), integer(p.get('l'), 'last_trade_id')
        if first > last or type(p.get('m')) is not bool:
            raise ValidationError('Invalid trade IDs or maker flag')
        result = event(symbol, 'trade', integer(p.get('a'), 'aggregate_trade_id'), p.get('T'),
                       dict(price=number(p.get('p'), positive=True), quantity=number(p.get('q'), positive=True),
                            first_trade_id=first, last_trade_id=last, buyer_is_maker=p['m']))
    elif kind == 'bookTicker':
        d = {name: number(p.get(key), positive=name in ('bid', 'ask'))
             for name, key in (('bid', 'b'), ('ask', 'a'), ('bid_qty', 'B'), ('ask_qty', 'A'))}
        if Decimal(d['bid']) > Decimal(d['ask']):
            raise ValidationError('Crossed quote')
        result = event(symbol, 'quote', integer(p.get('u'), 'update_id'), p.get('T'), d)
    elif kind == 'markPriceUpdate':
        result = event(symbol, 'mark', emitted, emitted,
                       dict(mark_price=number(p.get('p'), positive=True), index_price=number(p.get('i'), positive=True),
                            funding_rate=number(p.get('r'), signed=True),
                            next_funding_ms=integer(p.get('T'), 'next_funding_ms')))
    else:
        raise ValidationError(f'Unsupported WebSocket event: {kind}')
    result['exchange_event_ms'] = emitted
    return result


def rest_rows(kind, symbol, rows, received_ms):
    if not isinstance(rows, list):
        raise ValidationError('Expected a REST array')
    canonical(rows)
    result = []
    for row in rows:
        if kind == 'candle':
            item = candle(symbol, row)
            item['final'] = item['event_ms'] < received_ms
        elif kind == 'funding':
            if not isinstance(row, dict) or row.get('symbol') != symbol:
                raise ValidationError('Funding symbol mismatch')
            stamp = integer(row.get('fundingTime'), 'fundingTime')
            item = event(symbol, kind, stamp, stamp,
                         dict(funding_rate=number(row.get('fundingRate'), signed=True),
                              mark_price=number(row.get('markPrice'), positive=True)))
        elif kind == 'open_interest':
            if not isinstance(row, dict) or row.get('symbol') != symbol:
                raise ValidationError('Open interest symbol mismatch')
            stamp = integer(row.get('timestamp'), 'timestamp')
            item = event(symbol, kind, stamp, stamp,
                         dict(open_interest=number(row.get('sumOpenInterest')),
                              notional=number(row.get('sumOpenInterestValue'))))
        else:
            raise ValidationError('Unsupported REST dataset')
        result.append(item)
    return result


def aggregate(events, interval_ms):
    """Aggregate a point-in-time candle view. Never fill or emit incomplete buckets."""
    if type(interval_ms) is not int or interval_ms < MINUTE or interval_ms % MINUTE or 86_400_000 % interval_ms:
        raise ValidationError('Aggregation interval must be whole minutes dividing a UTC day')
    groups = {}
    for e in events:
        if e['kind'] != 'candle' or not e['final']:
            continue
        d = e['data']
        if d['interval_ms'] != MINUTE:
            raise ValidationError('Aggregation requires base one-minute candles')
        bucket = d['open_ms'] // interval_ms * interval_ms
        group = groups.setdefault((e['instrument_id'], bucket), {})
        if d['open_ms'] in group:
            raise ValidationError('Supply a latest-per-key view, not revision events')
        group[d['open_ms']] = e
    output = []
    for (_, start), group in sorted(groups.items()):
        if set(group) != set(range(start, start + interval_ms, MINUTE)):
            continue
        parts = [group[t] for t in sorted(group)]
        ds = [p['data'] for p in parts]
        with localcontext() as ctx:
            ctx.prec = 120
            data = {key: number(str(sum(Decimal(d[key]) for d in ds)))
                    for key in ('volume', 'quote_volume', 'taker_base', 'taker_quote')}
        data.update(open=ds[0]['open'], close=ds[-1]['close'],
                    high=max((d['high'] for d in ds), key=Decimal), low=min((d['low'] for d in ds), key=Decimal),
                    open_ms=start, close_ms=start + interval_ms - 1, interval_ms=interval_ms,
                    trades=sum(d['trades'] for d in ds))
        output.append(dict(symbol=parts[0]['symbol'], instrument_id=parts[0]['instrument_id'], kind='candle',
                           final=True, event_ms=data['close_ms'], available_ms=max(p['available_ms'] for p in parts),
                           constituents=[p['id'] for p in parts], data=data))
    return output
