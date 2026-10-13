"""Synthetic finalized observations; independent from production feature calculations."""
from decimal import Decimal
from tradee.c02.domain import candle
from tradee.c01.domain import fingerprint

START=1788220800000  # 2026-09-01 00:00 UTC
IDENTITY='binance:usds_futures:BTCUSDT:test'


def event(index, close=None, start=START, event_id=None, available=None, final=True, symbol='BTCUSDT'):
    opened=start+index*60000
    c=Decimal(str(close if close is not None else 100+(index%13)*0.25))
    raw=[opened,str(c-Decimal('0.1')),str(c+1),str(c-1),str(c),'10',opened+59999,'1000',5,'7','700','0']
    doc=candle(symbol,raw,final)
    received=available if available is not None else opened+60000
    doc.update(id=event_id if event_id is not None else index+1,
               instrument_id=IDENTITY if symbol=='BTCUSDT' else IDENTITY.replace('BTC','ETH'),
               metadata_version='metadata-v1',received_ms=received,available_ms=received,
               availability_basis='recorded',source='test',raw_sha256=fingerprint(raw))
    return doc


def dataset(start=START,end=START+10000*60000,mode='recorded',kinds=('candle','quote')):
    return dict(schema_version=1,dataset_hash='synthetic-dataset',start_ms=start,end_ms=end,
                mode=mode,symbols=['BTCUSDT','ETHUSDT'],kinds=list(kinds))


def quote(event_id, stamp, available=None, bid='99',ask='101',B='3',A='1'):
    received=stamp if available is None else available
    return dict(schema_version=1,id=event_id,symbol='BTCUSDT',instrument_id=IDENTITY,metadata_version='metadata-v1',
        kind='quote',key=str(event_id),event_ms=stamp,received_ms=received,available_ms=received,final=True,
        availability_basis='recorded',source='test',raw_sha256='quote',data=dict(bid=bid,ask=ask,bid_qty=B,ask_qty=A))
