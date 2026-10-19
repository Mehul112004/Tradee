"""Register, validate, explicitly open holdout, and inspect frozen research evidence."""
import json
from pathlib import Path
from tradee.c01 import ValidationError
from tradee.c11 import SimulationStore
from .contracts import Experiment, EvidencePolicy
from .store import ResearchStore


def register(sub):
    p=sub.add_parser('research',help='C12 nested walk-forward, trial registry and one-way holdout access')
    p.add_argument('--simulation-db',default='data/c11.sqlite3'); p.add_argument('--research-db',default='data/c12.sqlite3')
    actions=p.add_subparsers(dest='research_command',required=True); actions.add_parser('explain')
    a=actions.add_parser('register'); a.add_argument('--manifest',required=True)
    for name in ('manifest','jobs','events','decision','release','run','open-holdout'):
        a=actions.add_parser(name); a.add_argument('experiment_hash')
        if name=='open-holdout': a.add_argument('--reason',required=True)
    actions.add_parser('artifact').add_argument('hash')
    actions.add_parser('ledger').add_argument('family')


def execute(args):
    if args.research_command=='explain':
        return dict(component='C12',policy=EvidencePolicy().document(),selection='Earlier inner windows only; no outer reselection',
            sources='Pinned immutable C11 outputs; generate them with simulate run. Separate untouched holdout run IDs; TBot/inspected data is development.',
            holdout='Explicit logged open-holdout binds final choice/model before reading results; outside-C12 raw access cannot be controlled',
            release='Versioned research decision only; independent signal utility, no portfolio return or live approval')
    paths=[Path(p).resolve() for p in (args.db,args.simulation_db,args.research_db)]
    if len(set(paths))!=3: raise ValidationError('C01/C11/C12 paths must differ')
    if args.research_command in ('run','open-holdout') and not paths[1].is_file(): raise ValidationError('Existing C11 simulation database required')
    s=ResearchStore(args.research_db,forbidden_paths=(args.db,args.simulation_db))
    action=args.research_command
    if action=='register': return s.register(Experiment.from_dict(json.loads(Path(args.manifest).read_text())))
    if action=='run': return s.run(args.experiment_hash,SimulationStore(args.simulation_db))
    if action=='open-holdout': return s.open_holdout(args.experiment_hash,SimulationStore(args.simulation_db),args.reason)
    if action=='artifact': return s.artifact(args.hash)
    if action=='ledger': return s.ledger(args.family)
    return getattr(s,action)(args.experiment_hash)
