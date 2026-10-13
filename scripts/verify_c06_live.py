"""Opt-in public Binance smoke. Uses synthetic exposure, never actual account positions."""
import argparse
import json
from pathlib import Path

from tradee.c01 import Registry, BinanceProvider
from tradee.c02 import MarketStore
from tradee.c02.provider import RestClient
from tradee.c02.live import connection, stream_urls
from tradee.c06 import FundingStore, PositionTimeline, SettlementCalendar, FundingConfig
from tradee.c06.engine import code_hash


def capture(root):
    registry=Registry(root/'c01.sqlite3'); registry.refresh(BinanceProvider())
    market=MarketStore(registry,root/'c02.sqlite3')
    response=RestClient().fetch('/fapi/v1/fundingRate',dict(symbol='BTCUSDT',limit=3))
    market.ingest_rest(response.raw,'BTCUSDT','funding',source=response.source,received_ms=response.received_ms)
    with connection(stream_urls(['BTCUSDT'],['mark'])['market']) as ws:
        raw=ws.recv(timeout=15)
        market.ingest_ws(raw)
    rows=json.loads(response.raw)
    start=min(r['fundingTime'] for r in rows)-120000
    end=market.now()+1
    dataset=market.snapshot(['BTCUSDT'],start,end,kinds=('funding','mark'))
    (root/'capture.json').write_text(json.dumps({'dataset_hash':dataset['dataset_hash']},indent=2)+'\n')
    return market,dataset


def compare(root,market,dataset):
    ident=market.binding('BTCUSDT')['instrument_id']
    p=PositionTimeline('synthetic-public-smoke',ident,'BTCUSDT','long',
        [dict(at_ms=dataset['start_ms'],quantity='0.001')])
    events=list(market.replay(dataset['dataset_hash']))
    decision=max(e['available_ms'] for e in events)
    times=sorted({e['event_ms'] for e in events if e['kind']=='funding'})
    calendar=SettlementCalendar(ident,'BTCUSDT',dataset['start_ms'],dataset['end_ms'],times,
        'operator_assumption:only-selected-public-smoke-settlements; not certified full history')
    from tradee.c06 import FundingEngine
    a=FundingEngine(dataset,[p],[calendar],FundingConfig(),decision_ms=decision)
    for e in events: a.push(e)
    expected=a.report()
    store=FundingStore(root/'c06.sqlite3')
    summary=store.run(market,dataset['dataset_hash'],[p],[calendar],FundingConfig(),decision_ms=decision,batch_size=2)
    saved=store.report(summary['report_hash']); saved.pop('report_hash')
    if saved!=expected.document():
        raise AssertionError('Public incremental evaluation and persisted replay differ')
    position=saved['positions'][0]
    if len(times)!=3 or position['estimate']['status']!='valid' or not saved['ready']:
        raise AssertionError('Public funding/mark smoke did not produce expected ready accounting and fresh context')
    result=dict(passed=True,settlements=len(times),mark_events=sum(e['kind']=='mark' for e in events),
        parity=True,code_hash=code_hash(),dataset_hash=dataset['dataset_hash'],decision_as_of_ms=decision,summary=summary,
        estimated_next_cashflow_usdt=position['estimate']['estimated_cashflow_usdt'],
        note='Recorded replay evaluated at latest input availability, not a wall-clock action test. Synthetic 0.001 base-unit long; no account charge reconciliation or orders.')
    (root/'live_report.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--replay',action='store_true'); args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    if args.replay:
        market=MarketStore(Registry(args.output/'c01.sqlite3'),args.output/'c02.sqlite3')
        metadata=json.loads((args.output/'capture.json').read_text())
        dataset=market.dataset(metadata['dataset_hash'])
    else:
        if (args.output/'capture.json').exists(): raise ValueError('Use a fresh output directory for public capture')
        market,dataset=capture(args.output)
    print(json.dumps(compare(args.output,market,dataset),indent=2))
