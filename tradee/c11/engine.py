"""Causal two-pass orchestration of shared detectors and independent lifecycles.

Detection prepares immutable intents; C09 activates each only at its exact
source prefix in pass two. No future outcome is passed into detection/admission.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from itertools import groupby
import platform

from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c08 import CandidateConfig, CandidateEngine
from tradee.c09 import LifecycleEngine, TradeIntent
from tradee.c06 import FundingConfig, SettlementCalendar
from tradee.c06.engine import code_hash
from .contracts import Scenario, SimulationConfig, SimulationRecord
from .analysis import metrics, attribution, valuation, regular_diagnostics


@dataclass(frozen=True)
class SimulationResult:
    manifest: SimulationRecord
    report: SimulationRecord
    artifacts: tuple


class Simulator:
    def __init__(self, dataset, scenarios, snapshots, versions, fees, execution, candidates=None, funding=None, calendars=(), config=None):
        from tradee.c07 import FeeSchedule, ExecutionConfig
        if not isinstance(fees,FeeSchedule) or not isinstance(execution,ExecutionConfig): raise ValidationError('Explicit fee and execution contracts required')
        if not isinstance(dataset,dict) or type(dataset.get('event_count')) is not int or dataset['event_count']<0:
            raise ValidationError('Pinned dataset event count required')
        self.dataset=deepcopy(dataset)
        self.scenarios=tuple(s if isinstance(s,Scenario) else Scenario.from_dict(s) for s in scenarios)
        if not self.scenarios or len({s.name for s in self.scenarios})!=len(self.scenarios): raise ValidationError('Unique nonempty simulation scenarios required')
        if len({(s.strategy.strategy_hash,s.policy.policy_hash,s.quantity) for s in self.scenarios})!=len(self.scenarios):
            raise ValidationError('Duplicate independent scenario hypothesis/policy/size')
        self.execution=execution; self.fees=fees
        self.candidates=candidates or CandidateConfig(execution.enabled_symbols,execution.metadata_mode,execution.max_metadata_age_ms)
        if (self.candidates.enabled_symbols!=execution.enabled_symbols or self.candidates.metadata_mode!=execution.metadata_mode or
                self.candidates.max_metadata_age_ms!=execution.max_metadata_age_ms):
            raise ValidationError('Candidate and execution metadata policies must agree')
        self.config=config or SimulationConfig(); self.start,self.end=self.config.window(dataset)
        self.funding=funding or FundingConfig()
        self.calendars=tuple(c if isinstance(c,SettlementCalendar) else SettlementCalendar.from_dict(c) for c in calendars)
        if len({c.instrument_id for c in self.calendars})!=len(self.calendars): raise ValidationError('Duplicate simulation funding calendar')
        # These engines also validate the dataset and all pinned metadata.
        self.detectors={s.name:CandidateEngine(dataset,s.strategy,snapshots,versions,self.candidates) for s in self.scenarios}
        first=next(iter(self.detectors.values()))
        self.snapshots=first.book.snapshots; self.versions=first.book.versions
        for s in self.scenarios:
            if dataset['mode']=='modeled' and s.policy.trigger_source not in ('bar_close','bar_range'):
                raise ValidationError('Modeled simulations require explicit candle triggers')
            required={'contract_trade':'trade','mark':'mark'}.get(s.policy.trigger_source)
            if required and required not in dataset['kinds']: raise ValidationError('Scenario trigger missing from dataset scope')
        if dataset['mode']=='modeled' and (execution.market_model!='modeled_bar' or execution.bar_mark_proxy!='bar_close' or execution.metadata_mode!='research_assumption'):
            raise ValidationError('Modeled simulation requires explicit modeled execution, metadata assumption and bar mark proxy')
        if dataset['mode']=='recorded' and execution.market_model!='recorded_quote': raise ValidationError('Recorded simulation requires recorded quote execution')
        # Validate fees/config even when there are no candidates.
        self.manifest=SimulationRecord.create(dict(schema_version=1,component='C11',dataset=dataset,
            scenarios=[s.document() for s in self.scenarios],config=self.config.document(),decision_window_ms=[self.start,self.end],
            candidates=self.candidates.document(),execution=execution.document(),fees=fees.document(),funding=self.funding.document(),
            calendars=[c.document() for c in self.calendars],metadata_snapshots=self.snapshots,metadata_versions=self.versions,
            detectors={name:e.manifest.document() for name,e in self.detectors.items()},code_hash=code_hash(),python=platform.python_version(),
            schedule='C02 (available_ms,id) prefix; source events at a timestamp precede same-time timers and regular samples; exact deadlines between source timestamps',
            boundaries='Decision detection times in [start,end); pre-roll remains context; all selected trades consume the pinned outcome tail through as_of, without forced closure',
            track='independent candidates; overlapping hypotheses do not share capital or consume each other\'s market liquidity',
            publication='Completed results publish atomically. Interrupted runs replay both passes; partial-run checkpointing is a deferred scale feature.',
            labels='Prefix-mature outcomes retain first-known revision times; later funding/path revisions can change or revoke labels. Consumers must respect availability.',
            limits='No finite-capital portfolio, liquidation, walk-forward selection, profitability certification or authenticated orders'))
        self.artifacts=[]; self._seen=set(); self.ran=False

    def _add(self,kind,payload,scenario=None):
        key=(kind,scenario,fingerprint(payload))
        if key in self._seen: return
        if len(self.artifacts)>=self.config.max_artifacts: raise ValidationError('Simulation artifact budget exceeded; no results published')
        self._seen.add(key)
        self.artifacts.append(SimulationRecord.create(dict(schema_version=1,run_hash=self.manifest.digest,sequence=len(self.artifacts)+1,
            kind=kind,scenario=scenario,payload_hash=key[2],payload=payload)))

    @staticmethod
    def _validate_coverage(engine, dataset):
        if engine.features.event_count!=dataset['event_count']: raise ValidationError('Simulation did not consume the complete pinned dataset')

    def run(self,source):
        """source is a repeatable iterator factory over the same pinned C02 data."""
        if self.ran: raise ValidationError('Simulator instances are single-use; construct a new run for replay')
        self.ran=True
        intents={s.name:[] for s in self.scenarios}; coverage={}; count=0
        statuses={s.name:Counter() for s in self.scenarios}; reasons={s.name:Counter() for s in self.scenarios}
        for event in source():
            for scenario in self.scenarios:
                engine=self.detectors[scenario.name]
                for record in engine.advance(event):
                    d=record.document(); selected=bool(d['candidate'] and self.start<=d['candidate']['detected_ms']<self.end)
                    statuses[scenario.name][d['status']]+=1; reasons[scenario.name].update(d['reasons'])
                    self._add('candidate_decision',dict(record_hash=record.digest,record=d,selected=selected),scenario.name)
                    if selected:
                        count+=1
                        if count>self.config.max_candidates: raise ValidationError('Simulation candidate budget exceeded; no candidates silently truncated')
                        c=d['candidate']; f=engine.pending_features[c['feature_snapshot_hash']]
                        intents[scenario.name].append(TradeIntent(c,{'snapshot_hash':f.digest,**f.document()},scenario.quantity,scenario.policy.document()))
                for f in engine.pending_features.values(): self._add('feature',{'snapshot_hash':f.digest,**f.document()},scenario.name)
                for h,d in engine.features.lineages.items(): self._add('lineage',dict(lineage_hash=h,document=d),scenario.name)
                engine.pending_features.clear(); engine.features.lineages.clear()
        for name,e in self.detectors.items():
            self._validate_coverage(e,self.dataset)
            coverage[name]=dict(evaluations=e.output_count,emitted=e.emitted_count,selected=len(intents[name]),
                outside_decision_window=e.emitted_count-len(intents[name]),event_count=e.features.event_count,input_cursor=e.cursor,input_prefix_hash=e.prefix_hash)
            coverage[name].update(statuses=dict(sorted(statuses[name].items())),reasons=dict(sorted(reasons[name].items())))
        engines={s.name:LifecycleEngine(self.dataset,intents[s.name],self.snapshots,self.versions,self.fees,self.execution,self.funding,self.calendars)
                 for s in self.scenarios if intents[s.name]}
        for name,e in engines.items(): self._add('lifecycle_manifest',dict(run_hash=e.manifest.digest,**e.manifest.document()),name)
        reports={}; samples={s.name:[] for s in self.scenarios}; last_revisions={}; final_trades=[]
        now=self.dataset['start_ms']-1; grid=self.start; clock_ticks=0

        def transitions(name,records):
            for r in records: self._add('transition',dict(transition_hash=r.digest,**r.document()),name)

        def observe(when,sample=False):
            for scenario in self.scenarios:
                name=scenario.name; e=engines.get(name)
                if e is None:
                    if sample:
                        point=dict(at_ms=when,pnl_usdt='0',gross_realized_usdt='0',fees_usdt='0',funding_usdt='0',unrealized_gross_usdt='0',
                            known_cash_subtotal_usdt='0',missing_marks=[],mark_sources=[],open_trades=0,input_cursor=None,input_prefix_hash=None)
                        samples[name].append(point); self._add('sample',point,name)
                    continue
                r=e.report(when,complete_prefix=True).document(); reports[name]=r
                for t in r['trades']:
                    if not t['state']['activated']: continue
                    # Economic/label revision, not a new observation merely because clock advanced.
                    rev=fingerprint(dict(ledger=t['state']['ledger'],status=t['status'],flags=t['ambiguity_flags'],
                        funding=t['funding_usdt'],ready=t['ready'],outcome_revision=t['outcome_revision_hash']))
                    key=(name,t['trade_id'])
                    if last_revisions.get(key)!=rev:
                        last_revisions[key]=rev
                        self._add('outcome_revision',dict(observed_ms=when,revision_hash=rev,outcome=t),name)
                if sample:
                    point=valuation(e,r,when,self.config); samples[name].append(point); self._add('sample',point,name)

        def next_deadline():
            deadlines=[]
            for e in engines.values():
                for i in e.intents:
                    s=e.states[i.trade_id]
                    if s['status']=='pending_entry':
                        c=i.candidate.document(); deadlines.extend([e.execution.action_time(e._entry_intent(i)),c['expires_ms']])
                    if s['status'] in ('open','exit_pending'):
                        deadlines.append(s['entry_ms']+i.policy.max_holding_ms)
                        if s['exit_pending']:
                            deadlines.extend([s['exit_pending']['not_before_ms'],s['exit_pending']['deadline_ms']])
            return min((t for t in deadlines if t>now),default=self.dataset['as_of_ms']+1)

        def timers_before(boundary,inclusive=False):
            nonlocal now,grid,clock_ticks
            while True:
                stamp=min(grid,next_deadline())
                if stamp>self.dataset['as_of_ms'] or stamp>boundary or (stamp==boundary and not inclusive): break
                for name,e in engines.items(): transitions(name,e.tick(stamp))
                now=stamp; clock_ticks+=1; sample=stamp==grid
                observe(stamp,sample)
                if sample: grid+=self.config.sample_interval_ms

        # Consume equal-time sources before that time's scheduled timers/samples.
        second_count=0; second_prefix=fingerprint([]); second_cursor=None
        for stamp,group in groupby(source(),key=lambda e:e['available_ms']):
            if stamp<now or stamp>self.dataset['as_of_ms']: raise ValidationError('Nonchronological or future simulation source')
            timers_before(stamp)
            for event in group:
                cursor=(event['available_ms'],event['id'])
                if second_cursor is not None and cursor<=second_cursor: raise ValidationError('Duplicate or nonchronological simulation source')
                second_prefix=fingerprint([second_prefix,fingerprint(event)])
                second_cursor=cursor; second_count+=1
                for name,e in engines.items():
                    transitions(name,e.advance(event)); e.features.lineages.clear()
            now=stamp; observe(stamp)
            timers_before(stamp,inclusive=True)
        timers_before(self.dataset['as_of_ms'],inclusive=True)
        for name,e in self.detectors.items():
            if second_count!=self.dataset['event_count'] or second_cursor!=e.cursor or second_prefix!=e.prefix_hash:
                raise ValidationError('Simulation source changed between detection and lifecycle replay')
        for scenario in self.scenarios:
            name=scenario.name; e=engines.get(name)
            if e is None: continue
            self._validate_coverage(e,self.dataset)
            records,r=e.finish(); transitions(name,records); reports[name]=r.document()
        observe(self.dataset['as_of_ms'])
        # End-of-tail ambiguity does not change cash/mark amounts; it remains in outcomes.
        for scenario in self.scenarios:
            e=engines.get(scenario.name)
            if e is None: continue
            intent_map={i.trade_id:i.candidate.document() for i in e.intents}
            for t in reports[scenario.name]['trades']:
                c=intent_map[t['trade_id']]
                final_trades.append(dict(**t,scenario=scenario.name,horizon=scenario.horizon,family=c['hypothesis_family'],
                    strategy_hash=c['strategy_hash'],symbol=c['symbol'],side=c['side'],timeframe=c['timeframe'],candidate_id=c['candidate_id'],
                    detected_ms=c['detected_ms'],feature_snapshot_hash=c['feature_snapshot_hash'],availability_basis=c['availability_basis']))
        all_samples=[]
        from decimal import Decimal
        from tradee.c07.math import exact
        from tradee.c06.contracts import decimal_text
        for idx in range(len(next(iter(samples.values())))):
            group=[samples[s.name][idx] for s in self.scenarios]
            with exact(): value=None if any(p['pnl_usdt'] is None for p in group) else decimal_text(sum((Decimal(p['pnl_usdt']) for p in group),Decimal(0)))
            all_samples.append(dict(at_ms=group[0]['at_ms'],pnl_usdt=value))
            self._add('sample',dict(**all_samples[-1],scope='combined independent scenarios; not portfolio equity'))
        groups={}
        for field in ('scenario','family','horizon','symbol','side','timeframe'):
            groups[field]={value:metrics([t for t in final_trades if t[field]==value]) for value in sorted({t[field] for t in final_trades})}
        for s in self.scenarios: groups['scenario'].setdefault(s.name,metrics([]))
        inventory=Counter(a.document()['kind'] for a in self.artifacts)
        summary=metrics(final_trades)
        report=SimulationRecord.create(dict(schema_version=1,run_hash=self.manifest.digest,dataset_hash=self.dataset['dataset_hash'],completed=True,
            ready=bool(final_trades) and summary['unresolved']==0,has_mature_evidence=summary['mature']>0,
            scope='independent-candidate evaluation; not portfolio returns, trained expectancy or out-of-sample evidence',
            evaluation_as_of_ms=self.dataset['as_of_ms'],input_cursor=second_cursor,input_prefix_hash=second_prefix,event_count=second_count,
            decision_window_ms=[self.start,self.end],candidate_coverage=coverage,clock_ticks=clock_ticks,
            metrics=summary,attribution=attribution(final_trades),groups=groups,trades=final_trades,
            regular_pnl=dict(combined=regular_diagnostics(all_samples),scenarios={name:regular_diagnostics(rows) for name,rows in samples.items()}),
            artifact_inventory=dict(sorted(inventory.items())),artifact_manifest_hash=fingerprint([a.digest for a in self.artifacts]),
            outcome_export='Use mature revisions with outcome_known_ms strictly before inference; unresolved/revoked outcomes and observation times are retained. C12 must also purge overlapping intervals.',
            limitations=['independent size; no shared capital/liquidation or book consumption','no walk-forward selection or multiple-testing control',
                'coverage-dependent sampled trigger path and valuation','modeled candle funding remains unknown','completed-run atomic publication; interrupted runs restart']))
        return SimulationResult(self.manifest,report,tuple(self.artifacts))
