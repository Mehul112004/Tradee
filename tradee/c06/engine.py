"""Funding settlement accounting and prefix-causal next-settlement estimates."""
from copy import deepcopy
from decimal import Decimal
import hashlib
from pathlib import Path
import platform
import re

from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c02.domain import KINDS, integer, number
from .contracts import (FundingConfig, FundingRecord, PositionTimeline, SettlementCalendar,
                        cashflow, total_amounts, identity)


def code_hash():
    root=Path(__file__).resolve().parents[1]
    return fingerprint({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(root.rglob('*.py'))})


class FundingEngine:
    def __init__(self, dataset, positions=(), calendars=(), config=None, decision_ms=None):
        if (not isinstance(dataset,dict) or type(dataset.get('schema_version')) is not int or dataset.get('schema_version')!=1 or dataset.get('mode')!='recorded'
                or not isinstance(dataset.get('dataset_hash'),str) or not dataset['dataset_hash']):
            raise ValidationError('Funding requires a pinned recorded C02 dataset')
        for field in ('start_ms','end_ms','as_of_ms'):
            integer(dataset.get(field),field)
        if (dataset['start_ms']>=dataset['end_ms'] or dataset['as_of_ms']<dataset['start_ms']
                or not isinstance(dataset.get('symbols'),list) or not dataset['symbols']
                or not isinstance(dataset.get('kinds'),list) or not dataset['kinds'] or set(dataset['kinds'])-set(KINDS)):
            raise ValidationError('Invalid funding dataset range')
        self.dataset=deepcopy(dataset)
        self.config=config or FundingConfig()
        self.positions=tuple(p if isinstance(p,PositionTimeline) else PositionTimeline.from_dict(p) for p in positions)
        self.calendars=tuple(c if isinstance(c,SettlementCalendar) else SettlementCalendar.from_dict(c) for c in calendars)
        if len({p.position_id for p in self.positions})!=len(self.positions):
            raise ValidationError('Duplicate position ID')
        if len({c.instrument_id for c in self.calendars})!=len(self.calendars):
            raise ValidationError('One calendar per instrument per run is required')
        if any(p.symbol not in dataset['symbols'] for p in (*self.positions,*self.calendars)):
            raise ValidationError('Position/calendar outside dataset symbol scope')
        self.decision_ms=dataset['as_of_ms'] if decision_ms is None else integer(decision_ms,'decision time')
        if not dataset['start_ms']<=self.decision_ms<=dataset['as_of_ms']:
            raise ValidationError('Decision must be within the pinned evidence horizon and >= dataset start')
        self.manifest=FundingRecord.create(dict(schema_version=1,checkpoint_schema=1,component='C06',
            dataset=dataset,positions=[p.document() for p in self.positions],calendars=[c.document() for c in self.calendars],
            config=self.config.document(),decision_ms=self.decision_ms,code_hash=code_hash(),python=platform.python_version(),
            formula='cashflow_USDT = -side_sign * base_quantity * settlement_mark_price * settled_rate',
            side_sign={'long':1,'short':-1},numeric_policy='Decimal400-exact-unrounded-v1',
            exposure_policy='post-change quantity at nominal timestamp; strict guard suppresses boundary ambiguity',
            input_role='caller-supplied position evidence/scenarios; not trading decisions or account execution'))
        self.settlements={}; self.marks={}
        self.cursor=None; self.last_event_hash=None; self.prefix_hash=fingerprint([])
        self.event_count=0; self.evaluated_through_ms=-1

    def _validate(self, e):
        if not isinstance(e,dict) or type(e.get('schema_version')) is not int or e.get('schema_version')!=1 or e.get('availability_basis')!='recorded':
            raise ValidationError('Unsupported or mixed funding input contract')
        for name in ('id','available_ms','received_ms','event_ms'):
            integer(e.get(name),name)
        if (not e['id'] or type(e.get('final')) is not bool or e.get('symbol') not in self.dataset['symbols']
                or e.get('kind') not in self.dataset['kinds'] or not e.get('metadata_version')):
            raise ValidationError('Funding event outside scope or missing identity')
        identity(e.get('instrument_id'),e['symbol'])
        if not isinstance(e.get('raw_sha256'),str) or not re.fullmatch('[a-f0-9]{64}',e['raw_sha256']):
            raise ValidationError('Funding source checksum is required')
        stamp=e.get('data',{}).get('open_ms',e['event_ms'])
        if not self.dataset['start_ms']<=stamp<self.dataset['end_ms']:
            raise ValidationError('Funding event outside dataset range')
        if e['available_ms']>self.decision_ms:
            raise ValidationError('Funding input is beyond the pinned run decision horizon')
        if e['received_ms']>e['available_ms'] or (e['final'] and e['event_ms']>e['available_ms']):
            raise ValidationError('Funding event available before receipt/event time')
        if e['kind'] in ('funding','mark'):
            if not e['final'] or e.get('key')!=str(e['event_ms']):
                raise ValidationError('Funding/mark requires canonical finalized event identity')
            d=e.get('data',{})
            if e['kind']=='funding':
                if set(d)!={'funding_rate','mark_price'}:
                    raise ValidationError('Invalid settlement fields')
            else:
                if set(d)!={'funding_rate','mark_price','index_price','next_funding_ms'}:
                    raise ValidationError('Invalid mark estimate fields')
                number(d['index_price'],positive=True); integer(d['next_funding_ms'],'next funding time')
            if number(d['funding_rate'],signed=True)!=d['funding_rate'] or number(d['mark_price'],positive=True)!=d['mark_price']:
                raise ValidationError('Noncanonical funding decimals')

    def push(self, event):
        e=deepcopy(event); self._validate(e)
        cursor=(e['available_ms'],e['id']); digest=fingerprint(e)
        if cursor==self.cursor and digest==self.last_event_hash:
            return False
        if self.cursor is not None and cursor<=self.cursor:
            raise ValidationError('Funding input must follow exact pinned replay order')
        if cursor[0]<self.evaluated_through_ms:
            raise ValidationError('Funding input predates an evaluated decision')
        self.cursor=cursor; self.last_event_hash=digest
        self.prefix_hash=fingerprint([self.prefix_hash,digest]); self.event_count+=1
        if e['kind']=='funding':
            self.settlements[(e['instrument_id'],e['event_ms'])]=e
        elif e['kind']=='mark':
            previous=self.marks.get(e['instrument_id'])
            rank=lambda r:(r['event_ms'],r['available_ms'],r['id'])
            if previous is None or rank(e)>rank(previous):
                self.marks[e['instrument_id']]=e
        return True

    def _decision(self, when):
        integer(when,'evaluation time')
        if when>self.decision_ms or when<self.dataset['start_ms'] or (self.cursor and when<self.cursor[0]):
            raise ValidationError('Cannot evaluate funding outside run horizon or through a future prefix')
        self.evaluated_through_ms=max(self.evaluated_through_ms,when)

    def context(self, position, when):
        """Estimate only the next known settlement, assuming current exposure persists."""
        self._decision(when)
        if not isinstance(position,PositionTimeline):
            position=PositionTimeline.from_dict(position)
        mark=self.marks.get(position.instrument_id)
        quantity=position.quantity_at(when)
        status='missing_estimate'; amount=None
        if mark:
            if when-mark['event_ms']>=self.config.max_mark_age_ms:
                status='stale_estimate'
            elif mark['data']['next_funding_ms']<=when:
                status='expired_estimate'
            else:
                status='valid'; amount=cashflow(position.side,quantity,mark['data']['mark_price'],mark['data']['funding_rate'])
        return dict(position_id=position.position_id,instrument_id=position.instrument_id,kind='next_settlement_estimate',
            status=status,estimated_cashflow_usdt=amount,quantity=quantity,
            rate=None if mark is None else mark['data']['funding_rate'],
            mark_price=None if mark is None else mark['data']['mark_price'],
            next_funding_ms=None if mark is None else mark['data']['next_funding_ms'],
            time_to_funding_ms=None if mark is None else mark['data']['next_funding_ms']-when,
            source_event_id=None if mark is None else mark['id'],
            source_available_ms=None if mark is None else mark['available_ms'],
            event_age_ms=None if mark is None else when-mark['event_ms'],
            assumption='current quantity, published rate and mark held unchanged until next funding; not a settled charge')

    def report(self, when=None):
        when=self.decision_ms if when is None else when
        self._decision(when)
        start=self.dataset['start_ms']; end=min(self.dataset['end_ms'],when+1)
        calendars={c.instrument_id:c for c in self.calendars}; results=[]
        for p in self.positions:
            calendar=calendars.get(p.instrument_id)
            calendar_covers=calendar is not None and calendar.start_ms<=start and calendar.end_ms>=end
            expected=set(t for t in calendar.settlement_times_ms if start<=t<end) if calendar else set()
            observed={t:e for (identity_id,t),e in self.settlements.items() if identity_id==p.instrument_id and start<=t<end}
            status='complete_under_declared_calendar' if calendar_covers else 'unknown_schedule'
            if calendar_covers and set(observed)-expected:
                status='schedule_conflict'
            entries=[]
            for stamp in sorted(expected|set(observed)):
                source=observed.get(stamp); quantity=p.quantity_at(stamp)
                entry_status='valid'; amount=None
                if self.config.boundary_policy=='strict' and p.boundary_ambiguous(stamp,self.config.boundary_guard_ms):
                    entry_status='boundary_ambiguous'
                elif Decimal(quantity)==0:
                    entry_status='not_exposed'; amount='0'
                elif source is None:
                    entry_status='missing_settlement'
                else:
                    amount=cashflow(p.side,quantity,source['data']['mark_price'],source['data']['funding_rate'])
                key=fingerprint([p.position_id,p.instrument_id,stamp,'funding'])
                entry=dict(cashflow_key=key,position_id=p.position_id,instrument_id=p.instrument_id,
                    funding_time_ms=stamp,quantity=quantity,side=p.side,status=entry_status,amount_usdt=amount,
                    settled_rate=None if source is None else source['data']['funding_rate'],
                    settlement_mark_price=None if source is None else source['data']['mark_price'],
                    source_event_id=None if source is None else source['id'],
                    source_available_ms=None if source is None else source['available_ms'],
                    source_metadata_version=None if source is None else source['metadata_version'],
                    source_raw_sha256=None if source is None else source['raw_sha256'],
                    recognition_as_of_ms=when,boundary_policy=self.config.boundary_policy)
                entry['revision_hash']=fingerprint({k:v for k,v in entry.items() if k!='recognition_as_of_ms'})
                entries.append(entry)
            unresolved=[e['status'] for e in entries if e['amount_usdt'] is None]
            if unresolved and status=='complete_under_declared_calendar':
                status='unresolved_cashflows'
            observed_total=total_amounts(e['amount_usdt'] for e in entries if e['amount_usdt'] is not None)
            complete=status=='complete_under_declared_calendar'
            results.append(dict(position_id=p.position_id,instrument_id=p.instrument_id,symbol=p.symbol,side=p.side,
                coverage_status=status,calendar_evidence=None if calendar is None else calendar.evidence,
                cashflows=entries,known_cashflow_subtotal_usdt=observed_total,
                total_cashflow_usdt=observed_total if complete else None,
                estimate=self.context(p,when),ready=complete))
        return FundingRecord.create(dict(schema_version=1,run_hash=self.manifest.digest,
            dataset_hash=self.dataset['dataset_hash'],evaluation_as_of_ms=when,
            window_start_ms=start,window_end_ms=end,input_cursor=self.cursor,input_prefix_hash=self.prefix_hash,
            availability_basis='recorded',numeric_policy='Decimal400-exact-unrounded-v1',
            positions=results,ready=bool(results) and all(p['ready'] for p in results),
            booking_policy='one current amount per cashflow_key; corrections replace/reconcile previous amount, never add a second full charge'))

    def checkpoint(self):
        retained=list(self.settlements.values())+list(self.marks.values())
        return dict(schema_version=1,run_hash=self.manifest.digest,cursor=self.cursor,
            prefix_hash=self.prefix_hash,last_event_hash=self.last_event_hash,event_count=self.event_count,
            evaluated_through_ms=self.evaluated_through_ms,
            latest=sorted(retained,key=lambda e:(e['available_ms'],e['id'])))

    @classmethod
    def restore(cls, dataset, positions, calendars, config, decision_ms, checkpoint):
        obj=cls(dataset,positions,calendars,config,decision_ms)
        if not isinstance(checkpoint,dict) or checkpoint.get('schema_version')!=1 or checkpoint.get('run_hash')!=obj.manifest.digest:
            raise ValidationError('Incompatible funding checkpoint')
        count=checkpoint.get('event_count'); latest=checkpoint.get('latest'); cursor=checkpoint.get('cursor')
        evaluated=checkpoint.get('evaluated_through_ms')
        if (type(count) is not int or count<0 or not isinstance(latest,list) or count<len(latest)
                or type(evaluated) is not int or evaluated < -1 or evaluated>obj.decision_ms):
            raise ValidationError('Invalid funding checkpoint state')
        if cursor is None:
            if count or latest or checkpoint.get('last_event_hash') is not None or checkpoint.get('prefix_hash')!=fingerprint([]):
                raise ValidationError('Invalid empty funding checkpoint')
        else:
            if not isinstance(cursor,(list,tuple)) or len(cursor)!=2 or not count:
                raise ValidationError('Invalid funding checkpoint cursor')
            integer(cursor[0],'cursor time'); integer(cursor[1],'cursor ID')
            if not cursor[1] or cursor[0]>obj.decision_ms:
                raise ValidationError('Invalid funding checkpoint cursor')
            for key in ('prefix_hash','last_event_hash'):
                if not isinstance(checkpoint.get(key),str) or not re.fullmatch('[a-f0-9]{64}',checkpoint[key]):
                    raise ValidationError('Invalid funding checkpoint digest')
        for e in latest: obj.push(e)
        if obj.cursor is not None and (cursor is None or obj.cursor>tuple(cursor)):
            raise ValidationError('Checkpoint precedes retained input')
        if cursor is not None and obj.cursor==tuple(cursor) and obj.last_event_hash!=checkpoint['last_event_hash']:
            raise ValidationError('Checkpoint last input digest mismatch')
        obj.cursor=None if cursor is None else tuple(cursor)
        obj.prefix_hash=checkpoint['prefix_hash']; obj.last_event_hash=checkpoint['last_event_hash']
        obj.event_count=count; obj.evaluated_through_ms=evaluated
        return obj
