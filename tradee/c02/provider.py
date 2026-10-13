"""Public Binance adapters. Historical data remains observed at download time."""
import csv
from datetime import date, datetime, timezone
import calendar
import hashlib
from io import BytesIO, StringIO
import json
from pathlib import PurePosixPath
import re
import time
from urllib.parse import urlencode, quote
from urllib.request import Request
from zipfile import ZipFile

from tradee.c01 import ValidationError
from tradee.c01.domain import symbol_name
from tradee.c01.provider import BinanceProvider, ProviderError, verified_urlopen
from .domain import MINUTE, integer, candle, rest_rows


class RestClient:
    def __init__(self, provider_factory=BinanceProvider, sleep=time.sleep, clock=time.time):
        self.provider_factory, self.sleep, self.clock = provider_factory, sleep, clock

    def fetch(self, path, params):
        provider = self.provider_factory()
        provider.endpoint = 'https://fapi.binance.com' + path + '?' + urlencode(params)
        return provider.fetch()

    def backfill(self, store, symbol, start_ms, end_ms, kind='candle', resume=True):
        symbol_name(symbol)
        integer(start_ms, 'start_ms'); integer(end_ms, 'end_ms')
        paths = {'candle': '/fapi/v1/klines', 'funding': '/fapi/v1/fundingRate',
                 'open_interest': '/futures/data/openInterestHist'}
        if kind not in paths or start_ms >= end_ms or end_ms > int(self.clock()*1000):
            raise ValidationError('Invalid historical range or dataset')
        if kind == 'candle' and (start_ms % MINUTE or end_ms % MINUTE):
            raise ValidationError('Candle ranges require minute-aligned [start,end) bounds')
        store.binding(symbol)
        name = f'rest:{kind}:{symbol}:{start_ms}:{end_ms}'
        saved = store.checkpoint(name) if resume else None
        cursor = saved['next_ms'] if saved else start_ms
        added = pages = 0
        while cursor < end_ms:
            params = dict(symbol=symbol, startTime=cursor, endTime=end_ms-1, limit=499)
            if kind == 'candle':
                params['interval'] = '1m'
            if kind == 'open_interest':
                params['period'] = '5m'
            result = self.fetch(paths[kind], params)
            next_cursor = [None]

            def parse(raw):
                items = rest_rows(kind, symbol, json.loads(raw), result.received_ms)
                stamps = [e['data'].get('open_ms', e['event_ms']) for e in items]
                if stamps != sorted(set(stamps)) or any(t < cursor or t >= end_ms for t in stamps):
                    raise ValidationError('Nonprogressing, duplicated or out-of-range REST page')
                if kind == 'candle' and any(not e['final'] for e in items):
                    raise ValidationError('REST repair returned an unclosed candle')
                next_cursor[0] = (stamps[-1] + (MINUTE if kind == 'candle' else 1)) if stamps else end_ms
                return items

            # The parser fills the checkpoint inside the same transaction as its page.
            checkpoint = {'next_ms': cursor}
            def parse_checkpoint(raw):
                items = parse(raw)
                checkpoint['next_ms'] = next_cursor[0]
                return items
            output = store.ingest(result.raw, result.source, parse_checkpoint, result.received_ms, (name, checkpoint))
            cursor = next_cursor[0]
            pages += 1
            added += output['added']
            if cursor < end_ms:
                self.sleep(0.25)
        return dict(symbol=symbol, kind=kind, pages=pages, added=added, next_ms=cursor,
                    coverage='Inspect a dataset quality report; empty or sparse responses do not prove completeness')


class ArchiveClient:
    """One daily/monthly USD-M 1m ZIP, verified against its published SHA-256."""
    def __init__(self, opener=verified_urlopen, clock=time.time):
        self.opener, self.clock = opener, clock

    def url(self, symbol, period):
        symbol_name(symbol)
        if not re.fullmatch(r'\d{4}-\d{2}(-\d{2})?', period):
            raise ValidationError('Archive period must be YYYY-MM or YYYY-MM-DD')
        date.fromisoformat(period if len(period) == 10 else period + '-01')
        frequency = 'daily' if len(period) == 10 else 'monthly'
        encoded = quote(symbol, safe='')
        return f'https://data.binance.vision/data/futures/um/{frequency}/klines/{encoded}/1m/{encoded}-1m-{period}.zip'

    def download(self, url, limit):
        with self.opener(Request(url, headers={'User-Agent': 'Tradee-C02/0.1'}), timeout=30) as response:
            content = response.read(limit + 1)
        if len(content) > limit:
            raise ProviderError('Archive response exceeds size limit')
        return content

    def fetch(self, store, symbol, period):
        url = self.url(symbol, period)
        store.binding(symbol)
        checksum = self.download(url + '.CHECKSUM', 4096).decode('ascii')
        content = self.download(url, 50_000_000)
        return self.ingest(store, symbol, content, checksum, url, int(self.clock()*1000))

    def ingest(self, store, symbol, content, checksum, source='file:archive', received_ms=None):
        def parse(raw):
            parts = checksum.split()
            if len(parts) != 2 or not re.fullmatch(r'[a-fA-F0-9]{64}', parts[0]):
                raise ValidationError('Invalid archive CHECKSUM file')
            if hashlib.sha256(raw).hexdigest() != parts[0].lower():
                raise ValidationError('Archive checksum mismatch')
            with ZipFile(BytesIO(raw)) as archive:
                files = archive.infolist()
                if len(files) != 1 or files[0].file_size > 100_000_000:
                    raise ValidationError('Expected one bounded CSV archive member')
                filename = files[0].filename
                if PurePosixPath(filename).name != filename or not filename.startswith(symbol + '-1m-') or not filename.endswith('.csv'):
                    raise ValidationError('Archive filename/identity mismatch')
                if PurePosixPath(parts[1].lstrip('*')).name != filename[:-4] + '.zip':
                    raise ValidationError('Checksum filename does not match archive member')
                # No extraction to disk; bound both compressed and expanded input.
                with archive.open(files[0]) as stream:
                    data = stream.read(100_000_001)
                if len(data) > 100_000_000:
                    raise ValidationError('Expanded archive exceeds size limit')
            rows = list(csv.reader(StringIO(data.decode('utf-8-sig'))))
            if rows and rows[0] and rows[0][0] == 'open_time':
                rows = rows[1:]
            if not rows:
                raise ValidationError('Empty archive')
            events = [candle(symbol, row, csv=True) for row in rows]
            stamps = [e['data']['open_ms'] for e in events]
            period = filename[len(symbol)+4:-4]
            if not re.fullmatch(r'\d{4}-\d{2}(-\d{2})?', period):
                raise ValidationError('Invalid archive member period')
            first = date.fromisoformat(period if len(period) == 10 else period+'-01')
            start = int(datetime(first.year, first.month, first.day, tzinfo=timezone.utc).timestamp()*1000)
            days = 1 if len(period) == 10 else calendar.monthrange(first.year, first.month)[1]
            if any(t < start or t >= start+days*86400000 for t in stamps):
                raise ValidationError('Candle falls outside archive filename period')
            if stamps != sorted(set(stamps)):
                raise ValidationError('Archive timestamps are duplicated or unordered')
            return events
        if len(content) > 50_000_000:
            raise ValidationError('Compressed archive exceeds size limit')
        return store.ingest(content, source, parse, received_ms, binary=True)
