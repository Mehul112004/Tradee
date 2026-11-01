"""Exploratory setup sessions. No orders, paper fills, or research promotion.

Native closed Binance candles are retained in a separate store, with receipt
times. C03 numerical primitives and C08 predicates are shared with research.
Historical downloads do not pretend to have recorded historical availability.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request

from tradee.c01 import Registry, Policy, ValidationError
from tradee.c01.domain import canonical, fingerprint
from tradee.c01.provider import BinanceProvider, ProviderError, verified_urlopen
from tradee.c03.catalog import TIMEFRAMES
from tradee.c03.evaluator import Evaluator
from tradee.c08 import StrategySpec
from tradee.c08.strategy import prior_range, trend_recovery
from tradee.c14.telegram import TelegramTransport
from tradee.environment import load_environment

STRATEGIES = {
    "prior_range_breakout": "Range breakout",
    "ema_pullback_continuation": "EMA pullback",
}
MAX_BARS = 2000
CHECK_SECONDS = 1  # Local supervision/notification timers, never Binance REST polling.


def validate_spec(doc):
    required = {
        "name",
        "symbols",
        "timeframe",
        "strategies",
        "mode",
        "history_bars",
        "telegram",
    }
    if not isinstance(doc, dict) or set(doc) != required:
        raise ValidationError(
            "Choose a name, instruments, timeframe, strategies and session mode"
        )
    if not isinstance(doc["name"], str) or not 1 <= len(doc["name"].strip()) <= 80:
        raise ValidationError("Session name must contain 1–80 characters")
    symbols = doc["symbols"]
    if (
        not isinstance(symbols, list)
        or not 1 <= len(symbols) <= 5
        or any(
            not isinstance(s, str) or not re.fullmatch(r"[A-Z0-9]{1,26}USDT", s)
            for s in symbols
        )
    ):
        raise ValidationError(
            "Choose 1–5 Binance USDT perpetual symbols, such as BTCUSDT"
        )
    if not isinstance(doc["timeframe"], str) or doc["timeframe"] not in TIMEFRAMES:
        raise ValidationError("Choose 1m, 15m, 1h, 4h or 1d")
    if (
        not isinstance(doc["strategies"], list)
        or not doc["strategies"]
        or any(not isinstance(s, str) or s not in STRATEGIES for s in doc["strategies"])
    ):
        raise ValidationError("Choose at least one supported strategy")
    if doc["mode"] not in ("live", "history") or type(doc["telegram"]) is not bool:
        raise ValidationError("Choose Watch live or Scan history")
    if type(doc["history_bars"]) is not int or doc["history_bars"] not in (
        100,
        500,
        1500,
    ):
        raise ValidationError(
            "Historical scans support 100, 500 or 1500 closed candles"
        )
    if doc["mode"] == "history" and doc["telegram"]:
        raise ValidationError("Historical scans never send Telegram alerts")
    for family in doc["strategies"]:
        StrategySpec(
            family=family,
            timeframe=doc["timeframe"],
            entry_window_ms=min(300000, TIMEFRAMES[doc["timeframe"]]),
        )
    return dict(
        doc,
        name=doc["name"].strip(),
        symbols=sorted(set(symbols)),
        strategies=sorted(set(doc["strategies"])),
    )


def telegram_config():
    env = load_environment()
    try:
        bot_id = int(env.telegram_token.split(":")[0])
        chat_id = int(env.telegram_chat_id)
        if not chat_id:
            raise ValueError()
        transport = TelegramTransport(env.telegram_token, bot_id)
        return transport, bot_id, chat_id
    except (ValueError, ValidationError):
        raise ValidationError(
            "Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in the repository .env, then try again"
        ) from None


class AnalysisStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS analysis_sessions (
                    id TEXT PRIMARY KEY, workspace TEXT NOT NULL, request_key TEXT NOT NULL,
                    spec TEXT NOT NULL, state TEXT NOT NULL, phase TEXT NOT NULL,
                    created_ms INTEGER NOT NULL, updated_ms INTEGER NOT NULL,
                    started_ms INTEGER, last_poll_ms INTEGER NOT NULL DEFAULT 0,
                    metadata_ms INTEGER NOT NULL DEFAULT 0, watermark TEXT NOT NULL DEFAULT '{}',
                    detail TEXT NOT NULL DEFAULT '{}', message TEXT NOT NULL DEFAULT '',
                    bot_id INTEGER, chat_id INTEGER, build TEXT NOT NULL,
                    alerts_after_ms INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(workspace, request_key));
                CREATE TABLE IF NOT EXISTS analysis_bars (
                    session_id TEXT NOT NULL, symbol TEXT NOT NULL, open_ms INTEGER NOT NULL,
                    document TEXT NOT NULL, received_ms INTEGER NOT NULL,
                    PRIMARY KEY(session_id,symbol,open_ms));
                CREATE TABLE IF NOT EXISTS analysis_bar_revisions (
                    session_id TEXT NOT NULL, symbol TEXT NOT NULL, open_ms INTEGER NOT NULL,
                    hash TEXT NOT NULL, document TEXT NOT NULL, received_ms INTEGER NOT NULL,
                    PRIMARY KEY(session_id,symbol,open_ms,hash));
                CREATE TABLE IF NOT EXISTS analysis_setups (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, symbol TEXT NOT NULL,
                    end_ms INTEGER NOT NULL, document TEXT NOT NULL,
                    delivery TEXT NOT NULL, attempted_ms INTEGER, message_id INTEGER);
                CREATE INDEX IF NOT EXISTS analysis_setup_session ON analysis_setups(session_id,end_ms);
                CREATE TABLE IF NOT EXISTS analysis_delivery_clock (
                    id INTEGER PRIMARY KEY CHECK(id=1), next_ms INTEGER NOT NULL);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, workspace, doc, key, now):
        spec = validate_spec(doc)
        if not isinstance(key, str) or not 1 <= len(key) <= 100:
            raise ValidationError("A bounded idempotency key is required")
        bot_id = chat_id = None
        if spec["telegram"]:
            _, bot_id, chat_id = telegram_config()
        from .config import build_hash
        from tradee.c06.engine import code_hash

        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT id,spec FROM analysis_sessions WHERE workspace=? AND request_key=?",
                (workspace, key),
            ).fetchone()
            if old:
                if old["spec"] != canonical(spec):
                    raise ValidationError(
                        "This request key already belongs to different session settings"
                    )
                return self.get(workspace, old["id"])
            if (
                db.execute(
                    "SELECT count(*) FROM analysis_sessions WHERE state='running'"
                ).fetchone()[0]
                >= 5
            ):
                raise ValidationError(
                    "Pause or stop an existing session first; at most five can run together"
                )
            uid = uuid.uuid4().hex
            db.execute(
                """INSERT INTO analysis_sessions
                (id,workspace,request_key,spec,state,phase,created_ms,updated_ms,bot_id,chat_id,build,alerts_after_ms)
                VALUES(?,?,?,?,'running','preparing',?,?,?,?,?,?)""",
                (
                    uid,
                    workspace,
                    key,
                    canonical(spec),
                    now,
                    now,
                    bot_id,
                    chat_id,
                    fingerprint([build_hash(), code_hash()]),
                    now,
                ),
            )
            end = (
                (now - 2000)
                // TIMEFRAMES[spec["timeframe"]]
                * TIMEFRAMES[spec["timeframe"]]
            )
            db.execute(
                "UPDATE analysis_sessions SET detail=? WHERE id=?",
                (canonical(dict(scan_end_ms=end)), uid),
            )
        return self.get(workspace, uid)

    def get(self, workspace, uid):
        with self.connection() as db:
            r = db.execute(
                "SELECT * FROM analysis_sessions WHERE workspace=? AND id=?",
                (workspace, uid),
            ).fetchone()
            if r is None:
                from .readers import MissingSource

                raise MissingSource("Analysis session not found in this workspace")
            d = dict(r)
            for k in ("spec", "watermark", "detail"):
                d[k] = json.loads(d[k])
            setups = db.execute(
                "SELECT document,delivery,message_id FROM analysis_setups WHERE session_id=? ORDER BY end_ms DESC,id LIMIT 200",
                (uid,),
            ).fetchall()
            d["setups"] = [
                dict(
                    json.loads(s["document"]),
                    delivery=s["delivery"],
                    message_id=s["message_id"],
                )
                for s in setups
            ]
            d["setup_count"] = db.execute(
                "SELECT count(*) FROM analysis_setups WHERE session_id=?", (uid,)
            ).fetchone()[0]
            d["counts"] = {
                r["symbol"]: r["n"]
                for r in db.execute(
                    "SELECT symbol,count(*) n FROM analysis_setups WHERE session_id=? GROUP BY symbol",
                    (uid,),
                )
            }
            d.pop("chat_id")
            d.pop("bot_id")
            d.pop("request_key")
            return d

    def catalog(self, workspace):
        with self.connection() as db:
            rows = db.execute(
                "SELECT id FROM analysis_sessions WHERE workspace=? ORDER BY created_ms DESC LIMIT 100",
                (workspace,),
            ).fetchall()
        return [
            {
                k: v
                for k, v in self.get(workspace, r["id"]).items()
                if k not in ("detail", "setups", "watermark")
            }
            for r in rows
        ]

    def control(self, workspace, uid, action, now):
        session = self.get(workspace, uid)
        if action not in ("pause", "resume", "stop"):
            raise ValidationError("Choose pause, resume or stop")
        if session["state"] in ("completed", "stopped"):
            raise ValidationError("This session has ended; create a new session")
        state = {"pause": "paused", "resume": "running", "stop": "stopped"}[action]
        if action == "resume" and session["spec"]["telegram"]:
            _, bot, chat = telegram_config()
            with self.connection() as db:
                r = db.execute(
                    "SELECT bot_id,chat_id FROM analysis_sessions WHERE id=?", (uid,)
                ).fetchone()
            if (bot, chat) != (r["bot_id"], r["chat_id"]):
                raise ValidationError(
                    "Telegram destination changed; create a new session"
                )
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if (
                state == "running"
                and session["state"] != "running"
                and db.execute(
                    "SELECT count(*) FROM analysis_sessions WHERE state='running'"
                ).fetchone()[0]
                >= 5
            ):
                raise ValidationError(
                    "Pause or stop an existing session first; at most five can run together"
                )
            db.execute(
                "UPDATE analysis_sessions SET state=?,phase=?,message='',updated_ms=?,alerts_after_ms=? WHERE id=?",
                (state, "preparing" if state == "running" else state, now, now, uid),
            )
            db.execute(
                "UPDATE analysis_setups SET delivery='suppressed' WHERE session_id=? AND delivery='pending'",
                (uid,),
            )
        return self.get(workspace, uid)

    def bars(self, uid, symbol):
        with self.connection() as db:
            return [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT document FROM analysis_bars WHERE session_id=? AND symbol=? ORDER BY open_ms",
                    (uid, symbol),
                )
            ]

    def save_bars(self, uid, symbol, bars, now):
        with self.connection() as db:
            db.executemany(
                "INSERT OR IGNORE INTO analysis_bar_revisions VALUES(?,?,?,?,?,?)",
                [
                    (uid, symbol, b["open_ms"], fingerprint(b), canonical(b), now)
                    for b in bars
                ],
            )
            db.executemany(
                "INSERT INTO analysis_bars VALUES(?,?,?,?,?) ON CONFLICT(session_id,symbol,open_ms) DO UPDATE SET document=excluded.document,received_ms=excluded.received_ms",
                [(uid, symbol, b["open_ms"], canonical(b), now) for b in bars],
            )

    def is_running(self, uid):
        with self.connection() as db:
            r = db.execute(
                "SELECT state FROM analysis_sessions WHERE id=?", (uid,)
            ).fetchone()
            return bool(r and r[0] == "running")


def parse_candles(raw, interval, cutoff):
    """Strict native-interval adapter; only fully closed candles are analysis inputs."""
    if not isinstance(raw, list) or len(raw) > 1000:
        raise ValidationError("Binance returned an invalid candle response")
    rows, seen = [], set()
    from tradee.c02.domain import number

    for r in raw:
        if (
            not isinstance(r, list)
            or len(r) < 11
            or type(r[0]) is not int
            or type(r[6]) is not int
        ):
            raise ValidationError("Malformed Binance candle")
        opened = r[0]
        if (
            opened < 0
            or opened % interval
            or r[6] != opened + interval - 1
            or opened in seen
        ):
            raise ValidationError("Misaligned or duplicate Binance candle")
        seen.add(opened)
        d = dict(
            open_ms=opened,
            close_ms=r[6],
            **{
                k: number(r[i], positive=i < 5)
                for k, i in (
                    ("open", 1),
                    ("high", 2),
                    ("low", 3),
                    ("close", 4),
                    ("volume", 5),
                    ("quote_volume", 7),
                    ("taker_base", 9),
                    ("taker_quote", 10),
                )
            },
        )
        d["raw"] = r
        if (
            Decimal(d["low"]) > min(Decimal(d["open"]), Decimal(d["close"]))
            or Decimal(d["high"]) < max(Decimal(d["open"]), Decimal(d["close"]))
            or Decimal(d["low"]) > Decimal(d["high"])
        ):
            raise ValidationError("Invalid candle price envelope")
        if opened + interval <= cutoff:
            rows.append(d)
    if any(a["open_ms"] >= b["open_ms"] for a, b in zip(rows, rows[1:])):
        raise ValidationError("Binance candles are out of order")
    return rows


class CandleSource:
    def __init__(self, opener=verified_urlopen):
        self.opener = opener

    def fetch(self, symbol, timeframe, start, end):
        rows = []
        interval = TIMEFRAMES[timeframe]
        while start < end:
            url = "https://fapi.binance.com/fapi/v1/klines?" + urlencode(
                dict(
                    symbol=symbol,
                    interval=timeframe,
                    startTime=start,
                    endTime=end - 1,
                    limit=1000,
                )
            )
            try:
                with self.opener(
                    Request(url, headers={"User-Agent": "Tradee-Analysis/1"}),
                    timeout=12,
                ) as response:
                    body = response.read(2000001)
                if len(body) > 2000000:
                    raise ValidationError("Candle response exceeds the analysis budget")
                page = parse_candles(json.loads(body), interval, end)
                if any(b["open_ms"] < start for b in page):
                    raise ValidationError(
                        "Binance returned candles outside the requested range"
                    )
            except ValidationError:
                raise
            except Exception:
                raise ProviderError(
                    "Market data request failed. Check Binance connectivity and try Resume.",
                    retry_after_seconds=60,
                ) from None
            if not page:
                break
            rows.extend(page)
            if len(rows) > MAX_BARS:
                raise ValidationError(
                    "Analysis candle limit reached; choose a smaller scan"
                )
            start = page[-1]["open_ms"] + interval
            if len(page) < 1000:
                break
        return rows


def levels(rows, interval):
    """Causal reference levels: prior range, completed UTC day, confirmed pivots."""
    if not rows:
        return []
    result = []

    def add(label, price, confirmed):
        result.append(dict(label=label, price=price, confirmed_ms=confirmed))

    if len(rows) >= 21:
        p = prior_range(rows, 20, interval)
        if p:
            add("Previous 20 candles · high", p["upper"], rows[-1]["open_ms"])
            add("Previous 20 candles · low", p["lower"], rows[-1]["open_ms"])
    # At a midnight close the just-completed day becomes the previous UTC day.
    day = (rows[-1]["open_ms"] + interval) // 86400000 * 86400000
    prior = [r for r in rows if day - 86400000 <= r["open_ms"] < day]
    if (
        len(prior) == 86400000 // interval
        and prior
        and prior[0]["open_ms"] == day - 86400000
    ):
        add(
            "Previous UTC day · high", max((r["high"] for r in prior), key=Decimal), day
        )
        add("Previous UTC day · low", min((r["low"] for r in prior), key=Decimal), day)
    for name, cmp in (("high", max), ("low", min)):
        for i in range(len(rows) - 3, 1, -1):
            value = Decimal(rows[i][name])
            neighbors = [Decimal(rows[j][name]) for j in (i - 2, i - 1, i + 1, i + 2)]
            if value > cmp(neighbors) if name == "high" else value < cmp(neighbors):
                add(
                    "Confirmed swing " + name,
                    rows[i][name],
                    rows[i + 2]["open_ms"] + interval,
                )
                break
    return result


def evaluate(rows, spec, scan_start):
    """One chronological pass. No future candles enter a signal's level snapshot."""
    interval = TIMEFRAMES[spec["timeframe"]]
    segment, setups, features = [], [], []
    # Recursive arrays are rebuilt only at a gap, with the same SMA seeding as C03.
    from tradee.c03.rolling import Smoother, exact_floats

    e20, e50 = Smoother(20), Smoother(50)
    previous_values = None
    for r in rows:
        if segment and r["open_ms"] != segment[-1]["open_ms"] + interval:
            segment, previous_values = [], None
            e20, e50 = Smoother(20), Smoother(50)
        segment.append(r)
        close = exact_floats([r["close"]])[0]
        a, b = e20.push(close), e50.push(close)
        values = {
            "ema20": dict(
                value=a,
                stable=a is not None and e20.seed_weight <= 1e-6,
                status="valid" if a is not None else "insufficient_history",
            ),
            "ema50": dict(
                value=b,
                stable=b is not None and e50.seed_weight <= 1e-6,
                status="valid" if b is not None else "insufficient_history",
            ),
        }
        features.append(dict(target_open_ms=r["open_ms"], values=values))
        if r["open_ms"] >= scan_start:
            for family in spec["strategies"]:
                trigger = None
                if family == "prior_range_breakout" and len(segment) >= 21:
                    # C08 also requires a valid log return measurement.
                    if Evaluator(segment[-2:]).get("log_return_1").stable:
                        trigger = prior_range(segment, 20, interval)
                elif (
                    family == "ema_pullback_continuation"
                    and previous_values
                    and all(
                        v["stable"]
                        for v in (*values.values(), *previous_values.values())
                    )
                ):
                    trigger = trend_recovery(segment[-2], r, previous_values, values)
                if trigger:
                    for side in ("long", "short"):
                        if trigger[side]:
                            level = (
                                trigger.get("level")
                                or trigger["upper" if side == "long" else "lower"]
                            )
                            setups.append(
                                dict(
                                    symbol="",
                                    strategy=family,
                                    strategy_name=STRATEGIES[family],
                                    side=side,
                                    open_ms=r["open_ms"],
                                    end_ms=r["open_ms"] + interval,
                                    price=r["close"],
                                    trigger_level=level,
                                    expires_ms=r["open_ms"]
                                    + interval
                                    + min(300000, interval),
                                    levels=levels(segment, interval),
                                    explanation=(
                                        (
                                            "Closed above the previous 20-candle high"
                                            if side == "long"
                                            else "Closed below the previous 20-candle low"
                                        )
                                        if family == "prior_range_breakout"
                                        else (
                                            "Closed back above EMA20 while EMA20 is above EMA50"
                                            if side == "long"
                                            else "Closed back below EMA20 while EMA20 is below EMA50"
                                        )
                                    ),
                                )
                            )
        previous_values = values
    ready = {
        "prior_range_breakout": len(segment) >= 21,
        "ema_pullback_continuation": len(segment) >= 397,
    }
    return dict(
        setups=setups,
        features=features,
        levels=levels(segment, interval),
        contiguous_bars=len(segment),
        readiness={s: ready[s] for s in spec["strategies"]},
    )


def alert_text(session, signal):
    stamp = datetime.fromtimestamp(signal["end_ms"] / 1000, timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )
    expiry = datetime.fromtimestamp(signal["expires_ms"] / 1000, timezone.utc).strftime(
        "%H:%M:%S UTC"
    )
    return (
        f"TRADEE · SETUP OBSERVATION\n{signal['symbol']} · {signal['side'].upper()} · {session['spec']['timeframe']}\n"
        f"{signal['strategy_name']}\n{signal['explanation']}\nClosed at: {signal['price']} USDT\n"
        f"Trigger level: {signal['trigger_level']} USDT\nCandle closed: {stamp}\nExpires: {expiry}\n"
        f"Session: {session['spec']['name']}\nReference: {signal['id'][:16]}\n"
        "Rule match only; not a validated trade recommendation. No order or paper fill was created."
    )


class AnalysisService:
    def __init__(self, settings, source=None, clock=time.time, feed_factory=None):
        self.settings, self.clock = settings, clock
        target = Path(str(settings.state_path) + ".analysis.sqlite3").resolve()
        if any(target == p.path(k) for p in settings.profiles for k in p.paths):
            raise ValidationError(
                "Analysis storage must be separate from every component store"
            )
        self.store = AnalysisStore(target)
        self.source = source or CandleSource()
        from .analysis_live import C02LiveFeed

        self.feed_factory = feed_factory or C02LiveFeed
        self.feeds = {}
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.thread = None
        self.lock = None

    def start(self):
        self.lock = open(str(self.store.path) + ".lock", "a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            self.lock = None
            return
        with self.store.connection() as db:
            db.execute(
                "UPDATE analysis_sessions SET state='paused',phase='paused',message='Server restarted. Resume to continue; missed setups will not be sent.' WHERE state='running'"
            )
            db.execute(
                "UPDATE analysis_setups SET delivery='ambiguous' WHERE delivery='sending'"
            )
            db.execute(
                "UPDATE analysis_setups SET delivery='suppressed' WHERE delivery='pending'"
            )
        self.thread = threading.Thread(
            target=self.loop, name="tradee-analysis", daemon=True
        )
        self.thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        for feed in list(self.feeds.values()):
            feed.stop.set()
        if self.thread:
            self.thread.join(timeout=40)
        for feed in list(self.feeds.values()):
            feed.close()
        # Keep ownership if an in-flight network call is still returning.
        if (
            self.lock
            and (not self.thread or not self.thread.is_alive())
            and all(
                not f.thread or not f.thread.is_alive() for f in self.feeds.values()
            )
        ):
            self.lock.close()

    def ensure_feed(self, workspace, session):
        uid = session["id"]
        if uid in self.feeds and self.feeds[uid].stop.is_set():
            self.feeds[uid].close()
            if self.feeds[uid].thread and self.feeds[uid].thread.is_alive():
                return None
            self.feeds.pop(uid)
        if uid not in self.feeds:
            start = (
                min(session["watermark"].values())
                + TIMEFRAMES[session["spec"]["timeframe"]]
            )
            feed = self.feed_factory(
                self.settings, workspace, session, start, self.wake, self.clock
            )
            self.feeds[uid] = feed
            try:
                feed.start()
            except Exception:
                feed.close()
                self.feeds.pop(uid, None)
                raise
            if not self.store.is_running(uid) or self.stop.is_set():
                feed.close()
                self.feeds.pop(uid, None)
                return None
        return self.feeds[uid]

    def release_feeds(self, active):
        for uid in set(self.feeds) - set(active):
            feed = self.feeds[uid]
            feed.close()
            if not feed.thread or not feed.thread.is_alive():
                self.feeds.pop(uid, None)

    def loop(self):
        while not self.stop.is_set():
            self.wake.clear()
            with self.store.connection() as db:
                sessions = db.execute(
                    "SELECT workspace,id,last_poll_ms FROM analysis_sessions WHERE state='running' ORDER BY last_poll_ms"
                ).fetchall()
            self.release_feeds(r["id"] for r in sessions)
            for r in sessions:
                if self.stop.is_set():
                    break
                if self.clock() * 1000 - r["last_poll_ms"] >= CHECK_SECONDS * 1000:
                    try:
                        self.tick(r["workspace"], r["id"])
                    except Exception as exc:
                        # No network exception/credential URLs reach disk or browser.
                        message = (
                            str(exc)[:250]
                            if isinstance(exc, (ValidationError, ProviderError))
                            else "Data request interrupted. Check Binance access, then Resume."
                        )
                        with self.store.connection() as db:
                            db.execute(
                                "UPDATE analysis_sessions SET state='paused',phase='interrupted',message=? WHERE id=? AND state='running'",
                                (message, r["id"]),
                            )
            self.wake.wait(0.5)

    def metadata(self, workspace, session, now):
        profile = self.settings.profile(workspace)
        registry = Registry(profile.path("c01"))
        if now - session["metadata_ms"] >= 900000:
            registry.refresh(BinanceProvider(attempts=1, timeout=12))
            with self.store.connection() as db:
                db.execute(
                    "UPDATE analysis_sessions SET metadata_ms=? WHERE id=?",
                    (now, session["id"]),
                )
        universe = registry.universe(Policy(tuple(session["spec"]["symbols"])))
        selected = [
            d
            for d in universe["decisions"]
            if d["symbol"] in session["spec"]["symbols"]
        ]
        if set(universe["members"]) != set(session["spec"]["symbols"]):
            reasons = "; ".join(
                d["symbol"] + ": " + ", ".join(d["reasons"])
                for d in selected
                if d["state"] != "eligible"
            )
            raise ValidationError("Instrument not ready: " + reasons)

    def tick(self, workspace, uid):
        now = int(self.clock() * 1000)
        session = self.store.get(workspace, uid)
        if session["state"] != "running":
            return
        spec, watermark = session["spec"], session["watermark"]
        from .config import build_hash
        from tradee.c06.engine import code_hash

        if session["build"] != fingerprint([build_hash(), code_hash()]):
            raise ValidationError(
                "Analysis code changed. Create a new session so its saved settings and results remain reproducible."
            )
        interval = TIMEFRAMES[spec["timeframe"]]
        with self.store.connection() as db:
            db.execute(
                "UPDATE analysis_sessions SET last_poll_ms=? WHERE id=?", (now, uid)
            )
        if session["started_ms"] and now - session["started_ms"] >= 86400000:
            with self.store.connection() as db:
                db.execute(
                    "UPDATE analysis_sessions SET state='completed',phase='completed',message='24-hour session complete. Create a new session to keep watching.' WHERE id=?",
                    (uid,),
                )
            return
        self.metadata(workspace, session, now)
        feed = None
        if spec["mode"] == "live" and all(s in watermark for s in spec["symbols"]):
            feed = self.ensure_feed(workspace, session)
            if not feed:
                return
        # Leave 2 seconds for exchange finalization. Partial bars never trigger.
        end = (now - 2000) // interval * interval
        scan_end = session["detail"].get("scan_end_ms", end)
        if spec["mode"] == "history":
            end = scan_end
        count = spec["history_bars"] + 420 if spec["mode"] == "history" else 500
        detail = dict(session["detail"], scan_end_ms=scan_end)
        for symbol in spec["symbols"]:
            if not self.store.is_running(uid) or self.stop.is_set():
                return
            existing = self.store.bars(uid, symbol)
            start = end - count * interval if not existing else existing[-1]["open_ms"]
            from .readers import AccessPolicy

            AccessPolicy(self.settings.profile(workspace)).range(
                existing[0]["open_ms"] if existing else max(0, start),
                max(end, now + 1) if spec["mode"] == "live" else end,
            )
            live = feed.view(symbol) if feed else None
            if live and live["status"].get("error"):
                raise ProviderError(live["status"]["error"], halt_polling=True)
            # Native REST candles are only initial history. Live updates come
            # exclusively from the existing C02 Collector and its gap repair.
            fetched = (
                live["candles"]
                if live
                else self.source.fetch(symbol, spec["timeframe"], max(0, start), end)
            )
            if live:
                previous_bars = {r["open_ms"]: r for r in existing}
                fetched = [r for r in fetched if previous_bars.get(r["open_ms"]) != r]
            if not self.store.is_running(uid) or self.stop.is_set():
                return
            observed = int(self.clock() * 1000)
            self.store.save_bars(uid, symbol, fetched, observed)
            rows = self.store.bars(uid, symbol)
            if not rows:
                raise ValidationError(
                    f"No closed candles for {symbol}. Check its listing date and Binance availability."
                )
            if len(rows) > MAX_BARS:
                raise ValidationError(
                    "Session candle limit reached. Start a new session."
                )
            previous = watermark.get(symbol)
            start_scan = (
                end - spec["history_bars"] * interval
                if spec["mode"] == "history"
                else (
                    previous + interval
                    if previous is not None
                    else end - 100 * interval
                )
            )
            closed_hash = fingerprint(rows)
            old = session["detail"].get(symbol, {})
            analysis = (
                evaluate(rows, spec, start_scan)
                if closed_hash != old.get("closed_hash")
                else {
                    k: old[k]
                    for k in ("features", "levels", "contiguous_bars", "readiness")
                }
            )
            stream = live["status"] if live else dict(state="connecting")
            stale = rows[-1]["open_ms"] + interval < end or (
                spec["mode"] == "live" and stream["state"] != "connected"
            )
            for signal in analysis.pop("setups", []):
                signal.update(
                    symbol=symbol,
                    timeframe=spec["timeframe"],
                    observed_ms=observed,
                    basis=(
                        "downloaded_historical_candles"
                        if previous is None or spec["mode"] == "history"
                        else "c02_recorded_closed_candle"
                    ),
                )
                signal["id"] = fingerprint(
                    [uid, symbol, signal["strategy"], signal["open_ms"], signal["side"]]
                )
                signal["source_hash"] = fingerprint(
                    [r for r in rows if r["open_ms"] <= signal["open_ms"]]
                )
                delivery = (
                    "historical"
                    if previous is None
                    or spec["mode"] == "history"
                    or signal["end_ms"]
                    <= max(
                        session["alerts_after_ms"], stream.get("suppress_before_ms", 0)
                    )
                    else (
                        "expired"
                        if observed >= signal["expires_ms"] or stale
                        else "pending" if spec["telegram"] else "disabled"
                    )
                )
                with self.store.connection() as db:
                    if (
                        db.execute(
                            "SELECT state FROM analysis_sessions WHERE id=?", (uid,)
                        ).fetchone()[0]
                        != "running"
                    ):
                        return
                    db.execute(
                        "INSERT OR IGNORE INTO analysis_setups(id,session_id,symbol,end_ms,document,delivery) VALUES(?,?,?,?,?,?)",
                        (
                            signal["id"],
                            uid,
                            symbol,
                            signal["end_ms"],
                            canonical(signal),
                            delivery,
                        ),
                    )
            watermark[symbol] = rows[-1]["open_ms"]
            detail[symbol] = dict(
                analysis,
                candles=[dict(data=r) for r in rows],
                symbol=symbol,
                bars=len(rows),
                stale=stale,
                closed_hash=closed_hash,
                stream=stream if spec["mode"] == "live" else None,
                forming=live["forming"] if live else None,
                source=(
                    "C02 WebSocket collector + closed native candle history"
                    if spec["mode"] == "live"
                    else "Binance USDⓈ-M native closed candles"
                ),
                last_close_ms=rows[-1]["open_ms"] + interval,
                message=(
                    "Waiting for the next closed candle"
                    if not stale
                    else "Binance stream is not current or completed candles are missing; alerts are suppressed"
                ),
            )
        completed = spec["mode"] == "history"
        ready = all(
            all(detail[s]["readiness"].values()) and not detail[s]["stale"]
            for s in spec["symbols"]
        )
        published_ms = int(self.clock() * 1000)
        with self.store.connection() as db:
            db.execute(
                """UPDATE analysis_sessions SET detail=?,watermark=?,updated_ms=?,started_ms=COALESCE(started_ms,?),
                state=?,phase=?,message='' WHERE id=? AND state='running'""",
                (
                    canonical(detail),
                    canonical(watermark),
                    published_ms,
                    published_ms,
                    "completed" if completed else "running",
                    (
                        "completed"
                        if completed
                        else (
                            "watching"
                            if ready
                            else (
                                "waiting_stream"
                                if any(
                                    detail[s]["stream"]["state"] != "connected"
                                    for s in spec["symbols"]
                                )
                                else "warming_up"
                            )
                        )
                    ),
                    uid,
                ),
            )
        if not completed:
            if not feed:
                # Preparation has been committed. Connect the advanced collector;
                # the next event-driven tick consumes its persisted closed bars.
                self.ensure_feed(workspace, self.store.get(workspace, uid))
            self.dispatch(workspace, uid)

    def dispatch(self, workspace, uid):
        session = self.store.get(workspace, uid)
        if session["state"] != "running" or not session["spec"]["telegram"]:
            return
        now = int(self.clock() * 1000)
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            r = db.execute(
                "SELECT * FROM analysis_setups WHERE session_id=? AND delivery='pending' ORDER BY end_ms,id LIMIT 1",
                (uid,),
            ).fetchone()
            if not r:
                return
            signal = json.loads(r["document"])
            feed = self.feeds.get(uid)
            if feed:
                live_status = feed.view(signal["symbol"])["status"]
                if live_status["state"] != "connected" or signal[
                    "end_ms"
                ] <= live_status.get("suppress_before_ms", 0):
                    db.execute(
                        "UPDATE analysis_setups SET delivery='suppressed' WHERE id=?",
                        (r["id"],),
                    )
                    return
            if session["detail"].get(signal["symbol"], {}).get("stale"):
                db.execute(
                    "UPDATE analysis_setups SET delivery='suppressed' WHERE id=?",
                    (r["id"],),
                )
                return
            if now >= signal["expires_ms"]:
                db.execute(
                    "UPDATE analysis_setups SET delivery='expired' WHERE id=?",
                    (r["id"],),
                )
                return
            last = db.execute(
                "SELECT MAX(attempted_ms) FROM analysis_setups"
            ).fetchone()[0]
            if last and now - last < 3500:
                return
            next_send = db.execute(
                "SELECT next_ms FROM analysis_delivery_clock WHERE id=1"
            ).fetchone()
            if next_send and now < next_send[0]:
                return
            dest = db.execute(
                "SELECT state,bot_id,chat_id FROM analysis_sessions WHERE id=?", (uid,)
            ).fetchone()
            if dest["state"] != "running":
                return
            transport, bot, chat = telegram_config()
            if (bot, chat) != (dest["bot_id"], dest["chat_id"]):
                raise ValidationError(
                    "Telegram destination changed. Create a new session."
                )
            db.execute(
                "UPDATE analysis_setups SET delivery='sending',attempted_ms=? WHERE id=?",
                (now, r["id"]),
            )
        # One durable attempt. Unknown acceptance is never automatically retried.
        retry_after_ms = 0
        try:
            result = transport.send(
                chat,
                alert_text(session, signal),
                min(10000, signal["expires_ms"] - now),
            )
            status = (
                result.status
                if result.status in ("sent", "failed", "ambiguous")
                else "failed"
            )
            message_id = result.message_id
            retry_after_ms = result.retry_after_ms
        except Exception:
            status, message_id = "ambiguous", None
        with self.store.connection() as db:
            if retry_after_ms:
                db.execute(
                    "INSERT INTO analysis_delivery_clock VALUES(1,?) ON CONFLICT(id) DO UPDATE SET next_ms=MAX(next_ms,excluded.next_ms)",
                    (int(self.clock() * 1000) + retry_after_ms,),
                )
            db.execute(
                "UPDATE analysis_setups SET delivery=?,message_id=? WHERE id=?",
                (status, message_id, r["id"]),
            )
