"""Opt-in public Binance C07 smoke; paper scenario, no account endpoints or orders."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
from decimal import Decimal

from tradee.c01 import Registry, BinanceProvider, Policy
from tradee.c02 import MarketStore
from tradee.c02.live import connection, stream_urls
from tradee.c06.engine import code_hash
from tradee.c06.contracts import decimal_text
from tradee.c07 import ExecutionStore, ExecutionEngine, ExecutionIntent, ExecutionConfig, FeeSchedule
from tradee.c07.math import exact, common_step, adverse_tick


def capture(root):
    registry=Registry(root/'c01.sqlite3'); registry.refresh(BinanceProvider())
    market=MarketStore(registry,root/'c02.sqlite3'); urls=stream_urls(['BTCUSDT'],['mark','quote'])
    with ExitStack() as stack:
        quote=stack.enter_context(connection(urls['public'])); mark=stack.enter_context(connection(urls['market']))
        market.ingest_ws(quote.recv(timeout=15),source=urls['public'])
        market.ingest_ws(mark.recv(timeout=15),source=urls['market'])
    now=market.now(); dataset=market.snapshot(['BTCUSDT'],now-120000,now+1,kinds=('mark','quote'))
    (root/'capture.json').write_text(json.dumps(dict(dataset_hash=dataset['dataset_hash']),indent=2)+'\n')
    return market,dataset


def compare(root,market,dataset):
    events=list(market.replay(dataset['dataset_hash'])); decision=max(e['available_ms'] for e in events)
    mark=next(e for e in events if e['kind']=='mark'); quote=next(e for e in events if e['kind']=='quote')
    cfg=ExecutionConfig(manual_delay_ms=0)
    universe=market.registry.universe(Policy(cfg.enabled_symbols),decision)
    versions={d['version_hash']:market.registry.version(d['version_hash'])['spec'] for d in universe['decisions'] if d['version_hash']}
    spec=versions[next(d['version_hash'] for d in universe['decisions'] if d['symbol']=='BTCUSDT')]
    with exact():
        step=common_step([spec['filters'][k]['stepSize'] for k in ('LOT_SIZE','MARKET_LOT_SIZE')])
        # Round up only when constructing this explicit fixture quantity; the engine
        # never increases a user's submitted quantity. Fixture targets minimum notional.
        from fractions import Fraction
        mark_price=Decimal(mark['data']['mark_price'])
        units=Fraction(Decimal(spec['filters']['MIN_NOTIONAL']['notional']))/Fraction(mark_price)/Fraction(step)
        qty=max(step*(-(-units.numerator//units.denominator)),*(Decimal(spec['filters'][k]['minQty']) for k in ('LOT_SIZE','MARKET_LOT_SIZE')))
        qty=adverse_tick(qty,step,'buy')
        ref=(Decimal(quote['data']['bid'])+Decimal(quote['data']['ask']))/2
    intent=ExecutionIntent('synthetic-public-smoke',mark['instrument_id'],'BTCUSDT','buy',decimal_text(qty),
        min(e['available_ms'] for e in events),decision+60000,decimal_text(ref),holding_until_ms=mark['data']['next_funding_ms']+60000)
    fees=FeeSchedule('0.0005','0.0002','operator_assumption:illustrative; not verified account fee')
    a=ExecutionEngine(dataset,[intent],universe,versions,fees,cfg,decision_ms=decision)
    for e in events: a.push(e)
    expected=a.report(); store=ExecutionStore(root/'c07.sqlite3')
    summary=store.run(market,dataset['dataset_hash'],[intent],fees,cfg,decision_ms=decision,batch_size=1)
    report=store.report(summary['report_hash']); report.pop('report_hash')
    if report!=expected.document(): raise AssertionError('Public prefix evaluation and persisted replay differ')
    if store.run(market,dataset['dataset_hash'],[intent],fees,cfg,decision_ms=decision,batch_size=1)!=summary:
        raise AssertionError('Public repeated replay duplicated outputs')
    estimate=report['estimates'][0]
    if not summary['ready'] and estimate['fill'] is not None: raise AssertionError('Rejected scenario invented a fill')
    result=dict(passed=True,parity=True,event_kinds=[e['kind'] for e in events],code_hash=code_hash(),dataset_hash=dataset['dataset_hash'],
        decision_as_of_ms=decision,summary=summary,note='Paper minimum-notional buy; explicit zero delay and illustrative fees. Business-policy rejection is valid. Recorded replay at latest input availability; no real-time action timing or actual order validation.')
    (root/'live_report.json').write_text(json.dumps(result,indent=2)+'\n'); return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True); parser.add_argument('--replay',action='store_true')
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    if args.replay:
        market=MarketStore(Registry(args.output/'c01.sqlite3'),args.output/'c02.sqlite3')
        ds=market.dataset(json.loads((args.output/'capture.json').read_text())['dataset_hash'])
    else:
        if (args.output/'capture.json').exists(): raise ValueError('Use a fresh directory for capture')
        market,ds=capture(args.output)
    print(json.dumps(compare(args.output,market,ds),indent=2))
