"""Synthetic metadata, quotes and intent clocks with independent monetary expectations."""
from copy import deepcopy
from tradee.c01.domain import fingerprint, normalize
from tradee.c03.contracts import FeatureSnapshot
from tradee.c02.domain import candle
from tradee.c07 import ExecutionIntent, ExecutionConfig, FeeSchedule, ExecutionEngine
from tests.support import payload

START=1788220800000


def metadata():
    raw=payload()
    btc=raw['symbols'][0]
    for f in btc['filters']:
        if f['filterType']=='PRICE_FILTER': f.update(minPrice='1',maxPrice='1000000',tickSize='0.1')
        if f['filterType']=='MIN_NOTIONAL': f['notional']='5'
    spec=normalize(raw)[0]; version=fingerprint(spec)
    doc=dict(schema_version=1,as_of_ms=START,policy={'enabled':['BTCUSDT','ETHUSDT']},decisions=[
        dict(symbol='BTCUSDT',state='eligible',reasons=[],instrument_id=spec['instrument_id'],version_hash=version,last_observed_ms=START)])
    doc['snapshot_hash']=fingerprint(doc)
    return raw,doc,{version:spec}


def dataset(mode='recorded'):
    return dict(schema_version=1,dataset_hash='execution-fixture',mode=mode,start_ms=START-3600000,
                end_ms=START+600000,as_of_ms=START+600000,symbols=['BTCUSDT'],
                kinds=['quote','mark','candle','funding'] if mode=='recorded' else ['candle'])


def intent(**kwargs):
    _,u,v=metadata()
    data=dict(intent_id='entry',instrument_id=u['decisions'][0]['instrument_id'],symbol='BTCUSDT',side='buy',
              quantity='1',detected_ms=START,expires_ms=START+60000,reference_price='100',stop_price='99',holding_until_ms=START+3660000)
    data.update(kwargs); return ExecutionIntent(**data)


def event(kind,eid=1,stamp=START+1000,available=None,**kwargs):
    _,u,v=metadata(); spec=next(iter(v.values()))
    d=dict(bid='99.9',ask='100.1',bid_qty='10',ask_qty='10') if kind=='quote' else dict(mark_price='100',index_price='100',funding_rate='0.001',next_funding_ms=START+3600000)
    d.update(kwargs); received=stamp if available is None else available
    return dict(schema_version=1,id=eid,symbol='BTCUSDT',instrument_id=spec['instrument_id'],metadata_version=next(iter(v)),
        kind=kind,key=str(eid) if kind=='quote' else str(stamp),event_ms=stamp,available_ms=received,received_ms=received,
        availability_basis='recorded',final=True,source='synthetic',raw_sha256=fingerprint(d),data=d)


def bar(eid=1,opened=START,close='100',volume='1000',available=None):
    _,u,v=metadata(); spec=next(iter(v.values()))
    row=[opened,close,str(float(close)+1),str(float(close)-1),close,volume,opened+59999,str(float(volume)*float(close)),5,'0','0','0']
    result=candle('BTCUSDT',row); end=opened+60000
    result.update(id=eid,instrument_id=spec['instrument_id'],metadata_version=next(iter(v)),received_ms=end,
        available_ms=end if available is None else available,availability_basis='modeled',raw_sha256=fingerprint(row))
    return result


def engine(config=None,intents=None,fees=None,features=(),mode='recorded'):
    _,u,v=metadata(); cfg=config or ExecutionConfig(manual_delay_ms=0)
    return ExecutionEngine(dataset(mode),intents or [intent()],u,v,
        fees or FeeSchedule('0.0005','0.0002','operator_assumption:test'),cfg,features)


def seeded(**kwargs):
    e=engine(**kwargs); e.push(event('mark')); e.push(event('quote',eid=2)); return e


def feature(cursor=None,**kwargs):
    _,u,_=metadata()
    doc=dict(schema_version=1,instrument_id=u['decisions'][0]['instrument_id'],timeframe='1m',dataset_hash='execution-fixture',
        evaluation_as_of_ms=START+1000,input_available_ms=START+1000,target_end_ms=START,
        input_cursor=cursor or [START+1000,1],assumed_usable_ms=START+1000,
        values={'log_return_1':{'value':0.001,'status':'valid','stable':True}})
    doc.update(kwargs); snap=FeatureSnapshot.create(doc)
    return {'snapshot_hash':snap.digest,**doc}
