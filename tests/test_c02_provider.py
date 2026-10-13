from io import BytesIO
import csv
import hashlib
import json
from unittest.mock import Mock
from urllib.parse import urlparse, parse_qs
from zipfile import ZipFile

from tradee.c01 import ValidationError
from tradee.c01.provider import FetchResult
from tradee.c02 import RestClient, ArchiveClient
from tests.c02_support import DataCase, START, row


class AdapterTests(DataCase):
    def client(self, responses):
        fetch = Mock(side_effect=[FetchResult(json.dumps(rows), 'test:REST', self.now) for rows in responses])
        provider = Mock(fetch=fetch)
        client = RestClient(provider_factory=lambda: provider, sleep=Mock(), clock=lambda: self.now/1000)
        return client, provider

    def test_pagination_progress_resume_and_end_exclusion(self):
        client, provider = self.client([[row()], [row(START+60000)], []])
        result = client.backfill(self.store, 'BTCUSDT', START, START+180000)
        self.assertEqual(result['pages'], 3)
        self.assertEqual(result['added'], 2)
        query = parse_qs(urlparse(provider.endpoint).query)
        self.assertEqual(query['startTime'], [str(START+120000)])
        self.assertEqual(query['endTime'], [str(START+179999)])
        self.assertEqual(query['interval'], ['1m'])
        result = client.backfill(self.store, 'BTCUSDT', START, START+180000)
        self.assertEqual(result['pages'], 0)
        digest = self.store.snapshot(['BTCUSDT'], START, START+180000)['dataset_hash']
        self.assertTrue(self.store.quality(digest)['symbols'][0]['gaps'])

    def test_nonprogressing_or_out_of_bounds_pages_quarantined(self):
        for rows in ([row(START-60000)], [row(), row()], [row(START+60000), row()]):
            with self.subTest(rows=rows):
                client, _ = self.client([rows])
                with self.assertRaises(ValidationError):
                    client.backfill(self.store, 'BTCUSDT', START, START+120000, resume=False)
        self.assertIsNone(self.store.checkpoint(f'rest:candle:BTCUSDT:{START}:{START+120000}'))

    def test_resume_after_failure_preserves_committed_page(self):
        client, provider = self.client([[row()]])
        provider.fetch.side_effect = [FetchResult(json.dumps([row()]), 'test', self.now), OSError('offline')]
        with self.assertRaises(OSError):
            client.backfill(self.store, 'BTCUSDT', START, START+120000)
        saved = self.store.checkpoint(f'rest:candle:BTCUSDT:{START}:{START+120000}')
        self.assertEqual(saved['next_ms'], START+60000)
        client, provider = self.client([[row(START+60000)]])
        client.backfill(self.store, 'BTCUSDT', START, START+120000)
        self.assertIn('startTime='+str(START+60000), provider.endpoint)

    def test_funding_and_open_interest_endpoint_selection(self):
        for kind, path, response in (
            ('funding', '/fapi/v1/fundingRate', dict(symbol='BTCUSDT', fundingTime=START, fundingRate='0.001', markPrice='100')),
            ('open_interest', '/futures/data/openInterestHist', dict(symbol='BTCUSDT', timestamp=START, sumOpenInterest='10', sumOpenInterestValue='1000'))):
            with self.subTest(kind=kind):
                client, provider = self.client([[response], []])
                result = client.backfill(self.store, 'BTCUSDT', START, START+60000, kind)
                self.assertEqual(result['added'], 1)
                self.assertEqual(urlparse(provider.endpoint).path, path)

    def test_invalid_range_never_fetches(self):
        client, provider = self.client([])
        for start, end in ((START, START), (START+1, START+60000), (START, self.now+60000)):
            with self.assertRaises(ValidationError):
                client.backfill(self.store, 'BTCUSDT', start, end)
        provider.fetch.assert_not_called()

    def archive(self, rows=None, name='BTCUSDT-1m-2027-01-15.csv', header=False):
        from io import StringIO
        text = StringIO()
        writer = csv.writer(text)
        if header:
            writer.writerow(['open_time']+['column']*11)
        writer.writerows(rows or [row()])
        buffer = BytesIO()
        with ZipFile(buffer, 'w') as archive:
            archive.writestr(name, text.getvalue())
        raw = buffer.getvalue()
        checksum = hashlib.sha256(raw).hexdigest()+'  '+name[:-4]+'.zip'
        return raw, checksum

    def test_checked_archive_preserves_zip_bytes_and_matches_rest(self):
        raw, checksum = self.archive(header=True)
        result = ArchiveClient().ingest(self.store, 'BTCUSDT', raw, checksum)
        self.assertEqual(result['added'], 1)
        self.assertEqual(self.ingest()['duplicates'], 1)
        with self.store.connection() as db:
            self.assertEqual(bytes(db.execute('SELECT raw FROM raw_observations ORDER BY id LIMIT 1').fetchone()[0]), raw)

    def test_corrupt_archive_checksum_quarantines_without_events(self):
        raw, checksum = self.archive()
        with self.assertRaisesRegex(ValidationError, 'checksum mismatch'):
            ArchiveClient().ingest(self.store, 'BTCUSDT', raw+b'broken', checksum)
        self.assertEqual(self.store.dataset(self.snapshot())['event_count'], 0)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT accepted FROM raw_observations').fetchone()[0], 0)

    def test_archive_identity_traversal_and_duplicate_rows_rejected(self):
        for kwargs in ({'name': '../BTCUSDT-1m-2027-01-15.csv'}, {'name': 'ETHUSDT-1m-2027-01-15.csv'},
                       {'rows': [row(), row()]}):
            with self.subTest(kwargs=kwargs):
                raw, checksum = self.archive(**kwargs)
                with self.assertRaises(ValidationError):
                    ArchiveClient().ingest(self.store, 'BTCUSDT', raw, checksum)

    def test_archive_url_limits_and_resource_closure(self):
        client = ArchiveClient(opener=Mock(return_value=BytesIO(b'x'*11)))
        self.assertIn('/futures/um/monthly/klines/BTCUSDT/1m/', client.url('BTCUSDT', '2026-08'))
        self.assertIn('/daily/', client.url('BTCUSDT', '2026-08-01'))
        for period in ('../data', '2026-13', '2026-02-31'):
            with self.assertRaises(ValueError):
                client.url('BTCUSDT', period)
        with self.assertRaisesRegex(RuntimeError, 'size limit'):
            client.download('https://data.binance.vision/test', 10)
        self.assertTrue(client.opener.return_value.closed)

    def test_archive_period_and_invalid_zip_quarantined(self):
        raw, checksum = self.archive(name='BTCUSDT-1m-2026-01-15.csv')
        with self.assertRaisesRegex(ValidationError, 'outside archive'):
            ArchiveClient().ingest(self.store, 'BTCUSDT', raw, checksum)
        raw = b'not a zip'
        checksum = hashlib.sha256(raw).hexdigest()+'  BTCUSDT-1m-2027-01-15.zip'
        with self.assertRaises(ValidationError):
            ArchiveClient().ingest(self.store, 'BTCUSDT', raw, checksum)
