"""C02 command registration, kept separate from C01's command implementation."""
import json
from pathlib import Path

from . import MarketStore, RestClient, ArchiveClient, Collector, aggregate


def register(sub):
    parser = sub.add_parser('data', help='C02 ingestion, quality and replay')
    parser.add_argument('--market-db', default='data/c02.sqlite3')
    commands = parser.add_subparsers(dest='data_command', required=True)
    for name in ('backfill', 'repair'):
        p = commands.add_parser(name)
        p.add_argument('symbol')
        p.add_argument('--start', required=True)
        p.add_argument('--end', required=True)
        p.add_argument('--kind', choices=('candle', 'funding', 'open_interest'), default='candle')
    p = commands.add_parser('archive')
    p.add_argument('symbol')
    p.add_argument('period', help='YYYY-MM or YYYY-MM-DD')
    p = commands.add_parser('import-rest')
    p.add_argument('symbol')
    p.add_argument('file')
    p.add_argument('--kind', choices=('candle', 'funding', 'open_interest'), default='candle')
    p = commands.add_parser('import-ws')
    p.add_argument('file', help='One JSON WebSocket envelope per line')
    p = commands.add_parser('import-archive')
    p.add_argument('symbol')
    p.add_argument('file')
    p.add_argument('checksum_file')
    p = commands.add_parser('collect')
    p.add_argument('--symbols', default='BTCUSDT,ETHUSDT')
    p.add_argument('--streams', default='candle', help='candle,trade,quote,mark')
    p = commands.add_parser('snapshot')
    p.add_argument('--symbols', default='BTCUSDT,ETHUSDT')
    p.add_argument('--kinds', default='candle')
    p.add_argument('--start', required=True)
    p.add_argument('--end', required=True)
    p.add_argument('--as-of')
    p.add_argument('--mode', choices=('recorded', 'modeled'), default='recorded')
    p.add_argument('--delay-ms', type=int)
    for name in ('replay', 'quality', 'bars', 'dataset'):
        p = commands.add_parser(name)
        p.add_argument('hash')
        if name != 'dataset':
            p.add_argument('--as-of')
        if name == 'bars':
            p.add_argument('--minutes', type=int, default=5)
        if name == 'replay':
            p.add_argument('--after-id', type=int)


def execute(args, registry, timestamp):
    store = MarketStore(registry, args.market_db)
    command = args.data_command
    if command in ('backfill', 'repair'):
        return RestClient().backfill(store, args.symbol.upper(), timestamp(args.start), timestamp(args.end),
                                     args.kind, resume=command == 'backfill')
    if command == 'archive':
        return ArchiveClient().fetch(store, args.symbol.upper(), args.period)
    if command == 'import-rest':
        return store.ingest_rest(Path(args.file).read_text(), args.symbol.upper(), args.kind,
                                 source='file:' + str(Path(args.file).resolve()))
    if command == 'import-ws':
        count = 0
        with Path(args.file).open() as stream:
            for line in stream:
                if line.strip():
                    store.ingest_ws(line, source='file:' + str(Path(args.file).resolve()))
                    count += 1
        return {'imported_messages': count}
    if command == 'import-archive':
        return ArchiveClient().ingest(store, args.symbol.upper(), Path(args.file).read_bytes(),
                                      Path(args.checksum_file).read_text(), 'file:' + str(Path(args.file).resolve()))
    if command == 'collect':
        Collector(store, args.symbols.upper().split(','), args.streams.split(',')).run()
        return {'stopped': True}
    if command == 'snapshot':
        return store.snapshot(args.symbols.upper().split(','), timestamp(args.start), timestamp(args.end),
                              args.kinds.split(','), args.mode, args.delay_ms,
                              timestamp(args.as_of) if args.as_of else None)
    if command == 'dataset':
        return store.dataset(args.hash)
    when = timestamp(args.as_of) if args.as_of else store.now()
    if command == 'quality':
        return store.quality(args.hash, when)
    if command == 'bars':
        return aggregate(store.view(args.hash, when), args.minutes * 60_000)
    if command == 'replay':
        for item in store.replay(args.hash, when, args.after_id):
            print(json.dumps(item, sort_keys=True))
        return None
