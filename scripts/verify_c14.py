"""Raw production C01--C14 paper notification E2E; Telegram network is scripted.

No credentials are read and no external messages or exchange orders are sent.
The preceding C13 E2E supplies a real frozen C12 research/compatibility release.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from decimal import Decimal
from scripts.verify_c13 import run_e2e as research_e2e,write,START,BIN,ROOT
from tradee.c01 import Registry,Policy
from tradee.c02 import MarketStore
from tradee.c11 import SimulationStore
from tradee.c12 import ResearchStore
from tradee.c13 import PortfolioStore
from tradee.c14 import SignalStore,SignalRuntime,RuntimeConfig,SessionSpec,Dispatcher,DeliveryResult,load_release

LIVE=START+17*BIN
BOT=123456789
CHAT=-1001234567890


class SyntheticFeed:
    def __init__(self,root,clock=None):
        self.root=Path(root); self.clock=clock or [LIVE-60000]; self.receipts=[]
        self.registry=Registry(self.root/'research/c01.sqlite3',clock=lambda:self.clock[0]/1000)
        self.market=MarketStore(self.registry,self.root/'research/c02.sqlite3',clock=lambda:self.clock[0]/1000)
    def initialize(self):
        raw=json.loads((self.root/'research/metadata.json').read_text()); self.clock[0]=LIVE-60000
        self.registry.ingest(json.dumps(raw),source='synthetic:C14 prospective metadata')
        self.candle(LIVE-60000,'100')
    def candle(self,opened,price):
        p=Decimal(price); self.clock[0]=opened+60000
        row=[opened,price,str(p+1),str(p-1),price,'1000',opened+59999,str(p*1000),5,'700',str(p*700),'0']
        for symbol in ('BTCUSDT','ETHUSDT'):
            self.market.ingest_rest(json.dumps([row]),symbol); self.receipts.append(dict(received_ms=self.clock[0],kind='candle',symbol=symbol,raw=row))
    def bars(self,k):
        for j,price in enumerate(('100','100','102')): self.candle(LIVE+(4*k+j)*60000,price)
    def price(self,stamp,price,trigger=False):
        self.clock[0]=stamp; p=Decimal(price)
        for symbol in ('BTCUSDT','ETHUSDT'):
            rows=[dict(e='markPriceUpdate',E=stamp,s=symbol,p=price,i=price,r='0.001',T=stamp+3600000)]
            if trigger: rows.append(dict(e='aggTrade',E=stamp,T=stamp,s=symbol,a=stamp,f=stamp,l=stamp,p=price,q='1',m=False))
            rows.append(dict(e='bookTicker',E=stamp,T=stamp,s=symbol,u=stamp,b=str(p-Decimal('0.1')),a=str(p+Decimal('0.1')),B='10',A='10'))
            for row in rows: self.market.ingest_ws(json.dumps(row)); self.receipts.append(dict(received_ms=stamp,kind=row['e'],raw=row))
    def entry(self,k=0): self.price(LIVE+k*BIN+181000,'102')
    def close(self,k=0):
        self.price(LIVE+k*BIN+220000,'105' if k%2==0 else '106',True)
        self.candle(LIVE+k*BIN+180000,'100')
    def save(self): (self.root/'live_receipts.jsonl').write_text('\n'.join(json.dumps(r) for r in self.receipts)+'\n')


class ScriptedTelegram:
    bot_id=BOT
    def __init__(self,results): self.results=list(results); self.calls=[]
    def send(self,chat,text,timeout_ms):
        self.calls.append(dict(chat_id=chat,text=text,timeout_ms=timeout_ms))
        result=self.results.pop(0)
        if isinstance(result,BaseException): raise result
        return result


def prepare(root):
    root=Path(root).resolve(); root.mkdir(parents=True,exist_ok=True)
    if (root/'research').exists(): raise ValueError('C14 E2E needs a fresh directory')
    prior=research_e2e(root/'research'); feed=SyntheticFeed(root); feed.initialize()
    cfg=RuntimeConfig(mode='paper_test',bot_id=BOT,chat_id=CHAT,source_settle_ms=0,max_cycle_age_ms=30000)
    spec=SessionSpec('paper_demo',LIVE,LIVE+3*BIN,LIVE-60000,180000,cfg.document())
    universe=feed.registry.universe(Policy(('BTCUSDT','ETHUSDT')),LIVE)
    calendars=[dict(instrument_id=d['instrument_id'],symbol=d['symbol'],start_ms=spec.warmup_start_ms,end_ms=spec.tail_end_ms,settlement_times_ms=[],evidence='operator_assumption:synthetic no-settlement prospective window') for d in universe['decisions'] if d['symbol'] in ('BTCUSDT','ETHUSDT')]
    write(root,'session.json',spec.document()); write(root,'calendar.json',dict(calendars=calendars))
    return prior,feed,spec,calendars


def runtime(root,feed):
    root=Path(root); s=SignalStore(root/'c14.sqlite3')
    return s,SignalRuntime(s,feed.market,SimulationStore(root/'research/c11.sqlite3'),PortfolioStore(root/'research/c13.sqlite3'))


def run_e2e(root):
    root=Path(root).resolve(); prior,feed,spec,cals=prepare(root); commands=[]
    def invoke(*args,expected=0):
        env=dict(os.environ); env.pop('TRADEE_TELEGRAM_BOT_TOKEN',None); env.pop('TELEGRAM_BOT_TOKEN',None); env['PYTHON_DOTENV_DISABLED']='1'
        p=subprocess.run([sys.executable,'-m','tradee','--db',str(root/'research/c01.sqlite3'),'signals','--market-db',str(root/'research/c02.sqlite3'),'--simulation-db',str(root/'research/c11.sqlite3'),
            '--research-db',str(root/'research/c12.sqlite3'),'--portfolio-db',str(root/'research/c13.sqlite3'),'--signal-db',str(root/'c14.sqlite3'),*map(str,args)],env=env,cwd=ROOT,capture_output=True,text=True,timeout=180)
        commands.append(dict(args=list(map(str,args)),exit_code=p.returncode)); write(root,'e2e_commands.json',commands)
        if p.returncode!=expected: raise AssertionError(f'C14 exit {p.returncode}, expected {expected}: {(p.stderr or p.stdout)[:2000]}')
        return json.loads(p.stdout or p.stderr)
    invoke('explain'); created=invoke('create','--spec',root/'session.json','--experiment',prior['experiment_hash'],'--portfolio-run',prior['baseline']['run_hash'],'--calendar',root/'calendar.json')
    if invoke('create','--spec',root/'session.json','--experiment',prior['experiment_hash'],'--portfolio-run',prior['baseline']['run_hash'],'--calendar',root/'calendar.json')!=created: raise AssertionError('Deployment changed on retry')
    s,r=runtime(root,feed); dispatcher=Dispatcher(s,clock=lambda:feed.clock[0]/1000)
    feed.bars(0); detected=invoke('tick','paper_demo','--at-ms',feed.clock[0])
    if len(detected['cycle']['signals'])!=2 or any(x['delivery'] for x in s.signals('paper_demo')): raise AssertionError('Detected candidates were notified before paper execution')
    feed.entry(0); first=invoke('tick','paper_demo','--at-ms',feed.clock[0]); rows=s.signals('paper_demo'); pending=next(x for x in rows if x['delivery'] and x['delivery']['state']=='pending'); sid=pending['signal']['signal_id']
    if first['cycle']['paper_account']['cash_usdt']!='319.9489': raise AssertionError('Paper entry fee/cash mismatch')
    if invoke('tick','paper_demo','--at-ms',feed.clock[0])!=first: raise AssertionError('Same prefix tick changed')
    invoke('status','paper_demo','--at-ms',feed.clock[0]); invoke('send','paper_demo','--send-paper',expected=1)
    wire=ScriptedTelegram([DeliveryResult('retry','telegram_rate_limited',retry_after_ms=1000),DeliveryResult('ambiguous','network_outcome_unknown')])
    if dispatcher.send_one('paper_demo',r.preflight,wire)['status']!='retry_wait': raise AssertionError('429 retry was not durable')
    feed.clock[0]+=1000
    if dispatcher.send_one('paper_demo',r.preflight,wire)['status']!='throttled': raise AssertionError('Chat throttle ignored')
    feed.clock[0]+=2500
    if dispatcher.send_one('paper_demo',r.preflight,wire)['status']!='ambiguous': raise AssertionError('Timeout not marked ambiguous')
    if dispatcher.send_one('paper_demo',r.preflight,wire)['status']!='idle' or len(wire.calls)!=2: raise AssertionError('Unknown delivery was auto-retried')
    invoke('reconcile',sid,'--decision','sent','--message-id',777,'--evidence','Synthetic operator acceptance assertion','--at-ms',feed.clock[0])
    if invoke('signal',sid)['delivery']['state']!='resolved_sent': raise AssertionError('Explicit reconciliation missing')
    feed.close(0); invoke('tick','paper_demo','--at-ms',feed.clock[0])
    feed.bars(1); feed.entry(1); invoke('tick','paper_demo','--at-ms',feed.clock[0]); crash=ScriptedTelegram([KeyboardInterrupt()])
    try: dispatcher.send_one('paper_demo',r.preflight,crash)
    except KeyboardInterrupt: pass
    else: raise AssertionError('Injected abrupt worker loss did not occur')
    inflight=next(x for x in s.signals('paper_demo') if x['delivery'] and x['delivery']['state']=='in_flight'); lost=inflight['signal']['signal_id']
    feed.clock[0]+=spec.runtime.lease_ms; s,r=runtime(root,feed); dispatcher=Dispatcher(s,clock=lambda:feed.clock[0]/1000)
    invoke('recover','paper_demo','--at-ms',feed.clock[0])
    if s.signal(lost)['delivery']['state']!='ambiguous': raise AssertionError('Lost in-flight attempt was retried or forgotten')
    if dispatcher.send_one('paper_demo',r.preflight,ScriptedTelegram([]))['status']!='idle': raise AssertionError('Restart retried unknown HTTP outcome')
    invoke('reconcile',lost,'--decision','not_sent','--evidence','Synthetic definitive non-acceptance assertion after expiry','--at-ms',feed.clock[0])
    if s.signal(lost)['delivery']['state']!='expired': raise AssertionError('Expired reconciliation revived stale notice')
    feed.close(1); feed.bars(2); feed.entry(2); invoke('tick','paper_demo','--at-ms',feed.clock[0])
    invoke('pause','paper_demo','--reason','Synthetic operational pause','--at-ms',feed.clock[0]); feed.clock[0]+=100
    invoke('resume','paper_demo','--reason','Synthetic operational recovery','--at-ms',feed.clock[0]); invoke('tick','paper_demo','--at-ms',feed.clock[0])
    if any(x['delivery'] and x['delivery']['state'] in ('pending','retry_wait') for x in s.signals('paper_demo')): raise AssertionError('Resume resurrected suppressed notices')
    feed.close(2); final=invoke('tick','paper_demo','--at-ms',feed.clock[0]); invoke('session','paper_demo'); invoke('list','paper_demo'); audit=invoke('events','paper_demo'); invoke('artifact',final['cycle_hash'])
    if final['cycle']['paper_account']['cash_usdt']!='328.489' or final['cycle']['paper_account']['positions']: raise AssertionError('Full funded paper book does not reconcile')
    if len([x for x in audit if x['kind']=='outbox_claimed'])!=3: raise AssertionError('Duplicate or missing delivery claims')
    if any('NO TRADE INSTRUCTION' not in c['text'] or sid not in c['text'] for c in wire.calls): raise AssertionError('Notice semantics or stable signal reference missing')
    feed.save(); write(root,'scripted_telegram.json',wire.calls)
    result=dict(passed=True,commands=len(commands),prior_research_commands=prior['commands'],deployment_hash=created['deployment_hash'],final_cycle_hash=final['cycle_hash'],
        paper_account=final['cycle']['paper_account'],delivery_states={x['signal']['signal_id']:x['delivery']['state'] for x in s.signals('paper_demo') if x['delivery']},
        checks=['Real frozen C12 release and counted C13 recipe','Raw prospective C02 receipts through production shared pipeline','Detected, suppressed, paper-open and paper-closed lifecycle',
            'Atomic paper state/signal/outbox and deterministic prefix retry','Fresh C07/C10/risk checks and unchanged tested entry economics','Explicit 429 retry and persistent chat throttle',
            'Timeout ambiguity without automatic resend','Abrupt in-flight process loss and restart reconciliation','Expired non-acceptance cannot resurrect a notice','Pause/resume without stale replay',
            'Exact funded cash and fee reconciliation','Stable paper-only message, no token storage and zero real external sends'],
        note='Synthetic engineering E2E, not real-market profitability, authenticated user execution or Telegram service acceptance. The production transport is tested separately with scripted HTTPS responses. Paper-fill notices are informational, not pre-entry trade instructions. C12 portfolio-policy inference/C15/operational gates remain.')
    write(root,'e2e_report.json',result); return result


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',required=True); a=p.parse_args(); print(json.dumps(run_e2e(a.output),indent=2))
