"""Offline transport fault injection; no network or wall-clock sleeps."""

from email.utils import formatdate
from http.client import IncompleteRead
from io import BytesIO
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

from tradee.c01.provider import BinanceProvider, ProviderError


class TransportFailureTests(unittest.TestCase):
    def provider(self, effects, attempts=3):
        self.opener = Mock(side_effect=effects)
        self.sleep = Mock()
        return BinanceProvider(opener=self.opener, sleep=self.sleep, clock=lambda: 1800000000, attempts=attempts)

    def http(self, code, retry=None):
        return HTTPError(BinanceProvider.endpoint, code, 'test', {'Retry-After': retry} if retry else {}, None)

    def test_transient_statuses_retry_and_recover(self):
        for status in (429, 500, 502, 503, 504):
            with self.subTest(status=status):
                body = BytesIO(b'{"symbols": []}')
                result = self.provider([self.http(status), body]).fetch()
                self.assertEqual(result.received_ms, 1800000000000)
                self.assertEqual(result.source, BinanceProvider.endpoint)
                self.assertEqual(self.opener.call_count, 2)
                self.sleep.assert_called_once_with(0.5)
                self.assertTrue(body.closed)

    def test_transport_exhaustion_is_bounded_and_retains_cooldown(self):
        for error in (TimeoutError(), URLError('offline'), OSError('reset'), IncompleteRead(b'{')):
            with self.subTest(error=type(error).__name__):
                provider = self.provider([error] * 3)
                with self.assertRaises(ProviderError) as caught:
                    provider.fetch()
                self.assertEqual(self.opener.call_count, 3)
                self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [0.5, 1.0])
                self.assertEqual(caught.exception.retry_after_seconds, 2.0)
                self.assertFalse(caught.exception.halt_polling)

    def test_permanent_http_errors_stop_immediately(self):
        for status in (400, 401, 403, 404, 418, 451):
            with self.subTest(status=status):
                provider = self.provider([self.http(status)])
                with self.assertRaises(ProviderError) as caught:
                    provider.fetch()
                self.assertTrue(caught.exception.halt_polling)
                self.opener.assert_called_once()
                self.sleep.assert_not_called()

    def test_retry_after_http_date(self):
        provider = self.provider([self.http(429, formatdate(1800000012, usegmt=True)), BytesIO(b'{}')])
        provider.fetch()
        self.sleep.assert_called_once_with(12)

    def test_invalid_or_past_retry_after_uses_bounded_backoff(self):
        for value in ('nonsense', '-1', 'NaN', 'Infinity', formatdate(1799999999, usegmt=True)):
            with self.subTest(value=value):
                provider = self.provider([self.http(429, value), BytesIO(b'{}')])
                provider.fetch()
                self.sleep.assert_called_once_with(0.5)

    def test_long_retry_after_is_returned_without_sleeping(self):
        provider = self.provider([self.http(429, '3600')])
        with self.assertRaises(ProviderError) as caught:
            provider.fetch()
        self.assertEqual(caught.exception.retry_after_seconds, 3600)
        self.sleep.assert_not_called()
        self.opener.assert_called_once()

    def test_final_attempt_preserves_server_cooldown(self):
        provider = self.provider([self.http(429, '7')], attempts=1)
        with self.assertRaises(ProviderError) as caught:
            provider.fetch()
        self.assertEqual(caught.exception.retry_after_seconds, 7)
        self.sleep.assert_not_called()

    def test_invalid_response_closes_resource_without_retry(self):
        for raw in (b'\xff', b'{broken', b'<html>unavailable</html>', b'x' * 20000001):
            with self.subTest(length=len(raw)):
                body = BytesIO(raw)
                provider = self.provider([body])
                with self.assertRaises(ProviderError):
                    provider.fetch()
                self.assertTrue(body.closed)
                self.opener.assert_called_once()
                self.sleep.assert_not_called()

    def test_response_size_boundary_and_request_contract(self):
        body = BytesIO(b'{}' + b' ' * 19999998)
        result = self.provider([body]).fetch()
        self.assertEqual(len(result.raw), 20000000)
        request = self.opener.call_args.args[0]
        self.assertEqual(request.full_url, BinanceProvider.endpoint)
        self.assertEqual(request.get_method(), 'GET')
        self.assertIsNone(request.data)
        self.assertEqual(request.get_header('Accept'), 'application/json')
        self.assertEqual(self.opener.call_args.kwargs['timeout'], 15)

    def test_invalid_configuration_fails_before_io(self):
        for attempts in (0, 6, True, 1.5, '3', None):
            with self.subTest(attempts=attempts), self.assertRaises(ValueError):
                BinanceProvider(attempts=attempts)
        for timeout in (0, -1, True, None, '15', float('nan'), float('inf')):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                BinanceProvider(timeout=timeout)

    def test_truncated_body_closes_response_and_recovers(self):
        class TruncatedBody(BytesIO):
            def read(self, size=-1):
                raise IncompleteRead(b'{')
        truncated = TruncatedBody()
        provider = self.provider([truncated, BytesIO(b'{}')])
        self.assertEqual(provider.fetch().raw, '{}')
        self.assertTrue(truncated.closed)
        self.sleep.assert_called_once_with(0.5)
