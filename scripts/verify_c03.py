"""Opt-in characterization; never part of the offline test suite.

Run from the repository root with the tradee environment. --live makes public
Binance requests and records a bounded session; no credentials or orders.
"""
import argparse
import json
import platform
from pathlib import Path
import time
import tracemalloc

from tradee.c03 import FeatureConfig, FeatureEngine, FeatureStore


def benchmark(root):
    from tests.c03_support import dataset, event, START
    if (root/'benchmark.sqlite3').exists():
        raise ValueError('Use a fresh output directory for each benchmark')
    config=FeatureConfig()
    engine=FeatureEngine(dataset(end=START+1440*60000),config)
    store=FeatureStore(root/'benchmark.sqlite3')
    pending=[]; output_count=0; update_times=[]
    tracemalloc.start(); wall=time.perf_counter(); cpu=time.process_time()
    for i in range(1440):
        for offset,symbol in enumerate(('BTCUSDT','ETHUSDT')):
            tick=time.perf_counter()
            outputs=engine.advance(event(i,event_id=i*2+offset+1,symbol=symbol))
            update_times.append(time.perf_counter()-tick)
            pending.extend(outputs); output_count+=len(outputs)
        if (i+1)%120==0:
            store.commit(engine,pending); pending=[]
    elapsed=time.perf_counter()-wall; cpu_elapsed=time.process_time()-cpu
    correction=event(0,102,event_id=2881,available=START+1440*60000+1)
    tick=time.perf_counter(); corrected=engine.advance(correction)
    correction_time=time.perf_counter()-tick
    store.commit(engine,corrected)
    current,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
    update_times.sort()
    return dict(platform=platform.platform(),python=platform.python_version(),events=2880,symbols=2,
        run_hash=engine.manifest.digest,code_hash=engine.manifest.document()['code_hash'],
        duration_days=1,timeframes=list(config.timeframes),baseline_outputs=14,snapshots=output_count,
        wall_seconds=elapsed,cpu_seconds=cpu_elapsed,median_update_ms=update_times[len(update_times)//2]*1000,
        p95_update_ms=update_times[int(len(update_times)*.95)]*1000,max_update_ms=max(update_times)*1000,
        old_correction_ms=correction_time*1000,traced_current_bytes=current,traced_peak_bytes=peak,
        database_bytes=(root/'benchmark.sqlite3').stat().st_size,
        note='Includes tracing overhead and periodic persistence. One old correction across all timeframes; not a worst-case bound.')


def live(root):
    from tradee.c01 import Registry, BinanceProvider
    from tradee.c02 import MarketStore
    from tradee.c02.provider import RestClient
    from tradee.c02.live import connection, stream_urls
    registry=Registry(root/'live_c01.sqlite3'); registry.refresh(BinanceProvider())
    market=MarketStore(registry,root/'live_c02.sqlite3')
    end=int(time.time()*1000)//60000*60000; start=end-25*60000
    RestClient().backfill(market,'BTCUSDT',start,end,resume=False)
    messages=0; finals=0; deadline=time.monotonic()+75
    url=stream_urls(['BTCUSDT'],['candle'])['market']
    with connection(url) as ws:
        while time.monotonic()<deadline:
            raw=ws.recv(timeout=max(.1,deadline-time.monotonic()))
            market.ingest_ws(raw); messages+=1
            data=json.loads(raw); data=data.get('data',data)
            if data.get('k',{}).get('x'):
                finals+=1; break
    if not finals: raise RuntimeError('No finalized WebSocket candle within the bounded session')
    stop=int(time.time()*1000)//60000*60000+60000
    dataset=market.snapshot(['BTCUSDT'],start,stop)
    return compare_capture(root,market,dataset,messages,finals)


def compare_capture(root,market,dataset,messages,finals):
    events=list(market.replay(dataset['dataset_hash']))
    config=FeatureConfig(features=('log_return_1','vwap20','rsi14'),timeframes=('1m',),require_stable=False)
    incremental=FeatureEngine(dataset,config); first=[]
    for e in events: first.extend(s.serialized for s in incremental.advance(e))
    batch=FeatureEngine(dataset,config); second=[s.serialized for s in batch.run(events)]
    if first!=second: raise AssertionError('Captured public session batch/incremental mismatch')
    store=FeatureStore(root/'live_c03.sqlite3')
    summary=store.run(market,dataset['dataset_hash'],config)
    return dict(websocket_messages=messages,finalized_websocket_candles=finals,events=len(events),
        parity=True,snapshots=len(first),dataset_hash=dataset['dataset_hash'],summary=summary,
        code_hash=batch.manifest.document()['code_hash'],
        note='Recorded public REST + WebSocket session replayed through incremental and batch APIs. No sustained-service or profitability claim.')


def replay_capture(root):
    from tradee.c01 import Registry
    from tradee.c02 import MarketStore
    report=json.loads((root/'live.json').read_text())
    market=MarketStore(Registry(root/'live_c01.sqlite3'),root/'live_c02.sqlite3')
    return compare_capture(root,market,market.dataset(report['dataset_hash']),
        report['websocket_messages'],report['finalized_websocket_candles'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(); mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--live',action='store_true'); mode.add_argument('--replay',action='store_true')
    parser.add_argument('--output',type=Path,required=True); args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    result=live(args.output) if args.live else replay_capture(args.output) if args.replay else benchmark(args.output)
    print(json.dumps(result,indent=2))
    (args.output/('live.json' if args.live or args.replay else 'benchmark.json')).write_text(json.dumps(result,indent=2)+'\n')
