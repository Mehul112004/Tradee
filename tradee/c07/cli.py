"""C07 paper execution: no account endpoints, order placement or notifications."""
import json
from pathlib import Path
from tradee.c01 import Registry, ValidationError
from tradee.c02 import MarketStore
from .contracts import ExecutionConfig, ExecutionIntent, FeeSchedule
from .store import ExecutionStore


def register(sub):
    p=sub.add_parser('execution',help='C07 fees, delay, paper fills and tradability')
    p.add_argument('--market-db',default='data/c02.sqlite3'); p.add_argument('--execution-db',default='data/c07.sqlite3')
    actions=p.add_subparsers(dest='execution_command',required=True); actions.add_parser('explain')
    run=actions.add_parser('run'); run.add_argument('dataset_hash'); run.add_argument('--intents',required=True)
    run.add_argument('--fees',required=True); run.add_argument('--config',default='configs/c07_execution.json')
    run.add_argument('--features',help='JSON containing C03 store snapshots and their hashes')
    run.add_argument('--as-of'); run.add_argument('--batch-size',type=int,default=256)
    for name in ('report','manifest','summary'): item=actions.add_parser(name); item.add_argument('hash')


def collection(path,field):
    doc=json.loads(Path(path).read_text())
    if (not isinstance(doc,dict) or set(doc)!={'schema_version',field} or type(doc['schema_version']) is not int
            or doc['schema_version']!=1 or not isinstance(doc[field],list)):
        raise ValidationError('Invalid execution collection schema')
    return doc[field]


def execute(args,timestamp):
    if args.execution_command=='explain':
        return dict(component='C07',currency='USDT',scope='independent paper execution scenarios',
            defaults=ExecutionConfig().document(),fee='explicit fee schedule; market scenarios use taker rate',
            model='buy at ask plus adverse impact; sell at bid minus adverse impact; adverse tick rounding',
            accounting='implementation shortfall = delay drift + spread crossing + extra slippage; never add shortfall again to fill-price P&L',
            bars='explicit modeled-bar preset, synthetic spread, volume proxy and optional mark/metadata research assumptions')
    paths=[Path(p).resolve() for p in (args.db,args.market_db,args.execution_db)]
    if len(set(paths))!=3: raise ValidationError('C01/C02/C07 database paths must differ')
    if args.execution_command=='run':
        if not Path(args.db).is_file() or not Path(args.market_db).is_file(): raise ValidationError('Existing C01/C02 databases required')
        intents=[ExecutionIntent.from_dict(i) for i in collection(args.intents,'intents')]
        features=() if args.features is None else collection(args.features,'feature_snapshots')
        cfg=ExecutionConfig.from_dict(json.loads(Path(args.config).read_text()))
        fees=FeeSchedule.from_dict(json.loads(Path(args.fees).read_text()))
        store=ExecutionStore(args.execution_db,forbidden_paths=(args.db,args.market_db))
        return store.run(MarketStore(Registry(args.db),args.market_db),args.dataset_hash,intents,fees,cfg,features,
                         None if args.as_of is None else timestamp(args.as_of),args.batch_size)
    return getattr(ExecutionStore(args.execution_db,forbidden_paths=(args.db,args.market_db)),args.execution_command)(args.hash)
