"""Actual multi-quantity C11/C10 inputs for shared-risk tests."""
from copy import deepcopy
from pathlib import Path
from tradee.c01.domain import fingerprint,normalize
from tradee.c06 import SettlementCalendar,FundingConfig
from tradee.c07 import ExecutionConfig,FeeSchedule,ExecutionEngine
from tradee.c08 import CandidateConfig
from tradee.c09 import TradePolicy
from tradee.c11 import Simulator,SimulationStore,Scenario,SimulationConfig
from tradee.c10 import snapshot,fit,publish,TrainingWindow,EstimateRequest
from tradee.c13 import PortfolioReplay,ReplayConfig,RiskPolicy,AccountSnapshot,Offer
from tradee.c13.source import load
from tests.c10_support import simulation,START,BIN,config
from tests.c08_support import spec


def make_source(n=12,start=START,positive=True,unknown=False,ladder=True,two_assets=True):
    base,events=simulation(n=n,start=start,positive=positive,unknown_funding=unknown); m=base.manifest.document()
    if two_assets:
        from tests.c07_support import metadata
        raw,_,_=metadata()
        for s in raw['symbols']:
            for f in s['filters']:
                if f['filterType']=='PRICE_FILTER': f.update(minPrice='1',maxPrice='1000000',tickSize='0.1')
                if f['filterType']=='MIN_NOTIONAL': f['notional']='5'
        specs=[s for s in normalize(raw) if s['symbol'] in ('BTCUSDT','ETHUSDT')]; versions={fingerprint(s):s for s in specs}
        universe=dict(schema_version=1,as_of_ms=START,policy={'enabled':['BTCUSDT','ETHUSDT']},decisions=[dict(symbol=s['symbol'],state='eligible',reasons=[],instrument_id=s['instrument_id'],version_hash=fingerprint(s),last_observed_ms=START) for s in specs])
        universe['snapshot_hash']=fingerprint(universe)
        pairs=[]
        for event in events:
            for s in specs:
                e=deepcopy(event); e['symbol']=s['symbol']; e['instrument_id']=s['instrument_id']; e['metadata_version']=fingerprint(s)
                pairs.append(e)
        pairs.sort(key=lambda e:(e['available_ms'],e['id'],e['symbol']))
        for idx,e in enumerate(pairs,1):
            e['id']=idx
            if e['kind'] in ('quote','trade'): e['key']=str(idx)
        events=pairs; m['metadata_snapshots']=[universe]; m['metadata_versions']=versions
        m['dataset'].update(symbols=['BTCUSDT','ETHUSDT'],event_count=len(events),dataset_hash=m['dataset']['dataset_hash']+'-both')
        m['calendars']=[] if unknown else [SettlementCalendar(s['instrument_id'],s['symbol'],start,start+n*BIN,[],'operator_assumption:synthetic empty settlement schedule').document() for s in specs]
    scenarios=[Scenario('range1',spec(sides=('long',)).document(),TradePolicy(max_holding_ms=60000).document(),'1')]
    if ladder:
        scenarios.extend([Scenario('rangehalf',spec(sides=('long',)).document(),TradePolicy(max_holding_ms=60000).document(),'0.5'),
            Scenario('swing',spec(sides=('long',)).document(),TradePolicy(max_holding_ms=120000).document(),'1','swing')])
    simulator=Simulator(m['dataset'],scenarios,m['metadata_snapshots'],m['metadata_versions'],FeeSchedule.from_dict(m['fees']),ExecutionConfig.from_dict(m['execution']),
        CandidateConfig.from_dict(m['candidates']),FundingConfig.from_dict(m['funding']),m['calendars'],SimulationConfig())
    return simulator.run(lambda:iter(events)),events


def setup(root,**later_kw):
    ss=SimulationStore(Path(root)/'c11.db'); training,_=make_source(); h=ss.commit(training)['run_hash']
    w=TrainingWindow(START,START+12*BIN,START+12*BIN+1); data=snapshot(ss,[h],w,config()); model=publish(fit(data,config()),w.cutoff_ms,'modeled')
    later,events=make_source(n=3,start=START+13*BIN,**later_kw); summary=ss.commit(later)
    return ss,{summary['run_hash']:summary['report_hash']},model,events


def policy(**kw): return RiskPolicy(**dict(dict(per_trade_risk_fraction='0.01'),**kw))


def batch(ss,pins,model,events,cash='320',clock=None):
    data=load(ss,pins); stamp=min(data['entries']) if clock is None else clock; offers=[]
    for key,old in data['entries'][stamp]:
        d=data['candidates'][key]; m=d['manifest']
        q=EstimateRequest(d['candidate'],d['feature'],d['scenario'],m['execution'],m['fees'],m['funding'],m['candidates'],stamp)
        offers.append(Offer(q.document(),model.document()))
    m=data['common']; marks=[]
    for symbol in m['dataset']['symbols']:
        e=next(e for e in events if e['kind']=='mark' and e['symbol']==symbol and e['available_ms']==stamp)
        marks.append(dict(instrument_id=e['instrument_id'],symbol=symbol,price=e['data']['mark_price'],event_ms=e['event_ms'],available_ms=stamp,event_id=e['id']))
    state=AccountSnapshot(stamp,stamp,cash,cash,marks=marks)
    def execute(offer,when):
        e=ExecutionEngine(m['dataset'],[offer.execution_intent],m['metadata_snapshots'][0],m['metadata_versions'],FeeSchedule.from_dict(m['fees']),ExecutionConfig.from_dict(m['execution']),[offer.request.feature_snapshot.document()],m['dataset']['as_of_ms'])
        for event in events:
            if event['available_ms']<=when: e.push(event)
        return e.evaluate(offer.execution_intent,when)
    return state,offers,execute


def funding_source(start,n=3):
    """Actual C11 states with a settlement and a later correction after each close."""
    from tests.c09_support import observation
    result,events=make_source(n=n,start=start); m=result.manifest.document(); extra=[]
    for k in range(n):
        stamp=start+k*BIN+200000
        for symbol in m['dataset']['symbols']:
            template=next(e for e in events if e['symbol']==symbol)
            for rate,available in (('0.001',stamp),('0.002',stamp+30000)):
                e=observation('funding',1,stamp,'102',available=available,funding_rate=rate)
                e.update(symbol=symbol,instrument_id=template['instrument_id'],metadata_version=template['metadata_version']); extra.append(e)
    events.extend(extra); events.sort(key=lambda e:(e['available_ms'],e['id'],e['symbol']))
    for idx,e in enumerate(events,1): e['id']=idx
    m['dataset'].update(event_count=len(events),dataset_hash=m['dataset']['dataset_hash']+'-funding')
    times=[start+k*BIN+200000 for k in range(n)]
    calendars=[dict(c,settlement_times_ms=times) for c in m['calendars']]
    simulator=Simulator(m['dataset'],[Scenario.from_dict(s) for s in m['scenarios']],m['metadata_snapshots'],m['metadata_versions'],FeeSchedule.from_dict(m['fees']),ExecutionConfig.from_dict(m['execution']),
        CandidateConfig.from_dict(m['candidates']),FundingConfig.from_dict(m['funding']),calendars,SimulationConfig())
    return simulator.run(lambda:iter(events)),events
