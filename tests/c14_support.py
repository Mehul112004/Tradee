"""Small explicit records for storage/dispatch unit tests, not research evidence."""
from tradee.c01.domain import fingerprint
from tradee.c03.contracts import FrozenRecord
from tradee.c06.engine import code_hash
from tradee.c13 import AccountSnapshot
from tradee.c14 import SessionSpec,RuntimeConfig
from tests.c07_support import START
from scripts.verify_c14 import BOT,CHAT,ScriptedTelegram
import platform

STAMP=START+181000


class Clock:
    def __init__(self,ms=STAMP): self.ms=ms
    def __call__(self): return self.ms/1000


def deployment(**cfg):
    config=RuntimeConfig(**dict(dict(mode='paper_test',bot_id=BOT,chat_id=CHAT),**cfg))
    spec=SessionSpec('paper',START,START+720000,START-60000,180000,config.document())
    return FrozenRecord.create(dict(kind='paper_deployment',spec=spec.document(),live_approved=False,promotion_authorized=False,code_hash=code_hash(),python=platform.python_version(),
        scenario=dict(horizon='intraday'),research=dict(model_hash='a'*64,release_hash='b'*64)))


def cycle(store,when=STAMP,phase='paper_open',entry=STAMP,signal_id='c'*64,health=True,extra=None):
    h=store.session('paper'); cash='1000'
    signal=dict(signal_id=signal_id,candidate_id='d'*64,phase=phase,entry_ms=entry,expires_ms=STAMP+10000,detected_ms=STAMP-1000,
        candidate=dict(symbol='BTCUSDT',side='long',timeframe='1m',hypothesis_family='prior_range_breakout',reference_price='102',breakout_level='101',expires_ms=STAMP+59000),
        trade_intent=dict(quantity='1',policy=dict(max_holding_ms=60000)),request={},thesis_valid=True,
        decision=dict(status='admitted',execution=dict(fill=dict(price='102.2',quantity='1',fee_usdt='0.0511',source_event_id=2,execution_as_of_ms=STAMP))),
        paper_outcome=dict(status='open' if phase=='paper_open' else 'closed',funding_usdt='0',state=dict(levels=dict(stop='100.98',target='104.04'))))
    signals=[signal]
    if extra: signals.append(dict(signal,signal_id=extra,candidate_id='e'*64))
    return FrozenRecord.create(dict(kind='paper_cycle',deployment_hash=h['deployment_hash'],as_of_ms=when,source_count=1,source_prefix_hash='0'*64,source_cursor=[when,1],
        paper_account=AccountSnapshot(when,when,cash,cash).document(),signals=signals,health=dict(ready=health,reasons=[] if health else ['missing_feed']),live_approved=False))


def ready(head,signal,when):
    return dict(ready=True,deferred=False,reasons=[],checked_ms=when,prediction=dict(uncertainty=dict(lower_mean_net_r='0.5')),execution=dict(costs=dict(execution_plus_fee_cost_usdt='0.1')))
