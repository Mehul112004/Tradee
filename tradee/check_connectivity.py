"""Run with python3 -m tradee.check_connectivity. Public data only; no credentials."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import time

from tradee.c01 import Registry
from tradee.c01.provider import BinanceProvider
from tradee.c02 import MarketStore, RestClient, ArchiveClient
from tradee.c02.domain import parse_ws
from tradee.c02.live import connection, stream_urls


def main():
    results = []

    def check(name, action):
        started = time.monotonic()
        try:
            detail = action()
            result = dict(check=name, passed=True, detail=detail)
        except Exception as exc:
            result = dict(check=name, passed=False, error=f'{type(exc).__name__}: {exc}')
        result['seconds'] = round(time.monotonic()-started, 2)
        print(json.dumps(result), flush=True)
        return result

    with tempfile.TemporaryDirectory(prefix='tradee-connectivity-') as directory:
        registry = Registry(Path(directory)/'c01.sqlite3')
        store = MarketStore(registry, Path(directory)/'c02.sqlite3')
        results.append(check('exchange_metadata', lambda: registry.refresh(BinanceProvider(timeout=10, attempts=1))))
        if results[0]['passed']:
            client = RestClient(provider_factory=lambda: BinanceProvider(timeout=10, attempts=1))

            def candles():
                end = int(time.time()*1000)//60000*60000
                output = client.backfill(store, 'BTCUSDT', end-180000, end)
                gaps = store.candle_gaps('BTCUSDT', end-180000, end)
                if gaps:
                    raise ValueError(f'Missing {len(gaps)} of three requested candles')
                return output

            results.append(check('rest_candles', candles))
            for kind, path, params in (
                ('funding', '/fapi/v1/fundingRate', {'symbol': 'BTCUSDT', 'limit': 1}),
                ('open_interest', '/futures/data/openInterestHist', {'symbol': 'BTCUSDT', 'period': '5m', 'limit': 1})):
                def derivatives(kind=kind, path=path, params=params):
                    response = client.fetch(path, params)
                    output = store.ingest_rest(response.raw, 'BTCUSDT', kind, response.source, response.received_ms)
                    if not output['added']:
                        raise ValueError('No observations returned')
                    return output
                results.append(check('rest_'+kind, derivatives))

            period = (datetime.now(timezone.utc)-timedelta(days=2)).strftime('%Y-%m-%d')
            results.append(check('archive_checksum_and_import', lambda: ArchiveClient().fetch(store, 'BTCUSDT', period)))

            def websocket(route, url):
                expected = {'quote'} if route == 'public' else {'candle', 'trade', 'mark'}
                seen = set()
                deadline = time.monotonic()+20
                with connection(url) as socket:
                    while seen != expected:
                        remaining = deadline-time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError(f'Missing streams: {sorted(expected-seen)}')
                        raw = socket.recv(timeout=remaining)
                        received = store.now()
                        event = parse_ws(raw)
                        store.ingest_ws(raw, url, received)
                        seen.add(event['kind'])
                return {'received_and_persisted': sorted(seen)}

            urls = stream_urls(['BTCUSDT'], ['candle', 'trade', 'quote', 'mark'])
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending = [pool.submit(check, 'websocket_'+route, lambda r=route, u=url: websocket(r, u))
                           for route, url in urls.items()]
                results.extend(future.result() for future in pending)
        else:
            print(json.dumps({'skipped': 'Data persistence checks require successful C01 metadata bootstrap'}), flush=True)
    passed = len(results) == 7 and all(result['passed'] for result in results)
    print(json.dumps({'passed': passed, 'credentials_used': False, 'temporary_databases_removed': True}), flush=True)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
