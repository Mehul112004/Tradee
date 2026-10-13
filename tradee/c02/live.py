"""Bounded reconnecting collectors; explicit foreground lifecycle, no daemon."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import ssl
import sqlite3
import sys
from threading import Event
from urllib.parse import quote

from tradee.c01 import ValidationError
from tradee.c01.domain import symbol_name
from tradee.c01.provider import ProviderError
from .domain import MINUTE, parse_ws
from .provider import RestClient

STREAMS = {'candle': ('market', 'kline_1m'), 'trade': ('market', 'aggTrade'),
           'mark': ('market', 'markPrice@1s'), 'quote': ('public', 'bookTicker')}


def connection(url):
    try:
        from websockets.sync.client import connect
    except ImportError as exc:
        raise ProviderError('Install live dependencies: python3 -m pip install -e ".[live]"', halt_polling=True) from exc
    context = ssl.create_default_context()
    if sys.platform == 'darwin' and not os.environ.get('SSL_CERT_FILE') and os.path.isfile('/etc/ssl/cert.pem'):
        context.load_verify_locations(cafile='/etc/ssl/cert.pem')
    return connect(url, ssl=context, open_timeout=15, close_timeout=5, ping_interval=20,
                   ping_timeout=20, max_size=1_000_000, max_queue=128)


def stream_urls(symbols, kinds):
    symbols = sorted({symbol_name(s) for s in symbols})
    kinds = sorted(set(kinds))
    if not symbols or not kinds or set(kinds) - set(STREAMS):
        raise ValidationError('Choose nonempty symbols and supported streams')
    groups = {}
    for kind in kinds:
        route, suffix = STREAMS[kind]
        groups.setdefault(route, []).extend(quote(s.lower(), safe='') + '@' + suffix for s in symbols)
    if any(len(streams) > 1024 for streams in groups.values()):
        raise ValidationError('More than 1024 streams on one connection')
    return {route: f'wss://fstream.binance.com/{route}/stream?streams=' + '/'.join(streams)
            for route, streams in groups.items()}


class Collector:
    def __init__(self, store, symbols, kinds=('candle',), connect=connection, rest=None, max_reconnects=20):
        self.store, self.symbols, self.kinds = store, tuple(symbols), tuple(kinds)
        self.urls = stream_urls(self.symbols, self.kinds)
        if type(max_reconnects) is not int or not 0 <= max_reconnects <= 100:
            raise ValidationError('max_reconnects must be an integer from 0 to 100')
        self.connect, self.rest, self.max_reconnects = connect, rest or RestClient(), max_reconnects
        for symbol in self.symbols:
            store.binding(symbol)

    def repair(self, symbol, end_ms=None, start_ms=None):
        end = self.store.now() // MINUTE * MINUTE if end_ms is None else end_ms
        checkpoint = self.store.checkpoint('live:candle:' + symbol)
        start = checkpoint['open_ms'] if checkpoint else max(0, end - 5 * MINUTE)
        gap = self.store.checkpoint('live:gap:' + symbol)
        if gap:
            start = min(start, gap['next_ms'])
        if start_ms is not None:
            start = min(start, start_ms)
        # Replay overlap to capture close corrections; larger outages need explicit backfill.
        if end - start > 1440 * MINUTE:
            self.store.log(action='repair_window_truncated', symbol=symbol, missing_start_ms=start,
                           repair_start_ms=end - 1440 * MINUTE)
            start = end - 1440 * MINUTE
        if start < end:
            self.store.save_checkpoint('live:gap:' + symbol, {'next_ms': start})
            result = self.rest.backfill(self.store, symbol, start, end, resume=False)
            gaps = self.store.candle_gaps(symbol, start, end)
            self.store.save_checkpoint('live:gap:' + symbol, {'next_ms': gaps[0] if gaps else end})
            self.store.log(action='repair_finished', symbol=symbol, missing_candles=len(gaps))
            return result

    def process(self, raw, source, received_ms):
        checkpoint = {}
        def parse(text):
            item = parse_ws(text)
            if item['symbol'] not in self.symbols or item['kind'] not in self.kinds:
                raise ValidationError('Unsubscribed symbol or stream')
            return [item]
        # One parse before repair, followed by the audited parser during ingestion.
        try:
            item = parse(raw)[0]
        except (ValueError, KeyError, TypeError):
            return self.store.ingest(raw, source, parse, received_ms)
        repair_start = None
        if item['kind'] == 'candle' and item['final']:
            name = 'live:candle:' + item['symbol']
            previous = self.store.checkpoint(name)
            if previous and item['data']['open_ms'] > previous['open_ms'] + MINUTE:
                repair_start = previous['open_ms']
            checkpoint = (name, {'open_ms': max(item['data']['open_ms'], previous['open_ms'] if previous else 0)})
        result = self.store.ingest(raw, source, parse, received_ms, checkpoint=checkpoint)
        if repair_start is not None:
            self.repair(item['symbol'], item['data']['open_ms'], repair_start)
        return result

    def run_route(self, route, stop):
        failures = 0
        while not stop.is_set():
            try:
                with self.connect(self.urls[route]) as socket:
                    self.store.log(action='connected', route=route)
                    silent = 0
                    if route == 'market' and 'candle' in self.kinds:
                        for symbol in self.symbols:
                            self.repair(symbol)
                    while not stop.is_set():
                        try:
                            raw = socket.recv(timeout=2)
                        except TimeoutError:
                            # Silence is explicit and causes a bounded reconnect, not a healthy-looking loop.
                            silent += 2
                            if silent >= 60:
                                raise OSError('No market messages for 60 seconds')
                            continue
                        silent = 0
                        received = self.store.now()
                        try:
                            self.process(raw, self.urls[route], received)
                        except ValidationError as exc:
                            self.store.log(action='quarantined', route=route, error=str(exc))
            except Exception as exc:
                self.store.log(action='disconnected', route=route, error=str(exc))
                if isinstance(exc, (ImportError, TypeError, AttributeError, sqlite3.Error)):
                    raise
                status = getattr(getattr(exc, 'response', None), 'status_code', None)
                if (isinstance(exc, ssl.SSLCertVerificationError) or getattr(exc, 'halt_polling', False)
                        or status in (400, 401, 403, 418, 451)):
                    raise ProviderError(str(exc), halt_polling=True) from exc
                failures += 1
                if failures > self.max_reconnects:
                    raise ProviderError('WebSocket reconnect budget exhausted') from exc
                wait = max(min(30, 2 ** min(failures-1, 5)), getattr(exc, 'retry_after_seconds', 0))
                if status == 429:
                    header = getattr(exc.response, 'headers', {}).get('Retry-After')
                    if header:
                        try:
                            delay = float(header)
                        except ValueError:
                            try:
                                delay = (parsedate_to_datetime(header) - datetime.fromtimestamp(self.store.now()/1000, timezone.utc)).total_seconds()
                            except (ValueError, TypeError):
                                delay = 0
                        if math.isfinite(delay):
                            wait = max(wait, delay)
                self.store.log(action='reconnect_wait', route=route, seconds=wait)
                stop.wait(wait)

    def run(self, stop=None):
        stop = stop or Event()
        with ThreadPoolExecutor(max_workers=len(self.urls)) as pool:
            futures = [pool.submit(self.run_route, route, stop) for route in self.urls]
            try:
                for future in as_completed(futures):
                    future.result()
            finally:
                stop.set()
