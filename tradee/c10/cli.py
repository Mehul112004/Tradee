"""Cohort expectancy fit, frozen inference and later-period diagnostics."""
import json
from pathlib import Path
from tradee.c01 import ValidationError
from tradee.c11 import SimulationStore
from .contracts import TrainingWindow,EstimatorConfig,EstimateRequest
from .store import EstimatorStore


def register(sub):
    p=sub.add_parser('expectancy',help='C10 causal cohort expectancy, time-block uncertainty and frozen inference')
    p.add_argument('--simulation-db',default='data/c11.sqlite3'); p.add_argument('--estimator-db',default='data/c10.sqlite3')
    actions=p.add_subparsers(dest='expectancy_command',required=True); actions.add_parser('explain')
    fit=actions.add_parser('fit'); fit.add_argument('--runs',nargs='+',required=True); fit.add_argument('--window',required=True)
    fit.add_argument('--config',default='configs/c10_estimator.json'); fit.add_argument('--modeled-available-ms',type=int)
    for name in ('model','summary','training-snapshot','fitted','estimate-record','evaluation'):
        actions.add_parser(name).add_argument('hash')
    item=actions.add_parser('estimate'); item.add_argument('model_hash'); item.add_argument('--request',required=True)
    item=actions.add_parser('evaluate'); item.add_argument('model_hash'); item.add_argument('--runs',nargs='+',required=True); item.add_argument('--window',required=True)


def load(path): return json.loads(Path(path).read_text())


def execute(args):
    if args.expectancy_command=='explain': return dict(component='C10',config=EstimatorConfig().document(),
        estimand='Mean net R conditional on fill and mature evidence, not unconditional profit per signal',
        training='Last C11 outcome revision observed strictly before cutoff; disjoint decision coverage, no unknown-funding labels or tiny-cohort fallback',
        uncertainty='Synchronized circular calendar-block percentile bootstrap, not IID trades; sparse/degenerate evidence abstains',
        publication='Recorded actual publication time by default; explicit modeled availability for historical research',
        release='Frozen research estimator; C12 walk-forward and C13/C14 release/portfolio integration remain')
    paths=[Path(p).resolve() for p in (args.db,args.simulation_db,args.estimator_db)]
    if len(set(paths))!=3: raise ValidationError('C01/C10/C11 paths must differ')
    if args.expectancy_command in ('fit','evaluate') and not Path(args.simulation_db).is_file(): raise ValidationError('Existing C11 simulation database required')
    store=EstimatorStore(args.estimator_db,forbidden_paths=(args.db,args.simulation_db))
    if args.expectancy_command=='fit':
        return store.fit(SimulationStore(args.simulation_db),args.runs,TrainingWindow.from_dict(load(args.window)),EstimatorConfig.from_dict(load(args.config)),args.modeled_available_ms)
    if args.expectancy_command=='estimate': return store.estimate(args.model_hash,EstimateRequest.from_dict(load(args.request)))
    if args.expectancy_command=='evaluate': return store.evaluate(args.model_hash,SimulationStore(args.simulation_db),args.runs,TrainingWindow.from_dict(load(args.window)))
    return getattr(store,args.expectancy_command.replace('-','_'))(args.hash)
