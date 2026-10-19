"""Replay a retained public Binance C08 capture through C09; no new network calls."""
import argparse
import json
from pathlib import Path
from tradee.c01 import Registry
from tradee.c02 import MarketStore
from tradee.c08 import CandidateEngine,CandidateConfig,StrategySpec
from tradee.c08.metadata import capture
from tradee.c07 import ExecutionConfig,FeeSchedule
from tradee.c09 import LifecycleEngine,LifecycleStore,TradeIntent,TradePolicy
from tradee.c06.engine import code_hash


def verify(source,root):
    source=Path(source); root=Path(root); root.mkdir(parents=True,exist_ok=True); initial=code_hash()
    doc=json.loads((source/'capture.json').read_text()); market=MarketStore(Registry(source/'c01.sqlite3'),source/'c02.sqlite3')
    ds=market.dataset(doc['modeled']); cfg=CandidateConfig(metadata_mode='research_assumption')
    snapshots,versions=capture(market.registry,ds,cfg); detector=CandidateEngine(ds,StrategySpec(),snapshots,versions,cfg)
    events=list(market.replay(ds['dataset_hash'])); candidate=None
    for event in events:
        for record in detector.advance(event):
            c=record.document()['candidate']
            if c is not None and candidate is None:
                feature=detector.pending_features[c['feature_snapshot_hash']]
                candidate=TradeIntent(c,{'snapshot_hash':feature.digest,**feature.document()},'0.001',
                    TradePolicy(trigger_source='bar_close',max_holding_ms=900000).document())
        detector.pending_features.clear(); detector.features.lineages.clear()
    if candidate is None: raise AssertionError('Retained public fixture had no declared range-breakout candidate')
    fees=FeeSchedule('0.0005','0.0002','operator_assumption:illustrative unverified account rates')
    execution=ExecutionConfig(market_model='modeled_bar',metadata_mode='research_assumption',bar_mark_proxy='bar_close')
    engine=LifecycleEngine(ds,[candidate],snapshots,versions,fees,execution)
    for event in events: engine.advance(event)
    _,expected=engine.finish()
    if code_hash()!=initial: raise RuntimeError('Production code changed during verification; rerun with a fixed source tree')
    store=LifecycleStore(root/'c09.sqlite3',forbidden_paths=(market.path,market.registry.path))
    result=store.run(market,ds['dataset_hash'],[candidate],fees,execution)
    saved=store.report(result['report_hash']); saved.pop('report_hash')
    if saved!=expected.document(): raise AssertionError('Public direct lifecycle and persisted replay differ')
    if store.run(market,ds['dataset_hash'],[candidate],fees,execution)!=result: raise AssertionError('Public replay duplicated trade charges')
    report=dict(passed=True,parity=True,source_capture=str(source.resolve()),dataset_hash=ds['dataset_hash'],code_hash=initial,
        events=len(events),lifecycle=result,note='Reused recorded public Binance candle payloads in an explicitly modeled dataset: close-time and current-metadata/mark-proxy assumptions, synthetic 0.001-unit trade and fees. Funding unavailable remains null. No new live feed, strategy performance inference, account reconciliation, orders or Telegram.')
    (root/'public_replay.json').write_text(json.dumps(report,indent=2)+'\n'); return report


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--source',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); print(json.dumps(verify(args.source,args.output),indent=2))
