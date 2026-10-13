"""C01 CLI; JSON output is also useful for shell-based inspection."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

from .c01 import BinanceProvider, Policy, ProviderError, Registry


def timestamp(text):
    value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("--as-of requires a timezone, for example 2026-09-13T12:00:00Z")
    return int(value.astimezone(timezone.utc).timestamp() * 1000)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tradee C01 — Binance instrument registry")
    parser.add_argument("--db", default="data/c01.sqlite3")
    parser.add_argument("--enabled", default="BTCUSDT,ETHUSDT", help="Comma-separated explicit universe")
    parser.add_argument("--max-age-seconds", type=int, default=1800)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("refresh", help="Fetch and persist public Binance exchangeInfo")
    imp = sub.add_parser("import", help="Import a response as observed now (offline development)")
    imp.add_argument("file")
    uni = sub.add_parser("universe", help="Evaluate the supplied policy at an observation time")
    uni.add_argument("--as-of")
    uni.add_argument("--save", action="store_true")
    uni.add_argument("--members-only", action="store_true")
    sub.add_parser("health")
    hist = sub.add_parser("history")
    hist.add_argument("symbol")
    ver = sub.add_parser("version")
    ver.add_argument("hash")
    snap = sub.add_parser("snapshot")
    snap.add_argument("hash")
    watch = sub.add_parser("watch", help="Refresh at startup, then periodically; Ctrl-C stops")
    watch.add_argument("--interval-seconds", type=int, default=900)
    args = parser.parse_args(argv)
    try:
        policy = Policy(tuple(s.strip().upper() for s in args.enabled.split(",")), args.max_age_seconds)
        registry = Registry(args.db)
        if args.command == "watch":
            if args.interval_seconds <= 0:
                raise ValueError("Refresh interval must be positive")
            while True:
                wait = args.interval_seconds
                try:
                    print(json.dumps(registry.refresh(BinanceProvider())), flush=True)
                except ProviderError as exc:
                    print(json.dumps({"error": str(exc)}), file=sys.stderr, flush=True)
                    if exc.halt_polling:
                        return 1
                    wait = max(wait, exc.retry_after_seconds)
                except Exception as exc:
                    print(json.dumps({"error": str(exc)}), file=sys.stderr, flush=True)
                time.sleep(wait)
        elif args.command == "refresh":
            result = registry.refresh(BinanceProvider())
        elif args.command == "import":
            result = registry.ingest(Path(args.file).read_text(), source="file:" + str(Path(args.file).resolve()))
        elif args.command == "universe":
            result = registry.universe(policy, timestamp(args.as_of) if args.as_of else None, args.save)
            if args.members_only:
                result = {k: result[k] for k in ("snapshot_hash", "as_of_ms", "members")}
        elif args.command == "health":
            result = registry.health(policy)
        elif args.command == "history":
            result = registry.history(args.symbol.upper())
        elif args.command == "version":
            result = registry.version(args.hash)
        elif args.command == "snapshot":
            result = registry.snapshot(args.hash)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if args.command != "health" or result["ready"] else 2
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
