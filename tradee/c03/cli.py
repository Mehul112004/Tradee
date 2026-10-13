"""Feature commands never open exchange connections."""
import json
from pathlib import Path
from tradee.c01 import Registry, ValidationError
from tradee.c02 import MarketStore
from .catalog import CATALOG, FeatureConfig, definition, resolve
from .store import FeatureStore


def register(sub):
    parser=sub.add_parser('features',help='C03 definitions, causal runs and snapshots')
    parser.add_argument('--market-db',default='data/c02.sqlite3')
    parser.add_argument('--feature-db',default='data/c03.sqlite3')
    commands=parser.add_subparsers(dest='feature_command',required=True)
    commands.add_parser('list')
    explain=commands.add_parser('explain'); explain.add_argument('feature')
    run=commands.add_parser('run'); run.add_argument('dataset_hash')
    run.add_argument('--config',default='configs/c03_baseline.json')
    run.add_argument('--start'); run.add_argument('--end')
    for name in ('snapshot','manifest','lineage','summary'):
        p=commands.add_parser(name); p.add_argument('hash')


def execute(args,timestamp):
    if args.feature_command=='list':
        return {'features':[definition(k).document() for k in sorted(CATALOG)],
                'parameterized':'simple_return_H, H=1..9999'}
    if args.feature_command=='explain':
        spec=definition(args.feature)
        return {**spec.document(),'definition_hash':spec.definition_hash,'evaluation_order':resolve((args.feature,))}
    paths=[Path(p).resolve() for p in (args.db,args.market_db,args.feature_db)]
    if len(set(paths))!=3:
        raise ValidationError('C01, C02 and C03 database paths must differ')
    store=FeatureStore(args.feature_db,forbidden_paths=(args.db,args.market_db))
    if args.feature_command=='run':
        configuration=json.loads(Path(args.config).read_text())
        if args.start:
            configuration['output_start_ms']=timestamp(args.start)
        if args.end:
            configuration['output_end_ms']=timestamp(args.end)
        config=FeatureConfig.from_dict(configuration)
        if not Path(args.db).is_file() or not Path(args.market_db).is_file():
            raise ValidationError('Existing C01 and C02 databases are required')
        market=MarketStore(Registry(args.db),args.market_db)
        return store.run(market,args.dataset_hash,config)
    return getattr(store,args.feature_command)(args.hash)
