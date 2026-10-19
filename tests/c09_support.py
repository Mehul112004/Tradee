"""Actual C08 candidate prefixes with synthetic C02 observations and exact prices."""
from decimal import Decimal
from tradee.c01.domain import fingerprint
from tradee.c02.domain import number
from tradee.c06 import SettlementCalendar,FundingConfig
from tradee.c07 import ExecutionConfig,FeeSchedule
from tradee.c09 import TradeIntent,TradePolicy,LifecycleEngine
from tests.c08_support import START,MINUTE,event as candle_event,engine as candidate_engine,dataset as candidate_dataset,metadata
from tradee.c08 import StrategySpec

DETECT=START+180000


def prepared(side='long',mode='recorded',policy=None,execution=None,calendars=(),quantity='1',**policy_kw):
    ds=candidate_dataset(mode=mode,bars=100)
    ds['kinds']=['candle','quote','mark','trade','funding'] if mode=='recorded' else ['candle']
    a=candidate_engine(ds=ds,strategy=StrategySpec(timeframe='15m',lookback_bars=2) if mode=='modeled' else None)
    price='102' if side=='long' else '98'
    events=([candle_event(j,price if j>=30 else '100',mode=mode) for j in range(45)] if mode=='modeled' else
            [candle_event(0,mode=mode),candle_event(1,mode=mode),candle_event(2,price,mode=mode)])
    records=list(a.run(events)); c=next(r.document()['candidate'] for r in records if r.document()['candidate'])
    f=next(s for s in a.pending_features.values() if s.digest==c['feature_snapshot_hash'])
    bundle={'snapshot_hash':f.digest,**f.document()}
    policy=policy or TradePolicy(trigger_source='contract_trade' if mode=='recorded' else 'bar_close',**policy_kw)
    intent=TradeIntent(c,bundle,quantity,policy.document())
    _,u,v=metadata()
    execution=execution or ExecutionConfig(manual_delay_ms=0,max_spread_bps='25',**({} if mode=='recorded' else dict(market_model='modeled_bar',metadata_mode='research_assumption',bar_mark_proxy='bar_close')))
    e=LifecycleEngine(ds,[intent],[u],v,FeeSchedule('0.0005','0.0002','synthetic fee assumption'),execution,FundingConfig(),calendars)
    return e,intent,events


def observation(kind,eid,stamp,price='102',available=None,**kwargs):
    _,u,v=metadata(); ident=u['decisions'][0]['instrument_id']; version=next(iter(v))
    p=Decimal(price)
    if kind=='quote': data=dict(bid=number(str(p-Decimal('0.1'))),ask=number(str(p+Decimal('0.1'))),bid_qty='10',ask_qty='10')
    elif kind=='mark': data=dict(mark_price=str(p),index_price=str(p),funding_rate='0.001',next_funding_ms=DETECT+3600000)
    elif kind=='funding': data=dict(mark_price=str(p),funding_rate='0.001')
    else: data=dict(price=str(p),quantity='1',first_trade_id=eid,last_trade_id=eid,buyer_is_maker=False)
    data.update(kwargs); received=stamp if available is None else available
    return dict(schema_version=1,id=eid,symbol='BTCUSDT',instrument_id=ident,metadata_version=version,kind=kind,
        key=str(stamp) if kind in ('funding','mark') else str(eid),event_ms=stamp,available_ms=received,received_ms=received,
        availability_basis='recorded',final=True,raw_sha256=fingerprint(data),source='synthetic',data=data)


def open_trade(e,events,price='102',stamp=DETECT+1000):
    for event in events: e.advance(event)
    e.advance(observation('mark',4,stamp,price)); e.advance(observation('quote',5,stamp,price))
    return next(iter(e.states.values()))


def close_trade(e,price='105',stamp=DETECT+30000,eid=6):
    e.advance(observation('mark',eid,stamp,price)); e.advance(observation('trade',eid+1,stamp,price)); e.advance(observation('quote',eid+2,stamp,price))
    return next(iter(e.states.values()))


def calendar(times=()):
    _,u,_=metadata()
    return SettlementCalendar(u['decisions'][0]['instrument_id'],'BTCUSDT',START,START+6000000,times,'operator_assumption:synthetic complete test schedule')
