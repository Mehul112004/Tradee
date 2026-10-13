"""Availability-prefix evaluation, strict aggregation and reconstructible state.

Corrections rebuild derived state from the retained source prefix. Historical batch
and incremental callers use exactly the same push/evaluate path.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib
import platform
import re
from pathlib import Path

from tradee.c01 import ValidationError
from tradee.c01.domain import canonical, fingerprint
from tradee.c02.domain import aggregate, candle, MINUTE, integer, number
from .catalog import FeatureConfig, TIMEFRAMES, definition, resolve
from .contracts import FeatureSnapshot, FeatureValue, RunManifest
from .evaluator import Evaluator
from .liquidity import quote_values


def implementation_hash():
    root = Path(__file__).resolve().parents[1]
    return fingerprint({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in sorted(root.rglob('*.py'))})


def make_manifest(dataset, config):
    if dataset.get('schema_version') != 1 or dataset.get('mode') not in ('recorded','modeled'):
        raise ValidationError('Unsupported C02 dataset contract')
    if config.output_start_ms is not None and config.output_start_ms < dataset['start_ms']:
        raise ValidationError('Output starts before dataset coverage')
    if config.output_end_ms is not None and config.output_end_ms > dataset['end_ms']:
        raise ValidationError('Output ends after dataset coverage')
    if (config.output_start_ms is not None and config.output_start_ms >= dataset['end_ms']) or (
            config.output_end_ms is not None and config.output_end_ms <= dataset['start_ms']):
        raise ValidationError('Output range does not intersect dataset coverage')
    return RunManifest.create(dict(schema_version=1, checkpoint_schema=1, dataset=dataset,
        config=config.document(), config_hash=config.config_hash,
        definitions={k: definition(k).definition_hash for k in resolve(config.features)},
        code_hash=implementation_hash(), python=platform.python_version(),
        numeric_policy='float64-centered-v1/exact-volume-decimal120',
        decision_schedule='after each finalized candle affecting a complete requested bucket; one prefix per event',
        initialization_origin_ms=dataset['start_ms']))


class FeatureEngine:
    def __init__(self, dataset, config=None):
        self.config = config or FeatureConfig()
        self.manifest = make_manifest(dataset, self.config)
        self.dataset = deepcopy(dataset)
        self.latest, self.buckets, self.bars = {}, {}, {}
        self.quotes = {}
        self.cursor, self.last_event_hash, self.prefix_hash = None, None, fingerprint([])
        self.lineages = {}
        self.event_count = 0
        self.evaluated_through_ms = -1

    def _validate(self, event):
        if not isinstance(event, dict) or event.get('schema_version') != 1:
            raise ValidationError('Unsupported market-event schema')
        if event.get('availability_basis') != self.dataset['mode']:
            raise ValidationError('Mixed availability modes')
        if event.get('symbol') not in self.dataset['symbols'] or event.get('kind') not in self.dataset['kinds']:
            raise ValidationError('Event outside dataset scope')
        for key in ('id','available_ms','event_ms','received_ms'):
            integer(event.get(key),key)
        if self.dataset['mode'] == 'recorded' and event['received_ms'] > event['available_ms']:
            raise ValidationError('Recorded event available before receipt')
        stamp = event.get('data', {}).get('open_ms', event['event_ms'])
        if not self.dataset['start_ms'] <= stamp < self.dataset['end_ms']:
            raise ValidationError('Event outside dataset time range')
        if event['id'] == 0 or type(event.get('final')) is not bool or not event.get('instrument_id') or not event.get('metadata_version'):
            raise ValidationError('Incomplete event identity or finality')
        if event['kind'] == 'candle':
            d = event['data']
            row = [d[k] for k in ('open_ms','open','high','low','close','volume','close_ms','quote_volume','trades','taker_base','taker_quote')]+['0']
            expected = candle(event['symbol'],row,event['final'])
            if d != expected['data'] or event['key'] != expected['key'] or event['event_ms'] != expected['event_ms']:
                raise ValidationError('Noncanonical candle event')
            if event['final'] and event['available_ms'] < event['event_ms']+1:
                raise ValidationError('Candle available before exclusive close')
        elif event['kind'] == 'quote':
            d = event['data']
            for key in ('bid','ask','bid_qty','ask_qty'):
                number(d[key],positive=key in ('bid','ask'))
            if Decimal(d['bid']) > Decimal(d['ask']):
                raise ValidationError('Crossed quote')
        if event['kind'] != 'candle' or event['final']:
            if event['event_ms'] > event['available_ms']:
                raise ValidationError('Final event available before event time')

    def push(self, event):
        """Append exactly one replay observation; return affected (instrument,timeframe) keys."""
        event = deepcopy(event)
        self._validate(event)
        cursor = (event['available_ms'],event['id'])
        digest = fingerprint(event)
        if self.cursor == cursor and self.last_event_hash == digest:
            return ()
        if self.cursor is not None and cursor <= self.cursor:
            raise ValidationError('Input must follow pinned replay order; conflicting/reversed cursor')
        if event['available_ms'] < self.evaluated_through_ms:
            raise ValidationError('Cannot append input earlier than an already evaluated decision time')
        self.cursor, self.last_event_hash = cursor, digest
        self.prefix_hash = fingerprint([self.prefix_hash, digest])
        self.event_count += 1
        if not event['final'] or event['kind'] not in ('candle','quote'):
            return ()
        identity = event['instrument_id']
        key = (identity,event['kind'],event['key'])
        if event['kind'] == 'quote':
            previous = self.quotes.get(identity)
            rank = lambda e: (e['event_ms'],e['available_ms'],e['id'])
            if previous is None or rank(event) > rank(previous):
                if previous is not None:
                    self.latest.pop((identity,'quote',previous['key']))
                self.quotes[identity] = event
                self.latest[key] = event
            return ()
        self.latest[key] = event
        start = event['data']['open_ms']
        changed = []
        for tf in self.config.timeframes:
            interval = TIMEFRAMES[tf]
            bucket_start = start//interval*interval
            bucket = self.buckets.setdefault((identity,tf,bucket_start),{})
            bucket[start] = event
            if len(bucket) == interval//MINUTE:
                bar = aggregate([bucket[t] for t in sorted(bucket)],interval)[0]
                bar['bar_id'] = fingerprint([identity,tf,bucket_start,bar['constituents']])
                bar['metadata_versions'] = sorted({e['metadata_version'] for e in bucket.values()})
                self.bars.setdefault((identity,tf),{})[bucket_start] = bar
                changed.append((identity,tf))
        return tuple(changed)

    def _lineage(self, events, parent=None):
        doc = dict(parent=parent, events=[{'id':e['id'],'metadata_version':e['metadata_version'],
                    'raw_sha256':e.get('raw_sha256'), 'available_ms':e['available_ms']} for e in events])
        digest = fingerprint(doc)
        self.lineages[digest] = doc
        return digest

    def evaluate(self, instrument_id, timeframe, decision_ms, target_open_ms=None, *, trigger='explicit'):
        integer(decision_ms,'decision_ms')
        if trigger not in ('explicit', 'closed_bar', 'revision'):
            raise ValidationError('Unknown decision trigger')
        if timeframe not in self.config.timeframes:
            raise ValidationError('Timeframe not configured')
        if self.cursor and decision_ms < self.cursor[0]:
            raise ValidationError('Evaluation cannot look backward through a future prefix')
        interval = TIMEFRAMES[timeframe]
        available = self.bars.get((instrument_id,timeframe),{})
        keys = sorted(t for t in available if t+interval <= decision_ms)
        target = target_open_ms if target_open_ms is not None else (keys[-1] if keys else None)
        if target_open_ms is not None and target_open_ms not in keys:
            raise ValidationError('Requested target is not a complete available bar')
        segment = []
        t = target
        while t is not None and t in available:
            segment.append(available[t]); t -= interval
        segment.reverse()
        gap = bool(segment and segment[0]['data']['open_ms'] > ((self.dataset['start_ms']+interval-1)//interval)*interval)
        rows = [b['data'] for b in segment]
        basis = self.dataset['mode']
        stale = bool(target is not None and decision_ms-(target+interval) >= interval+self.config.candle_grace_ms)
        source_events = {e['id']: e for e in self.latest.values()}
        lineage = None
        # Merkle chain deduplicates the shared prefix of recursive input histories.
        for bar in segment:
            lineage = self._lineage([source_events[i] for i in bar['constituents']],lineage)
        session_rows, session_events = None, []
        if any('vwap_utc_session' in k for k in self.config.features) and target is not None:
            end = target+interval
            anchor = (end-1)//86400000*86400000
            session_events = [self.latest.get((instrument_id,'candle',str(t))) for t in range(anchor,end,MINUTE)]
            if all(e is not None for e in session_events):
                session_rows = [e['data'] for e in session_events]
                lineage = self._lineage(session_events,lineage)
        evaluator = Evaluator(rows,self.config.seed_threshold,gap,session_rows)
        # All appended final event times are <= cursor availability <= decision.
        quote = self.quotes.get(instrument_id)
        qvalues, qstatus = {}, 'missing_source'
        if any(definition(k).inputs == ('quote',) for k in self.config.features):
            try:
                qvalues,qstatus = quote_values(quote,decision_ms,self.config.max_quote_age_ms,basis)
            except ArithmeticError:
                qstatus = 'numeric_error'
            if quote:
                lineage = self._lineage([quote],lineage)
        values = {}
        for name in self.config.features:
            spec = definition(name)
            if spec.inputs == ('quote',):
                value = qvalues.get(name)
                status = ('valid' if value is not None else 'unsupported_coverage' if name=='quote_receipt_age_ms' and basis!='recorded'
                          else qstatus if qstatus!='valid' else 'zero_denominator')
                fv = FeatureValue(value,status,0,int(quote is not None),status=='valid')
            elif not rows:
                fv = FeatureValue(None,'missing_source',spec.min_bars,0)
            elif stale:
                fv = FeatureValue(None,'stale_input',spec.min_bars,len(rows))
            elif 'vwap_utc_session' in name and session_rows is None:
                fv = FeatureValue(None,'anchor_incomplete',spec.min_bars,len(rows))
            else:
                fv = evaluator.get(name)
            values[name] = fv.document()
        required = self.config.required_features
        ready = bool(required) and all(values[k]['status']=='valid' and (not self.config.require_stable or values[k]['stable']) for k in required)
        self.evaluated_through_ms = max(self.evaluated_through_ms,decision_ms)
        input_available = max((b['available_ms'] for b in segment),default=0)
        if session_rows is not None:
            input_available = max(input_available,*(e['available_ms'] for e in session_events))
        if quote and any(definition(k).inputs==('quote',) for k in self.config.features):
            input_available = max(input_available,quote['available_ms'])
        return FeatureSnapshot.create(dict(schema_version=1, run_hash=self.manifest.digest,
            dataset_hash=self.dataset['dataset_hash'],config_hash=self.config.config_hash,
            definition_hashes={k:definition(k).definition_hash for k in self.config.features},
            instrument_id=instrument_id,timeframe=timeframe,target_open_ms=target,
            target_end_ms=None if target is None else target+interval,
            target_bar_id=None if target is None else available[target]['bar_id'],
            evaluation_as_of_ms=decision_ms,trigger=trigger,input_cursor=self.cursor,input_prefix_hash=self.prefix_hash,
            availability_basis=basis,input_available_ms=input_available,
            assumed_usable_ms=decision_ms+self.config.processing_delay_ms,
            lineage_hash=lineage,segment_start_ms=rows[0]['open_ms'] if rows else None,
            values=values,ready=ready))

    def advance(self, event):
        previous = {key: max(bars) for key, bars in self.bars.items()}
        changed = self.push(event)
        snapshots = []
        for identity,tf in changed:
            target = max(self.bars[(identity,tf)])
            if self.config.output_start_ms is not None and target < self.config.output_start_ms:
                continue
            if self.config.output_end_ms is not None and target >= self.config.output_end_ms:
                continue
            trigger = 'closed_bar' if target > previous.get((identity,tf),-1) else 'revision'
            snapshots.append(self.evaluate(identity,tf,event['available_ms'],trigger=trigger))
        return snapshots

    def checkpoint(self):
        return dict(schema_version=1,run_hash=self.manifest.digest,cursor=self.cursor,
                    last_event_hash=self.last_event_hash,prefix_hash=self.prefix_hash,event_count=self.event_count,
                    evaluated_through_ms=self.evaluated_through_ms,
                    latest=sorted(self.latest.values(),key=lambda e:(e['available_ms'],e['id'])))

    @classmethod
    def restore(cls, dataset, config, checkpoint):
        obj = cls(dataset,config)
        if checkpoint.get('schema_version')!=1 or checkpoint.get('run_hash')!=obj.manifest.digest:
            raise ValidationError('Incompatible feature checkpoint')
        count = checkpoint.get('event_count')
        evaluated = checkpoint.get('evaluated_through_ms')
        latest = checkpoint.get('latest')
        cursor = checkpoint.get('cursor')
        if (type(count) is not int or count < 0 or type(evaluated) is not int or evaluated < -1
                or not isinstance(latest,list) or count < len(latest)):
            raise ValidationError('Invalid checkpoint state')
        if cursor is None:
            if count or latest or checkpoint.get('last_event_hash') is not None or checkpoint.get('prefix_hash') != fingerprint([]):
                raise ValidationError('Invalid empty checkpoint')
        else:
            if not isinstance(cursor,(list,tuple)) or len(cursor)!=2 or count == 0:
                raise ValidationError('Invalid checkpoint cursor')
            integer(cursor[0],'checkpoint availability'); integer(cursor[1],'checkpoint event ID')
            if cursor[1] == 0:
                raise ValidationError('Invalid checkpoint event ID')
            for name in ('prefix_hash','last_event_hash'):
                if not isinstance(checkpoint.get(name),str) or not re.fullmatch('[a-f0-9]{64}',checkpoint[name]):
                    raise ValidationError('Invalid checkpoint digest')
        # Derived windows/recursive calculations reconstruct from canonical prefix evidence.
        for event in latest:
            obj.push(event)
        if cursor is not None and (len(cursor)!=2 or (obj.cursor is not None and tuple(cursor)<obj.cursor)):
            raise ValidationError('Invalid checkpoint cursor')
        if cursor is not None and obj.cursor == tuple(cursor) and obj.last_event_hash != checkpoint['last_event_hash']:
            raise ValidationError('Checkpoint last-event digest mismatch')
        obj.cursor = tuple(cursor) if cursor is not None else None
        obj.last_event_hash = checkpoint['last_event_hash']
        obj.prefix_hash = checkpoint['prefix_hash']
        obj.event_count = checkpoint['event_count']
        obj.evaluated_through_ms = checkpoint['evaluated_through_ms']
        return obj

    def run(self, events):
        for event in events:
            yield from self.advance(event)
