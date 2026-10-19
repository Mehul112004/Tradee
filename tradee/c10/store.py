"""Atomic pinned training snapshots, fits, publications, estimates and evaluations."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from .contracts import EstimatorConfig,ExpectancyRecord
from .source import snapshot
from .engine import fit,publish,estimate,verified_model
from .evaluation import evaluate

APP_ID=0x54523130


class EstimatorStore:
    def __init__(self,path='data/c10.sqlite3',forbidden_paths=(),clock=time.time):
        if str(path)==':memory:' or Path(path).resolve() in {Path(p).resolve() for p in forbidden_paths}: raise ValidationError('C10 requires its own persistent database')
        self.path=str(path); self.clock=clock; Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            tables=db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if (tables and db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID) or db.execute('PRAGMA user_version').fetchone()[0] not in (0,1): raise ValidationError('Not a supported C10 database')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS snapshots(hash TEXT PRIMARY KEY,document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS fits(hash TEXT PRIMARY KEY,snapshot_hash TEXT NOT NULL REFERENCES snapshots(hash),document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS models(hash TEXT PRIMARY KEY,publication_key TEXT NOT NULL UNIQUE,fit_hash TEXT NOT NULL REFERENCES fits(hash),document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS estimates(hash TEXT PRIMARY KEY,model_hash TEXT NOT NULL REFERENCES models(hash),document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS evaluations(hash TEXT PRIMARY KEY,model_hash TEXT NOT NULL REFERENCES models(hash),document TEXT NOT NULL);
            ''')
            db.execute(f'PRAGMA application_id={APP_ID}'); db.execute('PRAGMA user_version=1')

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=15); db.row_factory=sqlite3.Row; db.execute('PRAGMA foreign_keys=ON')
        try:
            with db: yield db
        finally: db.close()

    def _read(self,table,h):
        if table not in ('snapshots','fits','models','estimates','evaluations'): raise ValidationError('Unknown expectancy artifact table')
        with self.connection() as db: row=db.execute(f'SELECT document FROM {table} WHERE hash=?',(h,)).fetchone()
        if row is None: raise ValidationError('Unknown expectancy artifact')
        doc=json.loads(row[0])
        if fingerprint(doc)!=h: raise ValidationError('Corrupt expectancy artifact')
        return doc

    def training_snapshot(self,h): return dict(snapshot_hash=h,**self._read('snapshots',h))
    def fitted(self,h): return dict(fit_hash=h,**self._read('fits',h))
    def model(self,h):
        d=self._read('models',h); verified_model(d); fitted=self._read('fits',d['fit_hash'])
        if d['fit']!=fitted: raise ValidationError('Estimator does not match stored fit')
        self._read('snapshots',fitted['snapshot_hash'])
        return dict(model_hash=h,**d)
    def estimate_record(self,h): return dict(estimate_hash=h,**self._read('estimates',h))
    def evaluation(self,h): return dict(evaluation_hash=h,**self._read('evaluations',h))

    def summary(self,h):
        d=self.model(h); f=d['fit']
        return dict(model_hash=h,fit_hash=d['fit_hash'],snapshot_hash=f['snapshot_hash'],ready=f['ready'],available_ms=d['available_ms'],
            availability_basis=d['availability_basis'],window=f['window'],coverage=f['coverage'],cohorts=f['cohorts'],release_status=f['release_status'])

    def fit(self,simulations,runs,window,config=None,modeled_available_ms=None):
        if Path(simulations.path).resolve()==Path(self.path).resolve(): raise ValidationError('C10/C11 stores must differ')
        config=config or EstimatorConfig(); data=snapshot(simulations,runs,window,config); fitted=fit(data,config)
        key=fingerprint([fitted.digest,'recorded' if modeled_available_ms is None else 'modeled',modeled_available_ms])
        with self.connection() as db: row=db.execute('SELECT hash FROM models WHERE publication_key=?',(key,)).fetchone()
        if row: return self.summary(row[0])
        available=int(self.clock()*1000) if modeled_available_ms is None else modeled_available_ms
        model=publish(fitted,available,'recorded' if modeled_available_ms is None else 'modeled')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            # Concurrent identical fits reuse the first complete publication.
            old=db.execute('SELECT hash FROM models WHERE publication_key=?',(key,)).fetchone()
            if old: h=old[0]
            else:
                db.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?)',(data.digest,data.serialized))
                db.execute('INSERT OR IGNORE INTO fits VALUES(?,?,?)',(fitted.digest,data.digest,fitted.serialized))
                db.execute('INSERT INTO models VALUES(?,?,?,?)',(model.digest,key,fitted.digest,model.serialized)); h=model.digest
        return self.summary(h)

    def estimate(self,h,request):
        result=estimate(self.model(h),request)
        with self.connection() as db: db.execute('INSERT OR IGNORE INTO estimates VALUES(?,?,?)',(result.digest,h,result.serialized))
        return dict(estimate_hash=result.digest,**result.document())

    def evaluate(self,h,simulations,runs,window):
        result=evaluate(self.model(h),simulations,runs,window)
        with self.connection() as db: db.execute('INSERT OR IGNORE INTO evaluations VALUES(?,?,?)',(result.digest,h,result.serialized))
        return dict(evaluation_hash=result.digest,**result.document())
