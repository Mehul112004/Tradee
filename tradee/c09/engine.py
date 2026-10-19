"""Shared independent-trade state machine. No orders, fitted policy or portfolio loop."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import platform

from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c02.domain import integer,number
from tradee.c03 import FeatureEngine,FeatureConfig
from tradee.c03.catalog import TIMEFRAMES
from tradee.c06 import FundingEngine,FundingConfig,PositionTimeline,SettlementCalendar
from tradee.c06.contracts import decimal_text
from tradee.c06.engine import code_hash
from tradee.c07 import ExecutionEngine,ExecutionIntent,ExecutionConfig,FeeSchedule
from tradee.c07.engine import verified_feature
from tradee.c07.math import exact,quantity
from tradee.c08 import CandidateConfig
from tradee.c08.contracts import FAMILY
from tradee.c08.metadata import MetadataBook
from .contracts import TradeIntent,LifecycleRecord
from .ledger import book_fill,reconcile_funding,outcome


class LifecycleEngine:
    def __init__(self,dataset,intents,snapshots,versions,fees,execution=None,funding_config=None,calendars=()):
        self.dataset=deepcopy(dataset)
        self.intents=tuple(i if isinstance(i,TradeIntent) else TradeIntent.from_dict(i) for i in intents)
        if not self.intents or len({i.trade_id for i in self.intents})!=len(self.intents): raise ValidationError('Unique nonempty trade intents required')
        self.execution=execution or ExecutionConfig(); self.funding_config=funding_config or FundingConfig()
        self.fees=fees
        if not isinstance(fees,FeeSchedule): raise ValidationError('Explicit fee schedule required')
        self.book=MetadataBook(snapshots,versions,dataset['as_of_ms'])
        self.meta_config=CandidateConfig(self.execution.enabled_symbols,self.execution.metadata_mode,self.execution.max_metadata_age_ms)
        self.calendars=tuple(c if isinstance(c,SettlementCalendar) else SettlementCalendar.from_dict(c) for c in calendars)
        if len({c.instrument_id for c in self.calendars})!=len(self.calendars): raise ValidationError('Duplicate funding calendar')
        names=[]; frames=[]
        for i in self.intents:
            c=i.candidate.document(); f=i.feature_snapshot.document()
            if (c['symbol'] not in dataset['symbols'] or f['dataset_hash']!=dataset['dataset_hash']
                    or c['detected_ms']<dataset['start_ms'] or c['detected_ms']>dataset['as_of_ms']):
                raise ValidationError('Trade intent outside pinned dataset')
            if dataset['mode']=='modeled' and i.policy.trigger_source not in ('bar_close','bar_range'):
                raise ValidationError('Modeled candle data cannot supply contract-trade or mark triggers')
            if i.policy.trigger_source in ('contract_trade','mark') and ('trade' if i.policy.trigger_source=='contract_trade' else 'mark') not in dataset['kinds']:
                raise ValidationError('Declared trigger source missing from dataset scope')
            names.extend(i.required_features); frames.append(c['timeframe'])
        self.features=FeatureEngine(dataset,FeatureConfig(features=tuple(dict.fromkeys(names)),timeframes=tuple(dict.fromkeys(frames))))
        # C07 validates all source observations and retains latest quote/bar/mark;
        # the seed intent is never evaluated or booked.
        seed=self._entry_intent(self.intents[0])
        self.market=ExecutionEngine(dataset,[seed],self.book.snapshots[-1],self.book.versions,fees,self.execution,decision_ms=dataset['as_of_ms'])
        self.manifest=LifecycleRecord.create(dict(schema_version=1,component='C09',checkpoint_schema=1,dataset=dataset,
            intents=[i.document() for i in self.intents],fees=fees.document(),execution=self.execution.document(),funding=self.funding_config.document(),
            calendars=[c.document() for c in self.calendars],metadata_snapshots=self.book.snapshots,metadata_versions=self.book.versions,
            feature_manifest=self.features.manifest.document(),code_hash=code_hash(),python=platform.python_version(),
            exposure='independent trades; no shared capital/book consumption or authenticated account state',
            bar_execution='closed-bar triggers execute at C07 modeled close, never invented intrabar threshold fills; ambiguous ranges unresolved',
            accounting='keyed fill fees and current funding revisions once; exact Decimal400; diagnostic ratios 12dp'))
        self.states={}
        for i in self.intents:
            c=i.candidate.document()
            self.states[i.trade_id]=dict(trade_id=i.trade_id,candidate_id=c['candidate_id'],side=c['side'],instrument_id=c['instrument_id'],symbol=c['symbol'],
                status='waiting',levels=i.levels(),remaining_quantity='0',initial_quantity=None,entry_price=None,entry_ms=None,exit_ms=None,exit_reason=None,
                quantity_changes=[],ledger={},partial_done=False,exit_pending=None,attempts=[],ambiguity_flags=[],activated=False,
                last_trigger_ms=None,last_trigger_id=None,last_trigger_key=None,last_bar_open_ms=None,target_before_stop=None,mfe_price=None,mae_price=None,last_transition_ms=None,
                outcome_revision_hash=None,outcome_known_ms=None)
        self.latest_features={}; self.evaluated_ms=-1; self.record_count=0; self.cancellations={}; self.finish_called=False

    @property
    def cursor(self): return self.market.cursor
    @property
    def prefix_hash(self): return self.market.prefix_hash

    def _entry_intent(self,i):
        c=i.candidate.document()
        return ExecutionIntent(i.trade_id+':entry',c['instrument_id'],c['symbol'],'buy' if c['side']=='long' else 'sell',i.quantity,
            c['detected_ms'],c['expires_ms'],c['reference_price'],stop_price=i.levels()['stop'],
            holding_until_ms=c['expires_ms']+i.policy.max_holding_ms,required_features=i.required_features,feature_timeframe=c['timeframe'])

    def _universe(self,when):
        known=[u for u in self.book.snapshots if u['as_of_ms']<=when]
        if self.execution.metadata_mode=='research_assumption': return self.book.snapshots[-1]
        if known: return known[-1]
        # C07 will explicitly reject this unavailable future snapshot.
        return self.book.snapshots[0]

    def _execute(self,i,intent,when,exiting=False):
        cfg=self.execution
        if exiting:
            cfg=replace(cfg,processing_delay_ms=0,delivery_delay_ms=0,manual_delay_ms=0,quantity_rounding='reject',max_cost_r=None,require_funding_estimate=False)
        context=[]
        f=self.latest_features.get((intent.instrument_id,intent.feature_timeframe))
        if f is not None: context=[f]
        engine=ExecutionEngine(self.dataset,[intent],self._universe(when),self.book.versions,self.fees,cfg,context,self.dataset['as_of_ms'])
        # C07 source state and the exact full prefix are shared without replaying
        # history or replacing a source timestamp/price with a trigger threshold.
        for name in ('quotes','candles','cursor','prefix_hash','last_event_hash','event_count'):
            setattr(engine,name,deepcopy(getattr(self.market,name)))
        engine.funding=deepcopy(self.market.funding)
        return engine.evaluate(intent,when)

    def _thesis(self,i,s,when):
        c=i.candidate.document(); f=self.latest_features.get((c['instrument_id'],c['timeframe']))
        if f is None: return 'missing_current_thesis_context'
        if when-f['target_end_ms']>=TIMEFRAMES[c['timeframe']]+self.execution.candle_grace_ms: return 'stale_current_thesis_context'
        for name in i.required_features:
            v=f['values'].get(name,{})
            if v.get('status')!='valid' or not v.get('stable'): return 'invalid_current_thesis_context'
        bar=self.features.bars.get((c['instrument_id'],c['timeframe']),{}).get(f['target_open_ms'])
        if bar is None: return 'missing_current_thesis_context'
        close=Decimal(bar['data']['close']); sign=1 if c['side']=='long' else -1
        if c['hypothesis_family']==FAMILY:
            if sign*(close-Decimal(c['breakout_level']))<=0: return 'setup_invalidated'
        else:
            fast,slow=(f['values'][k]['value'] for k in ('ema20','ema50'))
            if sign*(fast-slow)<=0 or sign*(float(close)-fast)<=0: return 'setup_invalidated'
        return None

    def _activate(self,i,s,when):
        if s['activated'] or s['status']!='waiting': return
        c=i.candidate.document(); expected=tuple(c['input_cursor'])
        if self.cursor is None or self.cursor<expected: return
        if self.cursor!=expected or self.prefix_hash!=c['input_prefix_hash']:
            raise ValidationError('Candidate source prefix does not match this replay')
        s['activated']=True; s['status']='pending_entry'
        self.latest_features[(c['instrument_id'],c['timeframe'])]=i.feature_snapshot.document()

    def _entry(self,i,s,when):
        c=i.candidate.document()
        if when>=c['expires_ms']: s.update(status='expired',exit_reason='entry_window_expired'); return
        intent=self._entry_intent(i); action=self.execution.action_time(intent)
        if when<action: return
        invalid=self._thesis(i,s,when)
        if invalid=='setup_invalidated': s.update(status='cancelled',exit_reason=invalid); return
        if invalid: return
        source=self.market.quotes.get(c['instrument_id']) if self.execution.market_model=='recorded_quote' else self.market.candles.get(c['instrument_id'])
        if source is None or source['available_ms']<action: return
        if self.execution.market_model=='modeled_bar' and source['data']['open_ms']<c['detected_ms']: return
        estimate=self._execute(i,intent,when); doc=estimate.document(); s['attempts'].append({'kind':'entry','estimate_hash':estimate.digest,'estimate':doc})
        if not doc['ready']: return
        fill=doc['fill']; price=Decimal(fill['price']); sign=1 if c['side']=='long' else -1
        if sign*(price-Decimal(s['levels']['target']))>=0:
            s.update(status='cancelled',exit_reason='entry_beyond_target'); return
        book_fill(s,fill,'entry',initial=True); s['status']='open'; s['last_transition_ms']=when
        s['mfe_price']=s['mae_price']=fill['price']

    def _sample(self,i,s,event,when):
        p=i.policy; wanted={'contract_trade':'trade','mark':'mark','bar_close':'candle','bar_range':'candle'}[p.trigger_source]
        if event is None or event['instrument_id']!=s['instrument_id'] or event['kind']!=wanted or not event['final']: return None
        stamp=event['event_ms']; data=event['data']
        if stamp<s['entry_ms']: return None
        trade_key=integer(int(event['key']),'aggregate trade key') if wanted=='trade' else None
        if s['last_trigger_ms'] is not None and (stamp<s['last_trigger_ms'] or (stamp==s['last_trigger_ms'] and
                (wanted!='trade' or trade_key<=s['last_trigger_key']))):
            s['ambiguity_flags']=sorted(set(s['ambiguity_flags']+['late_or_revised_trigger_path'])); return None
        if when-stamp>=p.max_trigger_age_ms and wanted!='candle':
            s['ambiguity_flags']=sorted(set(s['ambiguity_flags']+['stale_trigger_path'])); return None
        if wanted=='candle':
            if data['open_ms']<s['entry_ms']: return None # no pre-entry range excursions
            if when-(data['close_ms']+1)>=60000+self.execution.candle_grace_ms:
                s['ambiguity_flags']=sorted(set(s['ambiguity_flags']+['stale_trigger_path'])); return None
            if s['last_bar_open_ms'] is not None and data['open_ms']!=s['last_bar_open_ms']+60000:
                s['ambiguity_flags']=sorted(set(s['ambiguity_flags']+['gap_in_trigger_path']))
            s['last_bar_open_ms']=data['open_ms']
            low,high=(Decimal(data[k]) for k in ('low','high')) if p.trigger_source=='bar_range' else (Decimal(data['close']),)*2
        else:
            if stamp-(s['last_trigger_ms'] if s['last_trigger_ms'] is not None else s['entry_ms'])>p.max_path_gap_ms:
                s['ambiguity_flags']=sorted(set(s['ambiguity_flags']+['gap_in_trigger_path']))
            low=high=Decimal(data['price'] if wanted=='trade' else data['mark_price'])
        s['last_trigger_ms']=stamp; s['last_trigger_id']=event['id']; s['last_trigger_key']=trade_key
        sign=1 if s['side']=='long' else -1
        with exact():
            favorable=high if sign==1 else low; adverse=low if sign==1 else high
            if sign*(favorable-Decimal(s['mfe_price']))>0: s['mfe_price']=decimal_text(favorable)
            if sign*(adverse-Decimal(s['mae_price']))<0: s['mae_price']=decimal_text(adverse)
        stop=low<=Decimal(s['levels']['stop']) if sign==1 else high>=Decimal(s['levels']['stop'])
        target=high>=Decimal(s['levels']['target']) if sign==1 else low<=Decimal(s['levels']['target'])
        partial=False if s['levels']['partial'] is None or s['partial_done'] else (high>=Decimal(s['levels']['partial']) if sign==1 else low<=Decimal(s['levels']['partial']))
        if stop and (target or partial):
            s['status']='unresolved'; s['exit_reason']='intrabar_order_unknown'; s['ambiguity_flags']=sorted(set(s['ambiguity_flags']+['stop_and_target_same_bar']))
            return None
        if stop:
            if s['target_before_stop'] is None: s['target_before_stop']=False
            return 'stop'
        if target:
            if s['target_before_stop'] is None: s['target_before_stop']=True
            return 'target'
        if partial: return 'partial_target'
        return None

    def _queue_exit(self,i,s,reason,when):
        # A stop/full close supersedes an unfilled partial; the first full exit
        # request remains latched even if price later recovers.
        old=s['exit_pending']
        if old and (old['reason']!='partial_target' or reason=='partial_target'): return
        s['exit_pending']=dict(reason=reason,triggered_ms=when,not_before_ms=when+i.policy.exit_delay_ms,
            deadline_ms=when+i.policy.exit_delay_ms+i.policy.max_exit_wait_ms)
        s['status']='exit_pending'

    def _exit(self,i,s,when):
        pending=s['exit_pending']
        if pending is None or when<pending['not_before_ms'] or when==s['last_transition_ms']: return
        if when>=pending['deadline_ms']:
            s.update(status='unresolved',exit_reason='exit_liquidity_timeout'); return
        with exact():
            remaining=Decimal(s['remaining_quantity']); requested=remaining
            if pending['reason']=='partial_target':
                proposed=Decimal(s['initial_quantity'])*Decimal(i.policy.partial_fraction)
                _,_,version=self.book.gate(s['instrument_id'],s['symbol'],when,self.meta_config)
                if version is None: return
                requested,_,reasons=quantity(decimal_text(proposed),self.book.versions[version]['filters'],'floor')
                if reasons or requested>=remaining or requested<=0:
                    s['ambiguity_flags']=sorted(set(s['ambiguity_flags']+['partial_quantity_unexecutable'])); s['partial_done']=True
                    s['exit_pending']=None; s['status']='open'; return
            source=self.market.quotes.get(s['instrument_id']) if self.execution.market_model=='recorded_quote' else self.market.candles.get(s['instrument_id'])
            if source is None or source['available_ms']<pending['not_before_ms']: return
            ref=source['data']['ask' if s['side']=='short' else 'bid'] if source['kind']=='quote' else source['data']['close']
            intent=ExecutionIntent(i.trade_id+':exit:'+str(len(s['quantity_changes'])),s['instrument_id'],s['symbol'],
                'sell' if s['side']=='long' else 'buy',decimal_text(requested),pending['triggered_ms'],pending['deadline_ms'],ref,
                purpose='exit',reduce_only=True,position_quantity=s['remaining_quantity'])
        estimate=self._execute(i,intent,when,True); doc=estimate.document(); s['attempts'].append({'kind':'exit','estimate_hash':estimate.digest,'estimate':doc})
        if not doc['ready']: return
        book_fill(s,doc['fill'],pending['reason']); s['last_transition_ms']=when
        if s['remaining_quantity']=='0':
            s.update(status='closed',exit_ms=when,exit_reason=pending['reason'],exit_pending=None)
        else:
            s['partial_done']=True; s['status']='open'; s['exit_pending']=None

    def advance(self,event):
        if self.finish_called: raise ValidationError('Cannot append to a finalized lifecycle prefix')
        # Validate all child inputs before mutating either child or trade state.
        self.market._validate(event); self.features._validate(event)
        if event['metadata_version'] not in self.book.versions: raise ValidationError('Unpinned lifecycle source metadata')
        if event['kind']=='trade':
            data=event.get('data',{})
            if set(data)!={'price','quantity','first_trade_id','last_trade_id','buyer_is_maker'} or type(data['buyer_is_maker']) is not bool:
                raise ValidationError('Invalid lifecycle contract trade')
            for name in ('price','quantity'):
                if number(data[name],positive=True)!=data[name]: raise ValidationError('Noncanonical lifecycle trade decimal')
            a=integer(data['first_trade_id'],'first trade'); b=integer(data['last_trade_id'],'last trade')
            if a>b: raise ValidationError('Reversed lifecycle trade IDs')
            if not isinstance(event.get('key'),str) or not event['key'].isascii() or not event['key'].isdigit(): raise ValidationError('Invalid aggregate trade key')
            integer(int(event['key']),'aggregate trade key')
        if event['available_ms']<self.evaluated_ms: raise ValidationError('Event predates lifecycle decision clock')
        if not self.market.push(event): return []
        for f in self.features.advance(event):
            d=f.document(); self.latest_features[(d['instrument_id'],d['timeframe'])]={'snapshot_hash':f.digest,**d}
        self.evaluated_ms=max(self.evaluated_ms,event['available_ms'])
        return self._step(event['available_ms'],event)

    def _step(self,when,event=None):
        records=[]
        for i in self.intents:
            s=self.states[i.trade_id]; before=fingerprint(s); self._activate(i,s,when)
            cancel=self.cancellations.get(i.trade_id)
            if cancel is not None and when>=cancel['at_ms'] and s['status'] in ('pending_entry','open','exit_pending'):
                if s['status']=='pending_entry': s.update(status='cancelled',exit_reason=cancel['reason'])
                else: self._queue_exit(i,s,'invalidation',when)
            if s['status']=='pending_entry': self._entry(i,s,when)
            elif s['status'] in ('open','exit_pending'):
                reason=self._sample(i,s,event,when)
                if s['status']!='unresolved':
                    if reason: self._queue_exit(i,s,reason,when)
                    if when>=s['entry_ms']+i.policy.max_holding_ms: self._queue_exit(i,s,'time_exit',s['entry_ms']+i.policy.max_holding_ms)
                    self._exit(i,s,when)
            if fingerprint(s)!=before:
                self.record_count+=1
                records.append(LifecycleRecord.create(dict(schema_version=1,run_hash=self.manifest.digest,sequence=self.record_count,
                    trade_id=i.trade_id,evaluation_as_of_ms=when,input_cursor=self.cursor,input_prefix_hash=self.prefix_hash,state=deepcopy(s))))
        return records

    def cancel(self,trade_id,when,reason='operator_invalidation'):
        self._clock(when)
        if trade_id not in self.states or not isinstance(reason,str) or not reason.strip(): raise ValidationError('Invalid lifecycle cancellation')
        self.cancellations[trade_id]=dict(at_ms=when,reason=reason)
        return self._step(when)

    def _clock(self,when):
        integer(when,'lifecycle clock')
        if when<self.dataset['start_ms'] or when<self.evaluated_ms or when>self.dataset['as_of_ms'] or (self.cursor and when<self.cursor[0]): raise ValidationError('Lifecycle clock outside known prefix/horizon')
        self.evaluated_ms=when

    def tick(self,when):
        if self.finish_called: raise ValidationError('Finalized lifecycle prefix')
        self._clock(when); return self._step(when)

    def _funding(self,i,s,when):
        if not s['quantity_changes']: return dict(total_cashflow_usdt='0',coverage_status='not_exposed',cashflows=[])
        if self.market.funding is None: return dict(total_cashflow_usdt=None,coverage_status='unsupported_modeled_funding',cashflows=[])
        end=(s['exit_ms']+1) if s['exit_ms'] is not None else min(when+1,self.dataset['end_ms'])
        guard=self.funding_config.boundary_guard_ms if self.funding_config.boundary_policy=='strict' else 0
        start=max(self.dataset['start_ms'],s['entry_ms']-guard)
        if s['exit_ms'] is not None: end=min(self.dataset['end_ms'],s['exit_ms']+guard+1)
        ds={**self.dataset,'start_ms':start,'end_ms':max(start+1,end)}
        position=PositionTimeline(i.trade_id,s['instrument_id'],s['symbol'],s['side'],s['quantity_changes'])
        engine=FundingEngine(ds,[position],self.calendars,self.funding_config,decision_ms=when)
        for e in sorted(self.market.funding.settlements.values(),key=lambda e:(e['available_ms'],e['id'])):
            if ds['start_ms']<=e['event_ms']<ds['end_ms']: engine.push(e)
        report=engine.report(when).document()['positions'][0]; reconcile_funding(s,report)
        return report

    def report(self,when=None,complete_prefix=False):
        when=self.evaluated_ms if when is None else when; self._clock(when)
        results=[]
        for i in self.intents:
            s=self.states[i.trade_id]; funding=self._funding(i,s,when)
            result=outcome(s,funding['total_cashflow_usdt'],when,complete_prefix)
            result.update(funding=funding,state=deepcopy(s),policy_hash=i.policy.policy_hash)
            results.append(result)
        return LifecycleRecord.create(dict(schema_version=1,run_hash=self.manifest.digest,dataset_hash=self.dataset['dataset_hash'],
            evaluation_as_of_ms=when,input_cursor=self.cursor,input_prefix_hash=self.prefix_hash,complete_prefix=complete_prefix,
            trades=results,ready=bool(results) and all(t['ready'] or t['label_status']=='unfilled' for t in results)))

    def finish(self,when=None):
        when=self.dataset['as_of_ms'] if when is None else when
        records=self.tick(when)
        for s in self.states.values():
            if s['status'] in ('waiting','pending_entry','open','exit_pending'):
                s['ambiguity_flags']=sorted(set(s['ambiguity_flags']+['unresolved_data_tail']))
        self.finish_called=True
        return records,self.report(when,True)

    def checkpoint(self):
        return dict(schema_version=1,run_hash=self.manifest.digest,market=self.market.checkpoint(),features=self.features.checkpoint(),
            states=deepcopy(self.states),latest_features=deepcopy(list(self.latest_features.values())),evaluated_ms=self.evaluated_ms,
            record_count=self.record_count,cancellations=deepcopy(self.cancellations),finish_called=self.finish_called)

    @classmethod
    def restore(cls,dataset,intents,snapshots,versions,fees,execution,funding_config,calendars,cp):
        obj=cls(dataset,intents,snapshots,versions,fees,execution,funding_config,calendars)
        if not isinstance(cp,dict) or type(cp.get('schema_version')) is not int or cp['schema_version']!=1 or cp.get('run_hash')!=obj.manifest.digest:
            raise ValidationError('Incompatible lifecycle checkpoint')
        obj.market=ExecutionEngine.restore(dataset,obj.market.intents,obj.market.universe,obj.book.versions,fees,execution,(),dataset['as_of_ms'],cp['market'])
        obj.features=FeatureEngine.restore(dataset,obj.features.config,cp['features'])
        if obj.market.cursor!=obj.features.cursor or obj.market.prefix_hash!=obj.features.prefix_hash: raise ValidationError('Lifecycle child prefixes differ')
        if set(cp.get('states',{}))!=set(obj.states) or type(cp.get('record_count')) is not int or cp['record_count']<0 or type(cp.get('finish_called')) is not bool:
            raise ValidationError('Invalid lifecycle checkpoint state')
        for key,s in cp['states'].items():
            if s['trade_id']!=key or s['status'] not in ('waiting','pending_entry','open','exit_pending','closed','expired','cancelled','unresolved'):
                raise ValidationError('Invalid position checkpoint')
            if s['quantity_changes']:
                timeline=PositionTimeline(key,s['instrument_id'],s['symbol'],s['side'],s['quantity_changes'])
                if timeline.changes[-1].quantity!=s['remaining_quantity']: raise ValidationError('Position quantity checkpoint mismatch')
                if any(Decimal(b.quantity)>=Decimal(a.quantity) for a,b in zip(timeline.changes,timeline.changes[1:])):
                    raise ValidationError('Position quantity cannot increase after initial entry')
                if timeline.changes[0].quantity!=s['initial_quantity'] or timeline.changes[0].at_ms!=s['entry_ms']:
                    raise ValidationError('Position entry timeline mismatch')
            initial=obj.states[key]
            if any(s[field]!=initial[field] for field in ('trade_id','candidate_id','side','instrument_id','symbol','levels')):
                raise ValidationError('Position checkpoint conflicts with pinned trade intent')
            with exact():
                exits=[v for v in s['ledger'].values() if v['kind']=='exit']; entries=[v for v in s['ledger'].values() if v['kind']=='entry']
                if len(entries)>1 or bool(entries)!=bool(s['quantity_changes']): raise ValidationError('Invalid entry ledger')
                if entries:
                    if entries[0]['quantity']!=s['initial_quantity'] or entries[0]['price']!=s['entry_price']:
                        raise ValidationError('Entry ledger conflicts with position')
                    if Decimal(s['initial_quantity'])-sum((Decimal(v['quantity']) for v in exits),Decimal(0))!=Decimal(s['remaining_quantity']):
                        raise ValidationError('Exit ledger does not conserve quantity')
                if s['status']=='closed' and (s['remaining_quantity']!='0' or s['exit_ms'] is None): raise ValidationError('Closed position is not flat')
                for ledger_key,v in s['ledger'].items():
                    if v['kind'] not in ('entry','exit','funding'): raise ValidationError('Invalid ledger entry kind')
                    if v['kind']=='funding':
                        if ledger_key!=fingerprint([key,s['instrument_id'],v['at_ms'],'funding']): raise ValidationError('Invalid funding ledger identity')
                        continue
                    fills=[a['estimate']['fill'] for a in s['attempts'] if a['estimate'].get('fill') and a['estimate']['fill']['fill_key']==ledger_key]
                    if not fills or fills[-1]['revision_hash']!=v['revision_hash']: raise ValidationError('Ledger fill has no matching execution evidence')
                    fill=fills[-1]
                    if any(v[a]!=fill[b] for a,b in (('quantity','quantity'),('price','price'),('fee_usdt','fee_usdt'),('at_ms','execution_as_of_ms'))):
                        raise ValidationError('Ledger fields conflict with execution evidence')
                    if fingerprint({k:x for k,x in fill.items() if k!='revision_hash'})!=fill['revision_hash']:
                        raise ValidationError('Corrupt fill revision')
                    gross=Decimal(0) if v['kind']=='entry' else (1 if s['side']=='long' else -1)*(Decimal(v['price'])-Decimal(s['entry_price']))*Decimal(v['quantity'])
                    if gross!=Decimal(v['gross_usdt']) or gross-Decimal(v['fee_usdt'])!=Decimal(v['amount_usdt']): raise ValidationError('Corrupt ledger arithmetic')
        obj.states=deepcopy(cp['states']); obj.latest_features={}
        for f in cp['latest_features']:
            verified_feature(f)
            if f['dataset_hash']!=dataset['dataset_hash'] or (obj.cursor and tuple(f['input_cursor'])>obj.cursor): raise ValidationError('Future/wrong-dataset checkpoint feature')
            obj.latest_features[(f['instrument_id'],f['timeframe'])]=deepcopy(f)
        obj.evaluated_ms=cp['evaluated_ms']; obj.record_count=cp['record_count']; obj.cancellations=deepcopy(cp['cancellations']); obj.finish_called=cp['finish_called']
        if obj.evaluated_ms>dataset['as_of_ms'] or (obj.cursor and obj.evaluated_ms<obj.cursor[0]): raise ValidationError('Invalid lifecycle checkpoint clock')
        return obj
