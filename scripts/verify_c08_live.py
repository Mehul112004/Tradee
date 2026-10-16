"""Public candle feed/replay parity for C08; no outcome/strategy-performance check."""
import argparse
import json
from pathlib import Path
from tradee.c01 import Registry,BinanceProvider
from tradee.c02 import MarketStore
from tradee.c02.provider import RestClient
from tradee.c02.live import connection,stream_urls
from tradee.c06.engine import code_hash
from tradee.c08 import CandidateEngine,CandidateStore,StrategySpec,CandidateConfig
from tradee.c08.contracts import FAMILIES
from tradee.c08.metadata import capture as capture_metadata


def capture(root):
    registry=Registry(root/'c01.sqlite3'); registry.refresh(BinanceProvider())
    market=MarketStore(registry,root/'c02.sqlite3'); end=market.now()//60000*60000
    start=end//900000*900000-400*900000
    history=RestClient().backfill(market,'BTCUSDT',start,end,resume=False)
    url=stream_urls(['BTCUSDT'],['candle'])['market']
    with connection(url) as ws:
        for _ in range(3): market.ingest_ws(ws.recv(timeout=15),source=url)
    stop=market.now()//60000*60000+60000
    recorded=market.snapshot(['BTCUSDT'],start,stop,kinds=('candle',))
    modeled=market.snapshot(['BTCUSDT'],start,stop,kinds=('candle',),mode='modeled',delay_ms=0)
    doc=dict(recorded=recorded['dataset_hash'],modeled=modeled['dataset_hash'],history=history,websocket_messages=3)
    (root/'capture.json').write_text(json.dumps(doc,indent=2)+'\n'); return market,doc


def compare(root,market,capture_doc):
    frozen_code=code_hash(); store=CandidateStore(root/'c08.sqlite3'); results=[]
    for mode in ('recorded','modeled'):
        ds=market.dataset(capture_doc[mode]); cfg=CandidateConfig(metadata_mode='observed' if mode=='recorded' else 'research_assumption')
        snapshots,versions=capture_metadata(market.registry,ds,cfg); events=list(market.replay(ds['dataset_hash']))
        for family in FAMILIES:
            strategy=StrategySpec(family=family); a=CandidateEngine(ds,strategy,snapshots,versions,cfg)
            expected=[r.digest for r in a.run(events)]
            summary=store.run(market,ds['dataset_hash'],strategy,cfg,batch_size=256)
            got=[]; cursor=0
            while True:
                page=store.records(summary['run_hash'],limit=1000,after_sequence=cursor)
                got.extend(r['evaluation_hash'] for r in page['records'])
                if not page['records']: break
                cursor=page['next_sequence']
            if got!=expected or not summary['completed']: raise AssertionError('Public direct/persisted candidate inventory differs')
            if code_hash()!=frozen_code: raise RuntimeError('Production source changed during verification; replay the saved capture with a fixed source tree')
            if store.run(market,ds['dataset_hash'],strategy,cfg)!=summary: raise AssertionError('Public repeated replay duplicated opportunities')
            if summary['evaluations']<800: raise AssertionError('Insufficient public pre-roll for EMA stabilization check')
            results.append(dict(mode=mode,family=family,events=len(events),summary=summary))
    result=dict(passed=True,parity=True,code_hash=frozen_code,datasets={m:capture_doc[m] for m in ('recorded','modeled')},
        websocket_messages=capture_doc['websocket_messages'],results=results,
        note='Public candle integration and saved replay only. Recorded imports retain actual receipts; old detections are suppressed. Modeled history explicitly assumes close-time availability and current metadata. No performance filtering, outcome calculation, account access, orders or Telegram.')
    (root/'live_report.json').write_text(json.dumps(result,indent=2)+'\n'); return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',type=Path,required=True); parser.add_argument('--replay',action='store_true')
    args=parser.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    if args.replay:
        market=MarketStore(Registry(args.output/'c01.sqlite3'),args.output/'c02.sqlite3')
        doc=json.loads((args.output/'capture.json').read_text())
    else:
        if (args.output/'capture.json').exists(): raise ValueError('Use a fresh capture directory')
        market,doc=capture(args.output)
    print(json.dumps(compare(args.output,market,doc),indent=2))
