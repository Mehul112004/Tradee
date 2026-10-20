"""Real raw-input C01--C15 E2E; no credentials, Telegram sends or orders."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from scripts.verify_c14 import prepare,runtime,ROOT,LIVE,BIN,ScriptedTelegram
from scripts.verify_c13 import write
from tradee.c14 import Dispatcher,DeliveryResult
from tradee.c15 import MonitorStore,ForwardMonitor


def run_e2e(root):
    root=Path(root).resolve(); prior,feed,spec,cals=prepare(root); commands=[]
    def invoke(component,*args,expected=0):
        env=dict(os.environ); env.pop('TRADEE_TELEGRAM_BOT_TOKEN',None)
        options=['--market-db',str(root/'research/c02.sqlite3'),'--simulation-db',str(root/'research/c11.sqlite3'),
            '--portfolio-db',str(root/'research/c13.sqlite3'),'--signal-db',str(root/'c14.sqlite3')]
        options+=['--research-db',str(root/'research/c12.sqlite3')] if component=='signals' else ['--monitor-db',str(root/'c15.sqlite3')]
        p=subprocess.run([sys.executable,'-m','tradee','--db',str(root/'research/c01.sqlite3'),component,*options,*map(str,args)],
            env=env,cwd=ROOT,capture_output=True,text=True,timeout=180)
        commands.append(dict(component=component,args=list(map(str,args)),exit_code=p.returncode)); write(root,'c15_commands.json',commands)
        if p.returncode!=expected: raise AssertionError(f'C15 E2E exit {p.returncode}, expected {expected}: {(p.stderr or p.stdout)[:1800]}')
        return json.loads(p.stdout or p.stderr)
    created=invoke('signals','create','--spec',root/'session.json','--experiment',prior['experiment_hash'],'--portfolio-run',prior['baseline']['run_hash'],'--calendar',root/'calendar.json')
    policy=dict(review_times_ms=[LIVE+BIN+2,LIVE+3*BIN+2],maturity_lag_ms=0,min_mature=2,min_occupied_spans=2,
        bin_ms=BIN,block_bins=1,bootstrap_replicates=200,alpha='0.1')
    write(root,'monitor_policy.json',policy)
    registered=invoke('monitor','create','forward','--session','paper_demo','--policy',root/'monitor_policy.json','--at-ms',LIVE)
    if invoke('monitor','create','forward','--session','paper_demo','--policy',root/'monitor_policy.json','--at-ms',LIVE)!=registered: raise AssertionError('Registration is not idempotent')
    s,r=runtime(root,feed); first_report=None; paused_report=None
    for k in range(3):
        feed.bars(k); invoke('signals','tick','paper_demo','--at-ms',feed.clock[0])
        detected=invoke('monitor','observe','forward','--at-ms',feed.clock[0]+1,expected=2)
        if any(x['status']=='mature' and x['detected_ms']>=LIVE+k*BIN for x in detected['rows']): raise AssertionError('Future outcomes leaked into detection')
        feed.entry(k); invoke('signals','tick','paper_demo','--at-ms',feed.clock[0])
        entry=invoke('monitor','observe','forward','--at-ms',feed.clock[0]+1,expected=0 if k==0 else 2)
        if k==0:
            first_report=entry
            if any(x['status']=='mature' for x in entry['rows']): raise AssertionError('Entry exposed a future label')
            wire=ScriptedTelegram([DeliveryResult('sent','telegram_accepted',message_id=555)])
            if Dispatcher(s,clock=lambda:feed.clock[0]/1000).send_one('paper_demo',r.preflight,wire)['status']!='sent': raise AssertionError('Scripted acceptance failed')
            delivery=invoke('monitor','observe','forward','--at-ms',feed.clock[0]+2)
            if delivery['telemetry']['delivery_states']!={'sent':1}: raise AssertionError('Delivery telemetry missing')
            paused_report=invoke('monitor','observe','forward','--at-ms',feed.clock[0]+30001,'--apply-pauses',expected=2)
            if not s.session('paper_demo')['paused']: raise AssertionError('Declared operational pause not applied')
        feed.close(k); feed.price(feed.clock[0],'100'); invoke('signals','tick','paper_demo','--at-ms',feed.clock[0])
        closed=invoke('monitor','observe','forward','--at-ms',feed.clock[0]+3,expected=2)
        if closed['summary']['portfolio']['statuses'].get('mature')!=k+1: raise AssertionError('Mature admitted outcomes missing')
    final=closed
    if final['summary']['portfolio']['mature_net_usdt']!='8.489': raise AssertionError('Funded labels do not reconcile to wallet')
    if final['summary']['independent']['count']!=6: raise AssertionError('Rejected independent outcomes missing')
    if final['reviews'][0]['status']!='insufficient_evidence' or len(final['reviews'])!=2: raise AssertionError('Fixed review schedule changed')
    replay=invoke('monitor','reconcile','forward','--at-ms',feed.clock[0]+3)
    if not all(replay['checks'].values()): raise AssertionError('Pinned raw production replay differs')
    exported=invoke('monitor','export','forward'); write(root,'forward_dataset.json',exported)
    if len(exported['rows'])!=9 or any(x['actual_user_fill'] for x in exported['rows']): raise AssertionError('Forward export mixed/omitted tracks')
    historical=invoke('monitor','artifact',first_report['report_hash'])
    if any(x['status']=='mature' for x in historical['rows']): raise AssertionError('Historical report was rewritten')
    receipt=invoke('monitor','apply-pause','forward','--report',paused_report['report_hash'],'--at-ms',feed.clock[0]+3)
    if receipt!=paused_report['pause_receipt']: raise AssertionError('Cross-store pause recovery/idempotence failed')
    feed.save(); write(root,'scripted_telegram.json',wire.calls)
    result=dict(passed=True,commands=len(commands),prior_research_commands=prior['commands'],deployment_hash=created['deployment_hash'],
        manifest_hash=registered['manifest_hash'],first_report_hash=first_report['report_hash'],final_report_hash=final['report_hash'],
        reconciliation=replay,paper_account=s.session('paper_demo')['cycle']['paper_account'],summary=final['summary'],reviews=final['reviews'],
        checks=['Raw C01--C14 lineage and prospective C15 policy registration','No future outcome at detection/admission','Rejected signals retained as independent shadow outcomes',
            'Separate funded book and independent labels','Audited delivery acceptance without claiming actual user fills','Immediate stale-cycle pause with revision CAS',
            'Paused delivery does not halt the shared paper outcome book','Mature revision export and immutable historical reports',
            'Fixed predeclared reviews retain insufficient early evidence','Full raw-input C11 and C13 replay hash reconciliation','Crash-gap pause receipt recovery; no automatic resume'],
        note='Synthetic engineering evidence. Test evidence minimums are intentionally small. No profitability, live promotion or actual Telegram/crypto execution validation.')
    write(root,'c15_e2e_report.json',result); return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',required=True); args=parser.parse_args()
    print(json.dumps(run_e2e(args.output),indent=2))
