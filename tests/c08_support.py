"""Synthetic exact-price candles and independent expected trigger cases."""
from copy import deepcopy
from decimal import Decimal
from tradee.c01.domain import fingerprint
from tradee.c02.domain import candle
from tradee.c08 import StrategySpec, CandidateConfig, CandidateEngine
from tradee.c08.contracts import TREND_FAMILY
from tests.c07_support import START, metadata

MINUTE=60000


def dataset(mode='recorded',bars=1000):
    return dict(schema_version=1,dataset_hash='candidate-fixture',mode=mode,start_ms=START,end_ms=START+bars*MINUTE,
        as_of_ms=START+bars*MINUTE,symbols=['BTCUSDT'],kinds=['candle'])


def event(index,close='100',high=None,low=None,opened=None,eid=None,available=None,mode='recorded',final=True):
    stamp=START+index*MINUTE if opened is None else opened; c=Decimal(str(close))
    row=[stamp,str(c),str(c+1) if high is None else high,str(c-1) if low is None else low,str(c),'1000',stamp+MINUTE-1,'100000',5,'700','70000','0']
    e=candle('BTCUSDT',row,final); _,u,v=metadata()
    e.update(id=index+1 if eid is None else eid,instrument_id=u['decisions'][0]['instrument_id'],metadata_version=next(iter(v)),
        available_ms=stamp+MINUTE if available is None else available,received_ms=stamp+MINUTE if available is None else available,
        availability_basis=mode,raw_sha256=fingerprint(row),source='synthetic')
    return e


def spec(family='prior_range_breakout',**kw):
    return StrategySpec(family=family,timeframe='1m',entry_window_ms=60000,**({'lookback_bars':2} if family!='ema_pullback_continuation' and 'lookback_bars' not in kw else {}),**kw)


def engine(strategy=None,config=None,ds=None,snapshots=None,versions=None):
    _,u,v=metadata()
    return CandidateEngine(ds or dataset(),strategy or spec(),snapshots or [u],v if versions is None else versions,
        config or CandidateConfig(max_metadata_age_ms=86400000))


def docs(records): return [r.document() for r in records]


def trend_events(short=False,mode='recorded'):
    closes=[(Decimal('200')-Decimal(i)/10 if short else Decimal('100')+Decimal(i)/10) for i in range(400)]
    closes+=list(map(Decimal,('162','160') if short else ('138','140')))
    return [event(i,str(c),mode=mode) for i,c in enumerate(closes)]
