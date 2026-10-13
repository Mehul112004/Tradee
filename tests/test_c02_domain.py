import copy
import json
import unittest

from tradee.c01 import ValidationError
from tradee.c02.domain import candle, parse_ws, rest_rows, number
from tests.c02_support import START, row, ws


class MarketContractTests(unittest.TestCase):
    def test_exact_decimal_normalization(self):
        self.assertEqual(number('0.00000000000000000001'), '0.00000000000000000001')
        self.assertEqual(number('1.0000'), '1')
        for value in (True, 0.1, 'NaN', 'Infinity', '-1', '1E9999'):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                number(value)

    def test_candle_shape_alignment_and_bounds(self):
        cases = [(0, START+1), (0, START*1000), (6, START+60000), (8, True),
                 (1, '0'), (2, '99'), (3, '102'), (4, '999'), (5, '-1'), (9, '11'), (10, '1001')]
        for index, value in cases:
            with self.subTest(index=index, value=value), self.assertRaises(ValidationError):
                data = row(); data[index] = value
                candle('BTCUSDT', data)
        with self.assertRaises(ValidationError):
            candle('BTCUSDT', row()[:-1])

    def test_csv_and_rest_produce_same_normalized_candle(self):
        self.assertEqual(candle('BTCUSDT', row()), candle('BTCUSDT', [str(v) for v in row()], csv=True))

    def test_rest_finality_exact_close_boundary(self):
        self.assertFalse(rest_rows('candle', 'BTCUSDT', [row()], START+59999)[0]['final'])
        self.assertTrue(rest_rows('candle', 'BTCUSDT', [row()], START+60000)[0]['final'])

    def test_websocket_raw_and_combined_envelopes(self):
        parsed = parse_ws(ws())
        self.assertEqual(parsed, parse_ws(json.dumps({'stream': 'btcusdt@kline_1m', 'data': json.loads(ws())})))
        self.assertEqual(parsed['data'], candle('BTCUSDT', row())['data'])
        self.assertFalse(parse_ws(ws(final=False))['final'])

    def test_websocket_kline_rejects_identity_interval_and_finality_errors(self):
        for field, value in (('s', 'ETHUSDT'), ('i', '5m'), ('x', 'true'), ('x', 1)):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                msg = json.loads(ws()); msg['k'][field] = value
                parse_ws(json.dumps(msg))
        msg = json.loads(ws()); msg['E'] = START
        with self.assertRaises(ValidationError):
            parse_ws(json.dumps(msg))

    def test_trade_quote_and_mark_contracts(self):
        trade = dict(e='aggTrade', E=START, T=START, s='BTCUSDT', a=1, f=1, l=2, m=True, p='100', q='2')
        quote = dict(e='bookTicker', E=START, T=START, s='BTCUSDT', u=1, b='99', a='101', B='2', A='3')
        mark = dict(e='markPriceUpdate', E=START, T=START+28800000, s='BTCUSDT', p='100', i='99', r='-0.0001')
        for message, kind in ((trade, 'trade'), (quote, 'quote'), (mark, 'mark')):
            self.assertEqual(parse_ws(json.dumps(message))['kind'], kind)
        for base, field, value in ((trade, 'm', 'false'), (trade, 'f', 3), (quote, 'b', '102'), (mark, 'r', 'NaN')):
            message = copy.deepcopy(base); message[field] = value
            with self.assertRaises(ValidationError):
                parse_ws(json.dumps(message))

    def test_raw_derivatives_do_not_compute_outcomes(self):
        funding = dict(symbol='BTCUSDT', fundingTime=START, fundingRate='-0.001', markPrice='100')
        oi = dict(symbol='BTCUSDT', timestamp=START, sumOpenInterest='42', sumOpenInterestValue='4200')
        for kind, data in (('funding', funding), ('open_interest', oi)):
            item = rest_rows(kind, 'BTCUSDT', [data], START+1)[0]
            self.assertEqual(item['kind'], kind)
            self.assertNotIn('pnl', item['data'])
            with self.assertRaises(ValidationError):
                rest_rows(kind, 'ETHUSDT', [data], START+1)

    def test_unsupported_and_nonfinite_payloads_rejected(self):
        for raw in ('null', '[]', '{bad', '{"data": []}', '{"ignored": NaN}', '{"s":"BTCUSDT","E":1,"e":"depthUpdate"}'):
            with self.subTest(raw=raw), self.assertRaises((ValidationError, ValueError)):
                parse_ws(raw)

    def test_nonfinite_ignored_rest_fields_and_preopen_updates_rejected(self):
        values = row(); values[-1] = float('nan')
        with self.assertRaises(ValueError):
            rest_rows('candle', 'BTCUSDT', [values], START+60000)
        msg = json.loads(ws(final=False)); msg['E'] = START-1
        with self.assertRaises(ValidationError):
            parse_ws(json.dumps(msg))
