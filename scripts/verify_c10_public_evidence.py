"""Saved public candle evidence must not become invented mature C10 labels."""
import argparse
import json
from pathlib import Path
from tradee.c06.engine import code_hash
from tradee.c10 import EstimatorStore,EstimatorConfig,TrainingWindow
from tradee.c11 import SimulationStore


def verify(source,output):
    source=Path(source); output=Path(output); output.mkdir(parents=True,exist_ok=True)
    doc=json.loads((source/'public_replay.json').read_text()); run=doc['simulation']['run_hash']; simulations=SimulationStore(source/'c11.sqlite3')
    manifest=simulations.manifest(run); start,end=manifest['decision_window_ms']; cutoff=manifest['dataset']['as_of_ms']+1
    store=EstimatorStore(output/'c10.sqlite3',forbidden_paths=[simulations.path])
    result=store.fit(simulations,[run],TrainingWindow(start,end,cutoff),EstimatorConfig())
    if result['ready'] or any(c['coverage']['mature'] for c in result['cohorts'].values()): raise AssertionError('Public modeled candles fabricated mature training labels')
    model=store.model(result['model_hash']); snapshot=store.training_snapshot(result['snapshot_hash'])
    if any(r['net_r'] is not None for r in snapshot['rows']): raise AssertionError('Unknown modeled net became a training target')
    if store.fit(simulations,[run],TrainingWindow(start,end,cutoff),EstimatorConfig())!=result: raise AssertionError('Repeated insufficient-evidence publication changed')
    report=dict(passed=True,source=str(source.resolve()),source_run_hash=run,code_hash=code_hash(),model=result,
        note='Saved real Binance candle replay with explicitly modeled availability/metadata/fills; settled funding and net labels remain unknown. C10 retains evidence and abstains. No new network, live account, calibrated prediction or profitability claim.')
    (output/'public_evidence.json').write_text(json.dumps(report,indent=2)+'\n'); return report


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--source',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); print(json.dumps(verify(args.source,args.output),indent=2))
