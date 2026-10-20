"""Causal shared-capital selection over actual C11/C07/C09 execution paths.

C11 executes each predeclared exact size with shared production logic. This
runner accepts/rejects only at that size's first executable opportunity, then
books its causal revisions. No final trade return participates in allocation.
"""
from collections import Counter,defaultdict
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from itertools import groupby
import platform
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c02.domain import integer
from tradee.c03.contracts import FrozenRecord
from tradee.c06.contracts import decimal_text
from tradee.c06.engine import code_hash
from tradee.c07 import ExecutionEngine,ExecutionConfig,FeeSchedule
from tradee.c07.math import exact,ratio
from tradee.c10 import EstimateRequest
from tradee.c10.engine import verified_model
from .contracts import fields,amount,RiskPolicy,AccountSnapshot,Offer
from .engine import allocate
from .risk import inspect
from .source import load


@dataclass(frozen=True)
class ReplayConfig:
    initial_cash_usdt: str = '10000'
    sample_interval_ms: int = 60000
    decision_start_ms: int | None = None
    decision_end_ms: int | None = None
    max_events: int = 250000
    max_candidates: int = 10000

    def __post_init__(self):
        object.__setattr__(self,'initial_cash_usdt',amount(self.initial_cash_usdt,positive=True))
        for k in ('sample_interval_ms','max_events','max_candidates'):
            integer(getattr(self,k),k)
            if not getattr(self,k): raise ValidationError('Positive funded replay limits required')
        for k in ('decision_start_ms','decision_end_ms'):
            if getattr(self,k) is not None: integer(getattr(self,k),k)
    def document(self): return {k:getattr(self,k) for k in self.__dataclass_fields__}
    @classmethod
    def from_dict(cls,d): fields(d,cls); return cls(**d)


def public_risk(value): return {k:v for k,v in value.items() if k!='rows'}


def diagnostics(samples,initial,terminal):
    peak=Decimal(initial); dd=Decimal(0); fraction=Decimal(0); missing=0; returns=[]; previous=None
    with exact():
        for point in samples:
            value=None if point['equity_usdt'] is None else Decimal(point['equity_usdt'])
            if value is None: missing+=1
            else:
                peak=max(peak,value); dd=max(dd,peak-value)
                fraction=max(fraction,Decimal(ratio(peak-value,peak)))
            returns.append(dict(at_ms=point['at_ms'],return_fraction=None if value is None or previous is None or previous<=0 else ratio(value-previous,previous)))
            previous=value
        final=None if terminal['equity_usdt'] is None else Decimal(terminal['equity_usdt']); net=None if final is None else final-Decimal(initial)
    return dict(initial_equity_usdt=initial,final_equity_usdt=None if final is None else decimal_text(final),net_pnl_usdt=None if net is None else decimal_text(net),
        total_return_fraction=None if net is None else ratio(net,Decimal(initial)),samples=len(samples),missing_samples=missing,
        max_drawdown_usdt=decimal_text(dd) if not missing else None,max_drawdown_fraction=decimal_text(fraction) if not missing else None,
        available_sample_drawdown_lower_bound_usdt=decimal_text(dd),regular_arithmetic_returns=returns,annualized_return=None,sharpe=None,
        note='One shared wallet plus mark PnL, with actual admitted fees/funding. No deposits/withdrawals, guaranteed stops, exchange margin tiers, liquidation fills or annualized performance estimator.')


class PortfolioReplay:
    def __init__(self,simulations,pins,models,events,policy=None,config=None):
        self.policy=policy or RiskPolicy(); self.config=config or ReplayConfig(); self.data=load(simulations,pins,self.config.decision_start_ms,self.config.decision_end_ms,self.config.max_candidates)
        self.events=tuple(events)
        if len(self.events)>self.config.max_events: raise ValidationError('Portfolio replay event budget exceeded')
        common=self.data['common']; self.ds=common['dataset']; self.start=self.data['start_ms']; self.end=self.data['end_ms']
        if (self.ds['as_of_ms']-self.start)//self.config.sample_interval_ms+1>self.policy.max_samples: raise ValidationError('Portfolio regular sample budget exceeded')
        prefix=fingerprint([]); cursor=None
        for e in self.events:
            point=(e['available_ms'],e['id'])
            if cursor is not None and point<=cursor or e['available_ms']>self.ds['as_of_ms']: raise ValidationError('Nonchronological funded replay prefix')
            prefix=fingerprint([prefix,fingerprint(e)]); cursor=point
        if len(self.events)!=self.ds['event_count'] or prefix!=common['input_prefix_hash'] or list(cursor or [])!=list(common['input_cursor'] or []):
            raise ValidationError('C02 event content differs from pinned C11 outcome prefix')
        self.models=tuple(verified_model(m) for m in models); self.by_protocol={}
        for model in self.models:
            d=model.document(); f=d['fit']
            if f['window']['cutoff_ms']>self.start or d['available_ms']>self.start: raise ValidationError('Funded replay models must be frozen and available before decision window')
            if {s['producer_code_hash'] for s in f['sources']}!={common['code_hash']}: raise ValidationError('Estimator labels and tested execution producer differ')
            for ph in f['protocols']:
                if ph in self.by_protocol: raise ValidationError('One frozen model per exact execution protocol; no opportunistic fallback')
                self.by_protocol[ph]=model
        self.manifest=FrozenRecord.create(dict(schema_version=1,component='C13',kind='funded_replay',sources=self.data['sources'],
            dataset=self.ds,input_prefix_hash=prefix,recipe_hash=fingerprint(dict(policy=self.policy.document(),config=self.config.document())),policy=self.policy.document(),policy_hash=self.policy.policy_hash,config=self.config.document(),
            models=[dict(model_hash=m.digest,model=m.document()) for m in self.models],decision_window_ms=[self.start,self.end],
            code_hash=code_hash(),python=platform.python_version(),
            semantics='Cold-start flat funded book. Same-time source prefix completes, existing closes/funding apply, exact C07 fills recheck, then deterministic batch admission. A later same-instrument event after the source first fill rejects that opportunity.',
            sizing='Predeclared quantity/model ladder; never rescale C11 outcomes or reuse expectancy at a different size.',live_approved=False))
        self.artifacts=[]; self.ran=False

    def add(self,kind,payload):
        if len(self.artifacts)>=self.policy.max_artifacts: raise ValidationError('Portfolio artifact budget exceeded; no truncation')
        d=dict(schema_version=1,run_hash=self.manifest.digest,sequence=len(self.artifacts)+1,kind=kind,payload=payload,payload_hash=fingerprint(payload))
        self.artifacts.append(FrozenRecord.create(d))

    def run(self):
        if self.ran: raise ValidationError('Funded replay instances are single-use')
        self.ran=True; common=self.data['common']; fees=FeeSchedule.from_dict(common['fees']); execution=ExecutionConfig.from_dict(common['execution'])
        shadow=None
        if self.data['candidates']:
            first=next(iter(self.data['candidates'].values())); intent=first['intent']; c=first['candidate']
            from .contracts import Offer
            from tradee.c07 import ExecutionIntent
            seed=ExecutionIntent(intent.trade_id+':entry',c['instrument_id'],c['symbol'],'buy' if c['side']=='long' else 'sell',intent.quantity,c['detected_ms'],c['expires_ms'],c['reference_price'])
            shadow=ExecutionEngine(self.ds,[seed],common['metadata_snapshots'][-1],common['metadata_versions'],fees,execution,decision_ms=self.ds['as_of_ms'])
        current={}; accepted={}; seen=set(); marks={}; samples=[]; peak=Decimal(self.config.initial_cash_usdt); breaches=[]; rejected=Counter(); attempts=0; source_events=defaultdict(list)
        for e in self.events: source_events[e['available_ms']].append(e)
        grid=set(range(self.start,self.ds['as_of_ms']+1,self.config.sample_interval_ms))
        clocks=sorted(set(source_events)|set(self.data['revisions'])|set(self.data['entries'])|grid|{self.ds['as_of_ms']})
        now_cursor=None; prefix=fingerprint([])

        def snapshot(when):
            nonlocal peak
            positions=[]; cash=Decimal(self.config.initial_cash_usdt); funding_known=True
            with exact():
                for key in accepted:
                    t=current.get(key)
                    if t is None: raise ValidationError('Accepted position lacks a causal outcome state')
                    cash+=sum((Decimal(v['amount_usdt']) for v in t['state']['ledger'].values() if v['amount_usdt'] is not None),Decimal(0))
                    funding_known&=t['funding_usdt'] is not None
                    s=t['state']; q=s['remaining_quantity']
                    if Decimal(q)>0:
                        meta=self.data['candidates'][key]
                        positions.append(dict(position_id='/'.join(key),candidate_id=s['candidate_id'],instrument_id=s['instrument_id'],symbol=s['symbol'],side=s['side'],
                            quantity=q,entry_price=s['entry_price'],stop_price=s['levels']['stop'],opened_ms=s['entry_ms'],horizon=meta['scenario']['horizon'],exit_fee_rate=fees.taker_rate))
            state=AccountSnapshot(when,when,decimal_text(cash),decimal_text(peak),positions=positions,marks=list(marks.values()),seen_candidates=sorted(seen),funding_known=funding_known)
            measure=inspect(state,when,self.policy); eq=measure['equity_usdt']
            if eq is not None: peak=max(peak,Decimal(eq))
            return state,measure

        for when in clocks:
            last_instrument={}
            for e in source_events.get(when,[]):
                now_cursor=(e['available_ms'],e['id']); prefix=fingerprint([prefix,fingerprint(e)]); last_instrument[e['instrument_id']]=e['id']
                if shadow is not None: shadow.push(e)
                if e['kind']=='mark' and e['final']:
                    old=marks.get(e['instrument_id'])
                    if old is None or (e['event_ms'],e['available_ms'],e['id'])>(old['event_ms'],old['available_ms'],old['event_id']):
                        marks[e['instrument_id']]=dict(instrument_id=e['instrument_id'],symbol=e['symbol'],price=e['data']['mark_price'],event_ms=e['event_ms'],available_ms=e['available_ms'],event_id=e['id'])
            for key,t in self.data['revisions'].get(when,[]):
                current[key]=t
                if key in accepted: self.add('book_revision',dict(at_ms=when,source_key=list(key),outcome=t))
            if when<self.start: continue
            state,measure=snapshot(when)
            offers=[]; contexts={}
            for key,old_execution in self.data['entries'].get(when,[]):
                meta=self.data['candidates'][key]; c=meta['candidate']; attempts+=1
                reason=None; t=current.get(key)
                if t is None or t['entry_ms']!=when: raise ValidationError('Missing current first-entry funding/state evidence')
                if t['funding_usdt'] is None: reason='candidate_funding_coverage_unknown'
                if last_instrument.get(c['instrument_id'],0)>old_execution['input_cursor'][1]: reason='later_same_time_instrument_event_requires_new_execution_path'
                q=EstimateRequest(c,meta['feature'],meta['scenario'],common['execution'],common['fees'],common['funding'],common['candidates'],when)
                model=self.by_protocol.get(fingerprint(q.protocol))
                if model is None: reason='no_frozen_exact_size_model'
                if reason:
                    rejected[reason]+=1; self.add('suppressed',dict(at_ms=when,source_key=list(key),candidate_id=c['candidate_id'],reason=reason)); continue
                offer=Offer(q.document(),model.document()); offers.append(offer); contexts[offer.offer_id]=(key,old_execution)
            if offers:
                def recheck(offer,stamp):
                    universe=[u for u in common['metadata_snapshots'] if u['as_of_ms']<=stamp]
                    chosen=universe[-1] if universe else common['metadata_snapshots'][0]
                    e=ExecutionEngine(self.ds,[offer.execution_intent],chosen,common['metadata_versions'],fees,execution,[offer.request.feature_snapshot.document()],self.ds['as_of_ms'])
                    for name in ('quotes','candles','cursor','prefix_hash','last_event_hash','event_count'): setattr(e,name,deepcopy(getattr(shadow,name)))
                    e.funding=deepcopy(shadow.funding); result=e.evaluate(offer.execution_intent,stamp)
                    d=result.document(); key,old=contexts[offer.offer_id]
                    if d['ready'] and any(d['fill'][k]!=old['fill'][k] for k in ('quantity','price','fee_usdt','source_event_id','execution_as_of_ms')):
                        raise ValidationError('C07 recheck differs from pinned C09 first fill; resimulation required')
                    return result
                allocation=allocate(state,offers,self.policy,recheck); d=allocation.document(); self.add('allocation',d)
                for decision in d['decisions']:
                    key,_=contexts[decision['offer_id']]
                    if decision['status']=='admitted': accepted[key]=dict(at_ms=when,decision=decision); seen.add(decision['candidate_id'])
                    else: rejected.update(decision['reasons'])
                state,measure=snapshot(when)
            if measure['exposure'] and measure['exposure']['unsupported_margin_breach']:
                flag=dict(at_ms=when,reason='fully_collateralized_margin_proxy_breached'); breaches.append(flag); self.add('risk_breach',flag)
            if when in grid:
                point=dict(at_ms=when,equity_usdt=measure['equity_usdt'],cash_usdt=state.cash_usdt,unrealized_gross_usdt=measure['unrealized_gross_usdt'],
                    risk=public_risk(measure),input_cursor=now_cursor,input_prefix_hash=prefix)
                samples.append(point); self.add('sample',point)
        terminal_state,terminal=snapshot(self.ds['as_of_ms'])
        trades=[]
        for key,a in accepted.items():
            t=current[key]; trades.append(dict(source_key=list(key),candidate_id=t['state']['candidate_id'],scenario=self.data['candidates'][key]['scenario'],admitted_ms=a['at_ms'],outcome=t))
        complete=bool(trades) and all(t['outcome']['ready'] for t in trades) and not breaches and all(p['equity_usdt'] is not None for p in samples)
        summary=diagnostics(samples,self.config.initial_cash_usdt,terminal)
        report=FrozenRecord.create(dict(schema_version=1,component='C13',kind='funded_portfolio_report',run_hash=self.manifest.digest,completed=True,ready=complete,live_approved=False,
            policy_hash=self.policy.policy_hash,sources=self.data['sources'],decision_window_ms=[self.start,self.end],evaluation_as_of_ms=self.ds['as_of_ms'],
            input_cursor=now_cursor,input_prefix_hash=prefix,metrics=summary,trades=trades,terminal_account=terminal_state.document(),terminal_risk=public_risk(terminal),
            coverage=dict(inventoried_size_options=len(self.data['candidates']),unique_candidates=len({m['candidate']['candidate_id'] for m in self.data['candidates'].values()}),
                executable_size_options=attempts,admitted_positions=len(accepted),not_executable=len(self.data['candidates'])-attempts,rejection_reasons=dict(sorted(rejected.items()))),
            margin_proxy_breaches=breaches,artifact_count=len(self.artifacts),artifact_manifest_hash=fingerprint([a.digest for a in self.artifacts]),
            limitations=['First executable opportunity only; unselected later entry times require different tested C09 policy','No external deposits/withdrawals or actual user fills',
                'One position per instrument; opposite sides and horizons do not receive hedge credit','Fully collateralized research proxy, no exchange liquidation or passive/partial entry model',
                'Recorded complete source prefixes and explicit funding evidence required; missing marks/funding keep equity unknown','C12 portfolio-policy inference/promotion and C14/C15 operations remain separate gates']))
        return self.manifest,report,tuple(self.artifacts)
