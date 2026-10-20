"""Foreground forward observation; optional local pause application, no messages."""
import json
from pathlib import Path
import time
from tradee.c01 import Registry,ValidationError
from tradee.c02 import MarketStore
from tradee.c11 import SimulationStore
from tradee.c13 import PortfolioStore
from tradee.c14 import SignalStore
from .contracts import MonitorPolicy
from .store import MonitorStore
from .engine import ForwardMonitor
from .reconcile import reconcile


def register(sub):
    p=sub.add_parser('monitor',help='C15 prospective paper evidence, fixed-look reviews and audited pause requests')
    for name,default in (('market','data/c02.sqlite3'),('simulation','data/c11.sqlite3'),('portfolio','data/c13.sqlite3'),('signal','data/c14.sqlite3'),('monitor','data/c15.sqlite3')):
        p.add_argument('--'+name+'-db',default=default)
    a=p.add_subparsers(dest='monitor_command',required=True); a.add_parser('explain')
    q=a.add_parser('create'); q.add_argument('name'); q.add_argument('--session',required=True); q.add_argument('--policy',required=True); q.add_argument('--at-ms',type=int)
    for name in ('status','events','observe','watch','export','reconcile','apply-pause'):
        q=a.add_parser(name); q.add_argument('name')
        if name in ('observe','reconcile','apply-pause'): q.add_argument('--at-ms',type=int)
        if name in ('reconcile','export','apply-pause'): q.add_argument('--report',required=name=='apply-pause')
        if name in ('observe','watch'): q.add_argument('--apply-pauses',action='store_true')
        if name=='watch':
            q.add_argument('--interval-seconds',type=float,default=5); q.add_argument('--max-cycles',type=int)
    a.add_parser('artifact').add_argument('hash')


def execute(args):
    action=args.monitor_command
    if action=='explain': return dict(component='C15',live_approved=False,
        operation='Register rules before any C14 cycle; retain revision-aware paper outcomes and independent shadow outcomes; monitor delivery and run fixed-look block reviews.',
        control='Observe produces durable pause requests. --apply-pauses explicitly applies local C14 pause controls; no automatic resume, trades, Telegram sends or model changes.',
        replay='Reconcile re-executes the pinned raw C02 dataset through C11/C13 and compares content hashes.',
        review='One predeclared family of cumulative forecast-residual reviews per deployment. Insufficient evidence never counts as success.')
    stamp=int(time.time()*1000) if getattr(args,'at_ms',None) is None else args.at_ms
    if action in ('status','events','export','artifact'):
        if not Path(args.monitor_db).is_file(): raise ValidationError('Existing C15 store required')
        store=MonitorStore(args.monitor_db,forbidden_paths=(args.db,args.market_db,args.simulation_db,args.portfolio_db,args.signal_db))
        if action=='artifact': return store.artifact(args.hash)
        if action=='events': return store.events(args.name)
        if action=='status': return store.head(args.name)
        # Export needs no operational databases; historical reports remain readable.
        h=store.head(args.name); key=args.report or h['report_hash']
        if key is None: raise ValidationError('Observe before exporting outcomes')
        r=store.artifact(key)
        if r.get('kind')!='forward_report' or r['manifest_hash']!=h['manifest_hash']: raise ValidationError('C15 export/report mismatch')
        from tradee.c01.domain import fingerprint
        rows=[x for x in r['rows'] if x['status']=='mature']
        return dict(component='C15',kind='forward_outcome_dataset',report_hash=key,as_of_ms=r['observed_ms'],deployment_hash=h['deployment_hash'],rows=rows,
            dataset_hash=fingerprint(rows),live_approved=False,use='Versioned research input only; no automatic fitting/holdout import. Keep independent and portfolio tracks separate.')
    paths=[Path(v).resolve() for v in (args.db,args.market_db,args.simulation_db,args.portfolio_db,args.signal_db,args.monitor_db)]
    if len(set(paths))!=len(paths): raise ValidationError('C01/C02/C11/C13/C14/C15 stores must differ')
    if not all(p.is_file() for p in paths[2:5]): raise ValidationError('Existing C11/C13/C14 evidence stores required')
    store=MonitorStore(args.monitor_db,forbidden_paths=paths[:-1])
    monitor=ForwardMonitor(store,SignalStore(args.signal_db),SimulationStore(args.simulation_db),PortfolioStore(args.portfolio_db))
    if action=='create': return monitor.register(args.name,args.session,MonitorPolicy.from_dict(json.loads(Path(args.policy).read_text())),stamp)
    if action=='apply-pause': return monitor.apply_pause(args.name,args.report,stamp)
    if action=='reconcile':
        if not all(p.is_file() for p in paths[:2]): raise ValidationError('Existing C01/C02 raw replay inputs required')
        return reconcile(monitor,args.name,MarketStore(Registry(args.db),args.market_db),stamp,args.report)
    def observe(at):
        r=monitor.observe(args.name,at)
        if args.apply_pauses and r['pause_requested'] and not r['health']['already_paused']: r=dict(r,pause_receipt=monitor.apply_pause(args.name,r['report_hash'],at))
        return r
    if action=='observe': return observe(stamp)
    if not 0.1<=args.interval_seconds<=60 or (args.max_cycles is not None and args.max_cycles<=0): raise ValidationError('Bounded monitor watch interval/cycle count required')
    count=0; stopped='cycle_limit'
    try:
        while args.max_cycles is None or count<args.max_cycles:
            r=observe(int(time.time()*1000)); print(json.dumps(dict(report_hash=r['report_hash'],observed_ms=r['observed_ms'],ready=r['ready'],health=r['health'],pause_requested=r['pause_requested']),sort_keys=True),flush=True)
            count+=1
            if args.max_cycles is None or count<args.max_cycles: time.sleep(args.interval_seconds)
    except KeyboardInterrupt: stopped='operator_interrupt'
    return dict(stopped=stopped,observations=count,live_approved=False)
