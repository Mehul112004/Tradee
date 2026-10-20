"""Offline raw-input funded portfolio E2E, with explicit synthetic assumptions.

Uses production ingestion, strategy, fills, funding ledgers, estimation, C12
holdout control, C13 shared equity and persistent reservation CLI. No mocks,
network credentials, Telegram, live orders or portfolio-promotion claim.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
from tradee.c01 import Registry,Policy
from tradee.c01.domain import fingerprint
from tradee.c02 import MarketStore
from tradee.c10 import EstimatorConfig
from tradee.c11 import SimulationStore
from tradee.c12 import EvidencePolicy
from tradee.c13 import PortfolioStore,RiskPolicy,ReplayConfig
from tradee.c13.source import load
from tradee.c10 import EstimateRequest
from tradee.c13 import Offer,AccountSnapshot

ROOT=Path(__file__).resolve().parents[1]
START=1788220800000
BIN=240000


def write(root,name,doc):
    p=root/name; p.write_text(json.dumps(doc,indent=2)+'\n'); return str(p)


def run_e2e(output):
    root=Path(output).resolve(); root.mkdir(parents=True,exist_ok=True)
    if any(root.glob('*.sqlite3')): raise ValueError('C13 E2E requires a fresh directory')
    commands=[]; clock=[START]; symbols=['BTCUSDT','ETHUSDT']
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
        commands.append(dict(args=list(map(str,args)),exit_code=p.returncode))
        write(root,'e2e_commands.json',commands)
        if p.returncode!=expected: raise AssertionError(f'Exit {p.returncode}, expected {expected}: {(p.stderr or p.stdout)[:3000]}')
        return json.loads(p.stdout or p.stderr)
    def research(*args,expected=0): return invoke('research','--simulation-db',root/'c11.sqlite3','--research-db',root/'c12.sqlite3',*args,expected=expected)
    def portfolio(*args,expected=0):
        return invoke('portfolio','--market-db',root/'c02.sqlite3','--simulation-db',root/'c11.sqlite3','--estimator-db',root/'c10.sqlite3','--portfolio-db',root/'c13.sqlite3',*args,expected=expected)
    def capture(name,start,n):
        clock[0]=start; registry.ingest(json.dumps(raw),source='synthetic:C13 receipt metadata'); receipts=[]
        for k in range(n):
            for j,price in enumerate(('100','100','102','100')):
                opened=start+(4*k+j)*60000; c=Decimal(price); clock[0]=opened+60000
                row=[opened,price,str(c+1),str(c-1),price,'1000',opened+59999,str(c*1000),5,'700',str(c*700),'0']
                for symbol in symbols:
                    market.ingest_rest(json.dumps([row]),symbol); receipts.append(dict(received_ms=clock[0],symbol=symbol,kind='candle',raw=row))
                if j!=2: continue
                detected=clock[0]; close='105' if k%2==0 else '106'
                for stamp,price,trigger in ((detected+1000,'102',False),(detected+40000,close,True)):
                    clock[0]=stamp; p=Decimal(price)
                    for symbol in symbols:
                        messages=[dict(e='markPriceUpdate',E=stamp,s=symbol,p=price,i=price,r='0.001',T=stamp+3600000)]
                        if trigger: messages.append(dict(e='aggTrade',E=stamp,T=stamp,s=symbol,a=stamp,f=stamp,l=stamp,p=price,q='1',m=False))
                        messages.append(dict(e='bookTicker',E=stamp,T=stamp,s=symbol,u=stamp,b=str(p-Decimal('0.1')),a=str(p+Decimal('0.1')),B='10',A='10'))
                        for message in messages: market.ingest_ws(json.dumps(message)); receipts.append(dict(received_ms=stamp,kind=message['e'],raw=message))
        end=start+n*BIN; clock[0]=end; ds=market.snapshot(symbols,start,end,kinds=('candle','quote','mark','trade','funding'))
        universe=registry.universe(Policy(tuple(symbols)))
        cal=write(root,name+'_calendar.json',dict(schema_version=1,calendars=[dict(instrument_id=x['instrument_id'],symbol=x['symbol'],start_ms=start,end_ms=end,settlement_times_ms=[],evidence='operator_assumption:synthetic no-settlement window') for x in universe['decisions'] if x['symbol'] in symbols]))
        (root/(name+'_receipts.jsonl')).write_text('\n'.join(json.dumps(r) for r in receipts)+'\n')
        return ds,cal
    scenarios=[dict(name='range1',strategy=dict(timeframe='1m',lookback_bars=2,entry_window_ms=60000,sides=['long']),policy=dict(max_holding_ms=60000),quantity='1',horizon='intraday')]
    single=write(root,'single_scenario.json',dict(schema_version=1,scenarios=scenarios))
    half={**scenarios[0],'name':'rangehalf','quantity':'0.5'}
    swing={**scenarios[0],'name':'swing','policy':dict(max_holding_ms=120000),'horizon':'swing'}
    ladder=write(root,'size_scenarios.json',dict(schema_version=1,scenarios=[*scenarios,half,swing]))
    execution=write(root,'execution.json',dict(enabled_symbols=symbols,manual_delay_ms=0,max_spread_bps='25',max_metadata_age_ms=86400000))
    simconfig=write(root,'simulation.json',dict(sample_interval_ms=BIN))
    fees=write(root,'fees.json',dict(taker_rate='0.0005',maker_rate='0.0002',evidence='synthetic assumed fees'))
    def simulate(ds,cal,scenarios):
        return invoke('simulate','--market-db',root/'c02.sqlite3','--simulation-db',root/'c11.sqlite3','run',ds['dataset_hash'],'--scenarios',scenarios,'--execution',execution,'--fees',fees,'--calendar',cal,'--config',simconfig)
    training,cal=capture('development',START,12); dev=simulate(training,cal,single); multi_dev=simulate(training,cal,ladder)
    held,cal=capture('holdout',START+13*BIN,3); hold=simulate(held,cal,single); multi_hold=simulate(held,cal,ladder)
    risk=RiskPolicy(per_trade_risk_fraction='0.01'); cfg=ReplayConfig(initial_cash_usdt='320')
    policyfile=write(root,'risk_policy.json',risk.document()); configfile=write(root,'portfolio_config.json',cfg.document())
    recipe=fingerprint(dict(policy=risk.document(),config=cfg.document()))
    estcfg=EstimatorConfig(min_trades=6,min_occupied_bins=6,min_occupied_spans=6,bin_ms=BIN,block_bins=1,bootstrap_replicates=200)
    def split(name,n,a,b):
        return dict(name=name,train=dict(start_ms=START,end_ms=START+n*BIN,cutoff_ms=START+n*BIN),test=dict(start_ms=START+a*BIN,end_ms=START+b*BIN,cutoff_ms=START+b*BIN+1))
    plan=dict(name='funded_engineering',family='funded_engineering',thesis='One predeclared shared-capital recipe compatibility check',prior_research='All mechanically generated data is synthetic engineering data; real inspected/TBot data remains development',historical_trials=0,family_trial_budget=2,
        variants=[dict(name='range1',hypothesis='Fixed long breakout baseline',development_runs=[dev['run_hash']],holdout_runs=[hold['run_hash']],estimator=estcfg.document(),rationale='Single fixed recipe, no tuning',parameters={})],
        folds=[dict(split=split('outer1',6,6,9),inner=[]),dict(split=split('outer2',9,9,12),inner=[])],holdout=dict(split=split('holdout',12,13,16),inner=[]),
        holdout_status='uninspected',holdout_attestation='Synthetic mechanically generated prices; explicitly opened before portfolio evidence inspection',
        source_report_hashes={d['run_hash']:d['report_hash'] for d in (dev,hold)},portfolio_recipe_hashes=[recipe],
        policy=EvidencePolicy(bin_ms=BIN,block_bins=1,bootstrap_replicates=200,min_candidates=6,min_eligible_mature=6,min_occupied_spans=3,require_stress=False,require_neighbors=False).document())
    h=research('register','--manifest',write(root,'experiment.json',plan))['experiment_hash']
    PortfolioStore(root/'c13.sqlite3')
    premature=research('check-portfolio',h,'--portfolio-db',root/'c13.sqlite3','--run','0'*64,expected=1)
    if 'holdout access' not in premature.get('error',''): raise AssertionError('Sealed portfolio boundary was not checked first')
    development=research('run',h); research('open-holdout',h,'--reason','Explicit synthetic funded E2E access')
    release=research('release',h); releasefile=write(root,'release_model.json',release['model'])
    pins=write(root,'single_sources.json',{hold['run_hash']:hold['report_hash']}); multi_pins=write(root,'size_sources.json',{multi_hold['run_hash']:multi_hold['report_hash']})
    portfolio('explain')
    s=PortfolioStore(root/'c13.sqlite3')
    with s.connection() as db: db.execute("CREATE TRIGGER fail BEFORE INSERT ON replay_events BEGIN SELECT RAISE(ABORT,'C13 injected publication failure'); END")
    args=('replay','--sources',pins,'--model-files',releasefile,'--policy',policyfile,'--config',configfile)
    portfolio(*args,expected=1)
    with s.connection() as db:
        if db.execute('SELECT COUNT(*) FROM artifacts').fetchone()[0] or db.execute('SELECT COUNT(*) FROM replays').fetchone()[0]: raise AssertionError('Failed C13 publication left partial artifacts')
        db.execute('DROP TRIGGER fail')
    baseline=portfolio(*args)
    if portfolio(*args)!=baseline: raise AssertionError('Funded replay retry changed')
    receipt=research('check-portfolio',h,'--portfolio-db',root/'c13.sqlite3','--run',baseline['run_hash'])
    if not receipt['ready'] or receipt['promotion_authorized']: raise AssertionError('Compatibility receipt crossed promotion boundary')
    if research('check-portfolio',h,'--portfolio-db',root/'c13.sqlite3','--run',baseline['run_hash'])!=receipt: raise AssertionError('Compatibility retry changed')
    # A cached compatibility receipt must still audit its funded source bytes.
    with s.connection() as db:
        stored=db.execute('SELECT document FROM artifacts WHERE hash=?',(baseline['report_hash'],)).fetchone()[0]
        db.execute("UPDATE artifacts SET document='{}' WHERE hash=?",(baseline['report_hash'],))
    research('check-portfolio',h,'--portfolio-db',root/'c13.sqlite3','--run',baseline['run_hash'],expected=1)
    with s.connection() as db: db.execute('UPDATE artifacts SET document=? WHERE hash=?',(stored,baseline['report_hash']))
    ec=write(root,'estimator.json',estcfg.document()); window=write(root,'training_window.json',dict(start_ms=START,end_ms=START+12*BIN,cutoff_ms=START+12*BIN+1))
    fit=invoke('expectancy','--simulation-db',root/'c11.sqlite3','--estimator-db',root/'c10.sqlite3','fit','--runs',multi_dev['run_hash'],'--window',window,'--config',ec,'--modeled-available-ms',START+12*BIN+1)
    multi=portfolio('replay','--sources',multi_pins,'--models',fit['model_hash'],'--policy',policyfile,'--config',configfile)
    if baseline['metrics']['net_pnl_usdt']!='8.489' or multi['metrics']['net_pnl_usdt']!='12.7335' or multi['coverage']['admitted_positions']!=6: raise AssertionError('Funded cash/size golden mismatch')
    # Same source/model but unregistered initial capital is a different experiment recipe.
    other=write(root,'other_capital.json',dict(cfg.document(),initial_cash_usdt='321'))
    altered=portfolio('replay','--sources',pins,'--model-files',releasefile,'--policy',policyfile,'--config',other)
    research('check-portfolio',h,'--portfolio-db',root/'c13.sqlite3','--run',altered['run_hash'],expected=1)
    report=portfolio('report',multi['report_hash']); portfolio('manifest',multi['run_hash']); portfolio('records',multi['run_hash']); portfolio('artifact',multi['report_hash']); portfolio('summary',multi['run_hash'])
    from tradee.c10 import EstimatorStore
    model=EstimatorStore(root/'c10.sqlite3').model(fit['model_hash']); ss=SimulationStore(root/'c11.sqlite3'); data=load(ss,{multi_hold['run_hash']:multi_hold['report_hash']}); stamp=min(data['entries']); offers=[]
    for key,_ in data['entries'][stamp]:
        d=data['candidates'][key]; m=d['manifest']; q=EstimateRequest(d['candidate'],d['feature'],d['scenario'],m['execution'],m['fees'],m['funding'],m['candidates'],stamp)
        offers.append(Offer(q.document(),model))
    marks=[dict(instrument_id=e['instrument_id'],symbol=e['symbol'],price=e['data']['mark_price'],event_ms=e['event_ms'],available_ms=e['available_ms'],event_id=e['id']) for e in market.replay(held['dataset_hash']) if e['kind']=='mark' and e['available_ms']==stamp]
    state=AccountSnapshot(stamp,stamp,'320','320',marks=marks); snapshotfile=write(root,'account_snapshot.json',state.document()); offersfile=write(root,'offers.json',[o.document() for o in offers])
    account=portfolio('account-create','paper','--snapshot',snapshotfile)
    aa=('allocate','paper','--expected',account['snapshot_hash'],'--offers',offersfile,'--dataset',held['dataset_hash'],'--at-ms',stamp,'--policy',policyfile)
    allocation=portfolio(*aa)
    if portfolio(*aa)!=allocation: raise AssertionError('Reservation retry changed')
    current=portfolio('account','paper')
    if current['snapshot']['cash_usdt']!='320' or len(current['snapshot']['reservations'])!=2 or current['revision']!=1: raise AssertionError('Reservations spent cash or double reserved')
    portfolio('account-update','paper','--expected',account['snapshot_hash'],'--snapshot',snapshotfile,expected=1)
    portfolio('account-update','paper','--expected',current['snapshot_hash'],'--snapshot',snapshotfile)
    ledger=research('ledger',plan['family'])
    if ledger['used_trials']!=2: raise AssertionError('Portfolio recipe trial was not counted')
    result=dict(passed=True,commands=len(commands),experiment_hash=h,baseline=baseline,portfolio=multi,compatibility=receipt,allocation_hash=allocation['allocation_hash'],checks=[
        'Raw C01/C02 recorded receipts for BTC and ETH','Production features, breakout, C07 fills, C06 funding, C09 ledgers and C11 revisions',
        'Two earlier outer folds and frozen exact-size C10 models','C12 logged holdout access and counted predeclared capital recipe','Shared finite capital and same-time multiasset batch',
        'Tested quantity ladder and intraday/swing duplicate suppression','Exact fee/cash reconciliation and regular equity grid','Atomic failed publication rollback and deterministic retry',
        'C12 compatibility-only receipt and rejection of undeclared capital','Persistent account CAS, reservation idempotence and explicit reconciliation'],
        note='Synthetic engineering verification, not real profitability evidence. 1m/two-bar long breakout, sizes 1 and 0.5, 320 USDT, no delay, assumed fees and explicitly empty settlement calendars. Six-span C10 / three-span C12 gates, 200 bootstrap draws; C12 neighborhood and fee-stress gates explicitly disabled for this fixture. No nested portfolio-policy inference, margin liquidation, live execution or Telegram.')
    write(root,'funded_report.json',report); write(root,'e2e_report.json',result); return result


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); a=p.parse_args(); r=run_e2e(a.output)
    print(json.dumps({k:r[k] for k in ('passed','commands','experiment_hash','portfolio','compatibility','note')},indent=2))
