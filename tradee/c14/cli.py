"""Explicit foreground paper runner and opt-in test Telegram dispatcher."""
import json
import re
from pathlib import Path
import time
from tradee.c01 import Registry,ValidationError
from tradee.c02 import MarketStore
from tradee.c11 import SimulationStore
from tradee.c12 import ResearchStore
from tradee.c13 import PortfolioStore
from tradee.environment import load_environment
from .contracts import SessionSpec,RuntimeConfig
from .message import utc
from .release import load_release
from .store import SignalStore
from .pipeline import SignalRuntime
from .delivery import Dispatcher
from .telegram import TelegramTransport


def read(path): return json.loads(Path(path).read_text())


def register(sub):
    p=sub.add_parser('signals',help='C14 recorded-live shadow/paper notifications, persistent outbox and recovery')
    for name,default in (('market','data/c02.sqlite3'),('simulation','data/c11.sqlite3'),('research','data/c12.sqlite3'),('portfolio','data/c13.sqlite3'),('signal','data/c14.sqlite3')):
        p.add_argument('--'+name+'-db',default=default)
    actions=p.add_subparsers(dest='signal_command',required=True); actions.add_parser('explain')
    a=actions.add_parser('create'); a.add_argument('--spec',required=True); a.add_argument('--experiment',required=True); a.add_argument('--portfolio-run',required=True); a.add_argument('--calendar')
    for name in ('status','session','list','events','tick','recover'):
        a=actions.add_parser(name); a.add_argument('name')
        if name in ('status','tick','recover'): a.add_argument('--at-ms',type=int)
    for name in ('signal','artifact'): actions.add_parser(name).add_argument('hash')
    for name in ('pause','resume'):
        a=actions.add_parser(name); a.add_argument('name'); a.add_argument('--reason',required=True); a.add_argument('--at-ms',type=int)
    a=actions.add_parser('send'); a.add_argument('name'); a.add_argument('--send-paper',action='store_true',required=True)
    a=actions.add_parser('watch'); a.add_argument('name'); a.add_argument('--interval-seconds',type=float,default=1); a.add_argument('--max-cycles',type=int); a.add_argument('--send-paper',action='store_true')
    a=actions.add_parser('reconcile'); a.add_argument('hash'); a.add_argument('--decision',choices=('sent','not_sent'),required=True); a.add_argument('--evidence',required=True); a.add_argument('--message-id',type=int); a.add_argument('--at-ms',type=int)
    a=actions.add_parser('telegram-test'); a.add_argument('--bot-id',type=int,help='Defaults to configured token prefix'); a.add_argument('--chat-id',type=int,help='Defaults to TELEGRAM_CHAT_ID'); a.add_argument('--test-id',required=True); a.add_argument('--send-paper',action='store_true',required=True)


def execute(args):
    action=args.signal_command
    if action=='explain': return dict(component='C14',runtime=RuntimeConfig().document(),live_approved=False,
        operation='Bounded full-prefix C02 replay through production C03/C08/C07/C06/C09/C10/C13; atomic paper state + signal + outbox',
        modes='shadow or clearly labelled PAPER TEST evaluated-fill notifications; actionable live promotion remains blocked',
        telegram='Explicit frozen numeric bot/chat for sessions; token from TRADEE_TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN in environment/root .env; --send-paper opt-in; never automatically retry unknown HTTP outcomes')
    if action=='telegram-test':
        env=load_environment()
        try:
            bot_id=args.bot_id if args.bot_id is not None else int(env.telegram_token.partition(':')[0])
            chat_id=args.chat_id if args.chat_id is not None else int(env.telegram_chat_id)
        except ValueError:
            raise ValidationError('Configured Telegram credential and numeric test destination required') from None
        cfg=RuntimeConfig(mode='paper_test',bot_id=bot_id,chat_id=chat_id)
        if not re.fullmatch('[A-Za-z0-9_-]{1,64}',args.test_id): raise ValidationError('Short public Telegram connectivity test identifier required')
        transport=TelegramTransport(env.telegram_token,cfg.bot_id)
        text='Tradee PAPER TEST connectivity check\nNO TRADE INSTRUCTION\nTest: '+args.test_id+'\nSent at: '+utc(int(time.time()*1000))
        result=transport.send(cfg.chat_id,text,cfg.http_timeout_ms)
        return dict(ready=result.status=='sent',test_id=args.test_id,bot_id=cfg.bot_id,chat_id=cfg.chat_id,result=result.document(),live_approved=False,
                    scope='One explicitly requested connectivity attempt; no strategy, account, outbox or automatic retry. Acceptance is not user receipt.')
    paths=[Path(p).resolve() for p in (args.db,args.market_db,args.simulation_db,args.research_db,args.portfolio_db,args.signal_db)]
    if len(set(paths))!=len(paths): raise ValidationError('C01/C02/C11/C12/C13/C14 stores must differ')
    s=SignalStore(args.signal_db,forbidden_paths=paths[:-1]); now=lambda:int(time.time()*1000)
    if action=='create':
        if not all(p.is_file() for p in paths[:-1]): raise ValidationError('Existing C01/C02/C11/C12/C13 evidence stores required')
        calendars=[] if args.calendar is None else read(args.calendar)['calendars']
        return s.create(load_release(ResearchStore(args.research_db),PortfolioStore(args.portfolio_db),SimulationStore(args.simulation_db),args.experiment,args.portfolio_run,SessionSpec.from_dict(read(args.spec)),calendars))
    if action in ('session','events'): return getattr(s,action)(args.name)
    if action=='list': return s.signals(args.name)
    if action in ('signal','artifact'): return getattr(s,action)(args.hash)
    if action=='status': return s.status(args.name,now() if args.at_ms is None else args.at_ms)
    if action in ('pause','resume'): return s.pause(args.name,action=='pause',args.reason,now() if args.at_ms is None else args.at_ms)
    if action in ('recover','reconcile'):
        stamp=now() if args.at_ms is None else args.at_ms; dispatcher=Dispatcher(s,clock=lambda:stamp/1000)
        return dispatcher.recover(args.name,stamp) if action=='recover' else dispatcher.reconcile(args.hash,args.decision,args.evidence,args.message_id)
    if not all(p.is_file() for p in (paths[0],paths[1],paths[2],paths[4])): raise ValidationError('Existing C01/C02/C11/C13 input stores required')
    runtime=SignalRuntime(s,MarketStore(Registry(args.db),args.market_db),SimulationStore(args.simulation_db),PortfolioStore(args.portfolio_db))
    if action=='tick': return runtime.tick(args.name,now() if args.at_ms is None else args.at_ms)
    head=s.session(args.name); cfg=SessionSpec.from_dict(head['manifest']['spec']).runtime; transport=None
    if args.send_paper:
        if cfg.mode!='paper_test': raise ValidationError('Explicit paper_test deployment required for Telegram')
        transport=TelegramTransport(load_environment().telegram_token,cfg.bot_id)
    dispatcher=Dispatcher(s)
    if action=='send':
        runtime.tick(args.name,now()-cfg.source_settle_ms)
        return dispatcher.send_one(args.name,runtime.preflight,transport)
    if not 0.1<=args.interval_seconds<=60 or (args.max_cycles is not None and (type(args.max_cycles) is not int or args.max_cycles<=0)): raise ValidationError('Bounded positive watch interval/cycle count required')
    count=0; stopped='cycle_limit'
    try:
        while args.max_cycles is None or count<args.max_cycles:
            stamp=now(); spec=SessionSpec.from_dict(s.session(args.name)['manifest']['spec'])
            if stamp-cfg.source_settle_ms<spec.start_ms:
                result=dict(state='awaiting_session_start',start_ms=spec.start_ms)
            elif stamp-cfg.source_settle_ms>spec.tail_end_ms:
                s.fault(args.name,'session_tail_elapsed',stamp); stopped='session_tail_elapsed'; break
            else:
                try:
                    runtime.tick(args.name,stamp-cfg.source_settle_ms); dispatcher.recover(args.name)
                    result=s.status(args.name,now())
                    if transport is not None: result['dispatch']=dispatcher.send_one(args.name,runtime.preflight,transport)
                except Exception:
                    s.fault(args.name,'pipeline_failed',now()); result=dict(ready=False,reasons=['pipeline_failed'])
            print(json.dumps(result,sort_keys=True),flush=True); count+=1
            if args.max_cycles is None or count<args.max_cycles: time.sleep(args.interval_seconds)
    except KeyboardInterrupt: stopped='operator_interrupt'
    return dict(stopped=stopped,cycles=count,live_approved=False)
