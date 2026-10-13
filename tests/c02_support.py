import json
from pathlib import Path
import tempfile
import unittest

from tradee.c01 import Registry
from tradee.c02 import MarketStore
from tests.support import payload

START = 1_800_000_000_000  # Minute-aligned UTC.


def row(start=START, close='101'):
    return [start, '100', '105', '95', close, '10', start+59999, '1000', 3, '4', '400', '0']


def ws(start=START, final=True, close='101', symbol='BTCUSDT'):
    values = row(start, close)
    k = dict(zip(('t', 'o', 'h', 'l', 'c', 'v', 'T', 'q', 'n', 'V', 'Q'), values[:11]))
    k.update(s=symbol, i='1m', x=final)
    return json.dumps(dict(e='kline', E=start+60000 if final else start+10000, s=symbol, k=k))


class DataCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.now = START + 600000
        self.registry = Registry(self.root/'c01.sqlite3', clock=lambda: self.now/1000)
        self.registry.ingest(json.dumps(payload()))
        self.store = MarketStore(self.registry, self.root/'c02.sqlite3', clock=lambda: self.now/1000)

    def snapshot(self, **kwargs):
        return self.store.snapshot(['BTCUSDT'], START, START+60000, **kwargs)['dataset_hash']

    def ingest(self, rows=None):
        return self.store.ingest_rest(json.dumps(rows or [row()]), 'BTCUSDT')
