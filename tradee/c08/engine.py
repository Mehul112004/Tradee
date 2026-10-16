"""Closed-bar setup detection using the same C03 prefix core as replay/live callers."""
from copy import deepcopy
import platform

from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c02.domain import integer, KINDS
from tradee.c03 import FeatureEngine
from tradee.c03.catalog import TIMEFRAMES
from tradee.c06.engine import code_hash
from tradee.c06.contracts import identity
from .contracts import StrategySpec, CandidateConfig, CandidateSpec, CandidateRecord, FAMILY, digest
from .metadata import MetadataBook
from .strategy import prior_range, trend_recovery


class CandidateEngine:
    def __init__(self,dataset,strategy,snapshots,versions,config=None):
        if (not isinstance(dataset,dict) or type(dataset.get('schema_version')) is not int or dataset['schema_version']!=1
                or dataset.get('mode') not in ('recorded','modeled') or not isinstance(dataset.get('dataset_hash'),str)):
            raise ValidationError('Pinned C02 dataset required')
        for name in ('start_ms','end_ms','as_of_ms'): integer(dataset.get(name),name)
        if (not dataset['start_ms']<dataset['end_ms'] or dataset['as_of_ms']<dataset['start_ms']
                or not isinstance(dataset.get('symbols'),list) or not dataset['symbols']
                or not isinstance(dataset.get('kinds'),list) or 'candle' not in dataset['kinds'] or set(dataset['kinds'])-set(KINDS)
                or (dataset['mode']=='modeled' and dataset['kinds']!=['candle'])):
            raise ValidationError('Invalid candidate dataset scope')
        self.dataset=deepcopy(dataset)
        self.strategy=strategy if isinstance(strategy,StrategySpec) else StrategySpec.from_dict(strategy)
        self.config=config or CandidateConfig()
        if not isinstance(self.config,CandidateConfig): raise ValidationError('Candidate config required')
        self.book=MetadataBook(snapshots,versions,dataset['as_of_ms'])
        self.features=FeatureEngine(dataset,self.strategy.feature_config())
        self.manifest=CandidateRecord.create(dict(schema_version=1,component='C08',checkpoint_schema=1,dataset=self.dataset,
            strategy=self.strategy.definition(),strategy_hash=self.strategy.strategy_hash,config=self.config.document(),
            metadata_snapshots=self.book.snapshots,metadata_versions=self.book.versions,
            feature_manifest=self.features.manifest.document(),feature_run_hash=self.features.manifest.digest,
            code_hash=code_hash(),python=platform.python_version(),
            schedule='one diagnostic per configured direction after every complete target-bar update; revisions cannot emit',
            numeric_policy='exact decimal range comparisons; C03 float64 EMA comparisons; exact source reference prices',
            ownership='setups only; no fills/position state, performance selection or trial-ledger claim'))
        self.cooldowns={}; self.output_count=0; self.emitted_count=0; self.pending_features={}

    @property
    def cursor(self): return self.features.cursor

    @property
    def prefix_hash(self): return self.features.prefix_hash

    def _feature_reasons(self,snapshot,prefix=''):
        reasons=[]
        for name in self.strategy.definition()['required_features']:
            v=snapshot['values'][name]
            if v['status']!='valid' or v['value'] is None: reasons.append(prefix+'invalid_feature:'+name+':'+v['status'])
            elif not v['stable']: reasons.append(prefix+'unstable_feature:'+name)
        return reasons

    def advance(self,event):
        if (not isinstance(event,dict) or type(event.get('schema_version')) is not int or event['schema_version']!=1):
            raise ValidationError('Unsupported candidate input schema')
        digest(event.get('raw_sha256'),'raw source')
        identity(event.get('instrument_id'),event.get('symbol'))
        if integer(event.get('available_ms'),'availability')>self.dataset['as_of_ms']:
            raise ValidationError('Candidate input beyond pinned dataset cutoff')
        outputs=[]
        for snapshot in self.features.advance(event):
            self.pending_features[snapshot.digest]=snapshot
            f=snapshot.document(); tf=f['timeframe']; interval=TIMEFRAMES[tf]; target=f['target_open_ms']
            available=self.features.bars[(f['instrument_id'],tf)]
            rows=[available[t]['data'] for t in sorted(available) if t<=target]
            when=f['evaluation_as_of_ms']; expires=integer(f['target_end_ms']+self.strategy.entry_window_ms,'candidate expiry')
            reasons=self._feature_reasons(f); context=None; previous_hash=None
            if self.strategy.family==FAMILY:
                context=prior_range(rows,self.strategy.lookback_bars,interval)
                if context is None:
                    reasons.append('insufficient_range_history' if len(rows)<self.strategy.lookback_bars+1 else 'gap_in_range_window')
            else:
                previous=available.get(target-interval)
                if previous is None: reasons.append('missing_previous_bar')
                else:
                    if not self._feature_reasons(f):
                        prior={k:f['values'][k+'_prior'] for k in ('ema20','ema50')}
                        try: context=trend_recovery(previous['data'],rows[-1],prior,f['values'])
                        except ArithmeticError: reasons.append('trigger_numeric_error')
            meta_reasons,meta_hash,version=self.book.gate(f['instrument_id'],event['symbol'],when,self.config)
            reasons.extend(meta_reasons)
            lag=when-f['target_end_ms']
            if lag>=self.config.max_detection_lag_ms: reasons.append('stale_detection')
            if when>=expires: reasons.append('candidate_window_expired')
            if f['input_cursor']!=list(self.cursor) or f['assumed_usable_ms']>when:
                raise ValidationError('Feature artifact is not available in this candidate prefix')
            revision=f['trigger']!='closed_bar'
            for side in self.strategy.sides:
                opportunity=fingerprint([self.strategy.strategy_hash,f['instrument_id'],tf,target,side])
                triggered=None if context is None else context[side]
                why=list(reasons); last=self.cooldowns.get((f['instrument_id'],side))
                cooldown=last is not None and target-last<self.strategy.cooldown_bars*interval
                if cooldown: why.append('cooldown_active')
                if revision: why.append('revision_only')
                candidate=None
                if not why and triggered:
                    level=(context['upper'] if side=='long' else context['lower']) if self.strategy.family==FAMILY else context['level']
                    details={k:context[k] for k in ('upper','lower')} if self.strategy.family==FAMILY else context['context']
                    candidate=CandidateSpec.create(dict(schema_version=1,candidate_id=opportunity,strategy_hash=self.strategy.strategy_hash,
                        hypothesis_family=self.strategy.family,instrument_id=f['instrument_id'],symbol=event['symbol'],side=side,timeframe=tf,
                        target_open_ms=target,target_end_ms=f['target_end_ms'],detected_ms=when,expires_ms=expires,
                        reference_price=context['reference_price'],breakout_level=level,trigger_context=details,
                        context_start_ms=context['start_ms'],context_end_ms=context['end_ms'],feature_snapshot_hash=snapshot.digest,
                        metadata_snapshot_hash=meta_hash,metadata_mode=self.config.metadata_mode,input_cursor=self.cursor,
                        input_prefix_hash=self.prefix_hash,availability_basis=self.dataset['mode'])).document()
                    self.cooldowns[(f['instrument_id'],side)]=target; self.emitted_count+=1
                status='emitted' if candidate else 'revision_only' if revision else 'rejected' if why else 'not_triggered'
                if not triggered and triggered is not None: why.append('trigger_not_met')
                self.output_count+=1
                outputs.append(CandidateRecord.create(dict(schema_version=1,run_hash=self.manifest.digest,sequence=self.output_count,
                    opportunity_key=opportunity,hypothesis_family=self.strategy.family,strategy_hash=self.strategy.strategy_hash,
                    instrument_id=f['instrument_id'],symbol=event['symbol'],side=side,timeframe=tf,target_open_ms=target,
                    target_end_ms=f['target_end_ms'],evaluation_as_of_ms=when,input_cursor=self.cursor,input_prefix_hash=self.prefix_hash,
                    feature_snapshot_hash=snapshot.digest,previous_feature_snapshot_hash=previous_hash,
                    metadata_snapshot_hash=meta_hash,metadata_version=version,metadata_mode=self.config.metadata_mode,
                    availability_basis=self.dataset['mode'],detection_lag_ms=lag,triggered=triggered,
                    context_ready=not reasons,status=status,reasons=sorted(set(why)),candidate=candidate,
                    checks=dict(closed_bar=not revision,required_features=not self._feature_reasons(f),
                        metadata_eligible=not meta_reasons,window_available=context is not None,fresh_detection=lag<self.config.max_detection_lag_ms,
                        entry_window_open=when<expires,cooldown_clear=not cooldown,trigger=triggered))))
        return outputs

    def checkpoint(self):
        return dict(schema_version=1,run_hash=self.manifest.digest,feature_checkpoint=self.features.checkpoint(),
            output_count=self.output_count,emitted_count=self.emitted_count,
            cooldowns=[dict(instrument_id=i,side=s,target_open_ms=t) for (i,s),t in sorted(self.cooldowns.items())])

    @classmethod
    def restore(cls,dataset,strategy,snapshots,versions,config,checkpoint):
        obj=cls(dataset,strategy,snapshots,versions,config)
        if not isinstance(checkpoint,dict) or type(checkpoint.get('schema_version')) is not int or checkpoint['schema_version']!=1 or checkpoint.get('run_hash')!=obj.manifest.digest:
            raise ValidationError('Incompatible candidate checkpoint')
        a,b=checkpoint.get('output_count'),checkpoint.get('emitted_count')
        if type(a) is not int or type(b) is not int or not 0<=b<=a or not isinstance(checkpoint.get('cooldowns'),list):
            raise ValidationError('Invalid candidate counters')
        obj.features=FeatureEngine.restore(dataset,obj.strategy.feature_config(),checkpoint['feature_checkpoint'])
        if obj.cursor and obj.cursor[0]>dataset['as_of_ms']: raise ValidationError('Candidate checkpoint exceeds cutoff')
        if a%len(obj.strategy.sides) or a>obj.features.event_count*len(obj.strategy.sides) or (a and obj.cursor is None):
            raise ValidationError('Candidate counters are inconsistent with input state')
        if b and not checkpoint['cooldowns']: raise ValidationError('Missing emitted-candidate cooldown state')
        for row in checkpoint['cooldowns']:
            if not isinstance(row,dict) or set(row)!={'instrument_id','side','target_open_ms'} or row['side'] not in obj.strategy.sides:
                raise ValidationError('Invalid cooldown state')
            t=integer(row['target_open_ms'],'cooldown bar'); key=(row['instrument_id'],row['side'])
            if key in obj.cooldowns or not b or t not in obj.features.bars.get((row['instrument_id'],obj.strategy.timeframe),{}):
                raise ValidationError('Cooldown references missing/duplicate candidate context')
            obj.cooldowns[key]=t
        if len(obj.cooldowns)>b: raise ValidationError('Inconsistent candidate cooldown count')
        obj.output_count=a; obj.emitted_count=b
        return obj

    def run(self,events):
        for event in events: yield from self.advance(event)
