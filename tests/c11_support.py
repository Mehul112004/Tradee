"""Shared C08 -> C09 -> C11 golden fixtures; no mocked fills or outcomes."""
from copy import deepcopy
from tradee.c08 import CandidateConfig
from tradee.c11 import Simulator, Scenario, SimulationConfig
from tests.c08_support import spec, metadata, START
from tests.c09_support import prepared, observation, calendar, DETECT


def fixture(side='long', end=None, policy=None, calendars=True, events=None, config=None, **kwargs):
    base,intent,candles=prepared(side=side,policy=policy)
    price='102' if side=='long' else '98'; exit_price='105' if side=='long' else '95'
    events=events if events is not None else candles+[
        observation('mark',4,DETECT+1000,price),observation('quote',5,DETECT+1000,price),
        observation('mark',6,DETECT+30000,exit_price),observation('trade',7,DETECT+30000,exit_price),observation('quote',8,DETECT+30000,exit_price)]
    ds=deepcopy(base.dataset); ds['as_of_ms']=end if end is not None else DETECT+60000; ds['event_count']=len(events)
    _,u,v=metadata()
    scenarios=kwargs.pop('scenarios',[Scenario('range',spec().document(),(policy or intent.policy).document(),'1')])
    simulator=Simulator(ds,scenarios,[u],v,base.fees,kwargs.pop('execution',base.execution),
        kwargs.pop('candidates',None),base.funding_config,[calendar()] if calendars else [],config,**kwargs)
    return simulator,events


def run(**kwargs):
    s,events=fixture(**kwargs)
    return s.run(lambda:iter(events))


def payloads(result,kind):
    return [a.document()['payload'] for a in result.artifacts if a.document()['kind']==kind]
