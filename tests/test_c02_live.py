from contextlib import contextmanager
import json
from threading import Event
from unittest.mock import Mock

from tradee.c01 import ValidationError
from tradee.c01.provider import ProviderError
from tradee.c02.live import Collector, stream_urls
from tests.c02_support import DataCase, START, ws


class LiveCollectorTests(DataCase):
    def test_streams_split_by_binance_route(self):
        urls = stream_urls(['BTCUSDT', 'ETHUSDT'], ['candle', 'trade', 'mark', 'quote'])
        self.assertIn('/public/stream?streams=btcusdt@bookTicker/', urls['public'])
        self.assertIn('btcusdt@kline_1m', urls['market'])
        self.assertIn('btcusdt@aggTrade', urls['market'])
        self.assertIn('btcusdt@markPrice@1s', urls['market'])
        self.assertNotIn('bookTicker', urls['market'])

    def test_invalid_streams_and_limits_rejected(self):
        for symbols, kinds in (([], ['candle']), (['BTCUSDT'], ['depth']), (['BTCUSDT'], []),
                               ([f'X{i}USDT' for i in range(1025)], ['quote'])):
            with self.assertRaises(ValidationError):
                stream_urls(symbols, kinds)

    def test_message_and_checkpoint_persist_together(self):
        collector = Collector(self.store, ['BTCUSDT'], rest=Mock())
        collector.process(ws(), 'test:ws', self.now)
        self.assertEqual(self.store.checkpoint('live:candle:BTCUSDT')['open_ms'], START)
        collector.process(ws(START-60000), 'test:ws', self.now)
        self.assertEqual(self.store.checkpoint('live:candle:BTCUSDT')['open_ms'], START)

    def test_unsubscribed_message_quarantined(self):
        collector = Collector(self.store, ['BTCUSDT'], rest=Mock())
        with self.assertRaises(ValidationError):
            collector.process(ws(symbol='ETHUSDT'), 'test:ws', self.now)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT accepted FROM raw_observations').fetchone()[0], 0)
        self.assertIsNone(self.store.checkpoint('live:candle:ETHUSDT'))

    def test_repair_failure_does_not_lose_received_event_or_gap_checkpoint(self):
        rest = Mock(); rest.backfill.side_effect = ProviderError('offline')
        collector = Collector(self.store, ['BTCUSDT'], rest=rest)
        collector.process(ws(), 'test:ws', self.now)
        with self.assertRaises(ProviderError):
            collector.process(ws(START+120000), 'test:ws', self.now)
        self.assertEqual(self.store.checkpoint('live:candle:BTCUSDT')['open_ms'], START+120000)
        self.assertEqual(self.store.checkpoint('live:gap:BTCUSDT')['next_ms'], START)
        with self.store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 2)

    def test_startup_repair_and_received_event(self):
        stop = Event()
        socket = Mock()
        def recv(timeout):
            stop.set()
            return ws()
        socket.recv.side_effect = recv
        @contextmanager
        def connect(url):
            yield socket
        rest = Mock()
        Collector(self.store, ['BTCUSDT'], connect=connect, rest=rest).run_route('market', stop)
        rest.backfill.assert_called_once()
        self.assertEqual(self.store.checkpoint('live:candle:BTCUSDT')['open_ms'], START)

    def test_reconnect_budget_and_backoff_are_bounded(self):
        connector = Mock(side_effect=OSError('disconnected'))
        stop = Mock(); stop.is_set.return_value = False
        collector = Collector(self.store, ['BTCUSDT'], connect=connector, rest=Mock(), max_reconnects=2)
        with self.assertRaisesRegex(ProviderError, 'budget exhausted'):
            collector.run_route('market', stop)
        self.assertEqual(connector.call_count, 3)
        self.assertEqual([c.args[0] for c in stop.wait.call_args_list], [1, 2])

    def test_permanent_errors_stop_without_retry(self):
        stop = Mock(); stop.is_set.return_value = False
        connector = Mock(side_effect=ProviderError('TLS or ban', halt_polling=True))
        with self.assertRaises(ProviderError):
            Collector(self.store, ['BTCUSDT'], connect=connector, rest=Mock()).run_route('market', stop)
        stop.wait.assert_not_called()
        connector.assert_called_once()

    def test_silent_connection_reconnects_and_closes(self):
        socket = Mock(); socket.recv.side_effect = TimeoutError()
        closed = []
        @contextmanager
        def connect(url):
            try:
                yield socket
            finally:
                closed.append(True)
        stop = Event()
        with self.assertRaisesRegex(ProviderError, 'budget exhausted'):
            Collector(self.store, ['BTCUSDT'], connect=connect, rest=Mock(), max_reconnects=0).run_route('market', stop)
        self.assertEqual(socket.recv.call_count, 30)
        self.assertEqual(closed, [True])

    def test_incomplete_repair_keeps_earliest_gap_for_restart(self):
        collector = Collector(self.store, ['BTCUSDT'], rest=Mock())
        collector.repair('BTCUSDT')
        gap = self.store.checkpoint('live:gap:BTCUSDT')
        self.assertEqual(gap['next_ms'], self.now//60000*60000-300000)
        self.now += 60000
        restarted = Collector(self.store, ['BTCUSDT'], rest=Mock())
        restarted.repair('BTCUSDT')
        self.assertEqual(restarted.rest.backfill.call_args.args[2], gap['next_ms'])

    def test_handshake_rate_limit_respects_retry_after(self):
        error = OSError('rate limited')
        error.response = Mock(status_code=429, headers={'Retry-After': '120'})
        stop = Mock(); stop.is_set.return_value = False
        collector = Collector(self.store, ['BTCUSDT'], connect=Mock(side_effect=error), rest=Mock(), max_reconnects=1)
        with self.assertRaises(ProviderError):
            collector.run_route('market', stop)
        stop.wait.assert_called_once_with(120)

    def test_shutdown_closes_both_route_workers(self):
        stop = Event()
        stop.set()
        connector = Mock()
        Collector(self.store, ['BTCUSDT'], ['candle', 'quote'], connect=connector, rest=Mock()).run(stop)
        connector.assert_not_called()
