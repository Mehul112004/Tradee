"""The preregistered comparisons: retain all failed variants and empty cohorts."""
import argparse
from collections import Counter,defaultdict
from concurrent.futures import ProcessPoolExecutor,as_completed
from copy import deepcopy
import json
from pathlib import Path
import subprocess

from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from .archive import audit
from .calendar import reconstructed
from .contracts import BAR,DAY,MODES,PRIORITY,PilotConfig
from .research import MinuteBook,detect,funding,implementation_hash,metrics,model_trade,walk_forward
from .risk import replay_capital


def observation_controls(trades):
    result=[]; last={}; counts=Counter()
    for trade in sorted(trades,key=lambda t:(t['plan']['end_ms'],t['plan']['symbol'],PRIORITY[t['plan']['strategy']],t['plan']['opportunity_id'])):
        t=deepcopy(trade); p=t['plan']; tags=p.get('family_tags',[p['strategy']]); keys=[(p['symbol'],tag,p['end_ms']//DAY) for tag in tags]; reason=None
        if 'entry_ms' in t:
            if p['symbol'] in last and p['end_ms']<last[p['symbol']]+4*BAR: reason='observation_cooldown'
            elif any(counts[key]>=3 for key in keys): reason='observation_family_cap'
            if reason:
                t.update(status='no_entry',reason=reason,net_r=None,marks=[])
                for field in ('entry_ms','entry','entry_risk','exit_ms','exit','net','entry_mid','fees','funding','entry_fee','expected_stopped_loss','scenario_stop_first_r'): t.pop(field,None)
            else:
                last[p['symbol']]=p['end_ms']
                for key in keys: counts[key]+=1
        result.append(t)
    return result


def task(directory,output,protocol,calendar,name,config,symbol,scope,code,dataset_hash):
    target=Path(output)/f'{name}-{symbol}.json'
    if target.exists():
        saved=json.loads(target.read_text())
        if (saved['implementation_hash']!=code or saved['config']!=config or saved['protocol_hash']!=fingerprint(protocol)
                or saved['calendar_hash']!=fingerprint(calendar) or saved['dataset_hash']!=dataset_hash): raise ValidationError('Comparison cache mismatch; use a new output path')
        return name,symbol,str(target)
    cfg=PilotConfig(**config); data=detect(directory,symbol,cfg,protocol,scope)
    book=MinuteBook(directory,protocol['development_end']); settlements=funding(directory,symbol,protocol['warmup_start'],protocol['development_end'])
    blackouts=reconstructed(calendar); stimes=[s['end_ms'] for s in data['states']]
    trades=[model_trade(p,book,data['states'],settlements,blackouts,protocol['modeled_execution'],state_times=stimes) for p in data['plans']]
    stresses={}
    if name=='base':
        variants={'fees':dict(fee_each_side='0.00075'),'slippage':dict(slippage_bps_each_side='4',exit_spread_bps='10'),
            'delay60':dict(entry_delay_seconds=60),'delay120':dict(entry_delay_seconds=120),
            'combined':dict(fee_each_side='0.00075',slippage_bps_each_side='4',exit_spread_bps='10',entry_delay_seconds=120)}
        # Freeze baseline detector plans. Changed execution eligibility remains explicit.
        for label,changes in variants.items():
            execution=dict(protocol['modeled_execution'],**changes)
            stresses[label]=[model_trade(p,book,data['states'],settlements,blackouts,execution,state_times=stimes) for p in data['plans']]
    saved=dict(implementation_hash=code,protocol_hash=fingerprint(protocol),calendar_hash=fingerprint(calendar),dataset_hash=dataset_hash,config=config,
        detection={k:v for k,v in data.items() if k not in ('states','plans')},trades=trades,stresses=stresses)
    target.write_text(json.dumps(saved,separators=(',',':'))+'\n')
    return name,symbol,str(target)


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--protocol',default='configs/pilot_research_v1.json')
    parser.add_argument('--calendar',default='configs/pilot_calendar_reconstructed.json'); parser.add_argument('--archives',default='data/pilot-research/archives')
    parser.add_argument('--output',default='data/pilot-research/comparisons-v1'); parser.add_argument('--workers',type=int,default=2)
    args=parser.parse_args(); protocol=json.loads(Path(args.protocol).read_text()); calendar=json.loads(Path(args.calendar).read_text())
    if protocol['development_end']>protocol['reserved_start'] or not 1<=args.workers<=4: raise ValidationError('Invalid comparison scope/budget')
    output=Path(args.output); output.mkdir(parents=True,exist_ok=True); code=implementation_hash()
    configs={'base':(PilotConfig(),None),'geom08':(PilotConfig(geometry_scale='0.8'),None),'geom12':(PilotConfig(geometry_scale='1.2'),None),
        'no_dull':(PilotConfig(dull_filter=False),None),'no_exhaustion':(PilotConfig(exhaustion_filter=False),None),
        'loose':(PilotConfig(regime_neighbor='loose'),None),'tight':(PilotConfig(regime_neighbor='tight'),None),
        'raw':(PilotConfig(regime_filter=False,dull_filter=False,exhaustion_filter=False),None),
        'raw_range':(PilotConfig(regime_filter=False,dull_filter=False,exhaustion_filter=False),'sweep_range')}
    sources=audit(args.archives,protocol); dataset_hash=fingerprint(sources)
    manifest=dict(implementation_hash=code,protocol=protocol,calendar_hash=fingerprint(calendar),dataset_hash=dataset_hash,sources=sources,
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),holdout_accessed=False,live_approved=False,
        configs={n:dict(config=c.document(),scope=s) for n,(c,s) in configs.items()},
        note='Modeled diagnostics only. No-exhaustion removes level episode caps and EMA clean-separation; break/retest timing and attempt/risk controls remain. Stress freezes detector plans, not baseline fills. Unknown historical trial count prevents adjusted significance.')
    manifest['run_id']=fingerprint(manifest); (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    datasets=defaultdict(list); detections=defaultdict(dict); stress=defaultdict(list)
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures=[pool.submit(task,args.archives,args.output,protocol,calendar,n,c.document(),s,scope,code,dataset_hash) for n,(c,scope) in configs.items() for s in protocol['symbols']]
        for f in as_completed(futures):
            name,symbol,path=f.result(); saved=json.loads(Path(path).read_text())
            datasets[name]+=saved['trades']; detections[name][symbol]=saved['detection']
            for label,trades in saved['stresses'].items(): stress[label]+=trades
            print(json.dumps(dict(completed=name,symbol=symbol,plans=len(saved['trades']))),flush=True)
    variants={}; capital={}; controlled={}
    datasets['raw']=[t for t in datasets['raw'] if t['plan']['mode']!='sweep_range']+datasets.pop('raw_range')
    for name,trades in datasets.items():
        controlled[name]={m:observation_controls([t for t in trades if t['plan']['mode']==m]) for m in MODES}
        variants[name]={m:metrics(ts) for m,ts in controlled[name].items()}
        capital[name]={m:replay_capital(ts) for m,ts in controlled[name].items()}
    stress_report={label:{m:metrics(observation_controls([t for t in trades if t['plan']['mode']==m])) for m in MODES} for label,trades in stress.items()}
    wf_cohorts={scale:controlled[name] for scale,name in [('0.8','geom08'),('1','base'),('1.2','geom12')]}
    # One fixed primary-plan portfolio per confirmation/instrument, before considering outcome labels.
    def bundle(trades):
        grouped=defaultdict(list); result=[]
        for t in trades:
            if 'entry_ms' in t: grouped[(t['plan']['symbol'],t['plan']['end_ms'])].append(t)
        for ts in grouped.values():
            if len({t['plan']['side'] for t in ts})>1: continue
            primary=deepcopy(sorted(ts,key=lambda t:(PRIORITY[t['plan']['strategy']],t['plan']['opportunity_id']))[0])
            primary['plan']['family_tags']=sorted({t['plan']['strategy'] for t in ts})
            result.append(primary)
        return observation_controls(result)
    report=dict(manifest=manifest,detection=detections,variants=variants,capital=capital,stress=stress_report,
        walk_forward={m:walk_forward(wf_cohorts,m,protocol) for m in MODES},
        combined_capital=replay_capital(bundle(datasets['base'])),combined_adverse_capital=replay_capital(bundle(stress['combined'])),
        promotion=dict(accepted=False,reasons=['modeled_execution_only','historical_trials_unknown','unattested_reserved_evidence','forward_paper_outstanding']))
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(report=str(output/'report.json'),run_id=manifest['run_id'])),flush=True)


if __name__=='__main__': main()
