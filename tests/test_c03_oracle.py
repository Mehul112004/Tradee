"""Frozen, versioned third-party outputs, generated independently of Tradee."""
import json
import math
from pathlib import Path
import unittest
from tradee.c03.rolling import smooth
from tradee.c03.volatility import atr
from tradee.c03.oscillators import rsi,bands


class ExternalOracleTests(unittest.TestCase):
    def test_talib_compatible_conventions_at_every_index(self):
        fixture=json.loads((Path(__file__).parent/'fixtures/c03/talib_0_6_8.json').read_text())
        self.assertEqual(fixture['provenance']['wrapper'],'0.6.8')
        inputs=fixture['input']; close=inputs['close']
        actual=dict(ema20=smooth(close,20),ema50=smooth(close,50),
            atr14=atr(inputs['high'],inputs['low'],close),rsi14=rsi(close)[0])
        for part in ('upper','middle','lower'):
            actual['bb20_'+part]=[None]*19+[bands(close[i-19:i+1])[part] for i in range(19,len(close))]
        for name,expected in fixture['expected'].items():
            with self.subTest(feature=name):
                self.assertEqual(len(actual[name]),len(expected))
                for i,(got,want) in enumerate(zip(actual[name],expected)):
                    if want is None: self.assertIsNone(got,(name,i))
                    else: self.assertTrue(math.isclose(got,want,abs_tol=1e-12,rel_tol=1e-10),(name,i,got,want))
