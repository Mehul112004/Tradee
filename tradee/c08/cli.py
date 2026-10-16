"""Candidate inventory commands; successful zero-candidate runs are normal."""
import json
from pathlib import Path
from tradee.c01 import Registry, ValidationError
from tradee.c02 import MarketStore
from .contracts import StrategySpec, CandidateConfig, FAMILIES
from .store import CandidateStore, STATUSES


def register(sub):
    p=sub.add_parser('candidates',help='C08 strategy definitions, setup detection and complete inventory')
    p.add_argument('--market-db',default='data/c02.sqlite3'); p.add_argument('--candidate-db',default='data/c08.sqlite3')
    actions=p.add_subparsers(dest='candidate_command',required=True)
    actions.add_parser('list'); explain=actions.add_parser('explain'); explain.add_argument('family',choices=FAMILIES)
    run=actions.add_parser('run'); run.add_argument('dataset_hash'); run.add_argument('--strategy',required=True)
    run.add_argument('--config',default='configs/c08_candidates.json'); run.add_argument('--batch-size',type=int,default=256)
    for name in ('manifest','summary','evaluation','feature','lineage'):
        item=actions.add_parser(name); item.add_argument('hash')
    records=actions.add_parser('records'); records.add_argument('hash'); records.add_argument('--limit',type=int,default=100)
    records.add_argument('--after-sequence',type=int,default=0); records.add_argument('--status',choices=STATUSES)


def execute(args):
    if args.candidate_command=='list': return {'strategies':[StrategySpec(family=f).definition() for f in FAMILIES]}
    if args.candidate_command=='explain':
        s=StrategySpec(family=args.family); return dict(strategy_hash=s.strategy_hash,**s.definition())
    paths=[Path(p).resolve() for p in (args.db,args.market_db,args.candidate_db)]
    if len(set(paths))!=3: raise ValidationError('C01/C02/C08 database paths must differ')
    if args.candidate_command=='run':
        if not Path(args.db).is_file() or not Path(args.market_db).is_file(): raise ValidationError('Existing C01/C02 stores required')
        strategy=StrategySpec.from_dict(json.loads(Path(args.strategy).read_text()))
        config=CandidateConfig.from_dict(json.loads(Path(args.config).read_text()))
        store=CandidateStore(args.candidate_db,forbidden_paths=(args.db,args.market_db))
        return store.run(MarketStore(Registry(args.db),args.market_db),args.dataset_hash,strategy,config,args.batch_size)
    store=CandidateStore(args.candidate_db,forbidden_paths=(args.db,args.market_db))
    if args.candidate_command=='records': return store.records(args.hash,args.limit,args.after_sequence,args.status)
    return getattr(store,args.candidate_command)(args.hash)
