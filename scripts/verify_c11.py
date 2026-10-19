"""Actual CLI E2E: raw Binance-shaped data -> both C08 families -> C11.

Real receipt times, synthetic prices/rules, explicit empty fixture calendars.
No network, credentials, account endpoints, orders or notifications.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
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
    if any(root.glob('*.sqlite3')): raise ValueError('C11 E2E requires a fresh directory')
    commands=[]
    def invoke(*args,expected=0):
        p=subprocess.run([sys.executable,'-m','tradee','--db',str(root/'c01.sqlite3'),*map(str,args)],cwd=ROOT,capture_output=True,text=True,timeout=120)
        if p.returncode!=expected: raise AssertionError(f'CLI exit {p.returncode}, expected {expected}: {p.stderr or p.stdout}')
        doc=json.loads(p.stdout or p.stderr); commands.append(dict(args=list(map(str,args)),exit_code=p.returncode)); return doc
    def data(*args): return invoke('data','--market-db',root/'c02.sqlite3',*args)
    def simulate(*args,expected=0): return invoke('simulate','--market-db',root/'c02.sqlite3','--simulation-db',root/'c11.sqlite3',*args,expected=expected)
    raw=json.loads((ROOT/'tests/fixtures/exchange_info.json').read_text())
    for item in raw['symbols']:
        for f in item['filters']:
            if f['filterType']=='PRICE_FILTER': f.update(minPrice='1',maxPrice='1000000',tickSize='0.1')
            if f['filterType']=='MIN_NOTIONAL': f['notional']='5'
    invoke('import',write(root,'metadata.json',raw))
    remainder=int(time.time()*1000)%60000
    if remainder>58000: time.sleep((60000-remainder)/1000+0.01)
    closed=int(time.time()*1000)//60000*60000; start=closed-402*60000
    for symbol,short in (('BTCUSDT',False),('ETHUSDT',True)):
        closes=[Decimal('200')-Decimal(i)/10 if short else Decimal('100')+Decimal(i)/10 for i in range(400)]
        closes+=list(map(Decimal,('162','158') if short else ('138','142')))
        rows=[]
        for k,c in enumerate(closes):
            stamp=start+k*60000
            rows.append([stamp,str(c),str(c+1),str(c-1),str(c),'1000',stamp+59999,str(c*1000),5,'700',str(c*700),'0'])
        data('import-rest',symbol,write(root,symbol+'_candles.json',rows))
    def ws(name,prices,trigger=False):
        stamp=int(time.time()*1000); rows=[]
        for symbol,price in prices:
            p=Decimal(price)
            rows.append(dict(e='markPriceUpdate',E=stamp,s=symbol,p=price,i=price,r='0.001',T=stamp+3600000))
            if trigger: rows.append(dict(e='aggTrade',E=stamp,T=stamp,s=symbol,a=stamp,f=stamp,l=stamp,p=price,q='1',m=False))
            rows.append(dict(e='bookTicker',E=stamp,T=stamp,s=symbol,u=stamp,b=str(p-Decimal('0.1')),a=str(p+Decimal('0.1')),B='10',A='10'))
        path=root/name; path.write_text('\n'.join(json.dumps(r) for r in rows)+'\n'); data('import-ws',path)
    ws('entry.jsonl',[('BTCUSDT','142'),('ETHUSDT','158')])
    ws('exit.jsonl',[('BTCUSDT','146'),('ETHUSDT','153')],True)
    end=(int(time.time()*1000)//60000+2)*60000
    ds=data('snapshot','--symbols','BTCUSDT,ETHUSDT','--kinds','candle,mark,quote,trade,funding','--start',iso(start),'--end',iso(end))
    if ds['as_of_ms']-closed>=60000: raise AssertionError('Fixture crossed a minute boundary; rerun in a fresh directory')
    from tradee.c01 import Registry, Policy
    from tradee.c11 import SimulationStore
    registry=Registry(root/'c01.sqlite3'); universe=registry.universe(Policy(('BTCUSDT','ETHUSDT')))
    calendar=write(root,'calendar.json',dict(schema_version=1,calendars=[dict(instrument_id=d['instrument_id'],symbol=d['symbol'],
        start_ms=start,end_ms=end,settlement_times_ms=[],evidence='operator_assumption:synthetic short fixture has no settlements') for d in universe['decisions'] if d['symbol'] in ('BTCUSDT','ETHUSDT')]))
    scenarios=write(root,'scenarios.json',dict(schema_version=1,scenarios=[dict(name=name,strategy=dict(family=family,timeframe='1m',entry_window_ms=60000,**({'lookback_bars':2} if name=='range' else {})),
        policy=dict(trigger_source='contract_trade'),quantity='1',horizon='intraday') for name,family in (('range','prior_range_breakout'),('trend','ema_pullback_continuation'))]))
    execution=write(root,'execution.json',dict(manual_delay_ms=0,max_spread_bps='25'))
    config=write(root,'simulation.json',dict(decision_start_ms=closed,sample_interval_ms=100,max_samples=10000))
    args=['run',ds['dataset_hash'],'--scenarios',scenarios,'--fees',ROOT/'configs/c07_fee_assumptions.json','--execution',execution,'--calendar',calendar,'--config',config]
    store=SimulationStore(root/'c11.sqlite3')
    with store.connection() as db:
        db.execute("CREATE TRIGGER fail BEFORE INSERT ON reports BEGIN SELECT RAISE(ABORT,'C11 injected atomic publication failure'); END")
    failed=simulate(*args,expected=1)
    if 'injected atomic publication failure' not in failed.get('error',''): raise AssertionError('Publication failure was not surfaced')
    with store.connection() as db:
        if any(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in ('runs','reports','artifacts')): raise AssertionError('Interrupted run leaked partial published evidence')
        db.execute('DROP TRIGGER fail')
    summary=simulate(*args); report=simulate('report',summary['report_hash']); simulate('manifest',summary['run_hash'])
    got=sorted((t['scenario'],t['symbol'],t['side'],t['net_usdt']) for t in report['trades'])
    expected=sorted((family,symbol,side,net) for family in ('range','trend') for symbol,side,net in (('BTCUSDT','long','3.456'),('ETHUSDT','short','4.4445')))
    if got!=expected or not summary['ready'] or summary['metrics']['net_usdt']!='15.801': raise AssertionError(('Golden two-family simulation mismatch',got,summary['metrics']))
    if not report['attribution']['reconciled'] or any(len(t['state']['ledger'])!=2 or t['remaining_quantity']!='0' for t in report['trades']): raise AssertionError('Ledger/quantity reconciliation failed')
    revisions=simulate('records',summary['run_hash'],'--kind','outcome_revision','--limit','1000')
    if sum(p['payload']['outcome']['ready'] for p in revisions['records'])!=4: raise AssertionError('Causal mature revision inventory mismatch')
    simulate('artifact',revisions['records'][0]['artifact_hash'])
    if simulate(*args)!=summary: raise AssertionError('Idempotent rerun changed completed results')
    unknown_args=args.copy(); unknown_args.remove('--calendar'); unknown_args.remove(calendar)
    unknown=simulate(*unknown_args,expected=2)
    if unknown['metrics']['unresolved']!=4 or unknown['metrics']['net_usdt'] is not None: raise AssertionError('Unknown funding was invented')
    stress=write(root,'fee_stress.json',dict(taker_rate='0.001',maker_rate='0.0002',evidence='explicit synthetic fee sensitivity'))
    stress_args=args.copy(); stress_args[stress_args.index('--fees')+1]=stress
    expensive=simulate(*stress_args); comparison=simulate('compare',summary['run_hash'],expensive['run_hash'])
    if comparison['paired_mature_outcomes']!=4 or comparison['paired_mature_net_delta_usdt']!='-0.599': raise AssertionError(('Fee sensitivity mismatch',comparison))
    delayed_path=write(root,'delayed.json',dict(manual_delay_ms=30000,max_spread_bps='25'))
    delayed_args=args.copy(); delayed_args[delayed_args.index('--execution')+1]=delayed_path
    delayed=simulate(*delayed_args,expected=2)
    if delayed['metrics']['filled']!=0: raise AssertionError('Manual delay created a retroactive fill')
    # Later observations never alter an already pinned source/report.
    data('import-rest','BTCUSDT',write(root,'later_funding.json',[dict(symbol='BTCUSDT',fundingTime=closed,fundingRate='0.001',markPrice='142')]),'--kind','funding')
    if simulate(*args)!=summary: raise AssertionError('Later source import rewrote pinned simulation')
    result=dict(passed=True,scenario='Raw C01/C02 -> C03 stabilized features -> C08 range and trend -> C07/C06/C09 -> C11 ledgers and attribution',
        simulation=summary,comparison=comparison,unknown_funding=unknown,delayed_entry=delayed,commands=len(commands),artifacts_directory=str(root),
        checks=['both families and directions','stabilized real C03 EMA evidence','exact source activation','literal golden fill and net amounts','full candidate inventory',
            'atomic publication rollback','new-process deterministic retry','causal outcome revisions','regular marks','idempotence','fee sensitivity','unknown funding','manual delay','pinned vintage'],
        note='Engineering fixture, not historical profitability evidence. 1m/2-bar range, explicit synthetic rules, size 1, zero delay and 25bps spread gate; independent scenarios share no capital or liquidity. C12 walk-forward and C13 portfolios remain separate.')
    write(root,'e2e_report.json',result); write(root,'e2e_commands.json',commands); return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path); args=parser.parse_args()
    if args.output: result=run_e2e(args.output)
    else:
        with tempfile.TemporaryDirectory(prefix='tradee-c11-e2e-') as folder:
            result=run_e2e(folder); result['artifacts_directory']='temporary artifacts removed after verification'
    print(json.dumps(result,indent=2))
