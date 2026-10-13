"""Pinned execution scenarios and atomic report/checkpoint transactions."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

from tradee.c01 import Policy, ValidationError
from tradee.c01.domain import canonical, fingerprint
from .contracts import ExecutionConfig, ExecutionIntent
from .engine import ExecutionEngine

APP_ID=0x54524437


class ExecutionStore:
    def __init__(self,path='data/c07.sqlite3',forbidden_paths=(),clock=time.time):
        if str(path)==':memory:' or Path(path).resolve() in {Path(p).resolve() for p in forbidden_paths}:
            raise ValidationError('C07 requires its own persistent database')
        self.path=str(path); self.clock=clock; Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            tables=db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            app=db.execute('PRAGMA application_id').fetchone()[0]; version=db.execute('PRAGMA user_version').fetchone()[0]
            if (tables and app!=APP_ID) or version not in (0,1): raise ValidationError('Not a supported C07 database')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS runs(hash TEXT PRIMARY KEY,document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reports(hash TEXT PRIMARY KEY,run_hash TEXT REFERENCES runs(hash),
                    document TEXT NOT NULL,computed_at_ms INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS reports_run ON reports(run_hash);
                CREATE TABLE IF NOT EXISTS checkpoints(run_hash TEXT PRIMARY KEY REFERENCES runs(hash),
                    document TEXT NOT NULL,checksum TEXT NOT NULL);
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
        if row is None: raise ValidationError('Unknown execution '+table+' record')
        doc=json.loads(row[0])
        if fingerprint(doc)!=digest: raise ValidationError('Corrupt execution '+table+' record')
        return doc

    def report(self,digest): return {'report_hash':digest,**self._read('reports',digest)}
    def manifest(self,digest): return {'run_hash':digest,**self._read('runs',digest)}

    def load_checkpoint(self,digest):
        with self.connection() as db: row=db.execute('SELECT document,checksum FROM checkpoints WHERE run_hash=?',(digest,)).fetchone()
        if row is None: return None
        doc=json.loads(row['document'])
        if fingerprint(doc)!=row['checksum']: raise ValidationError('Corrupt execution checkpoint')
        return doc

    def commit(self,engine,report):
        cp=engine.checkpoint(); doc=report.document()
        if (doc['run_hash']!=engine.manifest.digest or doc['input_cursor']!=json.loads(canonical(cp['cursor']))
                or doc['input_prefix_hash']!=cp['prefix_hash'] or doc['evaluation_as_of_ms']!=cp['evaluated_through_ms']):
            raise ValidationError('Execution report/checkpoint state mismatch')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT document,checksum FROM checkpoints WHERE run_hash=?',(engine.manifest.digest,)).fetchone()
            if row:
                old=json.loads(row['document'])
                if fingerprint(old)!=row['checksum']: raise ValidationError('Corrupt previous execution checkpoint')
                a,b=old['cursor'],cp['cursor']; same=(a is None and b is None) or (a is not None and b is not None and tuple(a)==tuple(b))
                if a is not None and (b is None or tuple(b)<tuple(a)): raise ValidationError('Execution cursor cannot move backward')
                if same and old['prefix_hash']!=cp['prefix_hash']: raise ValidationError('Conflicting execution prefix')
                if cp['evaluated_through_ms']<old['evaluated_through_ms']: raise ValidationError('Execution clock cannot move backward')
            db.execute('INSERT OR IGNORE INTO runs VALUES(?,?)',(engine.manifest.digest,engine.manifest.serialized))
            db.execute('INSERT OR IGNORE INTO reports VALUES(?,?,?,?)',(report.digest,engine.manifest.digest,report.serialized,int(self.clock()*1000)))
            db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?,?)',(engine.manifest.digest,canonical(cp),fingerprint(cp)))

    def summary(self,run_hash):
        self.manifest(run_hash)
        with self.connection() as db:
            count=db.execute('SELECT COUNT(*) FROM reports WHERE run_hash=?',(run_hash,)).fetchone()[0]
            row=db.execute('SELECT hash FROM reports WHERE run_hash=? ORDER BY rowid DESC LIMIT 1',(run_hash,)).fetchone()
        report=None if row is None else self.report(row[0])
        return dict(run_hash=run_hash,reports=count,report_hash=None if row is None else row[0],
            ready=False if report is None else report['ready'],estimates=[] if report is None else [dict(intent_id=e['intent_id'],
                status=e['status'],reasons=e['reasons'],fill=e['fill'],costs=e['costs'],
                projected_execution_cost_with_next_funding_usdt=e['projected_execution_cost_with_next_funding_usdt']) for e in report['estimates']])

    def run(self,market,dataset_hash,intents,fees,config=None,features=(),decision_ms=None,batch_size=256):
        if type(batch_size) is not int or batch_size<1: raise ValidationError('Positive execution batch size required')
        cfg=config or ExecutionConfig(); ds=market.dataset(dataset_hash)
        when=ds['as_of_ms'] if decision_ms is None else decision_ms
        # Freeze the C01 query as part of this run, instead of following later metadata changes.
        metadata_time=when if cfg.metadata_mode=='observed' else ds['as_of_ms']
        # C01 policy is in whole seconds; round up and let the engine enforce the
        # exact millisecond budget so 1500ms is not accidentally reduced to 1000ms.
        universe=market.registry.universe(Policy(cfg.enabled_symbols,max(1,(cfg.max_metadata_age_ms+999)//1000)),metadata_time)
        versions={d['version_hash']:market.registry.version(d['version_hash'])['spec'] for d in universe['decisions'] if d['version_hash']}
        engine=ExecutionEngine(ds,intents,universe,versions,fees,cfg,features,when)
        cp=self.load_checkpoint(engine.manifest.digest)
        if cp: engine=ExecutionEngine.restore(ds,engine.intents,universe,versions,fees,cfg,features,when,cp)
        count=0
        for e in market.replay(dataset_hash,until_ms=when,after_id=engine.cursor[1] if engine.cursor else None):
            engine.push(e); count+=1
            if count%batch_size==0: self.commit(engine,engine.report(e['available_ms']))
        self.commit(engine,engine.report())
        return self.summary(engine.manifest.digest)
