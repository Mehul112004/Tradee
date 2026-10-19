"""Real multi-period C08/C07/C06/C09/C11 outcomes, not assigned labels."""
from decimal import Decimal
from tradee.c01 import Registry
from tradee.c02 import MarketStore
from tradee.c06 import SettlementCalendar
from tradee.c07 import ExecutionConfig,FeeSchedule
from tradee.c08 import CandidateConfig
from tradee.c09 import TradePolicy
from tradee.c11 import Scenario,Simulator,SimulationConfig
from tradee.c10 import TrainingWindow,EstimatorConfig,EstimateRequest
from tests.c08_support import metadata,event,spec,START
from tests.c09_support import observation

BIN=240000


def config(**kw):
    return EstimatorConfig(**dict(dict(min_trades=6,min_occupied_bins=6,min_occupied_spans=6,bin_ms=BIN,block_bins=1,bootstrap_replicates=200),**kw))


def simulation(n=12,start=START,positive=True,unknown_funding=False):
    _,u,v=metadata(); events=[]; serial=0
    for k in range(n):
        for j,price in enumerate(('100','100','102','100')):
            opened=start+(k*4+j)*60000; serial+=1
            events.append(event(0,price,opened=opened,eid=serial))
            if j==2:
                detected=opened+60000
                exit_price=('105' if k%2==0 else '106') if positive else ('100' if k%2==0 else '99')
                for kind,stamp,p in (('mark',detected+1000,'102'),('quote',detected+1000,'102'),('mark',detected+40000,exit_price),('trade',detected+40000,exit_price),('quote',detected+40000,exit_price)):
                    serial+=1; events.append(observation(kind,serial,stamp,p))
    end=start+n*BIN; ds=dict(schema_version=1,dataset_hash='c10-'+str(start)+'-'+str(positive),mode='recorded',start_ms=start,end_ms=end,as_of_ms=end,event_count=len(events),symbols=['BTCUSDT'],kinds=['candle','quote','mark','trade','funding'])
    scenario=Scenario('range',spec(sides=('long',)).document(),TradePolicy(max_holding_ms=60000).document(),'1')
    execution=ExecutionConfig(manual_delay_ms=0,max_spread_bps='25',max_metadata_age_ms=86400000)
    fees=FeeSchedule('0.0005','0.0002','synthetic C10 execution assumption')
    calendars=[] if unknown_funding else [SettlementCalendar(u['decisions'][0]['instrument_id'],'BTCUSDT',start,end,[],'operator_assumption:synthetic no-settlement window')]
    result=Simulator(ds,[scenario],[u],v,fees,execution,calendars=calendars,config=SimulationConfig()).run(lambda:iter(events))
    return result,events


def request(store,run,index=0,**kw):
    from tradee.c10.source import pages
    m=store.manifest(run); rows=[a for a in pages(store,run,'candidate_decision') if a['payload']['selected']]
    a=rows[index]; c=a['payload']['record']['candidate']; features={a['payload']['snapshot_hash']:a['payload'] for a in pages(store,run,'feature')}
    d=dict(candidate=c,feature_snapshot=features[c['feature_snapshot_hash']],scenario=next(s for s in m['scenarios'] if s['name']==a['scenario']),execution=m['execution'],fees=m['fees'],funding=m['funding'],candidates=m['candidates'],evaluation_ms=c['detected_ms'])
    d.update(kw); return EstimateRequest.from_dict(d)


def window(n=12,start=START): return TrainingWindow(start,start+n*BIN,start+n*BIN+1)
