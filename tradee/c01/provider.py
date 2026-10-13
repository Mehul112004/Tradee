"""Read-only Binance exchangeInfo transport with bounded retries."""

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import IncompleteRead
import json
import math
import os
import ssl
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def verified_urlopen(request, timeout):
    context = ssl.create_default_context()
    # python.org macOS builds may omit the system CA bundle. Add trusted system
    # roots; never disable TLS verification or override an explicit CA setting.
    system_bundle = "/etc/ssl/cert.pem"
    if sys.platform == "darwin" and not os.environ.get("SSL_CERT_FILE") and os.path.isfile(system_bundle):
        context.load_verify_locations(cafile=system_bundle)
    return urlopen(request, timeout=timeout, context=context)


class ProviderError(RuntimeError):
    def __init__(self, message, retry_after_seconds=0, halt_polling=False):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
        self.halt_polling = halt_polling


@dataclass(frozen=True)
class FetchResult:
    raw: str
    source: str
    received_ms: int


class BinanceProvider:
    endpoint = "https://fapi.binance.com/fapi/v1/exchangeInfo"

    def __init__(self, timeout=15, attempts=3, opener=verified_urlopen, sleep=time.sleep, clock=time.time):
        if (type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0
                or type(attempts) is not int or not 1 <= attempts <= 5):
            raise ValueError("Invalid timeout or retry count")
        self.timeout, self.attempts = timeout, attempts
        self.opener, self.sleep, self.clock = opener, sleep, clock

    def fetch(self):
        for attempt in range(self.attempts):
            delay = 0.5 * 2 ** attempt
            try:
                request = Request(self.endpoint, headers={"User-Agent": "Tradee-C01/0.1", "Accept": "application/json"})
                with self.opener(request, timeout=self.timeout) as response:
                    raw = response.read(20_000_001)
                if len(raw) > 20_000_000:
                    raise ProviderError("Binance response exceeds 20 MB limit")
                try:
                    text = raw.decode("utf-8")
                    json.loads(text)
                except (UnicodeError, ValueError) as exc:
                    raise ProviderError("Binance returned invalid JSON") from exc
                return FetchResult(text, self.endpoint, int(self.clock() * 1000))
            except HTTPError as exc:
                if exc.code == 418:
                    raise ProviderError("Binance IP ban (418); refresh stopped", halt_polling=True) from exc
                if exc.code not in (429, 500, 502, 503, 504):
                    raise ProviderError(f"Binance HTTP {exc.code}; refresh stopped", halt_polling=True) from exc
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if retry_after:
                    try:
                        seconds = float(retry_after)
                        if math.isfinite(seconds):
                            delay = max(delay, seconds)
                    except ValueError:
                        try:
                            when = parsedate_to_datetime(retry_after)
                            delay = max(delay, (when - datetime.fromtimestamp(self.clock(), timezone.utc)).total_seconds())
                        except (TypeError, ValueError):
                            pass
                if delay > 30:
                    raise ProviderError(f"Binance HTTP {exc.code}; retry deferred by Retry-After", retry_after_seconds=delay) from exc
                error = f"Binance HTTP {exc.code}"
            except (URLError, TimeoutError, OSError, IncompleteRead) as exc:
                if isinstance(getattr(exc, "reason", exc), ssl.SSLCertVerificationError):
                    raise ProviderError("TLS certificate verification failed; configure SSL_CERT_FILE with a trusted CA bundle", halt_polling=True) from exc
                error = f"Binance transport failed ({type(exc).__name__})"
            if attempt + 1 < self.attempts:
                self.sleep(delay)
        raise ProviderError(f"{error}; retry budget exhausted", retry_after_seconds=delay)
