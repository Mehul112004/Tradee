"""Offline native-candle source for unit/browser verification only."""

import json
import threading
from pathlib import Path
from tradee.c01 import Registry
from tradee.c03.catalog import TIMEFRAMES


def candle(opened, interval=60000, price="100"):
    from decimal import Decimal

    p = Decimal(price)
    return dict(
        open_ms=opened,
        close_ms=opened + interval - 1,
        open=price,
        high=str(p + 1),
        low=str(p - 1),
        close=price,
        volume="1000",
        quote_volume=str(p * 1000),
        taker_base="500",
        taker_quote=str(p * 500),
    )


class FixtureCandleSource:
    def fetch(self, symbol, timeframe, start, end):
        interval = TIMEFRAMES[timeframe]
        return [
            candle(t, interval, "110" if (t // interval) % 50 == 49 else "100")
            for t in range(start, end, interval)
        ]


class FixtureFeed:
    """Deterministic feed for lifecycle tests; real C02 integration is tested separately."""

    def __init__(self, settings, workspace, session, start_ms, wake, clock):
        self.clock, self.start_ms, self.spec = clock, start_ms, session["spec"]
        self.stop, self.thread = threading.Event(), None
        self.suppress_before_ms = int(clock() * 1000)

    def start(self):
        pass

    def close(self):
        self.stop.set()

    def view(self, symbol):
        interval = TIMEFRAMES[self.spec["timeframe"]]
        end = (int(self.clock() * 1000) - 2000) // interval * interval
        bars = FixtureCandleSource().fetch(
            symbol, self.spec["timeframe"], self.start_ms, end
        )
        return dict(
            candles=bars,
            forming=None,
            status=dict(
                state="connected",
                last_message_ms=int(self.clock() * 1000),
                suppress_before_ms=self.suppress_before_ms,
            ),
        )


def seed_metadata(settings, workspace, session, now):
    raw = json.loads(
        (
            Path(__file__).resolve().parents[2] / "tests/fixtures/exchange_info.json"
        ).read_text()
    )
    Registry(settings.profile(workspace).path("c01")).ingest(
        json.dumps(raw), source="synthetic:analysis test"
    )


def stream_frame(opened, price="102", final=False, symbol="BTCUSDT", emitted=None):
    r = candle(opened, price=price)
    k = dict(
        t=opened,
        T=opened + 59999,
        s=symbol,
        i="1m",
        x=final,
        o=r["open"],
        h=r["high"],
        l=r["low"],
        c=r["close"],
        v=r["volume"],
        q=r["quote_volume"],
        n=5,
        V=r["taker_base"],
        Q=r["taker_quote"],
    )
    return json.dumps(
        dict(
            e="kline", s=symbol, E=emitted or opened + (60000 if final else 10000), k=k
        )
    )


class FixtureRest:
    def __init__(self, clock):
        self.clock = clock

    def backfill(self, store, symbol, start, end, resume=False):
        rows = []
        for t in range(start, end, 60000):
            b = candle(t)
            rows.append(
                [
                    t,
                    b["open"],
                    b["high"],
                    b["low"],
                    b["close"],
                    b["volume"],
                    t + 59999,
                    b["quote_volume"],
                    5,
                    b["taker_base"],
                    b["taker_quote"],
                    "0",
                ]
            )
        return store.ingest_rest(
            json.dumps(rows),
            symbol,
            source="synthetic:analysis repair",
            received_ms=int(self.clock() * 1000),
        )


def fixture_c02_feed(settings, workspace, session, start, wake, clock):
    """Real C02 Collector/MarketStore with a scripted socket and REST adapter."""
    from contextlib import contextmanager
    import time
    from backend.tradee_web.analysis_live import C02LiveFeed

    class Socket:
        counter = 0

        def recv(self, timeout):
            time.sleep(0.1)
            symbol = session["spec"]["symbols"][
                self.counter % len(session["spec"]["symbols"])
            ]
            self.counter += 1
            now = int(clock() * 1000)
            return stream_frame(now // 60000 * 60000, symbol=symbol, emitted=now)

    @contextmanager
    def connect(url):
        yield Socket()

    return C02LiveFeed(
        settings,
        workspace,
        session,
        start,
        wake,
        clock,
        connect=connect,
        rest=FixtureRest(clock),
    )
