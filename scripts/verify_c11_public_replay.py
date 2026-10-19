"""C11 replay of retained public Binance data, with explicit coarse assumptions."""
import argparse
import json
from pathlib import Path
from tradee.c01 import Registry
from tradee.c02 import MarketStore
from tradee.c06.engine import code_hash
from tradee.c07 import ExecutionConfig,FeeSchedule
from tradee.c08 import StrategySpec
from tradee.c09 import TradePolicy
from tradee.c11 import Scenario,SimulationStore


def verify(source,root):
    source=Path(source); root=Path(root); root.mkdir(parents=True,exist_ok=True); initial=code_hash()
    capture=json.loads((source/'capture.json').read_text())
    market=MarketStore(Registry(source/'c01.sqlite3'),source/'c02.sqlite3'); ds=market.dataset(capture['modeled'])
    policy=TradePolicy(trigger_source='bar_close',max_holding_ms=900000)
    scenarios=[Scenario(name,StrategySpec(family=family).document(),policy.document(),'0.001')
               for name,family in (('range','prior_range_breakout'),('trend','ema_pullback_continuation'))]
    fees=FeeSchedule('0.0005','0.0002','operator_assumption:illustrative unverified account rates')
    execution=ExecutionConfig(market_model='modeled_bar',metadata_mode='research_assumption',bar_mark_proxy='bar_close')
    store=SimulationStore(root/'c11.sqlite3',forbidden_paths=(market.path,market.registry.path))
    result=store.run(market,ds['dataset_hash'],scenarios,fees,execution)
    if code_hash()!=initial: raise RuntimeError('Production source changed during public replay; rerun with fixed source')
    report=store.report(result['report_hash'])
    if result['metrics']['candidates']<1 or result['metrics']['closed']<1: raise AssertionError('Retained fixture did not exercise candidate/closed-trade orchestration')
    if any(t['net_usdt'] is not None or t['profitable'] is not None for t in report['trades']): raise AssertionError('Modeled replay invented certified funding/net labels')
    if not report['attribution']['reconciled']: raise AssertionError('Public ledger did not reconcile')
    if store.run(market,ds['dataset_hash'],scenarios,fees,execution)!=result: raise AssertionError('Pinned public replay changed on repeat')
    doc=dict(passed=True,source_capture=str(source.resolve()),dataset_hash=ds['dataset_hash'],code_hash=initial,
        events=ds['event_count'],simulation=result,
        note='Retained real Binance candle payloads; explicit modeled close availability, current metadata, bar mark proxy, assumed fees, size 0.001 and 15-minute time exit. No historical quote/trade/funding fidelity or profitability claim; modeled funding/net remain null. No new network, account, orders or Telegram.')
    (root/'public_replay.json').write_text(json.dumps(doc,indent=2)+'\n'); return doc


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--source',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); print(json.dumps(verify(args.source,args.output),indent=2))
