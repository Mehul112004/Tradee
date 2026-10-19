"""Actual CLI E2E: raw two-symbol data -> C08 setups -> C07/C06/C09 ledger.

Synthetic prices/rules, real receipt times, explicit empty settlement calendar for
this short fixture. No network, account endpoints, real orders or notifications.
"""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
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
    p=root/name; p.write_text(json.dumps(doc,indent=2)+'\n'); return str(p)


def run_e2e(root):
    root=Path(root).resolve(); root.mkdir(parents=True,exist_ok=True)
    if any(root.glob('*.sqlite3')): raise ValueError('E2E requires a fresh directory')
    commands=[]
    def invoke(*args,expected=0):
        p=subprocess.run([sys.executable,'-m','tradee','--db',str(root/'c01.sqlite3'),*map(str,args)],cwd=ROOT,capture_output=True,text=True,timeout=60)
        if p.returncode!=expected: raise AssertionError(f'CLI exit {p.returncode}, expected {expected}: {p.stderr or p.stdout}')
        d=json.loads(p.stdout or p.stderr); commands.append(dict(args=list(map(str,args)),exit_code=p.returncode)); return d
    def data(*args): return invoke('data','--market-db',root/'c02.sqlite3',*args)
    def candidates(*args): return invoke('candidates','--market-db',root/'c02.sqlite3','--candidate-db',root/'c08.sqlite3',*args)
    def lifecycle(*args,expected=0): return invoke('lifecycle','--market-db',root/'c02.sqlite3','--lifecycle-db',root/'c09.sqlite3',*args,expected=expected)
    raw=json.loads((ROOT/'tests/fixtures/exchange_info.json').read_text())
    for spec in raw['symbols']:
        for f in spec['filters']:
            if f['filterType']=='PRICE_FILTER': f.update(minPrice='1',maxPrice='1000000',tickSize='0.1')
            if f['filterType']=='MIN_NOTIONAL': f['notional']='5'
    invoke('import',write(root,'synthetic_metadata.json',raw))
    closed=int(time.time()*1000)//60000*60000; start=closed-3*60000
    for symbol,price in (('BTCUSDT','102'),('ETHUSDT','98')):
        rows=[]
        for k in range(3):
            c=Decimal(price if k==2 else '100'); stamp=start+k*60000
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
        return stamp
    entry=ws('entry.jsonl',[('BTCUSDT','102'),('ETHUSDT','98')])
    exit_stamp=ws('exit.jsonl',[('BTCUSDT','105'),('ETHUSDT','95')],True)
    end=(int(time.time()*1000)//60000+2)*60000
    ds=data('snapshot','--symbols','BTCUSDT,ETHUSDT','--kinds','candle,mark,quote,trade,funding','--start',iso(start),'--end',iso(end))
    strategy=write(root,'strategy.json',dict(timeframe='1m',lookback_bars=2,entry_window_ms=60000))
    candidate_run=candidates('run',ds['dataset_hash'],'--strategy',strategy)
    records=candidates('records',candidate_run['run_hash'],'--status','emitted')['records']
    if [(r['symbol'],r['side']) for r in records]!=[('BTCUSDT','long'),('ETHUSDT','short')]:
        raise AssertionError('Raw recorded fixture did not produce independent expected C08 directions')
    policy=json.loads((ROOT/'configs/c09_trade_policy.json').read_text())
    intents=[dict(candidate=r['candidate'],feature_snapshot=candidates('feature',r['feature_snapshot_hash']),quantity='1',policy=policy) for r in records]
    intent_file=write(root,'intents.json',dict(schema_version=1,intents=intents))
    execution=write(root,'execution.json',dict(manual_delay_ms=0,max_spread_bps='25'))
    fees=ROOT/'configs/c07_fee_assumptions.json'
    calendar_file=write(root,'calendar.json',dict(schema_version=1,calendars=[dict(instrument_id=r['instrument_id'],symbol=r['symbol'],
        start_ms=start,end_ms=end,settlement_times_ms=[],evidence='operator_assumption:synthetic short E2E window has no settlements') for r in records]))
    args=['run',ds['dataset_hash'],'--intents',intent_file,'--fees',fees,'--execution',execution,'--calendar',calendar_file,'--batch-size','1']
    from tradee.c09 import LifecycleStore
    store=LifecycleStore(root/'c09.sqlite3')
    with store.connection() as db:
        db.execute("CREATE TRIGGER e2e_failure BEFORE INSERT ON reports WHEN (SELECT COUNT(*) FROM reports WHERE run_hash=NEW.run_hash)=1 BEGIN SELECT RAISE(ABORT,'E2E injected write failure'); END")
    failed=lifecycle(*args,expected=1)
    if 'E2E injected write failure' not in failed.get('error',''): raise AssertionError('Injected lifecycle failure did not surface')
    with store.connection() as db:
        if db.execute('SELECT COUNT(*) FROM reports').fetchone()[0]!=1 or db.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0]!=1:
            raise AssertionError('First atomic lifecycle checkpoint did not survive failure')
        db.execute('DROP TRIGGER e2e_failure')
    summary=lifecycle(*args); report=lifecycle('report',summary['report_hash'])
    expected=[('2.6','0.1035','2.4965'),('2.6','0.0965','2.5035')]
    got=[(t['gross_realized_usdt'],t['fees_usdt'],t['net_usdt']) for t in report['trades']]
    if got!=expected or not summary['ready']: raise AssertionError(('Independent golden trade-ledger amounts mismatch',got))
    if any(len(t['state']['ledger'])!=2 or t['remaining_quantity']!='0' or not t['target_before_stop'] for t in report['trades']):
        raise AssertionError('Trade quantity/ledger/trigger labels mismatch')
    if lifecycle(*args)!=summary: raise AssertionError('Repeated lifecycle resume duplicated fills/fees')
    lifecycle('manifest',summary['run_hash'])
    unknown_args=args.copy(); unknown_args.remove('--calendar'); unknown_args.remove(calendar_file)
    unknown=lifecycle(*unknown_args,expected=2); unknown_report=lifecycle('report',unknown['report_hash'])
    if any(t['net_usdt'] is not None or t['profitable'] is not None for t in unknown_report['trades']):
        raise AssertionError('Uncertified funding coverage invented net trade labels')
    delayed_file=write(root,'delayed_execution.json',dict(manual_delay_ms=30000,max_spread_bps='25'))
    delayed_args=args.copy(); delayed_args[delayed_args.index('--execution')+1]=delayed_file
    delayed=lifecycle(*delayed_args,expected=2); delayed_report=lifecycle('report',delayed['report_hash'])
    if any(t['state']['entry_price'] is not None for t in delayed_report['trades']): raise AssertionError('Default manual delay fabricated an early fill')
    # Public settlement data imported later has a new availability/vintage. Its
    # economic timestamp lies inside exposure, so the new run must revise net,
    # not fill prices or the original immutable report.
    settlement=(entry+exit_stamp)//2
    data('import-rest','BTCUSDT',write(root,'late_funding.json',[dict(symbol='BTCUSDT',fundingTime=settlement,fundingRate='0.001',markPrice='102')]),'--kind','funding')
    if lifecycle(*args)!=summary or lifecycle('report',summary['report_hash'])!=report:
        raise AssertionError('Later source data rewrote pinned fill/funding evidence')
    result=dict(passed=True,scenario='raw C01/C02 -> actual C03/C08 setups -> C07 fills -> C06 coverage -> C09 net outcomes',
        lifecycle=summary,unknown_funding=unknown,delayed_entry=delayed,candidates=candidate_run,commands=len(commands),artifacts_directory=str(root),
        checks=['recorded candidate source-prefix join','long and short fills','exact gross/fees/net','one-time ledger and flat quantities',
            'target event versus net-positive labels','atomic SQL failure','new-process recovery','idempotent rerun',
            'unknown funding remains null','manual delay','immutable old vintage'],
        note='Synthetic paper quantities/prices/rules; zero manual delay and 25bps spread gate are explicit fixture overrides. Empty funding schedule is a named assumption. No account/orders/Telegram; full strategy simulation and walk-forward remain C11/C12.')
    write(root,'e2e_report.json',result); write(root,'e2e_commands.json',commands); return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path); args=parser.parse_args()
    if args.output: result=run_e2e(args.output)
    else:
        with tempfile.TemporaryDirectory(prefix='tradee-c09-e2e-') as folder:
            result=run_e2e(folder); result['artifacts_directory']='temporary artifacts removed after successful check'
    print(json.dumps(result,indent=2))
