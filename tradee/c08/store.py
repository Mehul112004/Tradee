"""Complete opportunity inventory, feature evidence and atomic restart state."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from tradee.c01 import ValidationError
from tradee.c01.domain import canonical, fingerprint
from .contracts import CandidateConfig, CandidateSpec
from .engine import CandidateEngine
from .metadata import capture

APP_ID=0x54524438
STATUSES=('emitted','rejected','not_triggered','revision_only')


class CandidateStore:
    def __init__(self,path='data/c08.sqlite3',forbidden_paths=(),clock=time.time):
        if str(path)==':memory:' or Path(path).resolve() in {Path(p).resolve() for p in forbidden_paths}:
            raise ValidationError('C08 needs a separate persistent database')
        self.path=str(path); self.clock=clock; Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            tables=db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            app=db.execute('PRAGMA application_id').fetchone()[0]; version=db.execute('PRAGMA user_version').fetchone()[0]
            if (tables and app!=APP_ID) or version not in (0,1): raise ValidationError('Not a supported C08 database')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS runs(hash TEXT PRIMARY KEY,document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS evaluations(hash TEXT PRIMARY KEY,run_hash TEXT NOT NULL REFERENCES runs(hash),
                    sequence INTEGER NOT NULL,status TEXT NOT NULL,document TEXT NOT NULL,computed_at_ms INTEGER NOT NULL,
                    UNIQUE(run_hash,sequence));
                CREATE INDEX IF NOT EXISTS evaluations_status ON evaluations(run_hash,status,sequence);
                CREATE TABLE IF NOT EXISTS features(hash TEXT PRIMARY KEY,document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS lineage(hash TEXT PRIMARY KEY,document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS checkpoints(run_hash TEXT PRIMARY KEY REFERENCES runs(hash),
                    document TEXT NOT NULL,checksum TEXT NOT NULL,completed INTEGER NOT NULL);
            ''')
            db.execute(f'PRAGMA application_id={APP_ID}'); db.execute('PRAGMA user_version=1')

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=15); db.row_factory=sqlite3.Row; db.execute('PRAGMA foreign_keys=ON')
        try:
            with db: yield db
        finally: db.close()

    def _read(self,table,digest):
        with self.connection() as db: row=db.execute(f'SELECT document FROM {table} WHERE hash=?',(digest,)).fetchone()
        if row is None: raise ValidationError('Unknown candidate '+table+' record')
        doc=json.loads(row[0])
        if fingerprint(doc)!=digest: raise ValidationError('Corrupt candidate '+table+' record')
        return doc

    def manifest(self,h): return {'run_hash':h,**self._read('runs',h)}
    def evaluation(self,h): return {'evaluation_hash':h,**self._read('evaluations',h)}
    def feature(self,h): return {'snapshot_hash':h,**self._read('features',h)}
    def lineage(self,h): return self._read('lineage',h)

    def load_checkpoint(self,run_hash):
        with self.connection() as db: row=db.execute('SELECT document,checksum FROM checkpoints WHERE run_hash=?',(run_hash,)).fetchone()
        if row is None: return None
        doc=json.loads(row['document'])
        if fingerprint(doc)!=row['checksum']: raise ValidationError('Corrupt candidate checkpoint')
        return doc

    def commit(self,engine,records,completed=False):
        if type(completed) is not bool: raise ValidationError('Invalid completion flag')
        cp=json.loads(canonical(engine.checkpoint())); feature_cp=cp['feature_checkpoint']; run_hash=engine.manifest.digest
        if completed and feature_cp['event_count']!=engine.dataset.get('event_count'):
            raise ValidationError('Cannot complete a candidate run before all pinned inputs are consumed')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT document,checksum,completed FROM checkpoints WHERE run_hash=?',(run_hash,)).fetchone()
            previous=None
            if old:
                previous=json.loads(old['document'])
                if fingerprint(previous)!=old['checksum']: raise ValidationError('Corrupt previous candidate checkpoint')
                a,b=previous['feature_checkpoint']['cursor'],feature_cp['cursor']
                if a is not None and (b is None or tuple(b)<tuple(a)): raise ValidationError('Candidate cursor cannot move backward')
                if a==json.loads(canonical(b)) and previous['feature_checkpoint']['prefix_hash']!=feature_cp['prefix_hash']:
                    raise ValidationError('Conflicting candidate prefix')
                if cp['output_count']<previous['output_count'] or cp['emitted_count']<previous['emitted_count']:
                    raise ValidationError('Candidate counters cannot move backward')
                if feature_cp['evaluated_through_ms']<previous['feature_checkpoint']['evaluated_through_ms']:
                    raise ValidationError('Candidate decision clock cannot move backward')
                if old['completed'] and (not completed or cp!=previous): raise ValidationError('Cannot alter a completed pinned run')
            db.execute('INSERT OR IGNORE INTO runs VALUES(?,?)',(run_hash,engine.manifest.serialized))
            for h,doc in engine.features.lineages.items(): db.execute('INSERT OR IGNORE INTO lineage VALUES(?,?)',(h,canonical(doc)))
            for h,snapshot in engine.pending_features.items(): db.execute('INSERT OR IGNORE INTO features VALUES(?,?)',(h,snapshot.serialized))
            for record in records:
                doc=record.document(); cursor=doc.get('input_cursor')
                if (doc.get('run_hash')!=run_hash or doc.get('status') not in STATUSES or type(doc.get('sequence')) is not int
                        or not 1<=doc['sequence']<=cp['output_count'] or cursor is None or engine.cursor is None or tuple(cursor)>engine.cursor
                        or (doc['status']=='emitted')!=(doc['candidate'] is not None)):
                    raise ValidationError('Candidate record/checkpoint mismatch')
                if doc['candidate'] is not None: CandidateSpec.create(doc['candidate'])
                evidence=db.execute('SELECT document FROM features WHERE hash=?',(doc['feature_snapshot_hash'],)).fetchone()
                if evidence is None:
                    raise ValidationError('Missing candidate feature evidence')
                feature=json.loads(evidence[0])
                if (feature['input_cursor']!=cursor or feature['input_prefix_hash']!=doc['input_prefix_hash']
                        or feature['evaluation_as_of_ms']!=doc['evaluation_as_of_ms']):
                    raise ValidationError('Candidate feature prefix mismatch')
                row=db.execute('SELECT hash FROM evaluations WHERE run_hash=? AND sequence=?',(run_hash,doc['sequence'])).fetchone()
                if row and row[0]!=record.digest: raise ValidationError('Conflicting candidate evaluation sequence')
                db.execute('INSERT OR IGNORE INTO evaluations VALUES(?,?,?,?,?,?)',
                    (record.digest,run_hash,doc['sequence'],doc['status'],record.serialized,int(self.clock()*1000)))
            counts=db.execute("SELECT COUNT(*),COALESCE(SUM(status='emitted'),0),COALESCE(MAX(sequence),0) FROM evaluations WHERE run_hash=?",(run_hash,)).fetchone()
            if tuple(counts)!=(cp['output_count'],cp['emitted_count'],cp['output_count']):
                raise ValidationError('Incomplete candidate inventory at checkpoint')
            db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?,?,?)',(run_hash,canonical(cp),fingerprint(cp),int(completed)))
        engine.pending_features.clear(); engine.features.lineages.clear()

    def records(self,run_hash,limit=100,after_sequence=0,status=None):
        self.manifest(run_hash)
        if type(limit) is not int or not 1<=limit<=1000 or type(after_sequence) is not int or after_sequence<0 or (status is not None and status not in STATUSES):
            raise ValidationError('Invalid inventory page/filter')
        with self.connection() as db:
            rows=db.execute('SELECT hash,document FROM evaluations WHERE run_hash=? AND sequence>? AND (? IS NULL OR status=?) ORDER BY sequence LIMIT ?',
                            (run_hash,after_sequence,status,status,limit)).fetchall()
        result=[]
        for row in rows:
            doc=json.loads(row['document'])
            if fingerprint(doc)!=row['hash']: raise ValidationError('Corrupt evaluation inventory')
            result.append({'evaluation_hash':row['hash'],**doc})
        return dict(run_hash=run_hash,records=result,next_sequence=after_sequence if not result else result[-1]['sequence'])

    def summary(self,run_hash):
        manifest=self.manifest(run_hash)
        counts={s:0 for s in STATUSES}; reasons={}; latest=None
        with self.connection() as db:
            # Inventory and checkpoint must come from one read snapshot while a
            # writer advances the run; otherwise valid concurrent commits can
            # look like missing/corrupt opportunity records.
            db.execute('BEGIN')
            rows=db.execute('SELECT hash,document FROM evaluations WHERE run_hash=? ORDER BY sequence',(run_hash,)).fetchall()
            cp=db.execute('SELECT document,checksum,completed FROM checkpoints WHERE run_hash=?',(run_hash,)).fetchone()
        ready=0; represented={s:set() for s in manifest['dataset']['symbols']}
        for row in rows:
            doc=json.loads(row['document'])
            if fingerprint(doc)!=row['hash']: raise ValidationError('Corrupt evaluation inventory')
            counts[doc['status']]+=1; ready+=int(doc['context_ready'])
            represented[doc['symbol']].add(doc['target_open_ms'])
            for reason in doc['reasons']: reasons[reason]=reasons.get(reason,0)+1
            latest={'evaluation_hash':row['hash'],'target_open_ms':doc['target_open_ms'],'status':doc['status']}
        state=None if cp is None else json.loads(cp['document'])
        if state is not None and fingerprint(state)!=cp['checksum']: raise ValidationError('Corrupt candidate checkpoint')
        if state and (state['output_count']!=len(rows) or state['emitted_count']!=counts['emitted']):
            raise ValidationError('Candidate inventory no longer matches checkpoint')
        if cp and cp['completed'] and (state is None or state['feature_checkpoint']['event_count']!=manifest['dataset'].get('event_count')):
            raise ValidationError('Completed candidate run has an incomplete input prefix')
        from tradee.c03.catalog import TIMEFRAMES
        interval=TIMEFRAMES[manifest['strategy']['spec']['timeframe']]; ds=manifest['dataset']
        first=(ds['start_ms']+interval-1)//interval*interval; end=min(ds['end_ms'],ds['as_of_ms'])//interval*interval
        coverage=[]
        for symbol,seen in represented.items():
            missing=[t for t in range(first,end,interval) if t not in seen]
            coverage.append(dict(symbol=symbol,expected_completed_buckets=max(0,(end-first)//interval),
                represented_buckets=sum(first<=t<end for t in seen),missing_buckets=len(missing),
                missing_sample_open_ms=missing[:20],sample_truncated=len(missing)>20))
        return dict(run_hash=run_hash,hypothesis_family=manifest['strategy']['spec']['family'],completed=bool(cp and cp['completed']),
            evaluations=len(rows),emitted_candidates=counts['emitted'],context_ready_evaluations=ready,status_counts=counts,reasons=reasons,coverage=coverage,latest=latest)

    def run(self,market,dataset_hash,strategy,config=None,batch_size=256):
        if type(batch_size) is not int or batch_size<1: raise ValidationError('Positive candidate batch size required')
        config=config or CandidateConfig(); dataset=market.dataset(dataset_hash)
        snapshots,versions=capture(market.registry,dataset,config)
        engine=CandidateEngine(dataset,strategy,snapshots,versions,config)
        cp=self.load_checkpoint(engine.manifest.digest)
        if cp: engine=CandidateEngine.restore(dataset,strategy,snapshots,versions,config,cp)
        # A completed replay is immutable, including its completion marker.
        with self.connection() as db:
            row=db.execute('SELECT completed FROM checkpoints WHERE run_hash=?',(engine.manifest.digest,)).fetchone()
        if row and row[0]: return self.summary(engine.manifest.digest)
        pending=[]; count=0
        for event in market.replay(dataset_hash,after_id=engine.cursor[1] if engine.cursor else None):
            pending.extend(engine.advance(event)); count+=1
            if count%batch_size==0: self.commit(engine,pending); pending=[]
        self.commit(engine,pending,completed=True)
        return self.summary(engine.manifest.digest)
