"""Offline C01/C02/C03/C08 E2E for two independent 15m hypothesis families.

Synthetic BTC/ETH mirror paths exercise both directions. No internal mocks,
orders, fees/P&L inference, account access or notifications.
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

ROOT=Path(__file__).resolve().parents[1]
START=1788220800000
MINUTE=60000


def iso(stamp): return datetime.fromtimestamp(stamp/1000,timezone.utc).isoformat()


def write(root,name,doc):
    path=root/name; path.write_text(json.dumps(doc,indent=2)+'\n'); return str(path)


def run_e2e(root):
    root=Path(root).resolve(); root.mkdir(parents=True,exist_ok=True)
    if any(root.glob('*.sqlite3')): raise ValueError('E2E needs a fresh directory')
    commands=[]
    def invoke(*args,expected=0):
        result=subprocess.run([sys.executable,'-m','tradee','--db',str(root/'c01.sqlite3'),*map(str,args)],
            cwd=ROOT,capture_output=True,text=True,timeout=120)
        if result.returncode!=expected:
            raise AssertionError(f'CLI exit {result.returncode}, expected {expected}: {result.stderr or result.stdout}')
        doc=json.loads(result.stdout or result.stderr); commands.append(dict(args=list(map(str,args)),exit_code=result.returncode)); return doc
    def data(*args,expected=0): return invoke('data','--market-db',root/'c02.sqlite3',*args,expected=expected)
    def candidates(*args,expected=0): return invoke('candidates','--market-db',root/'c02.sqlite3','--candidate-db',root/'c08.sqlite3',*args,expected=expected)
    raw=json.loads((ROOT/'tests/fixtures/exchange_info.json').read_text())
    for symbol in raw['symbols']:
        for f in symbol['filters']:
            if f['filterType']=='PRICE_FILTER': f.update(minPrice='1',maxPrice='1000000',tickSize='0.1')
            if f['filterType']=='MIN_NOTIONAL': f['notional']='5'
    invoke('import',write(root,'synthetic_exchange_info.json',raw))
    closes=[Decimal(100)+Decimal(i)/10 for i in range(400)]+list(map(Decimal,('138','140','144','130')))
    rows={}
    for symbol in ('BTCUSDT','ETHUSDT'):
        prices=closes if symbol=='BTCUSDT' else [Decimal(300)-v for v in closes]
        candles=[]
        for n,close in enumerate(prices):
            for m in range(15):
                opened=START+(n*15+m)*MINUTE
                candles.append([opened,str(close),str(close+1),str(close-1),str(close),'1000',opened+59999,
                    str(close*1000),5,'700',str(close*700),'0'])
        rows[symbol]=candles; data('import-rest',symbol,write(root,symbol+'_candles.json',candles))
    end=START+404*15*MINUTE
    ds=data('snapshot','--symbols','BTCUSDT,ETHUSDT','--kinds','candle','--start',iso(START),'--end',iso(end),'--mode','modeled','--delay-ms','0')
    config=ROOT/'configs/c08_modeled_candidates.json'; range_spec=ROOT/'configs/c08_range_breakout.json'; trend_spec=ROOT/'configs/c08_trend_continuation.json'
    arguments=['run',ds['dataset_hash'],'--strategy',range_spec,'--config',config,'--batch-size','30']
    from tradee.c08 import CandidateStore
    store=CandidateStore(root/'c08.sqlite3')
    with store.connection() as db:
        db.execute("CREATE TRIGGER e2e_write_failure BEFORE INSERT ON evaluations WHEN (SELECT COUNT(*) FROM checkpoints)>0 BEGIN SELECT RAISE(ABORT,'E2E injected write failure'); END")
    fail=candidates(*arguments,expected=1)
    if 'E2E injected write failure' not in fail.get('error',''): raise AssertionError('Expected SQLite failure not surfaced')
    with store.connection() as db:
        if db.execute('SELECT COUNT(*) FROM evaluations').fetchone()[0]!=4 or db.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0]!=1:
            raise AssertionError('Failed batch did not preserve the first complete opportunity inventory')
        db.execute('DROP TRIGGER e2e_write_failure')
    # Preserve the small fault-injection prefix, then use normal batching for
    # replay; repeatedly serializing a full-history checkpoint is not the test.
    arguments[-1]='512'
    breakout=candidates(*arguments)
    if candidates(*arguments)!=breakout: raise AssertionError('Completed range replay duplicated outputs')
    range_records=candidates('records',breakout['run_hash'],'--status','emitted')['records']
    expected_range=[('BTCUSDT','long',402,'144'),('ETHUSDT','short',402,'156'),('BTCUSDT','short',403,'130'),('ETHUSDT','long',403,'170')]
    actual_range=[(r['symbol'],r['side'],(r['target_open_ms']-START)//(15*MINUTE),r['candidate']['reference_price']) for r in range_records]
    if actual_range!=expected_range: raise AssertionError(('Independent range trigger expectations mismatch',actual_range))
    trend_args=arguments.copy(); trend_args[trend_args.index('--strategy')+1]=trend_spec; trend_args[-1]='256'
    continuation=candidates(*trend_args)
    if candidates(*trend_args)!=continuation: raise AssertionError('Completed trend replay duplicated outputs')
    trend_records=candidates('records',continuation['run_hash'],'--status','emitted')['records']
    expected_trend=[('BTCUSDT','long',401,'140'),('ETHUSDT','short',401,'160')]
    actual_trend=[(r['symbol'],r['side'],(r['target_open_ms']-START)//(15*MINUTE),r['candidate']['reference_price']) for r in trend_records]
    if actual_trend!=expected_trend: raise AssertionError(('Independent trend recovery expectations mismatch',actual_trend))
    for summary in (breakout,continuation):
        if summary['evaluations']!=1616 or not summary['completed'] or any(c['missing_buckets'] for c in summary['coverage']):
            raise AssertionError('Full inventory/coverage mismatch')
    if breakout['run_hash']==continuation['run_hash']: raise AssertionError('Hypothesis families share a run identity')
    r=range_records[0]; feature=candidates('feature',r['feature_snapshot_hash'])
    if feature['target_open_ms']!=r['target_open_ms'] or feature['input_prefix_hash']!=r['input_prefix_hash']:
        raise AssertionError('Candidate was not joined to its actual C03 prefix')
    candidates('lineage',feature['lineage_hash']); candidates('evaluation',r['evaluation_hash']); candidates('manifest',breakout['run_hash'])
    page1=candidates('records',breakout['run_hash'],'--limit','3'); page2=candidates('records',breakout['run_hash'],'--limit','3','--after-sequence',page1['next_sequence'])
    if [r['sequence'] for r in page2['records']]!=[4,5,6]: raise AssertionError('Inventory pagination dropped opportunities')
    # Observed metadata imported today must not authorize these historical decisions.
    observed=candidates('run',ds['dataset_hash'],'--strategy',range_spec,'--config',ROOT/'configs/c08_candidates.json')
    if observed['emitted_candidates']!=0 or observed['reasons'].get('missing_instrument_rules',0)==0:
        raise AssertionError('Current metadata leaked into observed historical decisions')
    # Modeled datasets select the latest finalized source vintage. A correction
    # creates a different hypothetical history, never rewriting the old run.
    correction=deepcopy(rows['BTCUSDT'][-1]); correction[4]='131'
    data('import-rest','BTCUSDT',write(root,'correction.json',[correction]))
    revised=data('snapshot','--symbols','BTCUSDT,ETHUSDT','--kinds','candle','--start',iso(START),'--end',iso(end),'--mode','modeled','--delay-ms','0')
    new_args=arguments.copy(); new_args[1]=revised['dataset_hash']; new_args[-1]='256'
    corrected=candidates(*new_args)
    if corrected['status_counts']['revision_only']!=0 or corrected['emitted_candidates']!=4:
        raise AssertionError('Modeled latest-finalized source-vintage policy mismatch')
    corrected_records=candidates('records',corrected['run_hash'],'--status','emitted')['records']
    if next(r for r in corrected_records if r['symbol']=='BTCUSDT' and r['side']=='short')['candidate']['reference_price']!='131':
        raise AssertionError('New modeled vintage did not retain the corrected source price')
    recorded=data('snapshot','--symbols','BTCUSDT,ETHUSDT','--kinds','candle','--start',iso(START),'--end',iso(end))
    recorded_revision=candidates('run',recorded['dataset_hash'],'--strategy',range_spec,'--config',ROOT/'configs/c08_candidates.json')
    if recorded_revision['status_counts']['revision_only']!=2 or recorded_revision['emitted_candidates']!=0:
        raise AssertionError('Recorded correction invented a retroactive candidate')
    if candidates(*arguments)!=breakout or candidates('records',breakout['run_hash'],'--status','emitted')['records']!=range_records:
        raise AssertionError('New source vintage rewrote the original inventory')
    result=dict(passed=True,scenario='raw C01/C02 imports -> C03 indicators and exact range context -> two C08 15m inventories',
        range_breakout=breakout,trend_continuation=continuation,observed_historical=observed,corrected_range=corrected,recorded_revision=recorded_revision,
        commands=len(commands),expected_range=expected_range,expected_trend=expected_trend,artifacts_directory=str(root),
        checks=['two independent hypothesis families','15m aggregation','long/short exact target bars','full warmup/nontrigger/rejection inventory',
            'C03 prefix and lineage','atomic SQLite failure','new-process resume across nonmonotone modeled IDs','idempotent rerun',
            'pagination','observed metadata exclusion','explicit modeled assumptions','revision-only corrections','immutable prior candidates'],
        note='Synthetic prices/rules. Historical candle availability and metadata assumptions are explicit. No stops/targets, fills, P&L, strategy promotion or Telegram.')
    write(root,'e2e_report.json',result); write(root,'e2e_commands.json',commands); return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path); args=parser.parse_args()
    if args.output: result=run_e2e(args.output)
    else:
        with tempfile.TemporaryDirectory(prefix='tradee-c08-e2e-') as folder:
            result=run_e2e(folder); result['artifacts_directory']='temporary artifacts removed after successful check'
    print(json.dumps(result,indent=2))
