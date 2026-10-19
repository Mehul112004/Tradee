"""Historical simulation commands; all size, cost and calendar inputs are explicit."""
import json
from pathlib import Path

from tradee.c01 import Registry, ValidationError
from tradee.c02 import MarketStore
from tradee.c06 import FundingConfig, SettlementCalendar
from tradee.c07 import ExecutionConfig, FeeSchedule
from tradee.c08 import CandidateConfig
from tradee.c09.cli import collection
from .contracts import Scenario, SimulationConfig
from .store import SimulationStore, KINDS


def register(sub):
    p=sub.add_parser('simulate',help='C11 historical independent scenarios, reconciliation and regular P&L')
    p.add_argument('--market-db',default='data/c02.sqlite3'); p.add_argument('--simulation-db',default='data/c11.sqlite3')
    actions=p.add_subparsers(dest='simulation_command',required=True); actions.add_parser('explain')
    run=actions.add_parser('run'); run.add_argument('dataset_hash'); run.add_argument('--scenarios',required=True); run.add_argument('--fees',required=True)
    run.add_argument('--execution',default='configs/c07_execution.json'); run.add_argument('--funding',default='configs/c06_funding.json')
    run.add_argument('--calendar'); run.add_argument('--config',default='configs/c11_simulation.json'); run.add_argument('--candidates')
    for name in ('manifest','summary','report','artifact'):
        actions.add_parser(name).add_argument('hash')
    records=actions.add_parser('records'); records.add_argument('hash'); records.add_argument('--kind',choices=KINDS)
    records.add_argument('--scenario'); records.add_argument('--after-sequence',type=int,default=0); records.add_argument('--limit',type=int,default=100)
    compare=actions.add_parser('compare'); compare.add_argument('baseline_hash'); compare.add_argument('variant_hash')


def load(path): return json.loads(Path(path).read_text())


def execute(args):
    if args.simulation_command=='explain':
        return dict(component='C11',config=SimulationConfig().document(),track='independent candidates from both C08 families through shared C07/C06/C09 logic',
            schedule='full warm-up, half-open detection window, exact timers, source-before-same-time-sample, pinned outcome tail',
            publication='atomic completed run; interruptions replay from the beginning',
            results='all candidate diagnostics, causal outcome revisions, reconciled ledgers, stratified outcomes and regular marked P&L; no portfolio Sharpe/ROI')
    paths=[Path(p).resolve() for p in (args.db,args.market_db,args.simulation_db)]
    if len(set(paths))!=3: raise ValidationError('C01/C02/C11 database paths must differ')
    if args.simulation_command=='run':
        if not Path(args.db).is_file() or not Path(args.market_db).is_file(): raise ValidationError('Existing C01/C02 databases required')
        scenarios=[Scenario.from_dict(d) for d in collection(args.scenarios,'scenarios')]
        fees=FeeSchedule.from_dict(load(args.fees)); execution=ExecutionConfig.from_dict(load(args.execution))
        funding=FundingConfig.from_dict(load(args.funding)); config=SimulationConfig.from_dict(load(args.config))
        candidates=CandidateConfig.from_dict(load(args.candidates)) if args.candidates else None
        calendars=[] if args.calendar is None else [SettlementCalendar.from_dict(d) for d in collection(args.calendar,'calendars')]
        return SimulationStore(args.simulation_db,forbidden_paths=(args.db,args.market_db)).run(
            MarketStore(Registry(args.db),args.market_db),args.dataset_hash,scenarios,fees,execution,candidates,funding,calendars,config)
    store=SimulationStore(args.simulation_db,forbidden_paths=(args.db,args.market_db))
    if args.simulation_command=='compare': return store.compare(args.baseline_hash,args.variant_hash)
    if args.simulation_command=='records': return store.records(args.hash,args.kind,args.scenario,args.after_sequence,args.limit)
    return getattr(store,args.simulation_command)(args.hash)
