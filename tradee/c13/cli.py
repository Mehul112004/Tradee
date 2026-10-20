"""Offline shared-capital replay and persistent local allocation proposals."""
import json
from pathlib import Path
from tradee.c01 import Registry,ValidationError
from tradee.c02 import MarketStore
from tradee.c08 import CandidateConfig
from tradee.c08.metadata import capture
from tradee.c07 import ExecutionEngine,ExecutionConfig,FeeSchedule
from tradee.c10 import EstimatorStore
from tradee.c11 import SimulationStore
from .contracts import RiskPolicy,AccountSnapshot,Offer
from .replay import ReplayConfig
from .store import PortfolioStore


def load(path): return json.loads(Path(path).read_text())


def prefix_executor(market,dataset_hash,offers,when):
    ds=market.dataset(dataset_hash); events=list(market.replay(dataset_hash,until_ms=when))
    if len(events)>250000 or len(events)*len(offers)>2000000: raise ValidationError('Standalone allocation replay work budget exceeded')
    cache={}
    def execute(offer,stamp):
        q=offer.request.document(); cfg=ExecutionConfig.from_dict(q['execution']); fees=FeeSchedule.from_dict(q['fees'])
        key=json.dumps(q['candidates'],sort_keys=True)
        if key not in cache: cache[key]=capture(market.registry,ds,CandidateConfig.from_dict(q['candidates']))
        snapshots,versions=cache[key]; known=[s for s in snapshots if s['as_of_ms']<=stamp]
        e=ExecutionEngine(ds,[offer.execution_intent],known[-1] if known else snapshots[0],versions,fees,cfg,[q['feature_snapshot']],ds['as_of_ms'])
        for event in events: e.push(event)
        return e.evaluate(offer.execution_intent,stamp)
    return execute


def register(sub):
    p=sub.add_parser('portfolio',help='C13 shared paper risk, exact-size allocation and funded replay')
    p.add_argument('--market-db',default='data/c02.sqlite3'); p.add_argument('--simulation-db',default='data/c11.sqlite3')
    p.add_argument('--estimator-db',default='data/c10.sqlite3'); p.add_argument('--portfolio-db',default='data/c13.sqlite3')
    actions=p.add_subparsers(dest='portfolio_command',required=True); actions.add_parser('explain')
    a=actions.add_parser('replay'); a.add_argument('--sources',required=True); models=a.add_mutually_exclusive_group(required=True); models.add_argument('--models',nargs='+'); models.add_argument('--model-files',nargs='+')
    a.add_argument('--policy',default='configs/c13_risk_policy.json'); a.add_argument('--config',default='configs/c13_replay.json')
    for name in ('summary','manifest','report','records','artifact'): actions.add_parser(name).add_argument('hash')
    a=actions.add_parser('account-create'); a.add_argument('name'); a.add_argument('--snapshot',required=True)
    actions.add_parser('account').add_argument('name')
    a=actions.add_parser('account-update'); a.add_argument('name'); a.add_argument('--expected',required=True); a.add_argument('--snapshot',required=True)
    a=actions.add_parser('allocate'); a.add_argument('name'); a.add_argument('--expected',required=True); a.add_argument('--offers',required=True)
    a.add_argument('--dataset',required=True); a.add_argument('--at-ms',type=int,required=True); a.add_argument('--policy',default='configs/c13_risk_policy.json')


def execute(args):
    action=args.portfolio_command
    if action=='explain': return dict(component='C13',policy=RiskPolicy().document(),replay=ReplayConfig().document(),
        sizing='Largest feasible predeclared exact quantity with its own compatible C10 inference; no proportional outcome scaling',
        ranking='Smallest eligible size anchors lower-bound monetary expectancy per collateral-hour; lexical tie break',
        capacity='One shared wallet across families/horizons; per-trade/total/group/horizon/absolute-beta/collateral/joint-shock caps',
        release='Paper research only; no leverage>1, liquidation engine, exchange account access or Telegram')
    paths=[Path(p).resolve() for p in (args.db,args.market_db,args.simulation_db,args.estimator_db,args.portfolio_db)]
    if len(set(paths))!=len(paths): raise ValidationError('C01/C02/C10/C11/C13 paths must differ')
    s=PortfolioStore(args.portfolio_db,forbidden_paths=paths[:-1])
    if action=='replay':
        required=(args.db,args.market_db,args.simulation_db)+((args.estimator_db,) if args.models else ())
        if not all(Path(p).is_file() for p in required): raise ValidationError('Existing C01/C02/C10/C11 stores required')
        market=MarketStore(Registry(args.db),args.market_db)
        models=[EstimatorStore(args.estimator_db).model(h) for h in args.models] if args.models else [load(p) for p in args.model_files]
        return s.replay(SimulationStore(args.simulation_db),market,load(args.sources),models,RiskPolicy.from_dict(load(args.policy)),ReplayConfig.from_dict(load(args.config)))
    if action=='account-create': return s.create_account(args.name,AccountSnapshot.from_dict(load(args.snapshot)))
    if action=='account': return s.account(args.name)
    if action=='account-update': return s.replace_snapshot(args.name,args.expected,AccountSnapshot.from_dict(load(args.snapshot)))
    if action=='allocate':
        if not all(Path(p).is_file() for p in (args.db,args.market_db)): raise ValidationError('Existing C01/C02 input stores required')
        offers=[Offer.from_dict(d) for d in load(args.offers)]; market=MarketStore(Registry(args.db),args.market_db)
        result=s.allocate(args.name,args.expected,offers,RiskPolicy.from_dict(load(args.policy)),prefix_executor(market,args.dataset,offers,args.at_ms),args.at_ms)
        return dict(**result,ready=result['allocation']['ready'])
    return getattr(s,action)(args.hash)
