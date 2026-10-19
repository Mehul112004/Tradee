"""Pinned trade ledgers/reports with atomic lifecycle checkpoint recovery."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from tradee.c01 import ValidationError
from tradee.c01.domain import canonical,fingerprint
from tradee.c08 import CandidateConfig
from tradee.c08.metadata import capture
from tradee.c07 import ExecutionConfig
from .engine import LifecycleEngine

APP_ID=0x54524439


class LifecycleStore:
    def __init__(self,path='data/c09.sqlite3',forbidden_paths=(),clock=time.time):
        if str(path)==':memory:' or Path(path).resolve() in {Path(p).resolve() for p in forbidden_paths}: raise ValidationError('C09 requires its own persistent database')
        self.path=str(path); self.clock=clock; Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            tables=db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if (tables and db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID) or db.execute('PRAGMA user_version').fetchone()[0] not in (0,1):
                raise ValidationError('Not a supported C09 database')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS runs(hash TEXT PRIMARY KEY,document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS transitions(hash TEXT PRIMARY KEY,run_hash TEXT NOT NULL REFERENCES runs(hash),
                    sequence INTEGER NOT NULL,document TEXT NOT NULL,UNIQUE(run_hash,sequence));
                CREATE TABLE IF NOT EXISTS reports(hash TEXT PRIMARY KEY,run_hash TEXT NOT NULL REFERENCES runs(hash),document TEXT NOT NULL,computed_at_ms INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS checkpoints(run_hash TEXT PRIMARY KEY REFERENCES runs(hash),document TEXT NOT NULL,checksum TEXT NOT NULL);
            ''')
            db.execute(f'PRAGMA application_id={APP_ID}'); db.execute('PRAGMA user_version=1')

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=15); db.row_factory=sqlite3.Row; db.execute('PRAGMA foreign_keys=ON')
        try:
            with db: yield db
        finally: db.close()

    def _read(self,table,h):
        with self.connection() as db: row=db.execute(f'SELECT document FROM {table} WHERE hash=?',(h,)).fetchone()
        if row is None: raise ValidationError('Unknown lifecycle '+table+' record')
        doc=json.loads(row[0])
        if fingerprint(doc)!=h: raise ValidationError('Corrupt lifecycle '+table+' record')
        return doc

    def manifest(self,h): return {'run_hash':h,**self._read('runs',h)}
    def report(self,h): return {'report_hash':h,**self._read('reports',h)}
    def transition(self,h): return {'transition_hash':h,**self._read('transitions',h)}

    def load_checkpoint(self,h):
        with self.connection() as db: row=db.execute('SELECT document,checksum FROM checkpoints WHERE run_hash=?',(h,)).fetchone()
        if row is None: return None
        doc=json.loads(row['document'])
        if fingerprint(doc)!=row['checksum']: raise ValidationError('Corrupt lifecycle checkpoint')
        return doc

    def commit(self,engine,records,report):
        cp=json.loads(canonical(engine.checkpoint())); doc=report.document(); h=engine.manifest.digest
        if (doc['run_hash']!=h or doc['input_cursor']!=cp['market']['cursor'] or doc['input_prefix_hash']!=cp['market']['prefix_hash']
                or doc['evaluation_as_of_ms']!=cp['evaluated_ms'] or {t['trade_id']:t['state'] for t in doc['trades']}!=cp['states']):
            raise ValidationError('Lifecycle report/checkpoint state mismatch')
        if cp['finish_called'] and cp['market']['event_count']!=engine.dataset.get('event_count'):
            raise ValidationError('Cannot complete a lifecycle replay with unconsumed pinned events')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT document,checksum FROM checkpoints WHERE run_hash=?',(h,)).fetchone()
            if old:
                previous=json.loads(old['document'])
                if fingerprint(previous)!=old['checksum']: raise ValidationError('Corrupt previous lifecycle checkpoint')
                a,b=previous['market']['cursor'],cp['market']['cursor']
                if a is not None and (b is None or tuple(b)<tuple(a)): raise ValidationError('Lifecycle cursor cannot go backward')
                if a==b and previous['market']['prefix_hash']!=cp['market']['prefix_hash']: raise ValidationError('Conflicting lifecycle prefix')
                if cp['record_count']<previous['record_count'] or cp['evaluated_ms']<previous['evaluated_ms']: raise ValidationError('Lifecycle state cannot go backward')
                if previous['finish_called'] and previous!=cp: raise ValidationError('Cannot change completed pinned lifecycle')
            db.execute('INSERT OR IGNORE INTO runs VALUES(?,?)',(h,engine.manifest.serialized))
            for r in records:
                d=r.document()
                if d['run_hash']!=h or not 1<=d['sequence']<=cp['record_count'] or tuple(d['input_cursor'])>tuple(cp['market']['cursor']): raise ValidationError('Invalid lifecycle transition/checkpoint')
                row=db.execute('SELECT hash FROM transitions WHERE run_hash=? AND sequence=?',(h,d['sequence'])).fetchone()
                if row and row[0]!=r.digest: raise ValidationError('Conflicting lifecycle transition')
                db.execute('INSERT OR IGNORE INTO transitions VALUES(?,?,?,?)',(r.digest,h,d['sequence'],r.serialized))
            count=db.execute('SELECT COUNT(*) FROM transitions WHERE run_hash=?',(h,)).fetchone()[0]
            if count!=cp['record_count']: raise ValidationError('Incomplete lifecycle transition inventory')
            db.execute('INSERT OR IGNORE INTO reports VALUES(?,?,?,?)',(report.digest,h,report.serialized,int(self.clock()*1000)))
            db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?,?)',(h,canonical(cp),fingerprint(cp)))

    def summary(self,h):
        self.manifest(h)
        with self.connection() as db:
            db.execute('BEGIN')
            row=db.execute('SELECT hash,document FROM reports WHERE run_hash=? ORDER BY rowid DESC LIMIT 1',(h,)).fetchone()
            cp=db.execute('SELECT document,checksum FROM checkpoints WHERE run_hash=?',(h,)).fetchone()
            count=db.execute('SELECT COUNT(*) FROM transitions WHERE run_hash=?',(h,)).fetchone()[0]
        if cp:
            state=json.loads(cp['document'])
            if fingerprint(state)!=cp['checksum'] or state['record_count']!=count: raise ValidationError('Corrupt lifecycle checkpoint/inventory')
        if row is None: return dict(run_hash=h,completed=False,ready=False,trades=[],report_hash=None,transitions=count)
        d=json.loads(row['document'])
        if fingerprint(d)!=row['hash']: raise ValidationError('Corrupt lifecycle report')
        return dict(run_hash=h,completed=bool(cp and state['finish_called']),ready=d['ready'],report_hash=row['hash'],transitions=count,
            trades=[{k:t[k] for k in ('trade_id','status','label_status','ready','gross_realized_usdt','fees_usdt','funding_usdt','net_usdt','net_r','ambiguity_flags','reason')} for t in d['trades']])

    def run(self,market,dataset_hash,intents,fees,execution=None,funding_config=None,calendars=(),batch_size=256):
        if type(batch_size) is not int or batch_size<1: raise ValidationError('Positive lifecycle batch size required')
        execution=execution or ExecutionConfig(); ds=market.dataset(dataset_hash)
        cfg=CandidateConfig(execution.enabled_symbols,execution.metadata_mode,execution.max_metadata_age_ms)
        snapshots,versions=capture(market.registry,ds,cfg)
        engine=LifecycleEngine(ds,intents,snapshots,versions,fees,execution,funding_config,calendars)
        cp=self.load_checkpoint(engine.manifest.digest)
        if cp:
            engine=LifecycleEngine.restore(ds,intents,snapshots,versions,fees,execution,engine.funding_config,calendars,cp)
            if engine.finish_called: return self.summary(engine.manifest.digest)
        pending=[]; count=0
        for e in market.replay(dataset_hash,after_id=engine.cursor[1] if engine.cursor else None):
            pending.extend(engine.advance(e)); count+=1
            if count%batch_size==0: self.commit(engine,pending,engine.report()); pending=[]
        records,report=engine.finish(); pending.extend(records); self.commit(engine,pending,report)
        return self.summary(engine.manifest.digest)
