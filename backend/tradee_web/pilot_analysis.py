"""Native quick-flow adapter over the same structural detector used by research."""
from collections import Counter

from tradee.c01.domain import fingerprint
from tradee.pilots.contracts import BAR,FAMILIES,PRIORITY
from tradee.c08.pilots import PilotEngine
from tradee.pilots.execution import qualify


def evaluate_pilots(rows,spec,scan_start,*,symbol,tick_size,live_start_ms=0,evidence=None,now_ms=0,clock=None):
    families=[f for f in spec['strategies'] if f in FAMILIES]
    engine=PilotEngine(symbol,tick_size,start_seed_ms=live_start_ms,families=families)
    setups=[]; features=[]
    for source in rows:
        r=dict(source)
        if spec['mode']=='history':
            # An explicitly modeled historical clock; receipt stays in AnalysisStore revisions.
            r['available_ms']=r['open_ms']+BAR
        for plan in engine.advance(r):
            if plan['open_ms']<scan_start: continue
            plan['levels']=[dict(label='Frozen setup level',price=plan['trigger_level'],
                confirmed_ms=plan['level_confirmed_ms'],known_ms=plan['level_known_ms'] or plan['seed_ms'])]
            plan['strategy_name']={FAMILIES[0]:'Liquidity sweep',FAMILIES[1]:'200 EMA rejection',FAMILIES[2]:'Key-level retest'}[plan['strategy']]
            plan['explanation']=f"{plan['mode']} · closed-bar confirmation; structural stop {plan['stop']}, target {plan['target']}. Execution must be checked separately."
            if spec['mode']=='live' and evidence is not None:
                ev=evidence(plan); assessed=clock() if clock else now_ms
                plan['metadata_version_hash']=(ev.get('metadata') or {}).get('version_hash')
                assessment=qualify(plan,ev,assessed,context=engine.context,purpose='notification')
                plan['assessment']=assessment; plan['qualification']='qualified' if assessment['qualified'] else 'blocked'
                plan['reasons']=assessment['reasons']
            else:
                plan['qualification']='execution_unchecked'; plan['reasons']=['historical_execution_unchecked']
            setups.append(plan)
        v=engine.context.values[-1]
        features.append(dict(target_open_ms=r['open_ms'],values={name:dict(value=float(v[name]) if v[name] is not None else None,
            stable=v['stable'],status='valid' if v[name] is not None else 'insufficient_history') for name in ('ema20','ema50','ema200')}))
    # Only already-qualified plans participate in overlap selection. All other patterns remain diagnostic.
    grouped={}
    for p in setups:
        if p['qualification']=='qualified': grouped.setdefault(p['end_ms'],[]).append(p)
    for plans in grouped.values():
        if len({p['side'] for p in plans})>1:
            for p in plans: p.update(qualification='blocked',reasons=['direction_conflict'])
            continue
        ordered=sorted(plans,key=lambda p:(PRIORITY[p['strategy']],p['opportunity_id']))
        ordered[0]['family_tags']=sorted({p['strategy'] for p in plans})
        for p in ordered[1:]: p.update(qualification='blocked',reasons=['overlap'])
    c=engine.context
    ready=bool(c.values and c.values[-1]['stable'] and c.hour.values and c.hour.values[-1]['stable'])
    current=c.values[-1] if c.values else {}
    return dict(setups=setups,features=features[-500:],readiness={f:ready for f in families},
        pilot=dict(state=c.state,dull=current.get('dull',True),shock=c.shock_wait,execution='strict checks required',
                   reasons=dict(engine.reasons),hourly_bars=c.hour.count,execution_bars=c.exec.count,
                   qualification_counts=dict(Counter(p['qualification'] for p in setups)),
                   availability='modeled historical clock' if spec['mode']=='history' else 'recorded receipt clocks'),
        _engine=engine)


def save_attempts(db,workspace,uid,symbol,attempts):
    for a in attempts:
        db.execute('INSERT OR IGNORE INTO pilot_attempts VALUES(?,?,?,?,?,?,?,?)',
                   (workspace,symbol,a['level_id'],a['side'],a['day'],a['seed_ms'],a['family'],uid))


def claim_bundle(db,workspace,uid,signal):
    """One durable workspace-wide claim, regardless of Telegram enablement/result."""
    if signal.get('level_id'):
        owner=db.execute('SELECT seed_ms,family,session_id FROM pilot_attempts WHERE workspace=? AND symbol=? AND level_id=? AND side=? AND day=?',
            (workspace,signal['symbol'],signal['level_id'],signal['side'],signal['seed_ms']//86400000)).fetchone()
        if not owner or (owner['seed_ms'],owner['family'],owner['session_id'])!=(signal['seed_ms'],signal['strategy'],uid): return 'opportunity_consumed'
    prior=db.execute('SELECT MAX(end_ms) FROM pilot_bundles WHERE workspace=? AND symbol=?',(workspace,signal['symbol'])).fetchone()[0]
    if prior is not None and signal['end_ms']<prior+4*BAR: return 'cooldown'
    tags=signal.get('family_tags',[signal['strategy']]); day=signal['end_ms']//86400000
    for tag in tags:
        n=db.execute('SELECT count(*) FROM pilot_bundle_tags WHERE workspace=? AND symbol=? AND family=? AND day=?',
                     (workspace,signal['symbol'],tag,day)).fetchone()[0]
        if n>=3: return 'family_cap'
    db.execute('INSERT INTO pilot_bundles VALUES(?,?,?,?,?)',(workspace,signal['symbol'],signal['end_ms'],signal['side'],signal['id']))
    for tag in tags: db.execute('INSERT INTO pilot_bundle_tags VALUES(?,?,?,?,?,?)',(workspace,signal['symbol'],tag,day,signal['end_ms'],signal['id']))
    return None
