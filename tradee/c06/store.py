"""Immutable funding evidence and atomic report/checkpoint persistence."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

from tradee.c01 import ValidationError
from tradee.c01.domain import canonical, fingerprint
from .contracts import FundingConfig, PositionTimeline, SettlementCalendar
from .engine import FundingEngine

APP_ID=0x54524436


class FundingStore:
    def __init__(self, path='data/c06.sqlite3', forbidden_paths=(), clock=time.time):
        if str(path)==':memory:' or Path(path).resolve() in {Path(p).resolve() for p in forbidden_paths}:
            raise ValidationError('C06 requires its own persistent database')
        self.path=str(path); self.clock=clock
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            tables=db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            app=db.execute('PRAGMA application_id').fetchone()[0]
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if (tables and app!=APP_ID) or version not in (0,1):
                raise ValidationError('Not a supported C06 database')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS runs(hash TEXT PRIMARY KEY, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reports(hash TEXT PRIMARY KEY,
                    run_hash TEXT NOT NULL REFERENCES runs(hash),document TEXT NOT NULL,computed_at_ms INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS report_run ON reports(run_hash);
                CREATE TABLE IF NOT EXISTS checkpoints(run_hash TEXT PRIMARY KEY REFERENCES runs(hash),
                    document TEXT NOT NULL,checksum TEXT NOT NULL);
            ''')
            db.execute(f'PRAGMA application_id={APP_ID}')
            db.execute('PRAGMA user_version=1')

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=15); db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db: yield db
        finally:
            db.close()

    def _read(self, table, digest):
        with self.connection() as db:
            row=db.execute(f'SELECT document FROM {table} WHERE hash=?',(digest,)).fetchone()
        if row is None:
            raise ValidationError(f'Unknown funding {table} record')
        doc=json.loads(row[0])
        if fingerprint(doc)!=digest:
            raise ValidationError(f'Corrupt funding {table} record')
        return doc

    def manifest(self, digest):
        return {'run_hash':digest,**self._read('runs',digest)}

    def report(self, digest):
        return {'report_hash':digest,**self._read('reports',digest)}

    def load_checkpoint(self, run_hash):
        with self.connection() as db:
            row=db.execute('SELECT document,checksum FROM checkpoints WHERE run_hash=?',(run_hash,)).fetchone()
        if row is None:
            return None
        doc=json.loads(row['document'])
        if fingerprint(doc)!=row['checksum']:
            raise ValidationError('Corrupt funding checkpoint')
        return doc

    def commit(self, engine, report):
        checkpoint=engine.checkpoint(); doc=report.document()
        if (doc['run_hash']!=engine.manifest.digest or doc['input_cursor']!=json.loads(canonical(checkpoint['cursor']))
                or doc['input_prefix_hash']!=checkpoint['prefix_hash']
                or doc['evaluation_as_of_ms']!=checkpoint['evaluated_through_ms']):
            raise ValidationError('Funding report and checkpoint do not describe the same state')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT document,checksum FROM checkpoints WHERE run_hash=?',(engine.manifest.digest,)).fetchone()
            if old:
                previous=json.loads(old['document'])
                if fingerprint(previous)!=old['checksum']:
                    raise ValidationError('Corrupt previous funding checkpoint')
                a,b=previous['cursor'],checkpoint['cursor']
                if a is not None and (b is None or tuple(b)<tuple(a)):
                    raise ValidationError('Cannot move funding input cursor backward')
                same=(a is None and b is None) or (a is not None and b is not None and tuple(a)==tuple(b))
                if same and previous['prefix_hash']!=checkpoint['prefix_hash']:
                    raise ValidationError('Conflicting funding prefix at persisted cursor')
                if checkpoint['evaluated_through_ms']<previous['evaluated_through_ms']:
                    raise ValidationError('Cannot move persisted funding decision time backward')
            db.execute('INSERT OR IGNORE INTO runs VALUES(?,?)',(engine.manifest.digest,engine.manifest.serialized))
            db.execute('INSERT OR IGNORE INTO reports VALUES(?,?,?,?)',
                (report.digest,engine.manifest.digest,report.serialized,int(self.clock()*1000)))
            db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?,?)',
                (engine.manifest.digest,canonical(checkpoint),fingerprint(checkpoint)))

    def summary(self, run_hash):
        self.manifest(run_hash)
        with self.connection() as db:
            count=db.execute('SELECT COUNT(*) FROM reports WHERE run_hash=?',(run_hash,)).fetchone()[0]
            row=db.execute('SELECT hash FROM reports WHERE run_hash=? ORDER BY rowid DESC LIMIT 1',(run_hash,)).fetchone()
        latest=None if row is None else self.report(row[0])
        return dict(run_hash=run_hash,reports=count,report_hash=None if latest is None else latest['report_hash'],
            ready=False if latest is None else latest['ready'],
            positions=[] if latest is None else [dict(position_id=p['position_id'],coverage_status=p['coverage_status'],
                known_cashflow_subtotal_usdt=p['known_cashflow_subtotal_usdt'],total_cashflow_usdt=p['total_cashflow_usdt'])
                for p in latest['positions']])

    @staticmethod
    def validate_metadata(market, positions, calendars):
        """C02's binding evidence must describe an in-scope linear USDT instrument."""
        wanted={p.instrument_id:p.symbol for p in (*positions,*calendars)}
        with market.registry.connection() as db:
            rows=db.execute('SELECT instrument_id,spec FROM versions').fetchall()
        supported=set()
        for row in rows:
            spec=json.loads(row['spec'])
            if (spec.get('scope_supported') and spec.get('quoteAsset')=='USDT' and spec.get('marginAsset')=='USDT'
                    and spec.get('contractType')=='PERPETUAL' and 'identity_conflict' not in spec.get('issues',[])
                    and wanted.get(row['instrument_id'])==spec.get('symbol')):
                supported.add(row['instrument_id'])
        if set(wanted)-supported:
            raise ValidationError('Funding positions/calendars require supported C01 identity evidence')

    def run(self, market, dataset_hash, positions, calendars=(), config=None, decision_ms=None, batch_size=256):
        if type(batch_size) is not int or batch_size<1:
            raise ValidationError('Funding batch size must be positive')
        positions=tuple(p if isinstance(p,PositionTimeline) else PositionTimeline.from_dict(p) for p in positions)
        calendars=tuple(c if isinstance(c,SettlementCalendar) else SettlementCalendar.from_dict(c) for c in calendars)
        if not positions:
            raise ValidationError('At least one funding position timeline is required')
        self.validate_metadata(market,positions,calendars)
        dataset=market.dataset(dataset_hash); config=config or FundingConfig()
        engine=FundingEngine(dataset,positions,calendars,config,decision_ms)
        checkpoint=self.load_checkpoint(engine.manifest.digest)
        if checkpoint:
            engine=FundingEngine.restore(dataset,positions,calendars,config,engine.decision_ms,checkpoint)
        count=0
        for event in market.replay(dataset_hash,until_ms=engine.decision_ms,after_id=engine.cursor[1] if engine.cursor else None):
            if event['kind'] in ('funding','mark'):
                version=market.registry.version(event['metadata_version'])['spec']
                if (not version['scope_supported'] or version['quoteAsset']!='USDT' or version['marginAsset']!='USDT'
                        or version['instrument_id']!=event['instrument_id'] or version['symbol']!=event['symbol']):
                    raise ValidationError('Funding event metadata is not an in-scope instrument')
            engine.push(event); count+=1
            if count%batch_size==0:
                self.commit(engine,engine.report(event['available_ms']))
        self.commit(engine,engine.report())
        return self.summary(engine.manifest.digest)
