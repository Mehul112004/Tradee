"""Bounded prospective replay of the production C03/C08/C07/C06/C09/C10/C13 path.

Each tick rebuilds a complete immutable prefix. C14 persists its watermark,
book and notices atomically; no historical measuring component calls C14.
"""
from copy import deepcopy
from decimal import Decimal
import platform
import time
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c02.domain import integer
from tradee.c03.contracts import FrozenRecord
from tradee.c03 import FeatureEngine
from tradee.c06 import FundingConfig
from tradee.c06.engine import code_hash
from tradee.c07 import ExecutionEngine,ExecutionConfig,FeeSchedule
from tradee.c08 import CandidateConfig
from tradee.c08.contracts import FAMILY
from tradee.c09 import TradePolicy
from tradee.c08.metadata import capture
from tradee.c10 import EstimateRequest
from tradee.c10.engine import estimate
from tradee.c11 import SimulationConfig,Scenario
from tradee.c13 import PortfolioReplay,RiskPolicy,ReplayConfig,Offer,AccountSnapshot
from tradee.c13.risk import inspect
from tradee.c13.replay import public_risk
from .contracts import SessionSpec


def source_prefix(events):
    h=fingerprint([])
    for e in events: h=fingerprint([h,fingerprint(e)])
    return h


def feed_health(events,when,manifest):
    cfg=ExecutionConfig.from_dict(manifest['execution']); reasons=[]; latest={}
    for e in events:
        if e['final']:
            k=(e['symbol'],e['kind']); old=latest.get(k)
            if old is None or (e['event_ms'],e['available_ms'],e['id'])>(old['event_ms'],old['available_ms'],old['id']): latest[k]=e
    for symbol in cfg.enabled_symbols:
        for kind,age in (('quote',cfg.max_quote_age_ms),('mark',cfg.max_mark_age_ms),('candle',60000+cfg.candle_grace_ms)):
            e=latest.get((symbol,kind)); stamp=None if e is None else (e['data']['close_ms']+1 if kind=='candle' else e['event_ms'])
            if e is None or stamp>when or e['available_ms']>when or when-stamp>=age or when-e['available_ms']>=age: reasons.append(symbol+':missing_or_stale_'+kind)
    return dict(ready=not reasons,reasons=reasons)


def thesis_ok(detector,c,when):
    rows=detector.features.bars.get((c['instrument_id'],c['timeframe']),{})
    if not rows: return False
    row=rows[max(rows)]['data']; sign=1 if c['side']=='long' else -1
    if c['hypothesis_family']==FAMILY: return sign*(Decimal(row['close'])-Decimal(c['breakout_level']))>0
    f=detector.features.evaluate(c['instrument_id'],c['timeframe'],when).document()
    fast,slow=(f['values'][k] for k in ('ema20','ema50'))
    return all(v['status']=='valid' and v['stable'] for v in (fast,slow)) and sign*(fast['value']-slow['value'])>0 and sign*(float(row['close'])-fast['value'])>0


def position_prefix_requires_tick(events,cycle,when):
    """Allow benign trigger observations; defer anything changing/obscuring cash or size.

    C03 does not change on trades/marks. Fresh C07 and mark-risk checks still
    run below. C09 remains authoritative for triggers, reductions and timers.
    """
    if any(e['kind'] in ('candle','funding') for e in events): return True
    exposed={p['instrument_id'] for p in cycle['paper_account']['positions']}
    marks={m['instrument_id']:m['price'] for m in cycle['paper_account']['marks']}
    # Changed marks can alter the book's intraprefix peak/drawdown even if
    # the final price returns unchanged; let C13 replay that complete path.
    if any(e['kind']=='mark' and e['instrument_id'] in exposed and e['data']['mark_price']!=marks.get(e['instrument_id']) for e in events): return True
    for signal in cycle['signals']:
        if signal['phase']!='paper_open': continue
        state=signal['paper_outcome']['state']; policy=TradePolicy.from_dict(signal['trade_intent']['policy'])
        if state['status']!='open' or state['exit_pending'] is not None or when>=state['entry_ms']+policy.max_holding_ms: return True
        if set(state['ambiguity_flags'])-{'unresolved_data_tail'}: return True
        wanted={'contract_trade':'trade','mark':'mark','bar_close':'candle','bar_range':'candle'}[policy.trigger_source]
        last=state['last_trigger_ms']; last_key=state['last_trigger_key']; sign=1 if state['side']=='long' else -1
        for e in events:
            if e['instrument_id']!=state['instrument_id'] or e['kind']!=wanted or not e['final'] or e['event_ms']<state['entry_ms']: continue
            stamp=e['event_ms']; key=int(e['key']) if wanted=='trade' else None
            if (last is not None and (stamp<last or stamp==last and (wanted!='trade' or key<=last_key))
                    or when-stamp>=policy.max_trigger_age_ms or stamp-(last if last is not None else state['entry_ms'])>policy.max_path_gap_ms): return True
            price=Decimal(e['data']['price' if wanted=='trade' else 'mark_price']); levels=state['levels']
            if sign*(price-Decimal(levels['stop']))<=0 or sign*(price-Decimal(levels['target']))>=0: return True
            if levels['partial'] is not None and not state['partial_done'] and sign*(price-Decimal(levels['partial']))>=0: return True
            last,last_key=stamp,key
    return False


class SignalRuntime:
    def __init__(self,store,market,simulations,portfolios):
        self.store,self.market,self.simulations,self.portfolios=store,market,simulations,portfolios
        from pathlib import Path
        if len({Path(p).resolve() for p in (store.path,market.path,market.registry.path,simulations.path,portfolios.path)})!=5: raise ValidationError('C01/C02/C11/C13/C14 stores must differ')

    def tick(self,name,when):
        integer(when,'signal cutoff'); began=time.monotonic(); head=self.store.session(name); m=head['manifest']; spec=SessionSpec.from_dict(m['spec']); cfg=spec.runtime
        if m['code_hash']!=code_hash() or m['python']!=platform.python_version(): raise ValidationError('Frozen C14 code/runtime changed; new counted research/deployment required')
        if not spec.start_ms<=when<=spec.tail_end_ms: raise ValidationError('C14 tick outside declared session/tail')
        if head['cycle'] is not None and when<head['cycle']['as_of_ms']: raise ValidationError('C14 source clock cannot move backward')
        ds=self.market.snapshot(m['execution']['enabled_symbols'],spec.warmup_start_ms,spec.tail_end_ms,kinds=('candle','quote','mark','trade','funding'),as_of_ms=when)
        events=[]
        for e in self.market.replay(ds['dataset_hash']):
            events.append(e)
            if len(events)>cfg.max_events: raise ValidationError('C14 source event budget exceeded')
        old=head['cycle']; previous=0 if old is None else old['source_count']
        if old is not None:
            if len(events)<previous or source_prefix(events[:previous])!=old['source_prefix_hash'] or any(e['available_ms']<=old['as_of_ms'] for e in events[previous:]):
                raise ValidationError('Previously consumed source watermark changed; stop and reconcile')
        settings=SimulationConfig(decision_start_ms=spec.start_ms,decision_end_ms=min(spec.end_ms,when+1),sample_interval_ms=m['replay']['sample_interval_ms'],
            max_candidates=cfg.max_candidates,max_artifacts=cfg.max_artifacts)
        from tradee.c11 import Simulator
        cc=CandidateConfig.from_dict(m['candidates']); snapshots,versions=capture(self.market.registry,ds,cc)
        simulator=Simulator(ds,[Scenario.from_dict(m['scenario'])],snapshots,versions,FeeSchedule.from_dict(m['fees']),ExecutionConfig.from_dict(m['execution']),cc,FundingConfig.from_dict(m['funding']),m['calendars'],settings)
        result=simulator.run(lambda:iter(events)); summary=self.simulations.commit(result)
        engine=PortfolioReplay(self.simulations,{summary['run_hash']:summary['report_hash']},[m['model']],events,RiskPolicy.from_dict(m['risk']),ReplayConfig.from_dict(m['replay']))
        output=engine.run(); funded=self.portfolios.commit(output); report=output[1].document()
        decisions={}
        for artifact in output[2]:
            a=artifact.document()
            if a['kind']=='allocation':
                for d in a['payload']['decisions']: decisions[d['candidate_id']]=dict(d,admitted_ms=a['payload']['as_of_ms'])
        accepted={tuple(t['source_key']):t for t in report['trades']}; signals=[]; detector=simulator.detectors[m['scenario']['name']]
        for key,info in sorted(engine.data['candidates'].items()):
            c=info['candidate']; decision=decisions.get(c['candidate_id']); paper=accepted.get(key); baseline=engine.data['baseline'][key]
            phase=('paper_closed' if paper['outcome']['status']=='closed' else 'paper_open' if paper['outcome']['status'] in ('open','exit_pending') else 'paper_unresolved') if paper else ('suppressed' if decision else 'expired' if when>=c['expires_ms'] else 'detected')
            entry=None if paper is None else paper['admitted_ms']; expiry=min(c['expires_ms'],entry+cfg.max_notice_age_ms) if entry is not None else c['expires_ms']
            q=None
            if entry is not None: q=EstimateRequest(c,info['feature'],info['scenario'],m['execution'],m['fees'],m['funding'],m['candidates'],entry).document()
            signals.append(dict(signal_id=fingerprint([head['deployment_hash'],c['candidate_id'],info['intent'].policy.policy_hash,info['intent'].quantity,info['scenario']['horizon']]),
                candidate_id=c['candidate_id'],phase=phase,candidate=c,trade_intent=info['intent'].document(),decision=decision,request=q,
                detected_ms=c['detected_ms'],entry_ms=entry,expires_ms=expiry,paper_outcome=None if paper is None else paper['outcome'],
                independent_status=baseline['status'],thesis_valid=thesis_ok(detector,c,when)))
        health=feed_health(events,when,m); health['reasons']+=report['terminal_risk']['reasons']
        if any(Decimal(t['outcome']['remaining_quantity'])>0 and (t['outcome']['status']=='unresolved' or set(t['outcome']['ambiguity_flags'])-{'unresolved_data_tail'}) for t in report['trades']):
            health['reasons'].append('paper_position_path_unresolved')
        health['reasons']=sorted(set(health['reasons'])); health['ready']=not health['reasons']
        cycle=FrozenRecord.create(dict(schema_version=1,component='C14',kind='paper_cycle',deployment_hash=head['deployment_hash'],as_of_ms=when,
            dataset=ds,source_count=len(events),source_cursor=report['input_cursor'],source_prefix_hash=report['input_prefix_hash'],simulation=summary,portfolio=funded,
            paper_account=report['terminal_account'],paper_risk=report['terminal_risk'],signals=signals,health=health,live_approved=False))
        elapsed=max(0,int((time.monotonic()-began)*1000))
        return self.store.publish(name,head['revision'],cycle,elapsed)

    def preflight(self,head,signal,when):
        m=head['manifest']; spec=SessionSpec.from_dict(m['spec']); cfg=spec.runtime; cycle=head['cycle']; reasons=[]; deferred=False; execution=None
        if m['code_hash']!=code_hash() or m['python']!=platform.python_version(): reasons.append('runtime_changed')
        if cycle is None or when<cycle['as_of_ms'] or when-cycle['as_of_ms']>=cfg.max_cycle_age_ms: reasons.append('stale_or_future_cycle')
        if when>=signal['expires_ms']: reasons.append('notice_expired')
        if signal['phase']!='paper_open' or signal['paper_outcome']['status']!='open': reasons.append('paper_position_no_longer_open')
        if not signal['thesis_valid']: reasons.append('setup_invalidated')
        if cycle and not cycle['health']['ready']: reasons.extend(cycle['health']['reasons'])
        if reasons: return dict(ready=False,reasons=sorted(set(reasons)),deferred=False,checked_ms=when,execution=None)
        ds=self.market.snapshot(m['execution']['enabled_symbols'],spec.warmup_start_ms,spec.tail_end_ms,kinds=('candle','quote','mark','trade','funding'),as_of_ms=when)
        events=[]
        for e in self.market.replay(ds['dataset_hash']):
            events.append(e)
            if len(events)>cfg.max_events: raise ValidationError('C14 send-check event budget exceeded')
        count=cycle['source_count']
        if len(events)<count or source_prefix(events[:count])!=cycle['source_prefix_hash']: reasons.append('source_prefix_changed')
        fresh=events[count:]
        if any(e['available_ms']<=cycle['as_of_ms'] for e in fresh): reasons.append('source_watermark_changed')
        if position_prefix_requires_tick(fresh,cycle,when): reasons.append('position_or_thesis_prefix_requires_tick'); deferred=True
        reasons.extend(feed_health(events,when,m)['reasons'])
        if reasons: return dict(ready=False,reasons=sorted(set(reasons)),deferred=deferred and all(r.endswith('requires_tick') for r in reasons),checked_ms=when,execution=None)
        q=deepcopy(signal['request']); q['evaluation_ms']=when; offer=Offer(q,m['model']); prediction=estimate(m['model'],offer.request).document()
        if not prediction['eligible']: reasons.extend(['expectancy_no_longer_eligible',*prediction['reasons']])
        # C07 needs current C03 evidence bound to this new immutable C02
        # vintage. The C10 request keeps the original candidate feature proof.
        features=FeatureEngine(ds,Scenario.from_dict(m['scenario']).strategy.feature_config())
        snapshots,versions=capture(self.market.registry,ds,CandidateConfig.from_dict(m['candidates']))
        for event in events: features.advance(event)
        feature=features.evaluate(signal['candidate']['instrument_id'],signal['candidate']['timeframe'],when)
        context=dict(snapshot_hash=feature.digest,**feature.document())
        engine=ExecutionEngine(ds,[offer.execution_intent],snapshots[-1],versions,FeeSchedule.from_dict(m['fees']),ExecutionConfig.from_dict(m['execution']),[context],when)
        for event in events: engine.push(event)
        execution=engine.evaluate(offer.execution_intent,when).document()
        if not execution['ready']: reasons.extend(['execution_recheck_failed',*execution['reasons']])
        elif any(execution['fill'][k]!=signal['decision']['execution']['fill'][k] for k in ('price','quantity','fee_usdt')): reasons.append('tested_entry_economics_changed')
        state=deepcopy(cycle['paper_account']); marks={}
        for e in events:
            if e['kind']=='mark' and e['final']:
                old=marks.get(e['instrument_id'])
                if old is None or (e['event_ms'],e['available_ms'],e['id'])>(old['event_ms'],old['available_ms'],old['event_id']):
                    marks[e['instrument_id']]=dict(instrument_id=e['instrument_id'],symbol=e['symbol'],price=e['data']['mark_price'],event_ms=e['event_ms'],available_ms=e['available_ms'],event_id=e['id'])
        state.update(as_of_ms=when,available_ms=when,marks=list(marks.values()))
        risk=inspect(AccountSnapshot.from_dict(state),when,RiskPolicy.from_dict(m['risk'])); reasons.extend(risk['reasons'])
        return dict(ready=not reasons,reasons=sorted(set(reasons)),deferred=False,checked_ms=when,execution=execution,prediction=prediction,risk=public_risk(risk),source_prefix_hash=source_prefix(events))
