"""Offline C01/C02/C03/C06 E2E through actual CLI processes.

No mocks of internal components, network calls, credentials or real positions.
Retain a reviewable demo with --output data/c06_checks/demo1 (fresh directory).
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def iso(stamp):
    return datetime.fromtimestamp(stamp/1000,timezone.utc).isoformat()


def write(root, name, data):
    path=root/name
    path.write_text(json.dumps(data,indent=2)+'\n')
    return str(path)


def run_e2e(root):
    root=Path(root).resolve(); root.mkdir(parents=True,exist_ok=True)
    if any(root.glob('*.sqlite3')):
        raise ValueError('E2E requires a fresh directory to isolate the test')
    fixture=json.loads((ROOT/'tests/fixtures/c06/golden_scenario.json').read_text())
    start=fixture['start_ms']; hour=3600000; end=start+fixture['window_hours']*hour
    commands=[]
    def invoke(*args,expected=0):
        cmd=[sys.executable,'-m','tradee','--db',str(root/'c01.sqlite3'),*map(str,args)]
        result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=30)
        if result.returncode!=expected:
            raise AssertionError(f'CLI exit {result.returncode}, expected {expected}: {result.stderr or result.stdout}')
        doc=json.loads(result.stdout or result.stderr)
        commands.append(dict(args=list(map(str,args)),exit_code=result.returncode))
        return doc
    def data(*args,expected=0):
        return invoke('data','--market-db',root/'c02.sqlite3',*args,expected=expected)
    def funding(*args,expected=0):
        return invoke('funding','--market-db',root/'c02.sqlite3','--funding-db',root/'c06.sqlite3',*args,expected=expected)
    invoke('import',ROOT/'tests/fixtures/exchange_info.json')
    universe=invoke('--enabled','BTCUSDT','universe')
    identity=next(p['instrument_id'] for p in universe['decisions'] if p['symbol']=='BTCUSDT')
    candles=[[start+i*60000,'100','105','95',str(100+i%4),'10',start+i*60000+59999,'1000',5,'7','700','0'] for i in range(55)]
    data('import-rest','BTCUSDT',write(root,'candles.json',candles))
    candle_dataset=data('snapshot','--symbols','BTCUSDT','--kinds','candle','--start',iso(start),'--end',iso(end),
                        '--mode','modeled','--delay-ms',0)
    feature_config=write(root,'feature_config.json',dict(features=['log_return_1','vwap20','rsi14'],timeframes=['1m'],require_stable=False))
    features=invoke('features','--market-db',root/'c02.sqlite3','--feature-db',root/'c03.sqlite3',
                    'run',candle_dataset['dataset_hash'],'--config',feature_config)
    if features['snapshots']!=55 or features['ready_snapshots']!=36:
        raise AssertionError('C03 E2E readiness/coverage mismatch')
    latest=invoke('features','--feature-db',root/'c03.sqlite3','snapshot',features['latest'][0]['snapshot_hash'])
    if latest['values']['vwap20']['value']!=100 or not latest['ready']:
        raise AssertionError('C03 E2E numerical fixture mismatch')
    rows=[dict(symbol='BTCUSDT',fundingTime=start+s['offset_hours']*hour,
               fundingRate=s['rate'],markPrice=s['mark_price']) for s in fixture['settlements']]
    raw_file=write(root,'funding.json',rows)
    imported=data('import-rest','BTCUSDT',raw_file,'--kind','funding')
    duplicate=data('import-rest','BTCUSDT',raw_file,'--kind','funding')
    if imported['added']!=3 or duplicate['added']!=0 or duplicate['duplicates']!=3:
        raise AssertionError('C02 duplicate funding observations were not idempotent')
    mark=dict(e='markPriceUpdate',E=start+3*hour,s='BTCUSDT',p='100',i='99',r='0.99',T=start+4*hour)
    mark_file=root/'mark.jsonl'; mark_file.write_text(json.dumps(mark)+'\n'); data('import-ws',mark_file)
    pinned=data('snapshot','--symbols','BTCUSDT','--kinds','funding,mark','--start',iso(start),'--end',iso(end))
    positions=[dict(position_id='long',instrument_id=identity,symbol='BTCUSDT',side='long',changes=[
        dict(at_ms=start+60000,quantity='2'),dict(at_ms=start+2*hour-60000,quantity='1'),dict(at_ms=start+4*hour-60000,quantity='0')]),
        dict(position_id='short',instrument_id=identity,symbol='BTCUSDT',side='short',changes=[dict(at_ms=start+60000,quantity='3')])]
    positions_file=write(root,'positions.json',dict(schema_version=1,positions=positions))
    calendars=[dict(instrument_id=identity,symbol='BTCUSDT',start_ms=start,end_ms=end,
        settlement_times_ms=[r['fundingTime'] for r in rows],evidence='operator_assumption:synthetic-E2E-only')]
    calendar_file=write(root,'calendar.json',dict(schema_version=1,calendars=calendars))
    arguments=['run',pinned['dataset_hash'],'--positions',positions_file,'--calendar',calendar_file,'--batch-size','1']
    # Inject a real SQLite failure after the first batch commits. The next CLI
    # process must recover from that persisted prefix, not restart with empty state.
    from tradee.c06 import FundingStore
    fault_store=FundingStore(root/'c06.sqlite3')
    with fault_store.connection() as db:
        db.execute("CREATE TRIGGER e2e_write_failure BEFORE INSERT ON reports WHEN (SELECT COUNT(*) FROM reports WHERE run_hash=NEW.run_hash)=1 BEGIN SELECT RAISE(ABORT,'E2E injected write failure'); END")
    failure=funding(*arguments,expected=1)
    if 'E2E injected write failure' not in failure.get('error',''):
        raise AssertionError('Expected injected SQLite write failure was not surfaced')
    with fault_store.connection() as db:
        if db.execute('SELECT COUNT(*) FROM reports').fetchone()[0]!=1 or db.execute('SELECT COUNT(*) FROM checkpoints').fetchone()[0]!=1:
            raise AssertionError('Failed CLI batch did not preserve the first atomic checkpoint')
        db.execute('DROP TRIGGER e2e_write_failure')
    summary=funding(*arguments); report=funding('report',summary['report_hash'])
    totals=[p['total_cashflow_usdt'] for p in report['positions']]
    if totals!=fixture['expected_totals_usdt'] or not summary['ready']:
        raise AssertionError('C06 hand-calculated funding totals mismatch')
    if report['positions'][1]['estimate']['status']!='stale_estimate':
        raise AssertionError('Recorded old mark must not be mistaken for a fresh forecast')
    if funding(*arguments)!=summary:
        raise AssertionError('C06 CLI resume duplicated outputs')
    unknown=funding('run',pinned['dataset_hash'],'--positions',positions_file,expected=2)
    unknown_report=funding('report',unknown['report_hash'])
    if any(p['total_cashflow_usdt'] is not None for p in unknown_report['positions']):
        raise AssertionError('Unknown settlement coverage must leave totals unresolved')
    missing=deepcopy(calendars); missing[0]['settlement_times_ms'].insert(2,start+3*hour)
    missing_file=write(root,'missing_calendar.json',dict(schema_version=1,calendars=missing))
    unresolved=funding('run',pinned['dataset_hash'],'--positions',positions_file,'--calendar',missing_file,expected=2)
    missing_report=funding('report',unresolved['report_hash'])
    if missing_report['positions'][1]['cashflows'][2]['status']!='missing_settlement':
        raise AssertionError('Missing expected funding must not become a zero charge')
    boundary=deepcopy(positions[:1]); boundary[0]['changes']=[dict(at_ms=start+hour+5000,quantity='2')]
    boundary_file=write(root,'boundary_positions.json',dict(schema_version=1,positions=boundary))
    ambiguous=funding('run',pinned['dataset_hash'],'--positions',boundary_file,'--calendar',calendar_file,expected=2)
    ambiguous_report=funding('report',ambiguous['report_hash'])
    if ambiguous_report['positions'][0]['cashflows'][0]['status']!='boundary_ambiguous':
        raise AssertionError('Settlement-adjacent entry must be explicitly ambiguous')
    correction=dict(rows[0],fundingRate='0.0015')
    data('import-rest','BTCUSDT',write(root,'correction.json',[correction]),'--kind','funding')
    revised=data('snapshot','--symbols','BTCUSDT','--kinds','funding,mark','--start',iso(start),'--end',iso(end))
    revised_arguments=arguments.copy(); revised_arguments[1]=revised['dataset_hash']
    updated=funding(*revised_arguments); updated_report=funding('report',updated['report_hash'])
    if [p['total_cashflow_usdt'] for p in updated_report['positions']]!=fixture['corrected_totals_usdt']:
        raise AssertionError('Settlement correction must reconcile rather than double-book the charge')
    if funding(*arguments)!=summary or funding('report',summary['report_hash'])!=report:
        raise AssertionError('Later settlement correction rewrote pinned historical results')
    result=dict(passed=True,scenario='offline raw import to persisted C01/C02/C03/C06 outputs',
        features=features,funding=summary,corrected_funding=updated,commands=len(commands),
        checks=['golden funding totals','feature values/readiness','duplicate input','partial checkpoint write failure','CLI resume','idempotent resume',
                'unknown calendar','missing settlement','boundary ambiguity','correction','immutable old dataset'],
        artifacts_directory=str(root),note='Synthetic paper-exposure scenarios; no orders, strategy P&L, live network or Telegram.')
    write(root,'e2e_report.json',result); write(root,'e2e_commands.json',commands)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.output:
        result=run_e2e(args.output)
    else:
        with tempfile.TemporaryDirectory(prefix='tradee-c06-e2e-') as folder:
            result=run_e2e(folder); result['artifacts_directory']='temporary artifacts removed after successful check'
    print(json.dumps(result,indent=2))
