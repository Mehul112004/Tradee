"""Raw simulated-receipt Binance inputs -> C11 -> default C10 -> later scoring.

Injected clocks are explicit synthetic receipt evidence; components/fills/labels
are real production implementations. No network, account keys or notifications.
"""
import argparse
from datetime import datetime,timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from tradee.c01 import Registry,Policy
from tradee.c02 import MarketStore
from tradee.c10.source import pages
from tradee.c11 import SimulationStore

ROOT=Path(__file__).resolve().parents[1]
START=1788220800000
DAY=86400000


def write(root,name,doc):
    p=root/name; p.write_text(json.dumps(doc,indent=2)+'\n'); return str(p)


def run_e2e(root):
    root=Path(root).resolve(); root.mkdir(parents=True,exist_ok=True)
    if any(root.glob('*.sqlite3')): raise ValueError('C10 E2E requires a fresh directory')
    commands=[]; clock=[START]
    raw=json.loads((ROOT/'tests/fixtures/exchange_info.json').read_text())
    for spec in raw['symbols']:
        for f in spec['filters']:
            if f['filterType']=='PRICE_FILTER': f.update(minPrice='1',maxPrice='1000000',tickSize='0.1')
            if f['filterType']=='MIN_NOTIONAL': f['notional']='5'
    write(root,'metadata.json',raw)
    registry=Registry(root/'c01.sqlite3',clock=lambda:clock[0]/1000); market=MarketStore(registry,root/'c02.sqlite3',clock=lambda:clock[0]/1000)
    def invoke(*args,expected=0):
        p=subprocess.run([sys.executable,'-m','tradee','--db',str(root/'c01.sqlite3'),*map(str,args)],cwd=ROOT,capture_output=True,text=True,timeout=120)
        if p.returncode!=expected: raise AssertionError(f'CLI exit {p.returncode}, expected {expected}: {p.stderr or p.stdout}')
        d=json.loads(p.stdout or p.stderr); commands.append(dict(args=list(map(str,args)),exit_code=p.returncode)); return d
    def simulate(*args,expected=0): return invoke('simulate','--market-db',root/'c02.sqlite3','--simulation-db',root/'c11.sqlite3',*args,expected=expected)
    def expectancy(*args,expected=0): return invoke('expectancy','--simulation-db',root/'c11.sqlite3','--estimator-db',root/'c10.sqlite3',*args,expected=expected)
    def capture(name,start,days):
        receipts=[]
        for k in range(days):
            opened=start+k*DAY; clock[0]=opened; registry.ingest(json.dumps(raw),source='synthetic:C10 daily metadata')
            for j,price in enumerate(('100','100','102','100')):
                stamp=opened+j*60000; clock[0]=stamp+60000; c=Decimal(price)
                row=[stamp,price,str(c+1),str(c-1),price,'1000',stamp+59999,str(c*1000),5,'700',str(c*700),'0']
                market.ingest_rest(json.dumps([row]),'BTCUSDT'); receipts.append(dict(received_ms=clock[0],kind='candle',raw=row))
                if j!=2: continue
                detected=clock[0]; exit_price='105' if k%2==0 else '106'
                for stamp,price,trigger in ((detected+1000,'102',False),(detected+40000,exit_price,True)):
                    clock[0]=stamp; p=Decimal(price)
                    messages=[dict(e='markPriceUpdate',E=stamp,s='BTCUSDT',p=price,i=price,r='0.001',T=stamp+3600000)]
                    if trigger: messages.append(dict(e='aggTrade',E=stamp,T=stamp,s='BTCUSDT',a=stamp,f=stamp,l=stamp,p=price,q='1',m=False))
                    messages.append(dict(e='bookTicker',E=stamp,T=stamp,s='BTCUSDT',u=stamp,b=str(p-Decimal('0.1')),a=str(p+Decimal('0.1')),B='10',A='10'))
                    for message in messages: market.ingest_ws(json.dumps(message)); receipts.append(dict(received_ms=stamp,kind=message['e'],raw=message))
        end=start+days*DAY; clock[0]=end
        ds=market.snapshot(['BTCUSDT'],start,end,kinds=('candle','mark','quote','trade','funding'))
        path=root/(name+'_receipts.jsonl'); path.write_text('\n'.join(json.dumps(r) for r in receipts)+'\n')
        instrument=next(d['instrument_id'] for d in registry.universe(Policy(('BTCUSDT',)))['decisions'] if d['symbol']=='BTCUSDT')
        cal=write(root,name+'_calendar.json',dict(schema_version=1,calendars=[dict(instrument_id=instrument,symbol='BTCUSDT',start_ms=start,end_ms=end,settlement_times_ms=[],evidence='operator_assumption:synthetic no-settlement fixture')]))
        return ds,cal
    scenarios=write(root,'scenarios.json',dict(schema_version=1,scenarios=[dict(name='range',strategy=dict(timeframe='1m',lookback_bars=2,entry_window_ms=60000,sides=['long']),policy=dict(max_holding_ms=60000),quantity='1',horizon='intraday')]))
    execution=write(root,'execution.json',dict(enabled_symbols=['BTCUSDT'],manual_delay_ms=0,max_spread_bps='25'))
    simulation=write(root,'simulation.json',dict(sample_interval_ms=DAY))
    def sim_args(ds,cal=None):
        args=['run',ds['dataset_hash'],'--scenarios',scenarios,'--fees',ROOT/'configs/c07_fee_assumptions.json','--execution',execution,'--config',simulation]
        return args+(['--calendar',cal] if cal else [])
    train,calendar=capture('training',START,36); training=simulate(*sim_args(train,calendar))
    if training['metrics']['mature']!=36: raise AssertionError('Raw training fixture did not yield 36 genuine mature outcomes')
    cutoff=START+36*DAY+1; fit_window=write(root,'fit_window.json',dict(start_ms=START,end_ms=START+36*DAY,cutoff_ms=cutoff))
    args=['fit','--runs',training['run_hash'],'--window',fit_window,'--modeled-available-ms',cutoff]
    # One transaction must contain the entire publication.
    from tradee.c10 import EstimatorStore
    store=EstimatorStore(root/'c10.sqlite3')
    with store.connection() as db: db.execute("CREATE TRIGGER fail BEFORE INSERT ON models BEGIN SELECT RAISE(ABORT,'C10 injected publication failure'); END")
    failed=expectancy(*args,expected=1)
    if 'injected publication failure' not in failed.get('error',''): raise AssertionError('Publication failure not surfaced')
    with store.connection() as db:
        if any(db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('snapshots','fits','models')): raise AssertionError('Failed fit published partial artifacts')
        db.execute('DROP TRIGGER fail')
    model=expectancy(*args)
    if not model['ready'] or next(iter(model['cohorts'].values()))['statistics']['mean_net_r']!='2.455942622951': raise AssertionError('Default cohort fit disagrees with literal golden R')
    if expectancy(*args)!=model: raise AssertionError('Repeated model publication changed identity')
    expectancy('model',model['model_hash']); expectancy('training-snapshot',model['snapshot_hash']); expectancy('fitted',model['fit_hash'])
    later_start=START+37*DAY; later,cal=capture('later',later_start,4); test=simulate(*sim_args(later,cal))
    evaluation_window=write(root,'later_window.json',dict(start_ms=later_start,end_ms=later_start+4*DAY,cutoff_ms=later_start+4*DAY+1))
    simulation_store=SimulationStore(root/'c11.sqlite3'); manifest=simulation_store.manifest(test['run_hash'])
    a=next(a for a in pages(simulation_store,test['run_hash'],'candidate_decision') if a['payload']['selected']); c=a['payload']['record']['candidate']
    f=next(a['payload'] for a in pages(simulation_store,test['run_hash'],'feature') if a['payload']['snapshot_hash']==c['feature_snapshot_hash'])
    request=write(root,'request.json',dict(candidate=c,feature_snapshot=f,scenario=manifest['scenarios'][0],execution=manifest['execution'],fees=manifest['fees'],funding=manifest['funding'],candidates=manifest['candidates'],evaluation_ms=c['detected_ms']))
    prediction=expectancy('estimate',model['model_hash'],'--request',request)
    if not prediction['eligible'] or prediction['status']!='estimated': raise AssertionError('Frozen inference unexpectedly abstained')
    expectancy('estimate-record',prediction['estimate_hash'])
    evaluated=expectancy('evaluate',model['model_hash'],'--runs',test['run_hash'],'--window',evaluation_window)
    if evaluated['coverage']['matched_eligible_mature']!=4 or evaluated['metrics']['all_mature_mean_net_r']!='2.455942622951': raise AssertionError('Later frozen predictions/outcomes mismatch')
    expectancy('evaluation',evaluated['evaluation_hash'])
    unknown=simulate(*sim_args(later),expected=2)
    unresolved=expectancy('evaluate',model['model_hash'],'--runs',unknown['run_hash'],'--window',evaluation_window,expected=2)
    if unresolved['coverage']['estimated']!=4 or unresolved['coverage']['matched_estimated_mature']!=0 or unresolved['metrics']['mean_squared_net_r_error'] is not None: raise AssertionError('Unknown outcomes fabricated evaluation labels')
    unknown_fit=expectancy('fit','--runs',unknown['run_hash'],'--window',evaluation_window,'--modeled-available-ms',later_start+4*DAY+1,expected=2)
    if unknown_fit['ready']: raise AssertionError('Unknown-funding evidence produced a usable estimator')
    mismatched=json.loads(Path(request).read_text()); mismatched['fees']['taker_rate']='0.001'
    abstain=expectancy('estimate',model['model_hash'],'--request',write(root,'wrong_fees.json',mismatched),expected=2)
    if 'incompatible_strategy_policy_cost_or_feature_protocol' not in abstain['reasons']: raise AssertionError('Incompatible fees were accepted')
    if expectancy('summary',model['model_hash'])!=model: raise AssertionError('Later data or evaluations mutated frozen estimator')
    result=dict(passed=True,commands=len(commands),model=model,prediction=prediction,evaluation=evaluated,unknown_outcomes=unresolved,
        training_run=training['run_hash'],later_run=test['run_hash'],artifacts_directory=str(root),
        checks=['raw simulated receipt ingestion','36 separate calendar bins with default gates','exact real fill/funding net R','causal training snapshots','block uncertainty',
            'atomic publication failure/retry','idempotence','modeled publication clock','later frozen inference','later scoring/reliability','unknown-funding abstention','incompatible-cost abstention','immutable model'],
        note='Synthetic engineering evidence with explicitly injected historical receipt clocks, 1m/2-bar long-only setup, size 1, zero manual delay, assumed fees and empty funding calendars. Default C10 thresholds/bootstrap are used. No live capture, profitability, calibration, walk-forward promotion or shared-capital claim.')
    write(root,'e2e_report.json',result); write(root,'e2e_commands.json',commands); return result


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path); args=p.parse_args()
    if args.output: result=run_e2e(args.output)
    else:
        with tempfile.TemporaryDirectory(prefix='tradee-c10-e2e-') as folder:
            result=run_e2e(folder); result['artifacts_directory']='temporary artifacts removed after successful check'
    print(json.dumps(result,indent=2))
