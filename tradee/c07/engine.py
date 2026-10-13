"""Prefix-causal execution scenarios. Admission is under a model, not an exchange fill."""
from copy import deepcopy
from decimal import Decimal
import json
import platform
import re

from tradee.c01 import ValidationError
from tradee.c01.domain import canonical, fingerprint
from tradee.c02.domain import KINDS, candle, integer, number
from tradee.c03.catalog import TIMEFRAMES
from tradee.c06 import FundingEngine, FundingConfig, PositionTimeline
from tradee.c06.engine import code_hash
from tradee.c06.contracts import identity, decimal_text
from .contracts import ExecutionConfig, ExecutionIntent, ExecutionRecord, FeeSchedule
from .math import exact, dec, ratio, quantity, modeled_price, fill_costs


def verified_universe(value):
    if not isinstance(value,dict) or type(value.get('schema_version')) is not int or value.get('schema_version')!=1 or not isinstance(value.get('decisions'),list):
        raise ValidationError('C07 needs a C01 universe snapshot')
    doc=deepcopy(value); digest=doc.pop('snapshot_hash',None)
    if digest!=fingerprint(doc): raise ValidationError('Corrupt universe snapshot')
    integer(doc['as_of_ms'],'universe as-of')
    return value


def verified_feature(value):
    if not isinstance(value,dict): raise ValidationError('Feature snapshot must be an object')
    doc=deepcopy(value); digest=doc.pop('snapshot_hash',None)
    if digest!=fingerprint(doc) or type(doc.get('schema_version')) is not int or doc.get('schema_version')!=1:
        raise ValidationError('Corrupt feature snapshot')
    for name in ('evaluation_as_of_ms','input_available_ms','target_end_ms'):
        integer(doc.get(name),name)
    if doc.get('timeframe') not in TIMEFRAMES or not isinstance(doc.get('values'),dict):
        raise ValidationError('Invalid execution feature snapshot')
    return value


class ExecutionEngine:
    def __init__(self,dataset,intents,universe,versions,fees,config=None,features=(),decision_ms=None):
        if (not isinstance(dataset,dict) or type(dataset.get('schema_version')) is not int or dataset.get('schema_version')!=1
                or dataset.get('mode') not in ('recorded','modeled') or not isinstance(dataset.get('dataset_hash'),str)):
            raise ValidationError('C07 requires a pinned C02 dataset')
        for name in ('start_ms','end_ms','as_of_ms'): integer(dataset.get(name),name)
        if dataset['start_ms']>=dataset['end_ms'] or not isinstance(dataset.get('symbols'),list) or not isinstance(dataset.get('kinds'),list) or set(dataset['kinds'])-set(KINDS):
            raise ValidationError('Invalid execution dataset scope')
        self.dataset=deepcopy(dataset); self.config=config or ExecutionConfig()
        if not isinstance(self.config,ExecutionConfig) or not isinstance(fees,FeeSchedule):
            raise ValidationError('Execution config and explicit fee schedule are required')
        if (self.config.market_model=='recorded_quote')!=(dataset['mode']=='recorded'):
            raise ValidationError('Quote execution needs recorded data; bar execution needs explicitly modeled data')
        if dataset['mode']=='modeled' and dataset['kinds']!=['candle']:
            raise ValidationError('Modeled execution is candle-only')
        self.intents=tuple(i if isinstance(i,ExecutionIntent) else ExecutionIntent.from_dict(i) for i in intents)
        if not self.intents or len({i.intent_id for i in self.intents})!=len(self.intents):
            raise ValidationError('Nonempty unique execution intents are required')
        if any(i.symbol not in dataset['symbols'] or i.detected_ms<dataset['start_ms'] for i in self.intents):
            raise ValidationError('Execution intent outside dataset scope')
        self.fees=fees; self.universe=deepcopy(verified_universe(universe)); self.versions=deepcopy(versions)
        if not isinstance(versions,dict): raise ValidationError('Versioned instrument rules are required')
        for key,spec in self.versions.items():
            if fingerprint(spec)!=key: raise ValidationError('Corrupt C01 instrument version')
        self.features=tuple(deepcopy(verified_feature(f)) for f in features)
        self.decision_ms=dataset['as_of_ms'] if decision_ms is None else integer(decision_ms,'decision')
        if not dataset['start_ms']<=self.decision_ms<=dataset['as_of_ms']:
            raise ValidationError('Execution decision is outside the pinned evidence horizon')
        self.manifest=ExecutionRecord.create(dict(schema_version=1,checkpoint_schema=1,component='C07',dataset=dataset,
            intents=[i.document() for i in self.intents],config=self.config.document(),fees=fees.document(),
            universe=self.universe,metadata_versions=self.versions,feature_snapshots=list(self.features),
            decision_ms=self.decision_ms,code_hash=code_hash(),python=platform.python_version(),
            monetary_policy='Decimal400 exact; ratios rounded half-even to 12 decimals; adverse tick rounding',
            fill_policy='independent full-fill scenarios within declared liquidity cap; no resting-book guarantee or actual orders'))
        self.quotes={}; self.candles={}; self.cursor=None; self.prefix_hash=fingerprint([])
        self.last_event_hash=None; self.event_count=0; self.evaluated_through_ms=-1
        self.funding=None if dataset['mode']=='modeled' else FundingEngine(dataset,config=FundingConfig(max_mark_age_ms=self.config.max_mark_age_ms),decision_ms=self.decision_ms)

    def _validate(self,e):
        if (not isinstance(e,dict) or type(e.get('schema_version')) is not int or e['schema_version']!=1
                or e.get('availability_basis')!=self.dataset['mode'] or type(e.get('final')) is not bool):
            raise ValidationError('Unsupported execution market-event schema')
        for name in ('id','event_ms','received_ms','available_ms'): integer(e.get(name),name)
        if not e['id'] or e.get('kind') not in self.dataset['kinds'] or e.get('symbol') not in self.dataset['symbols']:
            raise ValidationError('Execution event outside scope')
        identity(e.get('instrument_id'),e['symbol'])
        if not e.get('metadata_version') or not isinstance(e.get('raw_sha256'),str) or not re.fullmatch('[a-f0-9]{64}',e['raw_sha256']):
            raise ValidationError('Execution event missing provenance')
        stamp=e.get('data',{}).get('open_ms',e['event_ms'])
        if not self.dataset['start_ms']<=stamp<self.dataset['end_ms'] or e['available_ms']>self.decision_ms:
            raise ValidationError('Execution event beyond dataset/decision horizon')
        if self.dataset['mode']=='recorded' and e['received_ms']>e['available_ms']:
            raise ValidationError('Execution event available before receipt')
        if e['final'] and e['event_ms']>e['available_ms']:
            raise ValidationError('Execution event available before event time')
        if e['kind']=='quote':
            d=e.get('data',{})
            if set(d)!={'bid','ask','bid_qty','ask_qty'} or not e['final']:
                raise ValidationError('Invalid finalized best quote')
            for k,v in d.items():
                if number(v,positive=k in ('bid','ask'))!=v: raise ValidationError('Noncanonical quote decimal')
            if dec(d['bid'])>dec(d['ask']): raise ValidationError('Crossed execution quote')
        if e['kind']=='candle':
            d=e['data']; raw=[d[k] for k in ('open_ms','open','high','low','close','volume','close_ms','quote_volume','trades','taker_base','taker_quote')]+['0']
            expected=candle(e['symbol'],raw,e['final'])
            if expected['data']!=d or expected['key']!=e.get('key') or expected['event_ms']!=e['event_ms']:
                raise ValidationError('Invalid canonical execution candle')
            if e['final'] and e['available_ms']<e['event_ms']+1:
                raise ValidationError('Execution candle available before exclusive close')

    def push(self,event):
        e=deepcopy(event); self._validate(e)
        cursor=(e['available_ms'],e['id']); digest=fingerprint(e)
        if cursor==self.cursor and digest==self.last_event_hash: return False
        if (self.cursor and cursor<=self.cursor) or e['available_ms']<self.evaluated_through_ms:
            raise ValidationError('Execution input violates replay/evaluation order')
        if self.funding: self.funding.push(e)
        self.cursor=cursor; self.prefix_hash=fingerprint([self.prefix_hash,digest]); self.last_event_hash=digest; self.event_count+=1
        if e['final'] and e['kind'] in ('quote','candle'):
            table=self.quotes if e['kind']=='quote' else self.candles
            old=table.get(e['instrument_id']); rank=lambda x:(x['event_ms'],x['available_ms'],x['id'])
            if old is None or rank(e)>rank(old): table[e['instrument_id']]=e
        return True

    def _decision(self,when):
        integer(when,'execution evaluation')
        if when>self.decision_ms or when<self.dataset['start_ms'] or when<self.evaluated_through_ms or (self.cursor and when<self.cursor[0]):
            raise ValidationError('Cannot evaluate execution through a future prefix/outside horizon')
        self.evaluated_through_ms=max(self.evaluated_through_ms,when)

    def _rules(self,intent,when):
        reasons=[]; cfg=self.config
        if intent.symbol not in cfg.enabled_symbols: reasons.append('symbol_not_enabled')
        decision=next((d for d in self.universe['decisions'] if d['symbol']==intent.symbol),None)
        if decision is None or decision.get('version_hash') not in self.versions:
            return None,reasons+['missing_instrument_rules'],None
        spec=self.versions[decision['version_hash']]
        if decision.get('instrument_id')!=intent.instrument_id or spec.get('instrument_id')!=intent.instrument_id:
            reasons.append('instrument_identity_mismatch')
        if not spec.get('scope_supported') or spec.get('issues') or spec.get('status')!='TRADING':
            reasons.append('unsupported_or_ineligible_instrument')
        if decision['state']!='eligible':
            reasons.append('metadata_ineligible')
            reasons.extend('metadata:'+r for r in decision['reasons'])
        if cfg.metadata_mode=='observed':
            if self.universe['as_of_ms']>when or decision['last_observed_ms'] is None or decision['last_observed_ms']>when:
                reasons.append('metadata_not_available')
            elif when-decision['last_observed_ms']>=cfg.max_metadata_age_ms:
                reasons.append('metadata_stale')
        elif self.universe['as_of_ms']>self.dataset['as_of_ms']:
            reasons.append('metadata_vintage_after_dataset_cutoff')
        if spec.get('onboardDate',0)>when: reasons.append('before_reported_onboard_time')
        if intent.order_type not in spec.get('orderTypes',()): reasons.append('instrument_order_type_unsupported')
        for filter_id in ('LOT_SIZE','MARKET_LOT_SIZE','PRICE_FILTER','MIN_NOTIONAL'):
            if filter_id not in spec.get('filters',{}): reasons.append('missing_filter:'+filter_id)
        return spec,reasons,decision['version_hash']

    def _feature_gate(self,intent,when):
        if not intent.required_features: return {'status':'not_requested','snapshot_hash':None},[]
        candidates=[]
        for f in self.features:
            cursor=f.get('input_cursor')
            if (f['instrument_id']==intent.instrument_id and f['timeframe']==intent.feature_timeframe
                    and f['dataset_hash']==self.dataset['dataset_hash'] and f['evaluation_as_of_ms']<=when
                    and f['target_end_ms']<=when and f['input_available_ms']<=when
                    and f.get('assumed_usable_ms',f['evaluation_as_of_ms'])<=when
                    and cursor is not None and self.cursor is not None and tuple(cursor)<=self.cursor):
                candidates.append(f)
        if not candidates: return {'status':'missing_feature_context','snapshot_hash':None},['missing_feature_context']
        chosen=max(candidates,key=lambda f:(f['evaluation_as_of_ms'],tuple(f['input_cursor'])))
        reasons=[]
        if when-chosen['target_end_ms']>=TIMEFRAMES[intent.feature_timeframe]+self.config.candle_grace_ms:
            reasons.append('stale_feature_context')
        for name in intent.required_features:
            value=chosen['values'].get(name,{})
            if value.get('status')!='valid' or value.get('value') is None:
                reasons.append('invalid_feature:'+name)
            elif self.config.require_stable_features and value.get('stable') is not True:
                reasons.append('unstable_feature:'+name)
        return dict(status='valid' if not reasons else 'invalid',snapshot_hash=chosen['snapshot_hash']),reasons

    def _funding(self,intent,q,when):
        if intent.purpose=='exit': return dict(status='not_applicable',estimated_cashflow_usdt='0',scope='exit execution does not book funding')
        if intent.holding_until_ms is None: return dict(status='unknown_holding_horizon',estimated_cashflow_usdt=None,scope='next settlement only')
        if self.funding is None: return dict(status='unsupported_modeled_coverage',estimated_cashflow_usdt=None,scope='no invented historical forecast')
        position=PositionTimeline(intent.intent_id,intent.instrument_id,intent.symbol,'long' if intent.side=='buy' else 'short',
                                  [dict(at_ms=when,quantity=decimal_text(q))])
        context=self.funding.context(position,when)
        context['scope']='next known settlement only; additional funding over longer holds remains unresolved'
        if context['status']=='valid':
            target=context['next_funding_ms']
            if abs(intent.holding_until_ms-target)<=15000 or abs(when-target)<=15000:
                context['status']='funding_boundary_ambiguous'; context['estimated_cashflow_usdt']=None
            elif intent.holding_until_ms<target:
                context['status']='not_crossing_next_settlement'; context['estimated_cashflow_usdt']='0'
        return context

    def evaluate(self,intent,when=None):
        if not isinstance(intent,ExecutionIntent): intent=ExecutionIntent.from_dict(intent)
        if intent not in self.intents: raise ValidationError('Execution intent is not pinned in this run')
        when=self.decision_ms if when is None else when; self._decision(when)
        cfg=self.config; action=cfg.action_time(intent); reasons=[]
        if when<action: reasons.append('delay_not_elapsed')
        if when>=intent.expires_ms: reasons.append('intent_expired')
        if intent.holding_until_ms is not None and intent.holding_until_ms<=when: reasons.append('holding_horizon_elapsed')
        if intent.order_type!='MARKET': reasons.append('passive_execution_unsupported')
        spec,rule_reasons,version=self._rules(intent,when); reasons.extend(rule_reasons)
        gate,gate_reasons=self._feature_gate(intent,when); reasons.extend(gate_reasons)
        fees=self.fees
        if fees.available_ms is not None and fees.available_ms>when: reasons.append('fee_not_available')
        if fees.effective_from_ms is not None and fees.effective_from_ms>when: reasons.append('fee_not_effective')
        if fees.effective_until_ms is not None and when>=fees.effective_until_ms: reasons.append('fee_expired')
        model_source='recorded_quote' if cfg.market_model=='recorded_quote' else 'synthetic_spread_on_completed_bar'
        source=self.quotes.get(intent.instrument_id) if cfg.market_model=='recorded_quote' else self.candles.get(intent.instrument_id)
        price_inputs=None; price_info={}; q=None; fill=None; costs=None; funding=None; step=None
        if source is None: reasons.append('missing_quote' if cfg.market_model=='recorded_quote' else 'missing_completed_bar')
        else:
            age=when-source['event_ms']; price_info['source_event_age_ms']=age
            with exact():
                if cfg.market_model=='recorded_quote':
                    if age>=cfg.max_quote_age_ms: reasons.append('stale_quote')
                    d=source['data']; b,a=dec(d['bid']),dec(d['ask']); mid=(a+b)/2
                    visible=dec(d['ask_qty'] if intent.side=='buy' else d['bid_qty']); cap=dec(cfg.max_top_book_fraction)
                    coefficient=dec(cfg.impact_bps_per_participation)
                else:
                    end=source['data']['close_ms']+1
                    if when-end>=60000+cfg.candle_grace_ms: reasons.append('stale_completed_bar')
                    if end<action: reasons.append('bar_predates_action_time')
                    mid=dec(source['data']['close']); half=mid*dec(cfg.synthetic_spread_bps)/20000
                    b,a=mid-half,mid+half; visible=dec(source['data']['volume']); cap=dec(cfg.max_bar_volume_fraction)
                    coefficient=dec(cfg.bar_impact_bps_per_participation)
                touch=a if intent.side=='buy' else b
                spread=10000*(a-b)
                if spread>dec(cfg.max_spread_bps)*mid: reasons.append('spread_budget_exceeded')
                price_info.update(mid_price=decimal_text(mid),touch_price=decimal_text(touch),spread_bps=ratio(spread,mid),
                                  visible_quantity_proxy=decimal_text(visible),liquidity_cap_fraction=decimal_text(cap))
                price_inputs=(mid,touch,visible,cap,coefficient)
        # No hypothetical fill for any failed precondition.
        if not reasons and spec and price_inputs:
            with exact():
                q,step,q_reasons=quantity(intent.quantity,spec['filters'],cfg.quantity_rounding); reasons.extend(q_reasons)
                if intent.reduce_only and q>dec(intent.position_quantity): reasons.append('reduce_only_exceeds_position')
                mid,touch,visible,cap,coefficient=price_inputs
                if visible<=0 or q>visible*cap: reasons.append('liquidity_budget_exceeded')
                mark=None
                if self.funding is not None:
                    mark_event=self.funding.marks.get(intent.instrument_id)
                    if mark_event is not None and when-mark_event['event_ms']<cfg.max_mark_age_ms:
                        mark=dec(mark_event['data']['mark_price']); price_info['mark_source_event_id']=mark_event['id']
                    else: reasons.append('missing_or_stale_mark')
                elif cfg.bar_mark_proxy=='bar_close':
                    mark=mid; price_info['mark_proxy']='completed_contract_close_research_assumption'
                else: reasons.append('historical_mark_coverage_unsupported')
                if mark is not None and not intent.reduce_only and q*mark<dec(spec['filters']['MIN_NOTIONAL']['notional']):
                    reasons.append('minimum_notional_not_met')
                if not reasons:
                    fill=modeled_price(touch,q,visible,cfg.extra_slippage_bps,coefficient,
                                       spec['filters']['PRICE_FILTER']['tickSize'],intent.side)
                    pf=spec['filters']['PRICE_FILTER']; low,high=dec(pf['minPrice']),dec(pf['maxPrice'])
                    if fill<=0 or (low and fill<low) or (high and fill>high): reasons.append('modeled_fill_outside_price_bounds')
                    if intent.purpose=='entry':
                        sign=1 if intent.side=='buy' else -1
                        if sign*(fill-dec(intent.reference_price))*10000>dec(cfg.max_adverse_drift_bps)*dec(intent.reference_price):
                            reasons.append('adverse_entry_drift_exceeded')
                        if intent.stop_price is not None and (fill<=dec(intent.stop_price) if intent.side=='buy' else fill>=dec(intent.stop_price)):
                            reasons.append('entry_already_invalidated')
                    bound=spec.get('marketTakeBound')
                    if bound is None: reasons.append('missing_market_take_bound')
                    elif abs(fill-mark)>dec(number(bound))*mark: reasons.append('market_take_bound_exceeded')
                    costs=fill_costs(intent,q,mid,touch,fill,fees.taker_rate)
                    if cfg.max_cost_r is not None:
                        if costs['planned_risk_usdt'] is None: reasons.append('risk_budget_requires_stop')
                        elif dec(costs['execution_plus_fee_cost_usdt'])>dec(cfg.max_cost_r)*dec(costs['planned_risk_usdt']):
                            reasons.append('cost_r_budget_exceeded')
                    funding=self._funding(intent,q,when)
                    if cfg.require_funding_estimate and intent.purpose=='entry' and funding['estimated_cashflow_usdt'] is None:
                        reasons.append('funding_projection_unavailable')
                    price_info.update(participation_fraction=ratio(q,visible),impact_bps=ratio(coefficient*q,visible))
        admitted=not reasons
        fill_doc=None
        if admitted:
            fill_doc=dict(fill_key=fingerprint([intent.instrument_id,intent.intent_id,intent.purpose]),
                kind='simulated_market_fill',side=intent.side,quantity=decimal_text(q),price=decimal_text(fill),
                fee_usdt=costs['fee_usdt'],liquidity_role='taker',fee_evidence=fees.evidence,
                execution_as_of_ms=when,source_event_id=source['id'],model=cfg.market_model,guaranteed=False)
            fill_doc['revision_hash']=fingerprint(fill_doc)
        projected=None
        if admitted and funding is not None and funding['estimated_cashflow_usdt'] is not None:
            with exact(): projected=decimal_text(dec(costs['execution_plus_fee_cost_usdt'])-dec(funding['estimated_cashflow_usdt']))
        return ExecutionRecord.create(dict(schema_version=1,run_hash=self.manifest.digest,intent_id=intent.intent_id,
            instrument_id=intent.instrument_id,symbol=intent.symbol,evaluation_as_of_ms=when,action_not_before_ms=action,
            elapsed_from_detection_ms=when-intent.detected_ms,input_cursor=self.cursor,input_prefix_hash=self.prefix_hash,
            status='admitted' if admitted else 'rejected',reasons=sorted(set(reasons)),ready=admitted,
            source_event_id=None if source is None else source['id'],source_raw_sha256=None if source is None else source['raw_sha256'],
            metadata_version=version,metadata_mode=cfg.metadata_mode,availability_basis=self.dataset['mode'],model_source=model_source,
            requested_quantity=intent.quantity,effective_quantity=None if q is None else decimal_text(q),
            quantity_step=None if step is None else decimal_text(step),feature_gate=gate,price_context=price_info,
            fill=fill_doc,costs=costs if admitted else None,funding=funding,
            projected_execution_cost_with_next_funding_usdt=projected,
            scope='single execution leg and optional next-funding estimate; no round-trip expectancy or account-order confirmation'))

    def report(self,when=None):
        when=self.decision_ms if when is None else when
        estimates=[self.evaluate(i,when).document() for i in self.intents]
        return ExecutionRecord.create(dict(schema_version=1,run_hash=self.manifest.digest,dataset_hash=self.dataset['dataset_hash'],
            evaluation_as_of_ms=when,input_cursor=self.cursor,input_prefix_hash=self.prefix_hash,
            estimates=estimates,ready=all(e['ready'] for e in estimates)))

    def checkpoint(self):
        latest={e['id']:e for e in (*self.quotes.values(),*self.candles.values())}
        funding=None if self.funding is None else self.funding.checkpoint()
        if funding:
            latest.update({e['id']:e for e in funding['latest']})
        return dict(schema_version=1,run_hash=self.manifest.digest,cursor=self.cursor,prefix_hash=self.prefix_hash,
            last_event_hash=self.last_event_hash,event_count=self.event_count,evaluated_through_ms=self.evaluated_through_ms,
            latest=sorted(latest.values(),key=lambda e:(e['available_ms'],e['id'])),funding=funding)

    @classmethod
    def restore(cls,dataset,intents,universe,versions,fees,config,features,decision_ms,checkpoint):
        obj=cls(dataset,intents,universe,versions,fees,config,features,decision_ms)
        if not isinstance(checkpoint,dict) or checkpoint.get('schema_version')!=1 or checkpoint.get('run_hash')!=obj.manifest.digest:
            raise ValidationError('Incompatible execution checkpoint')
        latest=checkpoint.get('latest'); count=checkpoint.get('event_count'); cursor=checkpoint.get('cursor')
        evaluated=checkpoint.get('evaluated_through_ms')
        if (not isinstance(latest,list) or type(count) is not int or count<len(latest)
                or type(evaluated) is not int or not -1<=evaluated<=obj.decision_ms):
            raise ValidationError('Invalid execution checkpoint state')
        if cursor is None:
            if count or latest or checkpoint.get('last_event_hash') is not None or checkpoint.get('prefix_hash')!=fingerprint([]):
                raise ValidationError('Invalid empty execution checkpoint')
        else:
            if not isinstance(cursor,(list,tuple)) or len(cursor)!=2 or not count: raise ValidationError('Invalid execution cursor')
            integer(cursor[0],'cursor time'); integer(cursor[1],'cursor ID')
            if not cursor[1] or cursor[0]>obj.decision_ms: raise ValidationError('Invalid execution cursor horizon')
            for name in ('prefix_hash','last_event_hash'):
                if not isinstance(checkpoint.get(name),str) or not re.fullmatch('[a-f0-9]{64}',checkpoint[name]):
                    raise ValidationError('Invalid execution checkpoint digest')
        for e in latest: obj.push(e)
        if obj.cursor and (cursor is None or obj.cursor>tuple(cursor)): raise ValidationError('Checkpoint precedes retained evidence')
        if cursor is not None and obj.cursor==tuple(cursor) and obj.last_event_hash!=checkpoint['last_event_hash']:
            raise ValidationError('Checkpoint last-event mismatch')
        obj.cursor=None if cursor is None else tuple(cursor); obj.prefix_hash=checkpoint['prefix_hash']
        obj.last_event_hash=checkpoint['last_event_hash']; obj.event_count=count; obj.evaluated_through_ms=evaluated
        if obj.funding is not None:
            obj.funding=FundingEngine.restore(dataset,(),(),FundingConfig(max_mark_age_ms=config.max_mark_age_ms),decision_ms,checkpoint['funding'])
            if obj.funding.cursor!=obj.cursor or obj.funding.prefix_hash!=obj.prefix_hash:
                raise ValidationError('Execution/funding checkpoint prefix mismatch')
        elif checkpoint.get('funding') is not None: raise ValidationError('Unexpected modeled funding checkpoint')
        return obj
