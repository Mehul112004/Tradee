"""Independent synthetic funding observations and hand-calculated scenarios."""
from copy import deepcopy
from tradee.c01.domain import fingerprint
from tradee.c06 import PositionTimeline, SettlementCalendar

START=1788220800000
HOUR=3600000
IDENTITY='binance:usds_futures:BTCUSDT:test'


def dataset():
    return dict(schema_version=1,dataset_hash='test-funding-dataset',start_ms=START,end_ms=START+6*HOUR,
                as_of_ms=START+7*HOUR,mode='recorded',symbols=['BTCUSDT','ETHUSDT'],kinds=['funding','mark','candle'])


def position(position_id='long',side='long',quantity='2',changes=None,identity=IDENTITY):
    return PositionTimeline(position_id,identity,'BTCUSDT',side,
                            changes or [dict(at_ms=START+60000,quantity=quantity)])


def calendar(times=None,identity=IDENTITY,start=START,end=None):
    return SettlementCalendar(identity,'BTCUSDT',start,end or START+6*HOUR,
        [START+HOUR,START+2*HOUR,START+4*HOUR] if times is None else times,'operator_assumption:test-golden-calendar')


def funding(event_id,stamp,rate='0.001',mark='100',available=None,identity=IDENTITY):
    availability=stamp if available is None else available
    return dict(schema_version=1,id=event_id,symbol='BTCUSDT',kind='funding',key=str(stamp),event_ms=stamp,
        received_ms=availability,available_ms=availability,availability_basis='recorded',final=True,
        instrument_id=identity,metadata_version='fixture-metadata',raw_sha256=fingerprint([rate,mark,event_id]),
        data=dict(funding_rate=rate,mark_price=mark))


def mark(event_id,stamp,rate='0.003',next_ms=None,available=None,price='100'):
    result=funding(event_id,stamp,rate,price,available)
    result['kind']='mark'; result['data'].update(index_price='99',next_funding_ms=next_ms if next_ms is not None else stamp+HOUR)
    return result
