"""Offline raw-input E2E: nested selection, durable retry, stress and sealed access.

Synthetic historical receipt clocks and reduced evidence gates are explicit.
The actual ingestion, features, fills, funding, labels, fitting and CLI are used.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
from tradee.c01 import Registry, Policy
from tradee.c02 import MarketStore
from tradee.c10 import EstimatorConfig
from tradee.c12 import EvidencePolicy, ResearchStore

ROOT=Path(__file__).resolve().parents[1]
START=1788220800000
BIN=240000


def write(root,name,doc):
    p=root/name; p.write_text(json.dumps(doc,indent=2)+'\n'); return str(p)


def manifest(dev,held,stress_dev,stress_held):
    def split(name,n,a,b):
        return dict(name=name,train=dict(start_ms=START,end_ms=START+n*BIN,cutoff_ms=START+n*BIN),
                    test=dict(start_ms=START+a*BIN,end_ms=START+b*BIN,cutoff_ms=START+b*BIN))
    cfg=EstimatorConfig(min_trades=6,min_occupied_bins=6,min_occupied_spans=6,bin_ms=BIN,block_bins=1,bootstrap_replicates=200).document()
    variants=[]
    for name,buffer,neighbor in (('range_zero','0',None),('range_buffer','0.1','range_zero')):
        variants.append(dict(name=name,hypothesis='Fixed 1m two-bar long breakout; estimator admission buffer grid',development_runs=[dev],holdout_runs=[held],
            estimator={**cfg,'lower_bound_buffer_r':buffer},rationale='Predeclared estimator buffer neighborhood',parameters={'buffer_r':buffer},neighbor_of=neighbor))
        variants.append(dict(name=name+'_fees',hypothesis='Doubled assumed fees with frozen baseline admission',development_runs=[stress_dev],holdout_runs=[stress_held],
            estimator=cfg,rationale='Adverse fee stress',parameters={'fee_multiplier':2},stress_of=name))
    return dict(name='raw_engineering',family='raw_engineering',thesis='Verify C01 through C12 engineering contracts',prior_research='Synthetic mechanical fixture only; all real TBot/previously viewed data remains development',historical_trials=0,family_trial_budget=4,
        variants=variants,folds=[dict(split=split('outer1',24,24,32),inner=[split('inner1',12,12,20)]),dict(split=split('outer2',36,36,44),inner=[split('inner2',20,20,28)])],
        holdout=dict(split=split('holdout',48,48,60),inner=[split('finalinner',28,28,40)]),holdout_status='uninspected',
        holdout_attestation='Mechanically generated synthetic prices; C12 selection cannot inspect sealed outcomes before explicit access',
        policy=EvidencePolicy(bin_ms=BIN,block_bins=1,bootstrap_replicates=200,min_candidates=6,min_eligible_mature=6,min_occupied_spans=6).document())


def run_e2e(root,negative_holdout=False):
    root=Path(root).resolve(); root.mkdir(parents=True,exist_ok=True)
    if any(root.glob('*.sqlite3')): raise ValueError('C12 E2E requires a fresh directory')
    commands=[]; clock=[START]
    raw=json.loads((ROOT/'tests/fixtures/exchange_info.json').read_text())
    for spec in raw['symbols']:
        for f in spec['filters']:
            if f['filterType']=='PRICE_FILTER': f.update(minPrice='1',maxPrice='1000000',tickSize='0.1')
            if f['filterType']=='MIN_NOTIONAL': f['notional']='5'
    write(root,'metadata.json',raw)
    registry=Registry(root/'c01.sqlite3',clock=lambda:clock[0]/1000)
    market=MarketStore(registry,root/'c02.sqlite3',clock=lambda:clock[0]/1000)
    def invoke(*args,expected=0):
        p=subprocess.run([sys.executable,'-m','tradee','--db',str(root/'c01.sqlite3'),*map(str,args)],cwd=ROOT,capture_output=True,text=True,timeout=180)
        if p.returncode!=expected: raise AssertionError(f'Exit {p.returncode}, expected {expected}: {(p.stderr or p.stdout)[:3000]}')
        commands.append(dict(args=list(map(str,args)),exit_code=p.returncode)); return json.loads(p.stdout or p.stderr)
    def research(*args,expected=0): return invoke('research','--simulation-db',root/'c11.sqlite3','--research-db',root/'c12.sqlite3',*args,expected=expected)
    def capture(name,start,n,negative=False):
        clock[0]=start; registry.ingest(json.dumps(raw),source='synthetic:C12 receipt metadata'); receipts=[]
        for k in range(n):
            for j,price in enumerate(('100','100','102','100')):
                opened=start+(4*k+j)*60000; c=Decimal(price); clock[0]=opened+60000
                row=[opened,price,str(c+1),str(c-1),price,'1000',opened+59999,str(c*1000),5,'700',str(c*700),'0']
                market.ingest_rest(json.dumps([row]),'BTCUSDT'); receipts.append(dict(received_ms=clock[0],kind='candle',raw=row))
                if j!=2: continue
                detected=clock[0]; close=('100' if k%2==0 else '99') if negative else ('105' if k%2==0 else '106')
                for stamp,price,trigger in ((detected+1000,'102',False),(detected+40000,close,True)):
                    clock[0]=stamp; p=Decimal(price)
                    messages=[dict(e='markPriceUpdate',E=stamp,s='BTCUSDT',p=price,i=price,r='0.001',T=stamp+3600000)]
                    if trigger: messages.append(dict(e='aggTrade',E=stamp,T=stamp,s='BTCUSDT',a=stamp,f=stamp,l=stamp,p=price,q='1',m=False))
                    messages.append(dict(e='bookTicker',E=stamp,T=stamp,s='BTCUSDT',u=stamp,b=str(p-Decimal('0.1')),a=str(p+Decimal('0.1')),B='10',A='10'))
                    for message in messages: market.ingest_ws(json.dumps(message)); receipts.append(dict(received_ms=stamp,kind=message['e'],raw=message))
        end=start+n*BIN; clock[0]=end
        ds=market.snapshot(['BTCUSDT'],start,end,kinds=('candle','quote','mark','trade','funding'))
        instrument=next(x['instrument_id'] for x in registry.universe(Policy(('BTCUSDT',)))['decisions'] if x['symbol']=='BTCUSDT')
        calendar=write(root,name+'_calendar.json',dict(schema_version=1,calendars=[dict(instrument_id=instrument,symbol='BTCUSDT',start_ms=start,end_ms=end,settlement_times_ms=[],evidence='operator_assumption:synthetic no-settlement window')]))
        (root/(name+'_receipts.jsonl')).write_text('\n'.join(json.dumps(r) for r in receipts)+'\n')
        return ds,calendar
    scenarios=write(root,'scenarios.json',dict(schema_version=1,scenarios=[dict(name='range',strategy=dict(timeframe='1m',lookback_bars=2,entry_window_ms=60000,sides=['long']),policy=dict(max_holding_ms=60000),quantity='1',horizon='intraday')]))
    execution=write(root,'execution.json',dict(enabled_symbols=['BTCUSDT'],manual_delay_ms=0,max_spread_bps='25',max_metadata_age_ms=86400000))
    simconfig=write(root,'simulation.json',dict(sample_interval_ms=BIN))
    fees=write(root,'fees.json',dict(taker_rate='0.0005',maker_rate='0.0002',evidence='synthetic assumed fees'))
    stressfees=write(root,'stress_fees.json',dict(taker_rate='0.001',maker_rate='0.0004',evidence='synthetic doubled assumed fees'))
    def simulate(ds,cal,fee):
        return invoke('simulate','--market-db',root/'c02.sqlite3','--simulation-db',root/'c11.sqlite3','run',ds['dataset_hash'],
            '--scenarios',scenarios,'--execution',execution,'--fees',fee,'--calendar',cal,'--config',simconfig)['run_hash']
    development,cal=capture('development',START,48); dev=simulate(development,cal,fees); sd=simulate(development,cal,stressfees)
    held,cal=capture('holdout',START+48*BIN,12,negative_holdout); hold=simulate(held,cal,fees); sh=simulate(held,cal,stressfees)
    from tradee.c11 import SimulationStore
    source_store=SimulationStore(root/'c11.sqlite3')
    plan=manifest(dev,hold,sd,sh); plan['source_report_hashes']={r:source_store.summary(r)['report_hash'] for r in (dev,hold,sd,sh)}
    path=write(root,'experiment.json',plan)
    research('explain'); registered=research('register','--manifest',path); h=registered['experiment_hash']
    if research('register','--manifest',path)!=registered: raise AssertionError('Registration must be idempotent')
    research('manifest',h); research('open-holdout',h,'--reason','Premature access must fail',expected=1)
    s=ResearchStore(root/'c12.sqlite3')
    with s.connection() as db: db.execute("CREATE TRIGGER fail BEFORE INSERT ON artifacts BEGIN SELECT RAISE(ABORT,'C12 injected atomic publication failure'); END")
    research('run',h,expected=1)
    with s.connection() as db:
        if db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0]: raise AssertionError('Failed publication left partial artifacts')
        db.execute('DROP TRIGGER fail')
    report=research('run',h)
    if report['evidence']['coverage']['eligible_mature']!=16 or report['evidence']['utility_r_per_candidate']!='2.455942622951': raise AssertionError('Golden later-window net R mismatch')
    # Equal inner utility uses lexical name, independently of holdout results.
    if report['final_selection']['winner']!='range_buffer': raise AssertionError('Deterministic tie-break failed')
    if research('run',h)!=report: raise AssertionError('Completed experiment changed on retry')
    research('decision',h,expected=2); before=research('events',h)
    if any(e['kind']=='holdout_opened' for e in before): raise AssertionError('Development touched sealed outcomes')
    final=research('open-holdout',h,'--reason','Synthetic controlled E2E explicit holdout access',expected=2 if negative_holdout else 0)
    if research('open-holdout',h,'--reason','Idempotent resume',expected=2 if negative_holdout else 0)!=final: raise AssertionError('Holdout changed on retry')
    decision=research('decision',h,expected=2 if negative_holdout else 0); release=research('release',h)
    if release['live_approved'] or release['release_hash']!=decision['release_hash']: raise AssertionError('Frozen release reference mismatch')
    jobs=research('jobs',h); events=research('events',h); ledger=research('ledger',plan['family'])
    if len([e for e in events if e['kind']=='holdout_opened'])!=1 or ledger['used_trials']!=4: raise AssertionError('Access/trial accounting mismatch')
    if decision['live_approved'] or decision['status']!=('rejected' if negative_holdout else 'research_candidate'): raise AssertionError('Research decision or live boundary failed')
    if not any(e['kind']=='job_failed' for e in events) or not any(j['attempts']==2 for j in jobs): raise AssertionError('Failed trial/resume missing')
    research('artifact',next(j['artifact'] for j in jobs if j['status']=='completed'))
    result=dict(passed=True,negative_holdout=negative_holdout,experiment_hash=h,commands=len(commands),development=report,holdout=final,decision=decision,
        checks=['raw C01/C02 ingestion','real C03/C08 detection and C07/C06/C09/C11 ledgers','earlier inner selection','two nonoverlapping outer windows','purge journals',
            'frozen final fit','joint calendar uncertainty','declared family correction','parameter neighborhood','frozen-admission double-fee stress','trial budgets',
            'atomic publication failure/retry','idempotence','blocked premature holdout','one-way logged holdout access','immutable research decision; live disabled'],
        note='Synthetic engineering verification; reduced six-outcome/six-span gates, four-minute bins, 200 bootstrap draws, 1m/two-bar long-only strategy, size 1, zero manual delay, assumed fees and empty funding calendars. Not untouched real-market evidence or profitability validation.')
    write(root,'e2e_report.json',result); write(root,'e2e_commands.json',commands); return result


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); p.add_argument('--negative-holdout',action='store_true'); args=p.parse_args()
    result=run_e2e(args.output,args.negative_holdout)
    print(json.dumps({k:result[k] for k in ('passed','experiment_hash','commands','decision','note')},indent=2))
