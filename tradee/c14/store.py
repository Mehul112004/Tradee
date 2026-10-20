"""Atomic paper state + signal/outbox publication and hash-linked operational audit."""
from contextlib import contextmanager
from collections import Counter
import json
from pathlib import Path
import sqlite3
import time
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c02.domain import integer
from tradee.c03.contracts import FrozenRecord
from tradee.c13 import AccountSnapshot
from .contracts import SessionSpec

APP_ID=0x54523134


class SignalStore:
    def __init__(self,path='data/c14.sqlite3',forbidden_paths=()):
        if str(path)==':memory:' or Path(path).resolve() in {Path(p).resolve() for p in forbidden_paths}: raise ValidationError('C14 requires a separate persistent database')
        self.path=str(path); Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            tables=db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if (tables and db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID) or db.execute('PRAGMA user_version').fetchone()[0] not in (0,1): raise ValidationError('Not a supported C14 database')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS artifacts(hash TEXT PRIMARY KEY,document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(name TEXT PRIMARY KEY,manifest_hash TEXT REFERENCES artifacts(hash),revision INTEGER NOT NULL,cycle_hash TEXT REFERENCES artifacts(hash),paused INTEGER NOT NULL DEFAULT 0,fault TEXT,control_ms INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS cycles(hash TEXT PRIMARY KEY REFERENCES artifacts(hash),session TEXT REFERENCES sessions(name),as_of_ms INTEGER NOT NULL,processing_ms INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS signals(id TEXT PRIMARY KEY,session TEXT REFERENCES sessions(name),document_hash TEXT REFERENCES artifacts(hash));
                CREATE TABLE IF NOT EXISTS outbox(signal_id TEXT PRIMARY KEY REFERENCES signals(id),state TEXT NOT NULL,attempts INTEGER NOT NULL,next_ms INTEGER NOT NULL,expires_ms INTEGER NOT NULL,attempt_token TEXT,lease_until_ms INTEGER,message_id INTEGER,guard_hash TEXT REFERENCES artifacts(hash),text_hash TEXT REFERENCES artifacts(hash),reason TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS audit(session TEXT REFERENCES sessions(name),sequence INTEGER,event_hash TEXT UNIQUE REFERENCES artifacts(hash),PRIMARY KEY(session,sequence));
                CREATE TABLE IF NOT EXISTS throttle(key TEXT PRIMARY KEY,next_ms INTEGER NOT NULL);
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
        row=db.execute('SELECT document FROM artifacts WHERE hash=?',(h,)).fetchone()
        if row is None: raise ValidationError('Unknown C14 artifact')
        d=json.loads(row[0])
        if fingerprint(d)!=h: raise ValidationError('Corrupt C14 artifact')
        return d
    def artifact(self,h):
        with self.connection() as db: return self.read(db,h)
    def _event(self,db,name,kind,payload,when):
        integer(when,'audit time'); row=db.execute('SELECT sequence,event_hash FROM audit WHERE session=? ORDER BY sequence DESC LIMIT 1',(name,)).fetchone()
        d=dict(session=name,sequence=1 if row is None else row[0]+1,previous_hash=None if row is None else row[1],kind=kind,at_ms=when,recorded_ms=int(time.time()*1000),payload=payload)
        h=self.put(db,d); db.execute('INSERT INTO audit VALUES(?,?,?)',(name,d['sequence'],h))
    def _events(self,db,name):
        previous=None; result=[]
        for idx,row in enumerate(db.execute('SELECT sequence,event_hash FROM audit WHERE session=? ORDER BY sequence',(name,)).fetchall(),1):
            d=self.read(db,row[1])
            if row[0]!=idx or d['sequence']!=idx or d['previous_hash']!=previous or d['session']!=name: raise ValidationError('Corrupt C14 audit journal')
            result.append(dict(event_hash=row[1],**d)); previous=row[1]
        if not result or result[0]['kind']!='deployment_created': raise ValidationError('Missing C14 deployment journal')
        return result
    def _session(self,db,name):
        row=db.execute('SELECT * FROM sessions WHERE name=?',(name,)).fetchone()
        if row is None: raise ValidationError('Unknown C14 session')
        d=dict(row); m=self.read(db,d.pop('manifest_hash')); cycle=None if d['cycle_hash'] is None else self.read(db,d['cycle_hash']); events=self._events(db,name)
        if m.get('kind')!='paper_deployment' or m['spec']['name']!=name: raise ValidationError('Invalid C14 deployment')
        SessionSpec.from_dict(m['spec'])
        revisions=[e['payload']['revision'] for e in events if 'revision' in e['payload']]
        if not revisions or revisions[-1]!=d['revision']: raise ValidationError('C14 revision differs from journal')
        publications=[e for e in events if e['kind']=='cycle_published']
        if (bool(publications)!=(cycle is not None)) or (publications and publications[-1]['payload']['cycle_hash']!=d['cycle_hash']): raise ValidationError('C14 paper head differs from journal')
        controls=[e for e in events if e['kind'] in ('paused','resumed')]
        if bool(d['paused'])!=(bool(controls) and controls[-1]['kind']=='paused'): raise ValidationError('C14 pause index differs from journal')
        faults=[e['payload']['fault'] for e in events if 'fault' in e['payload']]
        if not faults or faults[-1]!=d['fault']: raise ValidationError('C14 fault index differs from journal')
        return dict(d,deployment_hash=fingerprint(m),manifest=m,cycle=cycle)
    def session(self,name):
        with self.connection() as db: db.execute('BEGIN'); return self._session(db,name)
    def events(self,name):
        with self.connection() as db: db.execute('BEGIN'); self._session(db,name); return self._events(db,name)
    def create(self,manifest):
        record=manifest if isinstance(manifest,FrozenRecord) else FrozenRecord.create(manifest); m=record.document()
        if m.get('kind')!='paper_deployment' or m.get('live_approved') is not False or m.get('promotion_authorized') is not False: raise ValidationError('Verified paper deployment required')
        spec=SessionSpec.from_dict(m['spec'])
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE'); old=db.execute('SELECT manifest_hash FROM sessions WHERE name=?',(spec.name,)).fetchone()
            if old:
                if old[0]!=record.digest: raise ValidationError('C14 deployment name already frozen')
            else:
                self.put(db,record); db.execute('INSERT INTO sessions VALUES(?,?,0,NULL,0,NULL,?)',(spec.name,record.digest,spec.start_ms))
                self._event(db,spec.name,'deployment_created',dict(manifest_hash=record.digest,revision=0,fault=None),spec.start_ms)
        return self.session(spec.name)
    def delivery_event(self,db,name,sid,kind,when,**extra):
        row=db.execute('SELECT * FROM outbox WHERE signal_id=?',(sid,)).fetchone()
        self._event(db,name,kind,dict(delivery=dict(row),**extra),when)
    def outbox_row(self,db,name,sid):
        row=db.execute('SELECT * FROM outbox WHERE signal_id=?',(sid,)).fetchone()
        if row is None: return None
        receipts=[e['payload']['delivery'] for e in self._events(db,name) if e['payload'].get('delivery',{}).get('signal_id')==sid]
        if not receipts or dict(row)!=receipts[-1]: raise ValidationError('C14 delivery index differs from audit')
        return row
    def signal(self,sid):
        with self.connection() as db:
            db.execute('BEGIN'); row=db.execute('SELECT * FROM signals WHERE id=?',(sid,)).fetchone()
            if row is None: raise ValidationError('Unknown C14 signal')
            head=self._session(db,row['session']); d=self.read(db,row['document_hash']); out=self.outbox_row(db,row['session'],sid)
            expected=next((s for s in head['cycle']['signals'] if s['signal_id']==sid),None) if head['cycle'] else None
            if expected is None or fingerprint(expected)!=row['document_hash']: raise ValidationError('C14 signal index differs from current cycle')
            if d['signal_id']!=sid: raise ValidationError('Corrupt C14 signal identity')
            return dict(signal=d,document_hash=row['document_hash'],delivery=None if out is None else dict(out))
    def signals(self,name):
        with self.connection() as db:
            db.execute('BEGIN'); head=self._session(db,name); rows=db.execute('SELECT id,document_hash FROM signals WHERE session=? ORDER BY id',(name,)).fetchall()
            expected={} if head['cycle'] is None else {s['signal_id']:fingerprint(s) for s in head['cycle']['signals']}
            if {r['id']:r['document_hash'] for r in rows}!=expected: raise ValidationError('C14 signal inventory differs from current cycle')
            result=[]
            for r in rows:
                d=self.read(db,r['document_hash'])
                if d['signal_id']!=r['id']: raise ValidationError('Corrupt C14 signal index')
                out=self.outbox_row(db,name,r['id']); result.append(dict(signal=d,delivery=None if out is None else dict(out)))
            return result
    def publish(self,name,expected,cycle,processing_ms):
        record=cycle if isinstance(cycle,FrozenRecord) else FrozenRecord.create(cycle); c=record.document(); integer(processing_ms,'processing latency')
        AccountSnapshot.from_dict(c['paper_account'])
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE'); head=self._session(db,name); spec=SessionSpec.from_dict(head['manifest']['spec']); cfg=spec.runtime
            if len(record.serialized.encode())>cfg.max_cycle_bytes: raise ValidationError('C14 cycle byte budget exceeded')
            if db.execute('SELECT 1 FROM cycles WHERE hash=? AND session=?',(record.digest,name)).fetchone(): return self._session(db,name)
            if head['revision']!=expected: raise ValidationError('C14 compare-and-swap conflict; recompute the cycle')
            if c['deployment_hash']!=head['deployment_hash'] or c.get('kind')!='paper_cycle' or c['live_approved'] is not False: raise ValidationError('Cycle/deployment mismatch')
            old=head['cycle']
            if old and c['as_of_ms']<old['as_of_ms']: raise ValidationError('C14 source clock moved backward')
            if db.execute('SELECT COUNT(*) FROM cycles WHERE session=?',(name,)).fetchone()[0]>=cfg.max_cycles: raise ValidationError('C14 cycle count budget exceeded')
            if len(c['signals'])>cfg.max_candidates or len({s['signal_id'] for s in c['signals']})!=len(c['signals']): raise ValidationError('C14 distinct signal budget exceeded')
            incoming={s['signal_id']:s for s in c['signals']}
            for row in db.execute('SELECT id,document_hash FROM signals WHERE session=?',(name,)).fetchall():
                prior=self.read(db,row['document_hash']); new=incoming.get(row['id'])
                if new is None or (prior['entry_ms'] is not None and (new['entry_ms']!=prior['entry_ms'] or new['decision']['status']!='admitted' or
                     any(new['decision']['execution']['fill'][k]!=prior['decision']['execution']['fill'][k] for k in ('price','quantity','fee_usdt','source_event_id','execution_as_of_ms')))):
                    raise ValidationError('Historical paper admission changed; stop and reconcile')
            self.put(db,record); db.execute('INSERT INTO cycles VALUES(?,?,?,?)',(record.digest,name,c['as_of_ms'],processing_ms))
            revision=head['revision']+1; healthy=c['health']['ready'] and processing_ms<cfg.max_cycle_age_ms
            for sid,s in incoming.items():
                prior=db.execute('SELECT document_hash FROM signals WHERE id=?',(sid,)).fetchone(); previous=None if prior is None else self.read(db,prior[0]); sh=self.put(db,s)
                db.execute('INSERT INTO signals VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET document_hash=excluded.document_hash',(sid,name,sh))
                first_entry=s['entry_ms'] is not None and (previous is None or previous['entry_ms'] is None)
                if first_entry and cfg.mode=='paper_test':
                    valid=not head['paused'] and healthy and s['phase']=='paper_open' and s['thesis_valid'] and c['as_of_ms']<s['expires_ms']
                    reason='awaiting_fresh_send_check' if valid else 'paused' if head['paused'] else 'stale_or_ineligible_paper_notice'
                    db.execute('INSERT INTO outbox(signal_id,state,attempts,next_ms,expires_ms,reason) VALUES(?,?,0,?,?,?)',(sid,'pending' if valid else 'suppressed',c['as_of_ms'],s['expires_ms'],reason))
                    self.delivery_event(db,name,sid,'outbox_created',c['as_of_ms'])
                out=db.execute('SELECT state FROM outbox WHERE signal_id=?',(sid,)).fetchone()
                if out and out[0] in ('pending','retry_wait') and (head['paused'] or not healthy or s['phase']!='paper_open' or not s['thesis_valid'] or c['as_of_ms']>=s['expires_ms']):
                    state='expired' if c['as_of_ms']>=s['expires_ms'] else 'suppressed'
                    db.execute('UPDATE outbox SET state=?,reason=? WHERE signal_id=?',(state,'notice_no_longer_eligible',sid))
                    self.delivery_event(db,name,sid,'outbox_suppressed',c['as_of_ms'])
            fault=None if healthy else 'paper_feed_or_risk_unready' if not c['health']['ready'] else 'processing_latency_exceeded'
            db.execute('UPDATE sessions SET cycle_hash=?,revision=?,fault=? WHERE name=?',(record.digest,revision,fault,name))
            self._event(db,name,'cycle_published',dict(cycle_hash=record.digest,revision=revision,processing_ms=processing_ms,healthy=healthy,fault=fault,signals=len(incoming)),c['as_of_ms'])
        return self.session(name)
    def evidence(self,name):
        """One consistent, verified operational snapshot for forward monitoring."""
        with self.connection() as db:
            db.execute('BEGIN'); head=self._session(db,name); events=self._events(db,name)
            cycles=[dict(cycle_hash=e['payload']['cycle_hash'],processing_ms=e['payload']['processing_ms'],
                         cycle=self.read(db,e['payload']['cycle_hash'])) for e in events if e['kind']=='cycle_published']
            indexed=db.execute('SELECT id,document_hash FROM signals WHERE session=? ORDER BY id',(name,)).fetchall()
            expected={} if head['cycle'] is None else {s['signal_id']:fingerprint(s) for s in head['cycle']['signals']}
            if {r['id']:r['document_hash'] for r in indexed}!=expected: raise ValidationError('C14 signal inventory differs from current cycle')
            deliveries=[]
            for r in indexed:
                out=self.outbox_row(db,name,r['id'])
                if out is not None: deliveries.append(dict(out))
            audited={}
            for e in events:
                d=e['payload'].get('delivery')
                if d is not None: audited[d['signal_id']]=d
            if {d['signal_id']:d for d in deliveries}!=audited: raise ValidationError('C14 delivery inventory differs from audit')
            return dict(head=head,events=events,cycles=cycles,deliveries=deliveries)

    def pause(self,name,paused,reason,when,expected_revision=None,expected_event_hash=None):
        if type(paused) is not bool: raise ValidationError('Explicit pause state required')
        from tradee.c13.contracts import text
        text(reason); integer(when,'pause clock')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE'); h=self._session(db,name)
            if expected_revision is not None and h['revision']!=expected_revision: raise ValidationError('C14 control compare-and-swap conflict; observe again')
            if expected_event_hash is not None and self._events(db,name)[-1]['event_hash']!=expected_event_hash: raise ValidationError('C14 control audit compare-and-swap conflict; observe again')
            if when<h['control_ms'] or (h['cycle'] and when<h['cycle']['as_of_ms']): raise ValidationError('Control clock moved backward')
            revision=h['revision']+1
            db.execute('UPDATE sessions SET paused=?,revision=?,control_ms=? WHERE name=?',(int(paused),revision,when,name))
            if paused:
                for r in db.execute("SELECT signal_id FROM outbox WHERE state IN ('pending','retry_wait') AND signal_id IN (SELECT id FROM signals WHERE session=?)",(name,)).fetchall():
                    self.outbox_row(db,name,r[0]); db.execute("UPDATE outbox SET state='suppressed',reason='operator_pause' WHERE signal_id=?",(r[0],))
                    self.delivery_event(db,name,r[0],'outbox_suppressed',when)
            self._event(db,name,'paused' if paused else 'resumed',dict(reason=reason,revision=revision),when)
        return self.session(name)
    def fault(self,name,reason,when):
        # Fixed internal reason code only; never persist provider exception strings.
        if reason not in ('pipeline_failed','session_tail_elapsed'): raise ValidationError('Redacted operational fault required')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE'); h=self._session(db,name); revision=h['revision']+1
            db.execute('UPDATE sessions SET fault=?,revision=? WHERE name=?',(reason,revision,name))
            for r in db.execute("SELECT signal_id FROM outbox WHERE state IN ('pending','retry_wait') AND signal_id IN (SELECT id FROM signals WHERE session=?)",(name,)).fetchall():
                self.outbox_row(db,name,r[0]); db.execute("UPDATE outbox SET state='suppressed',reason=? WHERE signal_id=?",(reason,r[0]))
                self.delivery_event(db,name,r[0],'outbox_suppressed',when)
            self._event(db,name,'operational_fault',dict(reason=reason,revision=revision,fault=reason),when)
        return self.session(name)
    def status(self,name,when):
        h=self.session(name); cfg=SessionSpec.from_dict(h['manifest']['spec']).runtime; c=h['cycle']; counts=Counter(s['delivery']['state'] for s in self.signals(name) if s['delivery'])
        reasons=[]
        if h['paused']: reasons.append('operator_pause')
        if h['fault']: reasons.append(h['fault'])
        if c is None or when<c['as_of_ms'] or when-c['as_of_ms']>=cfg.max_cycle_age_ms: reasons.append('no_fresh_cycle')
        if counts['ambiguous']: reasons.append('delivery_reconciliation_required')
        return dict(component='C14',session=name,deployment_hash=h['deployment_hash'],revision=h['revision'],mode=cfg.mode,ready=not reasons,reasons=reasons,
            cycle_hash=h['cycle_hash'],last_cutoff_ms=None if c is None else c['as_of_ms'],outbox=dict(counts),paper_account=None if c is None else c['paper_account'],live_approved=False)
