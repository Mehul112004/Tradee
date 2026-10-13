"""Offline C01/C02/C03/C06/C07 CLI E2E; synthetic observations and no orders.

Keep a fresh --output directory to inspect raw inputs and persisted reports.
Recorded receipt times are real; exchange event times are recent synthetic fixtures.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def iso(stamp): return datetime.fromtimestamp(stamp/1000,timezone.utc).isoformat()


def write(root,name,doc):
    path=root/name; path.write_text(json.dumps(doc,indent=2)+'\n'); return str(path)


def run_e2e(root):
    root=Path(root).resolve(); root.mkdir(parents=True,exist_ok=True)
    if any(root.glob('*.sqlite3')): raise ValueError('E2E requires a fresh directory')
    commands=[]
    def invoke(*args,expected=0):
        cmd=[sys.executable,'-m','tradee','--db',str(root/'c01.sqlite3'),*map(str,args)]
        result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=30)
        if result.returncode!=expected:
            raise AssertionError(f'CLI exit {result.returncode}, expected {expected}: {result.stderr or result.stdout}')
        doc=json.loads(result.stdout or result.stderr)
        commands.append(dict(args=list(map(str,args)),exit_code=result.returncode)); return doc
    def data(*args,expected=0):
        return invoke('data','--market-db',root/'c02.sqlite3',*args,expected=expected)
    def execution(*args,expected=0):
        return invoke('execution','--market-db',root/'c02.sqlite3','--execution-db',root/'c07.sqlite3',*args,expected=expected)
    raw=json.loads((ROOT/'tests/fixtures/exchange_info.json').read_text())
    # These are synthetic test rules for synthetic prices, not Binance historical rules.
    for f in raw['symbols'][0]['filters']:
        if f['filterType']=='PRICE_FILTER': f.update(minPrice='1',maxPrice='1000000',tickSize='0.1')
        if f['filterType']=='MIN_NOTIONAL': f['notional']='5'
    invoke('import',write(root,'synthetic_exchange_info.json',raw))
    universe=invoke('--enabled','BTCUSDT','universe')
    identity=next(d['instrument_id'] for d in universe['decisions'] if d['symbol']=='BTCUSDT')
    closed=int(time.time()*1000)//60000*60000; start=closed-55*60000
    candles=[[start+i*60000,'100','105','95','100','1000',start+i*60000+59999,'100000',5,'700','70000','0'] for i in range(55)]
    data('import-rest','BTCUSDT',write(root,'candles.json',candles))
    stamp=int(time.time()*1000); settlement=stamp+3600000
    mark=dict(e='markPriceUpdate',E=stamp,s='BTCUSDT',p='100',i='100',r='0.001',T=settlement)
    quote=dict(e='bookTicker',E=stamp,T=stamp,s='BTCUSDT',u=1,b='99.9',a='100.1',B='10',A='10')
    source=root/'websocket.jsonl'; source.write_text('\n'.join(json.dumps(x) for x in (mark,quote))+'\n')
    data('import-ws',source)
    end=(int(time.time()*1000)//60000+2)*60000
    ds=data('snapshot','--symbols','BTCUSDT','--kinds','candle,mark,quote','--start',iso(start),'--end',iso(end))
    feature_config=write(root,'feature_config.json',dict(features=['log_return_1','vwap20','rsi14'],timeframes=['1m'],require_stable=False))
    features=invoke('features','--market-db',root/'c02.sqlite3','--feature-db',root/'c03.sqlite3','run',ds['dataset_hash'],'--config',feature_config)
    latest=invoke('features','--feature-db',root/'c03.sqlite3','snapshot',features['latest'][0]['snapshot_hash'])
    if latest['values']['log_return_1']['value']!=0 or latest['values']['vwap20']['value']!=100:
        raise AssertionError('C03 actual feature values differ from the independent fixture')
    feature_file=write(root,'features.json',dict(schema_version=1,feature_snapshots=[latest]))
    intents=[]
    for side,stop in (('buy','99'),('sell','101')):
        intents.append(dict(intent_id=side,instrument_id=identity,symbol='BTCUSDT',side=side,quantity='1',
            detected_ms=stamp,expires_ms=stamp+60000,reference_price='100',stop_price=stop,holding_until_ms=settlement+60000,
            required_features=['log_return_1'],feature_timeframe='1m'))
    intent_file=write(root,'intents.json',dict(schema_version=1,intents=intents))
    config=write(root,'execution_config.json',dict(manual_delay_ms=0))
    fees=ROOT/'configs/c07_fee_assumptions.json'
    arguments=['run',ds['dataset_hash'],'--intents',intent_file,'--fees',fees,'--config',config,'--features',feature_file,'--batch-size','16']
    from tradee.c07 import ExecutionStore
    fault=ExecutionStore(root/'c07.sqlite3')
    with fault.connection() as db:
        db.execute("CREATE TRIGGER e2e_write_failure BEFORE INSERT ON reports WHEN (SELECT COUNT(*) FROM reports WHERE run_hash=NEW.run_hash)=1 BEGIN SELECT RAISE(ABORT,'E2E injected write failure'); END")
    error=execution(*arguments,expected=1)
    if 'E2E injected write failure' not in error.get('error',''): raise AssertionError('Expected SQLite failure was not reported')
    with fault.connection() as db:
        if db.execute('SELECT COUNT(*) FROM reports').fetchone()[0]!=1 or db.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0]!=1:
            raise AssertionError('A failed CLI batch did not preserve the first atomic checkpoint')
        db.execute('DROP TRIGGER e2e_write_failure')
    summary=execution(*arguments); report=execution('report',summary['report_hash'])
    estimates=report['estimates']
    if [e['fill']['price'] for e in estimates]!=['100.2','99.8']:
        raise AssertionError('Independent buy/sell golden fill prices mismatch')
    if [e['fill']['fee_usdt'] for e in estimates]!=['0.0501','0.0499']:
        raise AssertionError('Independent taker fee amounts mismatch')
    if [e['costs']['execution_plus_fee_cost_usdt'] for e in estimates]!=['0.2501','0.2499']:
        raise AssertionError('Shortfall decomposition or fees were double-counted')
    if [e['projected_execution_cost_with_next_funding_usdt'] for e in estimates]!=['0.3501','0.1499']:
        raise AssertionError('C06 funding projection signs mismatch')
    if any(e['feature_gate']['snapshot_hash']!=latest['snapshot_hash'] for e in estimates):
        raise AssertionError('C03 snapshots were not joined to the same pinned source prefix')
    if execution(*arguments)!=summary: raise AssertionError('Repeated CLI resume duplicated outputs')
    def rejected(name,rows=None,cfg=None,reason=None):
        path=write(root,name+'_intents.json',dict(schema_version=1,intents=rows or intents))
        conf=write(root,name+'_config.json',cfg or dict(manual_delay_ms=0))
        args=arguments.copy(); args[args.index('--intents')+1]=path; args[args.index('--config')+1]=conf
        result=execution(*args,expected=2); doc=execution('report',result['report_hash'])
        if any(e['fill'] is not None or reason not in e['reasons'] for e in doc['estimates']):
            raise AssertionError(name+' failed to reject without fabricating fills')
        return result
    rejected('manual_delay',cfg=dict(manual_delay_ms=30000),reason='delay_not_elapsed')
    off_step=deepcopy(intents)
    for i in off_step: i['quantity']='1.0004'
    rejected('off_step',rows=off_step,reason='quantity_off_step')
    passive=deepcopy(intents)
    for i in passive: i['order_type']='LIMIT'
    rejected('passive',rows=passive,reason='passive_execution_unsupported')
    expired=deepcopy(intents)
    for i in expired: i.update(detected_ms=ds['as_of_ms']-1,expires_ms=ds['as_of_ms'])
    rejected('expired',rows=expired,reason='intent_expired')
    # New quote revision must create a new dataset; the earlier report stays immutable.
    now=int(time.time()*1000); wide=dict(quote,E=now,T=now,u=2,b='99',a='101')
    wide_path=root/'wide_quote.jsonl'; wide_path.write_text(json.dumps(wide)+'\n'); data('import-ws',wide_path)
    revised=data('snapshot','--symbols','BTCUSDT','--kinds','candle,mark,quote','--start',iso(start),'--end',iso(end))
    no_features=deepcopy(intents)
    for i in no_features: i.pop('required_features'); i.pop('feature_timeframe')
    wide_intents=write(root,'wide_intents.json',dict(schema_version=1,intents=no_features))
    blocked=execution('run',revised['dataset_hash'],'--intents',wide_intents,'--fees',fees,'--config',config,expected=2)
    if any('spread_budget_exceeded' not in e['reasons'] or e['fill'] is not None for e in blocked['estimates']):
        raise AssertionError('Wide spread revision failed closed')
    if execution(*arguments)!=summary or execution('report',summary['report_hash'])!=report:
        raise AssertionError('New raw observations rewrote a pinned report')
    modeled=data('snapshot','--symbols','BTCUSDT','--kinds','candle','--start',iso(start),'--end',iso(end),'--mode','modeled','--delay-ms','0')
    coarse=deepcopy(no_features[:1]); coarse[0].update(detected_ms=closed-30000,expires_ms=closed+60000)
    coarse_file=write(root,'bar_intents.json',dict(schema_version=1,intents=coarse))
    bar_summary=execution('run',modeled['dataset_hash'],'--intents',coarse_file,'--fees',fees,'--config',ROOT/'configs/c07_modeled_bar.json','--as-of',iso(closed))
    bar_report=execution('report',bar_summary['report_hash']); e=bar_report['estimates'][0]
    if e['fill']['price']!='100.1' or e['costs']['execution_plus_fee_cost_usdt']!='0.15005':
        raise AssertionError('Explicit coarse bar golden scenario mismatch')
    if e['funding']['status']!='unsupported_modeled_coverage' or e['projected_execution_cost_with_next_funding_usdt'] is not None:
        raise AssertionError('Candle data invented a historical funding forecast')
    result=dict(passed=True,scenario='raw C01/C02 import -> actual C03 feature artifacts -> C06 context -> persisted C07 paper scenarios',
        execution=summary,modeled_bar=bar_summary,features=features,commands=len(commands),artifacts_directory=str(root),
        checks=['independent buy/sell fill and fee amounts','shortfall attribution','C03 prefix join','C06 funding signs','atomic write failure',
                'new-process checkpoint recovery','idempotent resume','manual action delay','off-grid quantity','unsupported passive order',
                'expiry','wide spread revision','immutable old dataset','explicit coarse bar model','no invented historical funding'],
        note='Synthetic prices/rules/exposure. Zero manual delay is explicit for the quote fixture; the default preset uses 30 seconds. No orders, account endpoints or notifications.')
    write(root,'e2e_report.json',result); write(root,'e2e_commands.json',commands); return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path); args=parser.parse_args()
    if args.output: result=run_e2e(args.output)
    else:
        with tempfile.TemporaryDirectory(prefix='tradee-c07-e2e-') as folder:
            result=run_e2e(folder); result['artifacts_directory']='temporary artifacts removed after successful check'
    print(json.dumps(result,indent=2))
