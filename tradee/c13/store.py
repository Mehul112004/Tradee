"""Atomic funded replay artifacts and compare-and-swap local risk reservations."""
from contextlib import contextmanager
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c03.contracts import FrozenRecord
from tradee.c07.math import exact
from tradee.c06.contracts import decimal_text
from .contracts import AccountSnapshot,RiskPolicy,Offer,text
from .engine import allocate
from .replay import PortfolioReplay,ReplayConfig,diagnostics

APP_ID=0x54523133


class PortfolioStore:
    def __init__(self,path='data/c13.sqlite3',forbidden_paths=()):
        if str(path)==':memory:' or Path(path).resolve() in {Path(p).resolve() for p in forbidden_paths}: raise ValidationError('C13 requires its own persistent database')
        self.path=str(path); Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            tables=db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if (tables and db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID) or db.execute('PRAGMA user_version').fetchone()[0] not in (0,1): raise ValidationError('Not a supported C13 database')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS artifacts(hash TEXT PRIMARY KEY,document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS replays(hash TEXT PRIMARY KEY,report_hash TEXT NOT NULL REFERENCES artifacts(hash));
                CREATE TABLE IF NOT EXISTS replay_events(run_hash TEXT REFERENCES replays(hash),sequence INTEGER,hash TEXT REFERENCES artifacts(hash),PRIMARY KEY(run_hash,sequence));
                CREATE TABLE IF NOT EXISTS accounts(name TEXT PRIMARY KEY,revision INTEGER NOT NULL,snapshot_hash TEXT REFERENCES artifacts(hash));
                CREATE TABLE IF NOT EXISTS account_events(account TEXT REFERENCES accounts(name),revision INTEGER,event_hash TEXT UNIQUE REFERENCES artifacts(hash),PRIMARY KEY(account,revision));
                CREATE TABLE IF NOT EXISTS batches(request_hash TEXT PRIMARY KEY,account TEXT REFERENCES accounts(name),before_hash TEXT,after_hash TEXT,allocation_hash TEXT REFERENCES artifacts(hash));
            ''')
            db.execute(f'PRAGMA application_id={APP_ID}'); db.execute('PRAGMA user_version=1')

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=15); db.row_factory=sqlite3.Row; db.execute('PRAGMA foreign_keys=ON')
        try:
            with db: yield db
        finally: db.close()

    @staticmethod
    def put(db,doc):
        record=doc if isinstance(doc,FrozenRecord) else FrozenRecord.create(doc)
        db.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?)',(record.digest,record.serialized)); return record.digest

    @staticmethod
    def read(db,h):
        r=db.execute('SELECT document FROM artifacts WHERE hash=?',(h,)).fetchone()
        if r is None: raise ValidationError('Unknown portfolio artifact')
        d=json.loads(r[0])
        if fingerprint(d)!=h: raise ValidationError('Corrupt portfolio artifact')
        return d

    def artifact(self,h):
        with self.connection() as db: return self.read(db,h)
    def manifest(self,h):
        d=self.artifact(h)
        if d.get('kind')!='funded_replay': raise ValidationError('Not a C13 replay manifest')
        return dict(run_hash=h,**d)
    def report(self,h):
        d=self.artifact(h)
        if d.get('kind')!='funded_portfolio_report': raise ValidationError('Not a C13 portfolio report')
        return dict(report_hash=h,**d)

    def records(self,h):
        with self.connection() as db:
            db.execute('BEGIN'); self.read(db,h)
            refs=db.execute('SELECT sequence,hash FROM replay_events WHERE run_hash=? ORDER BY sequence',(h,)).fetchall()
            records=[dict(artifact_hash=r['hash'],**self.read(db,r['hash'])) for r in refs]
        return records

    def summary(self,h):
        with self.connection() as db:
            db.execute('BEGIN'); manifest=self.read(db,h)
            row=db.execute('SELECT report_hash FROM replays WHERE hash=?',(h,)).fetchone()
            if row is None: raise ValidationError('Unknown portfolio replay')
            report=self.read(db,row[0]); refs=db.execute('SELECT sequence,hash FROM replay_events WHERE run_hash=? ORDER BY sequence',(h,)).fetchall()
            events=[self.read(db,r['hash']) for r in refs]
        if [r['sequence'] for r in refs]!=list(range(1,len(events)+1)): raise ValidationError('Incomplete portfolio event sequence')
        self.validate(manifest,report,events,[r['hash'] for r in refs])
        return dict(run_hash=h,report_hash=row[0],completed=True,ready=report['ready'],live_approved=False,policy_hash=manifest['policy_hash'],metrics=report['metrics'],coverage=report['coverage'])

    @staticmethod
    def validate(manifest,report,events,hashes):
        h=fingerprint(manifest)
        if (manifest.get('kind')!='funded_replay' or report.get('kind')!='funded_portfolio_report' or not report['completed']
                or report['run_hash']!=h or report['policy_hash']!=manifest['policy_hash'] or report['artifact_count']!=len(events)
                or report['artifact_manifest_hash']!=fingerprint(hashes)): raise ValidationError('Incomplete portfolio artifact inventory')
        for idx,e in enumerate(events,1):
            if e['sequence']!=idx or e['run_hash']!=h or fingerprint(e['payload'])!=e['payload_hash']: raise ValidationError('Corrupt portfolio event envelope')
        samples=[e['payload'] for e in events if e['kind']=='sample']
        terminal=report['terminal_risk']; initial=manifest['config']['initial_cash_usdt']
        if report['metrics']!=diagnostics(samples,initial,terminal): raise ValidationError('Portfolio metrics do not reconcile to equity samples')
        with exact():
            cash=Decimal(initial)
            for t in report['trades']:
                cash+=sum((Decimal(v['amount_usdt']) for v in t['outcome']['state']['ledger'].values() if v['amount_usdt'] is not None),Decimal(0))
            if decimal_text(cash)!=report['terminal_account']['cash_usdt']: raise ValidationError('Shared cash does not reconcile to admitted trade ledgers')

    def commit(self,result):
        manifest,report,events=result; m=manifest.document(); r=report.document()
        if r['run_hash']!=manifest.digest or not r['completed'] or r['artifact_manifest_hash']!=fingerprint([a.digest for a in events]): raise ValidationError('Invalid funded replay publication')
        self.validate(m,r,[e.document() for e in events],[e.digest for e in events])
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE'); old=db.execute('SELECT report_hash FROM replays WHERE hash=?',(manifest.digest,)).fetchone()
            if old and old[0]!=report.digest: raise ValidationError('Conflicting completed portfolio replay')
            self.put(db,manifest); self.put(db,report)
            db.execute('INSERT OR IGNORE INTO replays VALUES(?,?)',(manifest.digest,report.digest))
            for i,event in enumerate(events,1):
                d=event.document()
                if d['run_hash']!=manifest.digest or d['sequence']!=i or d['payload_hash']!=fingerprint(d['payload']): raise ValidationError('Invalid portfolio artifact')
                self.put(db,event); db.execute('INSERT OR IGNORE INTO replay_events VALUES(?,?,?)',(manifest.digest,i,event.digest))
        return self.summary(manifest.digest)

    def replay(self,simulations,market,pins,models,policy=None,config=None):
        if len({Path(p).resolve() for p in (self.path,simulations.path,market.path)})!=3: raise ValidationError('C02/C11/C13 databases must differ')
        first=simulations.manifest(next(iter(pins)))
        if market.dataset(first['dataset']['dataset_hash'])!=first['dataset']: raise ValidationError('Market dataset differs from outcome source')
        config=config or ReplayConfig(); events=[]
        for e in market.replay(first['dataset']['dataset_hash']):
            events.append(e)
            if len(events)>config.max_events: raise ValidationError('Portfolio event budget exceeded')
        engine=PortfolioReplay(simulations,pins,models,events,policy,config)
        with self.connection() as db: exists=db.execute('SELECT 1 FROM replays WHERE hash=?',(engine.manifest.digest,)).fetchone()
        return self.summary(engine.manifest.digest) if exists else self.commit(engine.run())

    def _account(self,db,name):
        r=db.execute('SELECT * FROM accounts WHERE name=?',(name,)).fetchone()
        if r is None: raise ValidationError('Unknown local risk account')
        events=db.execute('SELECT revision,event_hash FROM account_events WHERE account=? ORDER BY revision',(name,)).fetchall(); previous=None
        for idx,e in enumerate(events):
            d=self.read(db,e['event_hash'])
            if e['revision']!=idx or d['revision']!=idx or d['previous_event_hash']!=previous or d['account']!=name: raise ValidationError('Corrupt local risk account journal')
            self.read(db,d['snapshot_hash']); previous=e['event_hash']
        if not events or events[-1]['revision']!=r['revision'] or self.read(db,events[-1]['event_hash'])['snapshot_hash']!=r['snapshot_hash']: raise ValidationError('Account snapshot differs from journal')
        state=self.read(db,r['snapshot_hash']); AccountSnapshot.from_dict(state)
        return dict(account=name,revision=r['revision'],snapshot_hash=r['snapshot_hash'],snapshot=state,event_hash=previous)

    def account(self,name):
        with self.connection() as db: db.execute('BEGIN'); return self._account(db,name)

    def create_account(self,name,snapshot):
        text(name); state=snapshot if isinstance(snapshot,AccountSnapshot) else AccountSnapshot.from_dict(snapshot)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT snapshot_hash FROM accounts WHERE name=?',(name,)).fetchone()
            h=fingerprint(state.document())
            if old:
                if old[0]!=h: raise ValidationError('Account exists; use explicit compare-and-swap snapshot update')
            else:
                self.put(db,state.document()); db.execute('INSERT INTO accounts VALUES(?,0,?)',(name,h))
                e=dict(account=name,revision=0,previous_event_hash=None,snapshot_hash=h,kind='initial_snapshot')
                eh=self.put(db,e); db.execute('INSERT INTO account_events VALUES(?,0,?)',(name,eh))
        return self.account(name)

    def _replace(self,db,old,state,kind,request_hash=None):
        h=self.put(db,state.document()); revision=old['revision']+1
        e=dict(account=old['account'],revision=revision,previous_event_hash=old['event_hash'],snapshot_hash=h,kind=kind,request_hash=request_hash)
        eh=self.put(db,e); db.execute('UPDATE accounts SET revision=?,snapshot_hash=? WHERE name=?',(revision,h,old['account']))
        db.execute('INSERT INTO account_events VALUES(?,?,?)',(old['account'],revision,eh)); return h

    def replace_snapshot(self,name,expected,state):
        state=state if isinstance(state,AccountSnapshot) else AccountSnapshot.from_dict(state)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE'); old=self._account(db,name)
            if old['snapshot_hash']!=expected: raise ValidationError('Account compare-and-swap conflict; refresh before proposing risk')
            if state.as_of_ms<old['snapshot']['as_of_ms'] or state.available_ms<old['snapshot']['available_ms']: raise ValidationError('Account source clock cannot move backward')
            self._replace(db,old,state,'explicit_snapshot_reconciliation')
        return self.account(name)

    def _cached(self,db,row,name,expected):
        d=self.read(db,row['allocation_hash']); before=self.read(db,expected); self.read(db,row['after_hash'])
        linked=db.execute('SELECT event_hash FROM account_events WHERE account=?',(name,)).fetchall()
        receipts=[self.read(db,r[0]) for r in linked]
        if (row['account']!=name or row['before_hash']!=expected or d.get('kind')!='allocation_batch' or d['account_snapshot_hash']!=fingerprint(before)
                or not any(e.get('request_hash')==row['request_hash'] and e['snapshot_hash']==row['after_hash'] for e in receipts)):
            raise ValidationError('Corrupt cached portfolio reservation batch')
        return dict(request_hash=row['request_hash'],after_snapshot_hash=row['after_hash'],allocation_hash=row['allocation_hash'],allocation=d)

    def allocate(self,name,expected,offers,policy,recheck,evaluation_ms=None):
        policy=policy if isinstance(policy,RiskPolicy) else RiskPolicy.from_dict(policy)
        offers=tuple(o if isinstance(o,Offer) else Offer.from_dict(o) for o in offers)
        when=(offers[0].request.evaluation_ms if offers else self.account(name)['snapshot']['as_of_ms']) if evaluation_ms is None else evaluation_ms
        key=fingerprint(dict(account=name,before=expected,offers=sorted((o.document() for o in offers),key=fingerprint),policy=policy.document(),evaluation_ms=when))
        with self.connection() as db:
            db.execute('BEGIN'); old=self._account(db,name); cached=db.execute('SELECT * FROM batches WHERE request_hash=?',(key,)).fetchone()
            if cached: return self._cached(db,cached,name,expected)
        if old['snapshot_hash']!=expected: raise ValidationError('Account compare-and-swap conflict; refresh before proposing risk')
        result=allocate(AccountSnapshot.from_dict(old['snapshot']),offers,policy,recheck,when); d=result.document(); new=dict(old['snapshot'])
        new.update(available_ms=when,reservations=d['reservations_after'],seen_candidates=d['seen_candidates_after'])
        state=AccountSnapshot.from_dict(new)
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE'); cached=db.execute('SELECT * FROM batches WHERE request_hash=?',(key,)).fetchone()
            if cached: return self._cached(db,cached,name,expected)
            current=self._account(db,name)
            if current['snapshot_hash']!=expected: raise ValidationError('Account compare-and-swap conflict; proposed reservations were not committed')
            ah=self.put(db,result); after=self._replace(db,current,state,'risk_reservation_batch',key)
            db.execute('INSERT INTO batches VALUES(?,?,?,?,?)',(key,name,expected,after,ah))
        return dict(request_hash=key,after_snapshot_hash=after,allocation_hash=ah,allocation=d)
