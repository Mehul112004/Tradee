"""Atomic content-addressed forward reports and a verified append-only journal."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c02.domain import integer
from tradee.c03.contracts import FrozenRecord
from tradee.c12.contracts import identifier

APP_ID=0x54523135


class MonitorStore:
    def __init__(self,path='data/c15.sqlite3',forbidden_paths=()):
        if str(path)==':memory:' or Path(path).resolve() in {Path(p).resolve() for p in forbidden_paths}: raise ValidationError('C15 requires a separate persistent database')
        self.path=str(path); Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            tables=db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if (tables and db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID) or db.execute('PRAGMA user_version').fetchone()[0] not in (0,1): raise ValidationError('Not a supported C15 database')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS artifacts(hash TEXT PRIMARY KEY,document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS monitors(name TEXT PRIMARY KEY,manifest_hash TEXT REFERENCES artifacts(hash),deployment_hash TEXT UNIQUE,revision INTEGER NOT NULL,report_hash TEXT REFERENCES artifacts(hash),last_ms INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS journal(name TEXT REFERENCES monitors(name),sequence INTEGER,event_hash TEXT UNIQUE REFERENCES artifacts(hash),PRIMARY KEY(name,sequence));
                CREATE TABLE IF NOT EXISTS observations(name TEXT REFERENCES monitors(name),request_hash TEXT,report_hash TEXT REFERENCES artifacts(hash),PRIMARY KEY(name,request_hash));
                CREATE TABLE IF NOT EXISTS pauses(name TEXT REFERENCES monitors(name),report_hash TEXT REFERENCES artifacts(hash),receipt_hash TEXT REFERENCES artifacts(hash),PRIMARY KEY(name,report_hash));
            ''')
            db.execute(f'PRAGMA application_id={APP_ID}'); db.execute('PRAGMA user_version=1')

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=15); db.row_factory=sqlite3.Row; db.execute('PRAGMA foreign_keys=ON')
        try:
            with db: yield db
        finally: db.close()

    @staticmethod
    def put(db,value):
        r=value if isinstance(value,FrozenRecord) else FrozenRecord.create(value)
        db.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?)',(r.digest,r.serialized)); return r.digest

    @staticmethod
    def read(db,h):
        row=db.execute('SELECT document FROM artifacts WHERE hash=?',(h,)).fetchone()
        if row is None: raise ValidationError('Unknown C15 artifact')
        d=json.loads(row[0])
        if fingerprint(d)!=h: raise ValidationError('Corrupt C15 artifact')
        return d

    def artifact(self,h):
        with self.connection() as db: return self.read(db,h)

    def _events(self,db,name):
        events=[]; previous=None
        for seq,row in enumerate(db.execute('SELECT sequence,event_hash FROM journal WHERE name=? ORDER BY sequence',(name,)).fetchall(),1):
            d=self.read(db,row['event_hash'])
            if row['sequence']!=seq or d['sequence']!=seq or d['previous_hash']!=previous or d['name']!=name: raise ValidationError('Corrupt C15 journal')
            events.append(dict(event_hash=row['event_hash'],**d)); previous=row['event_hash']
        if not events or events[0]['kind']!='registered': raise ValidationError('Missing C15 registration journal')
        return events

    def _event(self,db,name,kind,payload,when):
        row=db.execute('SELECT sequence,event_hash FROM journal WHERE name=? ORDER BY sequence DESC LIMIT 1',(name,)).fetchone()
        d=dict(name=name,sequence=1 if row is None else row[0]+1,previous_hash=None if row is None else row[1],kind=kind,at_ms=when,payload=payload)
        h=self.put(db,d); db.execute('INSERT INTO journal VALUES(?,?,?)',(name,d['sequence'],h))

    def _head(self,db,name):
        r=db.execute('SELECT * FROM monitors WHERE name=?',(name,)).fetchone()
        if r is None: raise ValidationError('Unknown C15 monitor')
        d=dict(r); m=self.read(db,d['manifest_hash']); events=self._events(db,name)
        reports=[e for e in events if e['kind']=='observed']
        if (m['name']!=name or m['deployment_hash']!=d['deployment_hash'] or events[0]['payload']['manifest_hash']!=d['manifest_hash'] or
            len(reports)!=d['revision'] or (reports[-1]['payload']['report_hash'] if reports else None)!=d['report_hash'] or
            (reports[-1]['at_ms'] if reports else m['registered_ms'])!=d['last_ms']): raise ValidationError('C15 index differs from journal')
        report=None if d['report_hash'] is None else self.read(db,d['report_hash'])
        for row in db.execute('SELECT request_hash,report_hash FROM observations WHERE name=?',(name,)).fetchall():
            if not any(e['payload']==dict(request_hash=row[0],report_hash=row[1]) for e in reports): raise ValidationError('C15 observation index differs from journal')
        if db.execute('SELECT COUNT(*) FROM observations WHERE name=?',(name,)).fetchone()[0]!=len(reports): raise ValidationError('Missing C15 observation index')
        pause_rows=db.execute('SELECT report_hash,receipt_hash FROM pauses WHERE name=?',(name,)).fetchall()
        if len(pause_rows)!=len([e for e in events if e['kind']=='pause_applied']): raise ValidationError('Missing C15 pause receipt index')
        for row in pause_rows:
            receipt=self.read(db,row[1])
            if not any(e['kind']=='pause_applied' and e['payload']==dict(report_hash=row[0],receipt_hash=row[1]) for e in events) or receipt['report_hash']!=row[0]: raise ValidationError('C15 pause index differs from journal')
        return dict(d,manifest=m,report=report)

    def head(self,name):
        with self.connection() as db: db.execute('BEGIN'); return self._head(db,name)

    def events(self,name):
        with self.connection() as db: db.execute('BEGIN'); self._head(db,name); return self._events(db,name)

    def cached(self,name,request_hash):
        with self.connection() as db:
            db.execute('BEGIN'); self._head(db,name)
            row=db.execute('SELECT report_hash FROM observations WHERE name=? AND request_hash=?',(name,request_hash)).fetchone()
            return None if row is None else dict(report_hash=row[0],**self.read(db,row[0]))

    def reconciliation(self,name,record):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE'); self._head(db,name); h=self.put(db,record)
            prior=[e for e in self._events(db,name) if e['kind']=='replay_checked' and e['payload']['receipt_hash']==h]
            if not prior: self._event(db,name,'replay_checked',dict(receipt_hash=h),record['at_ms'])
        return dict(receipt_hash=h,**record)

    def register(self,manifest):
        m=manifest.document() if isinstance(manifest,FrozenRecord) else manifest; identifier(m['name']); integer(m['registered_ms'],'registration clock')
        if m.get('kind')!='forward_monitor' or m.get('live_approved') is not False: raise ValidationError('Frozen paper monitor required')
        h=fingerprint(m)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE'); row=db.execute('SELECT manifest_hash FROM monitors WHERE name=?',(m['name'],)).fetchone()
            if row:
                if row[0]!=h: raise ValidationError('C15 monitor name already frozen')
            else:
                if db.execute('SELECT 1 FROM monitors WHERE deployment_hash=?',(m['deployment_hash'],)).fetchone(): raise ValidationError('A deployment has one prospective monitoring policy')
                self.put(db,m); db.execute('INSERT INTO monitors VALUES(?,?,?,0,NULL,?)',(m['name'],h,m['deployment_hash'],m['registered_ms']))
                self._event(db,m['name'],'registered',dict(manifest_hash=h),m['registered_ms'])
        return self.head(m['name'])

    def publish(self,name,expected,request_hash,report):
        r=report.document() if isinstance(report,FrozenRecord) else report
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE'); head=self._head(db,name)
            cached=db.execute('SELECT report_hash FROM observations WHERE name=? AND request_hash=?',(name,request_hash)).fetchone()
            if cached:
                if cached[0]!=fingerprint(r): raise ValidationError('Conflicting deterministic C15 report')
                return dict(report_hash=cached[0],**self.read(db,cached[0]))
            if head['revision']!=expected: raise ValidationError('C15 compare-and-swap conflict; observe again')
            if (r.get('kind')!='forward_report' or r['manifest_hash']!=head['manifest_hash'] or r['observed_ms']<head['last_ms'] or
                r['source']['deployment_hash']!=head['deployment_hash'] or r.get('live_approved') is not False): raise ValidationError('C15 report identity/clock mismatch')
            old=head['report']
            if old and r['source']['event_hashes'][:len(old['source']['event_hashes'])]!=old['source']['event_hashes']: raise ValidationError('C14 audit prefix changed since observation')
            if old and r['reviews'][:len(old['reviews'])]!=old['reviews']: raise ValidationError('Prior fixed-look review changed')
            h=self.put(db,r); db.execute('INSERT INTO observations VALUES(?,?,?)',(name,request_hash,h))
            db.execute('UPDATE monitors SET revision=revision+1,report_hash=?,last_ms=? WHERE name=?',(h,r['observed_ms'],name))
            self._event(db,name,'observed',dict(request_hash=request_hash,report_hash=h),r['observed_ms'])
        return dict(report_hash=h,**r)

    def receipt(self,name,report_hash,receipt):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE'); self._head(db,name)
            old=db.execute('SELECT receipt_hash FROM pauses WHERE name=? AND report_hash=?',(name,report_hash)).fetchone()
            h=self.put(db,receipt)
            if old:
                if old[0]!=h: raise ValidationError('Conflicting C15 pause receipt')
            else:
                db.execute('INSERT INTO pauses VALUES(?,?,?)',(name,report_hash,h))
                self._event(db,name,'pause_applied',dict(report_hash=report_hash,receipt_hash=h),receipt['at_ms'])
        return receipt
