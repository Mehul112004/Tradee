"""Funding CLI: no network, account credentials, order or position execution."""
import json
from pathlib import Path

from tradee.c01 import Registry, ValidationError
from tradee.c02 import MarketStore
from .contracts import FundingConfig, PositionTimeline, SettlementCalendar, strict_object
from .store import FundingStore


def register(sub):
    p=sub.add_parser('funding',help='C06 exact settlement accounting and observed next-funding estimates')
    p.add_argument('--market-db',default='data/c02.sqlite3')
    p.add_argument('--funding-db',default='data/c06.sqlite3')
    commands=p.add_subparsers(dest='funding_command',required=True)
    commands.add_parser('explain')
    run=commands.add_parser('run'); run.add_argument('dataset_hash')
    run.add_argument('--positions',required=True,help='Schema-v1 quantity timeline JSON')
    run.add_argument('--calendar',help='Explicit expected settlement timestamps and evidence JSON')
    run.add_argument('--config',default='configs/c06_funding.json')
    run.add_argument('--as-of',help='Evaluation time; default is pinned C02 dataset cutoff')
    run.add_argument('--batch-size',type=int,default=256)
    for name in ('report','manifest','summary'):
        item=commands.add_parser(name); item.add_argument('hash')


def load_collection(path, field, cls):
    doc=json.loads(Path(path).read_text())
    strict_object(doc,('schema_version',field),('schema_version',field))
    if type(doc['schema_version']) is not int or doc['schema_version']!=1 or not isinstance(doc[field],list):
        raise ValidationError('Unsupported funding input schema')
    return tuple(cls.from_dict(item) for item in doc[field])


def execute(args, timestamp):
    if args.funding_command=='explain':
        return dict(schema_version=1,component='C06',currency='USDT',
            formula='cashflow = -side_sign * base_quantity * settlement_mark_price * settled_rate',
            side_sign={'long':1,'short':-1},numeric_policy='exact Decimal; positive received, negative paid; unrounded',
            default_config=FundingConfig().document(),
            boundary='strict: quantity change within inclusive +/-15000ms (or configured larger guard) is ambiguous; nominal: post-change quantity at settlement',
            coverage='explicit calendar required for a complete total; missing records never imply zero',
            estimates='latest eligible recorded mark observation; next settlement only; no historical settlement rate used as a forecast')
    paths=[Path(p).resolve() for p in (args.db,args.market_db,args.funding_db)]
    if len(set(paths))!=3:
        raise ValidationError('C01, C02 and C06 databases must differ')
    if args.funding_command=='run':
        if not Path(args.db).is_file() or not Path(args.market_db).is_file():
            raise ValidationError('Existing C01/C02 databases are required')
        positions=load_collection(args.positions,'positions',PositionTimeline)
        calendars=() if args.calendar is None else load_collection(args.calendar,'calendars',SettlementCalendar)
        config=FundingConfig.from_dict(json.loads(Path(args.config).read_text()))
        store=FundingStore(args.funding_db,forbidden_paths=(args.db,args.market_db))
        market=MarketStore(Registry(args.db),args.market_db)
        return store.run(market,args.dataset_hash,positions,calendars,config,
                         None if args.as_of is None else timestamp(args.as_of),args.batch_size)
    return getattr(FundingStore(args.funding_db,forbidden_paths=(args.db,args.market_db)),args.funding_command)(args.hash)
