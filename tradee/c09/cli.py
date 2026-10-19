"""Paper trade lifecycle commands with explicit candidate, fee and policy evidence."""
import json
from pathlib import Path
from tradee.c01 import Registry,ValidationError
from tradee.c02 import MarketStore
from tradee.c06 import FundingConfig,SettlementCalendar
from tradee.c07 import ExecutionConfig,FeeSchedule
from .contracts import TradeIntent,TradePolicy
from .store import LifecycleStore


def register(sub):
    p=sub.add_parser('lifecycle',help='C09 independent paper trades, one-time ledger and outcome reports')
    p.add_argument('--market-db',default='data/c02.sqlite3'); p.add_argument('--lifecycle-db',default='data/c09.sqlite3')
    actions=p.add_subparsers(dest='lifecycle_command',required=True); actions.add_parser('explain')
    run=actions.add_parser('run'); run.add_argument('dataset_hash'); run.add_argument('--intents',required=True); run.add_argument('--fees',required=True)
    run.add_argument('--execution',default='configs/c07_execution.json'); run.add_argument('--funding',default='configs/c06_funding.json')
    run.add_argument('--calendar'); run.add_argument('--batch-size',type=int,default=256)
    for name in ('manifest','summary','report','transition'):
        item=actions.add_parser(name); item.add_argument('hash')


def collection(path,key):
    doc=json.loads(Path(path).read_text())
    if not isinstance(doc,dict) or set(doc)!={'schema_version',key} or type(doc['schema_version']) is not int or doc['schema_version']!=1 or not isinstance(doc[key],list):
        raise ValidationError('Invalid lifecycle collection schema')
    return doc[key]


def execute(args):
    if args.lifecycle_command=='explain':
        return dict(component='C09',policy=TradePolicy().document(),states=['waiting','pending_entry','open','exit_pending','closed','expired','cancelled','unresolved'],
            formula='net = signed fill-price P&L - fill fees + signed settled funding; shortfall is already in fill prices',
            ambiguity='same-bar stop and target unresolved; no invented intrabar execution',scope='independent paper trade lifecycle, not account orders or portfolio simulation')
    paths=[Path(p).resolve() for p in (args.db,args.market_db,args.lifecycle_db)]
    if len(set(paths))!=3: raise ValidationError('C01/C02/C09 database paths must differ')
    if args.lifecycle_command=='run':
        if not Path(args.db).is_file() or not Path(args.market_db).is_file(): raise ValidationError('Existing C01/C02 databases required')
        intents=[TradeIntent.from_dict(d) for d in collection(args.intents,'intents')]
        fees=FeeSchedule.from_dict(json.loads(Path(args.fees).read_text())); execution=ExecutionConfig.from_dict(json.loads(Path(args.execution).read_text()))
        funding=FundingConfig.from_dict(json.loads(Path(args.funding).read_text()))
        calendars=[] if args.calendar is None else [SettlementCalendar.from_dict(d) for d in collection(args.calendar,'calendars')]
        return LifecycleStore(args.lifecycle_db,forbidden_paths=(args.db,args.market_db)).run(MarketStore(Registry(args.db),args.market_db),args.dataset_hash,
            intents,fees,execution,funding,calendars,args.batch_size)
    return getattr(LifecycleStore(args.lifecycle_db,forbidden_paths=(args.db,args.market_db)),args.lifecycle_command)(args.hash)
