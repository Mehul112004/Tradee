"""Immutable runs and outputs; checkpoint/output transactions are atomic."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

from tradee.c01 import ValidationError
from tradee.c01.domain import canonical, fingerprint
from .contracts import FeatureSnapshot
from .engine import FeatureEngine

APP_ID = 0x54524433


class FeatureStore:
    def __init__(self, path='data/c03.sqlite3', forbidden_paths=(), clock=time.time):
        if str(path)==':memory:' or Path(path).resolve() in {Path(p).resolve() for p in forbidden_paths}:
            raise ValidationError('C03 requires its own persistent database')
        self.path,self.clock = str(path),clock
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            app,version = db.execute('PRAGMA application_id').fetchone()[0],db.execute('PRAGMA user_version').fetchone()[0]
            if (tables and app!=APP_ID) or version not in (0,1):
                raise ValidationError('Not a supported C03 database')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS runs(hash TEXT PRIMARY KEY, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS lineage(hash TEXT PRIMARY KEY, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS snapshots(hash TEXT PRIMARY KEY, run_hash TEXT NOT NULL REFERENCES runs(hash),
                    document TEXT NOT NULL, computed_at_ms INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS snapshots_run ON snapshots(run_hash);
                CREATE TABLE IF NOT EXISTS checkpoints(run_hash TEXT PRIMARY KEY REFERENCES runs(hash),
                    document TEXT NOT NULL, checksum TEXT NOT NULL);
            ''')
            db.execute(f'PRAGMA application_id={APP_ID}')
            db.execute('PRAGMA user_version=1')

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=15)
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def commit(self, engine, snapshots):
        checkpoint=engine.checkpoint()
        document=canonical(checkpoint)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO runs VALUES(?,?)',(engine.manifest.digest,engine.manifest.serialized))
            previous=db.execute('SELECT document FROM checkpoints WHERE run_hash=?',(engine.manifest.digest,)).fetchone()
            if previous:
                old=json.loads(previous[0])
                old_cursor=old['cursor']
                if old_cursor is not None and (checkpoint['cursor'] is None or tuple(checkpoint['cursor'])<tuple(old_cursor)):
                    raise ValidationError('Cannot move a persisted feature run backward')
                current_cursor=checkpoint['cursor']
                same_cursor=(old_cursor is None and current_cursor is None) or (
                    old_cursor is not None and current_cursor is not None and tuple(old_cursor)==tuple(current_cursor))
                if same_cursor and old['prefix_hash']!=checkpoint['prefix_hash']:
                    raise ValidationError('Conflicting input prefix at persisted cursor')
                if checkpoint['evaluated_through_ms'] < old['evaluated_through_ms']:
                    raise ValidationError('Cannot move a persisted decision clock backward')
            for digest,doc in engine.lineages.items():
                db.execute('INSERT OR IGNORE INTO lineage VALUES(?,?)',(digest,canonical(doc)))
            for snapshot in snapshots:
                doc=snapshot.document()
                if doc['run_hash']!=engine.manifest.digest:
                    raise ValidationError('Snapshot belongs to another run')
                if doc['input_cursor'] is not None and (checkpoint['cursor'] is None or tuple(doc['input_cursor'])>tuple(checkpoint['cursor'])):
                    raise ValidationError('Snapshot extends beyond checkpoint')
                db.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?,?)',
                           (snapshot.digest,engine.manifest.digest,snapshot.serialized,int(self.clock()*1000)))
            db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?,?)',(engine.manifest.digest,document,fingerprint(checkpoint)))
        # Lineage already committed; the engine can recompute shared nodes when needed.
        engine.lineages.clear()

    def load_checkpoint(self, run_hash):
        with self.connection() as db:
            row=db.execute('SELECT document,checksum FROM checkpoints WHERE run_hash=?',(run_hash,)).fetchone()
        if row is None:
            return None
        doc=json.loads(row['document'])
        if fingerprint(doc)!=row['checksum']:
            raise ValidationError('Corrupt checkpoint checksum')
        return doc

    def _read(self,table,digest):
        with self.connection() as db:
            row=db.execute(f'SELECT document FROM {table} WHERE hash=?',(digest,)).fetchone()
        if not row:
            raise ValidationError(f'Unknown {table} record')
        doc=json.loads(row[0])
        if fingerprint(doc)!=digest:
            raise ValidationError(f'Corrupt {table} record')
        return doc

    def snapshot(self,digest):
        return {'snapshot_hash':digest,**self._read('snapshots',digest)}

    def manifest(self,digest):
        return {'run_hash':digest,**self._read('runs',digest)}

    def lineage(self,digest):
        return self._read('lineage',digest)

    def summary(self,run_hash):
        self.manifest(run_hash)
        with self.connection() as db:
            rows=db.execute('SELECT hash,document FROM snapshots WHERE run_hash=? ORDER BY rowid',(run_hash,)).fetchall()
        docs=[json.loads(r['document']) for r in rows]
        latest={}
        for row,doc in zip(rows,docs):
            latest[(doc['instrument_id'],doc['timeframe'])]={'snapshot_hash':row['hash'],'ready':doc['ready'],
                'target_open_ms':doc['target_open_ms'],'instrument_id':doc['instrument_id'],'timeframe':doc['timeframe']}
        return dict(run_hash=run_hash,snapshots=len(rows),ready_snapshots=sum(d['ready'] for d in docs),
                    latest=list(latest.values()))

    def run(self,market,dataset_hash,config,batch_size=256):
        if type(batch_size) is not int or batch_size<1:
            raise ValidationError('Batch size must be positive')
        dataset=market.dataset(dataset_hash)
        engine=FeatureEngine(dataset,config)
        checkpoint=self.load_checkpoint(engine.manifest.digest)
        if checkpoint:
            engine=FeatureEngine.restore(dataset,config,checkpoint)
        pending=[]
        count=0
        for event in market.replay(dataset_hash,after_id=engine.cursor[1] if engine.cursor else None):
            pending.extend(engine.advance(event))
            count+=1
            if count%batch_size==0:
                self.commit(engine,pending)
                pending=[]
        self.commit(engine,pending)
        return self.summary(engine.manifest.digest)
