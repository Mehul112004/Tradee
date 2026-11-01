"""Managed C02 collectors for analysis: persisted WebSocket events, not REST polls.

Each bounded analysis subscription owns one existing Collector. Identical market
observations are deduplicated by C02; all sessions use the workspace's C02 store.
REST is used only for initial minute context and the collector's reconnect repair.
"""

from copy import deepcopy
from decimal import Decimal, localcontext
import json
import threading
import time

from tradee.c01 import Registry
from tradee.c01.provider import BinanceProvider, ProviderError
from tradee.c02 import MarketStore
from tradee.c02.domain import MINUTE, aggregate, number
from tradee.c02.live import Collector, connection
from tradee.c02.provider import RestClient
from tradee.c03.catalog import TIMEFRAMES


class C02LiveFeed:
    def __init__(
        self,
        settings,
        workspace,
        session,
        start_ms,
        wake,
        clock=time.time,
        connect=connection,
        rest=None,
    ):
        self.clock, self.wake = clock, wake
        self.symbols = tuple(session["spec"]["symbols"])
        self.start_ms = start_ms
        self.timeframe = session["spec"]["timeframe"]
        self.guard = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.minutes = {s: {} for s in self.symbols}
        self.state, self.error = "connecting", ""
        self.last_message_ms, self.suppress_before_ms = 0, int(clock() * 1000)
        self.last_by_symbol = {s: 0 for s in self.symbols}
        self.repairing = 0
        feed = self
        profile = settings.profile(workspace)
        registry = Registry(profile.path("c01"), clock=clock)

        class ObservedStore(MarketStore):
            def log(self, **fields):
                super().log(**fields)
                with feed.guard:
                    action = fields.get("action")
                    if action == "connected":
                        feed.state = "connected"
                    elif action in ("disconnected", "reconnect_wait"):
                        feed.state = "reconnecting"
                    elif action == "quarantined":
                        feed.state = "data_error"
                feed.wake.set()

        self.store = ObservedStore(registry, profile.path("c02"), clock=clock)
        self.rest = rest or RestClient(
            provider_factory=lambda: BinanceProvider(attempts=1, timeout=12),
            clock=clock,
        )

        class ObservedCollector(Collector):
            def process(self, raw, source, received_ms):
                result = super().process(raw, source, received_ms)
                with feed.store.connection() as db:
                    rows = db.execute(
                        "SELECT id,document FROM events WHERE raw_id=? ORDER BY id",
                        (result["raw_id"],),
                    ).fetchall()
                with feed.guard:
                    for r in rows:
                        feed._apply(dict(json.loads(r["document"]), id=r["id"]))
                    feed.last_message_ms = received_ms
                    message = json.loads(raw)
                    feed.last_by_symbol[message.get("data", message)["s"]] = received_ms
                    feed.state = "connected"
                feed.wake.set()
                return result

            def repair(self, *args, **kwargs):
                with feed.guard:
                    feed.repairing += 1
                try:
                    result = super().repair(*args, **kwargs)
                    feed.reload()
                    with feed.guard:
                        # Repaired history is visible, but never sent as a fresh alert.
                        feed.suppress_before_ms = int(feed.clock() * 1000)
                    return result
                finally:
                    with feed.guard:
                        feed.repairing -= 1
                    feed.wake.set()

        self.collector = ObservedCollector(
            self.store, self.symbols, ("candle",), connect=connect, rest=self.rest
        )

    def _apply(self, event):
        if event["symbol"] not in self.minutes or event["kind"] != "candle":
            return
        cache = self.minutes[event["symbol"]]
        opened = event["data"]["open_ms"]
        if opened < self.start_ms:
            return
        previous = cache.get(opened)
        if previous and previous["final"] and not event["final"]:
            return
        if previous and previous["final"] == event["final"]:
            rank = lambda e: (e["available_ms"], e["id"])
            if rank(event) < rank(previous):
                return
        cache[opened] = event

    def reload(self):
        # Bound the in-memory view to the session's 24h window plus current UTC
        # day context. Finality wins over a late provisional update for a key.
        marks = ",".join("?" for _ in self.symbols)
        with self.store.connection() as db:
            rows = db.execute(
                f"""SELECT id,document FROM (
                SELECT id,document,ROW_NUMBER() OVER
                (PARTITION BY instrument_id,event_key ORDER BY final DESC,id DESC) n
                FROM events WHERE kind='candle' AND symbol IN ({marks})
                AND event_ms>=? AND event_ms<?) WHERE n=1 ORDER BY id LIMIT 15001""",
                (*self.symbols, self.start_ms, int(self.clock() * 1000) + MINUTE),
            ).fetchall()
        if len(rows) > 15000:
            raise ProviderError(
                "Analysis collector context limit reached; create a new session",
                halt_polling=True,
            )
        with self.guard:
            for r in rows:
                self._apply(dict(json.loads(r["document"]), id=r["id"]))

    def start(self):
        # Seed all already-completed minutes of the current strategy bucket.
        # Collector.repair also handles reconnect overlap and missing minutes.
        end = int(self.clock() * 1000) // MINUTE * MINUTE
        for symbol in self.symbols:
            if self.stop.is_set():
                return
            if self.start_ms < end:
                self.collector.repair(symbol, end_ms=end, start_ms=self.start_ms)
        self.reload()

        def run():
            try:
                self.collector.run(self.stop)
            except Exception:
                with self.guard:
                    self.state = "interrupted"
                    self.error = "Binance WebSocket collector stopped. Check connectivity and Resume; REST polling is not used as a fallback."
                self.wake.set()

        self.thread = threading.Thread(
            target=run, name="tradee-c02-analysis", daemon=True
        )
        self.thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=2.5)

    def view(self, symbol):
        now = int(self.clock() * 1000)
        interval = TIMEFRAMES[self.timeframe]
        with self.guard:
            events = deepcopy(
                [e for e in self.minutes[symbol].values() if e["available_ms"] <= now]
            )
            status = dict(
                state="repairing" if self.repairing else self.state,
                last_message_ms=self.last_by_symbol[symbol],
                suppress_before_ms=self.suppress_before_ms,
                error=self.error,
            )
        if status["state"] == "connected" and (
            not status["last_message_ms"] or now - status["last_message_ms"] > 15000
        ):
            status["state"] = "waiting" if not status["last_message_ms"] else "stale"
        finalized = [e for e in events if e["final"] and e["data"]["close_ms"] < now]
        bars = []
        for e in aggregate(finalized, interval):
            bars.append(
                dict(
                    e["data"],
                    c02_event_ids=e["constituents"],
                    available_ms=e["available_ms"],
                )
            )
        forming = None
        if events:
            latest = max(events, key=lambda e: e["data"]["open_ms"])
            bucket = latest["data"]["open_ms"] // interval * interval
            parts = sorted(
                (
                    e
                    for e in events
                    if e["data"]["open_ms"] // interval * interval == bucket
                ),
                key=lambda e: e["data"]["open_ms"],
            )
            expected = list(
                range(bucket, parts[-1]["data"]["open_ms"] + MINUTE, MINUTE)
            )
            if (
                bucket == now // interval * interval
                and [e["data"]["open_ms"] for e in parts] == expected
                and (
                    not all(e["final"] for e in parts)
                    or len(parts) < interval // MINUTE
                )
            ):
                ds = [p["data"] for p in parts]
                with localcontext() as ctx:
                    ctx.prec = 120
                    sums = {
                        k: number(str(sum(Decimal(d[k]) for d in ds)))
                        for k in ("volume", "quote_volume", "taker_base", "taker_quote")
                    }
                forming = dict(
                    data=dict(
                        sums,
                        open_ms=bucket,
                        close_ms=bucket + interval - 1,
                        open=ds[0]["open"],
                        close=ds[-1]["close"],
                        high=max((d["high"] for d in ds), key=Decimal),
                        low=min((d["low"] for d in ds), key=Decimal),
                    ),
                    final=False,
                )
            status["last_price"] = latest["data"]["close"]
        return dict(status=status, candles=bars, forming=forming)
