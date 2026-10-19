"""Durable trial accounting, immutable jobs, failure journals and one-way holdout access."""
from contextlib import contextmanager
import json
from pathlib import Path
import platform
import sqlite3
import time
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c03.contracts import FrozenRecord
from tradee.c06.engine import code_hash
from .contracts import Experiment
from . import engine

APP_ID=0x54523132


class ResearchStore:
    def __init__(self,path='data/c12.sqlite3',forbidden_paths=(),clock=time.time):
        if str(path)==':memory:' or Path(path).resolve() in {Path(p).resolve() for p in forbidden_paths}:
            raise ValidationError('C12 requires its own persistent database')
        self.path=str(path); self.clock=clock; Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            tables=db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if (tables and db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID) or db.execute('PRAGMA user_version').fetchone()[0] not in (0,1): raise ValidationError('Not a supported C12 database')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS families(name TEXT PRIMARY KEY,budget INTEGER NOT NULL,historical INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS experiments(hash TEXT PRIMARY KEY,family TEXT NOT NULL REFERENCES families(name),document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS artifacts(hash TEXT PRIMARY KEY,document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(experiment TEXT NOT NULL REFERENCES experiments(hash),key TEXT NOT NULL,status TEXT NOT NULL,
                    attempts INTEGER NOT NULL,artifact TEXT REFERENCES artifacts(hash),error TEXT,PRIMARY KEY(experiment,key));
                CREATE TABLE IF NOT EXISTS events(experiment TEXT NOT NULL REFERENCES experiments(hash),sequence INTEGER NOT NULL,
                    hash TEXT NOT NULL UNIQUE,document TEXT NOT NULL,PRIMARY KEY(experiment,sequence));
                CREATE TABLE IF NOT EXISTS holdouts(experiment TEXT PRIMARY KEY REFERENCES experiments(hash),start_ms INTEGER NOT NULL,end_ms INTEGER NOT NULL);
            ''')
            db.execute(f'PRAGMA application_id={APP_ID}'); db.execute('PRAGMA user_version=1')

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=15); db.row_factory=sqlite3.Row; db.execute('PRAGMA foreign_keys=ON')
        try:
            with db: yield db
        finally: db.close()

    @contextmanager
    def _lock(self):
        # Kernel lock is released after a process crash; the immutable failed/running job is retried.
        import fcntl
        with open(self.path+'.lock','a') as handle:
            try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc: raise ValidationError('C12 runner already active for this database') from exc
            try: yield
            finally: fcntl.flock(handle,fcntl.LOCK_UN)

    def _event(self,db,h,kind,payload):
        old=db.execute('SELECT sequence,hash FROM events WHERE experiment=? ORDER BY sequence DESC LIMIT 1',(h,)).fetchone()
        d=dict(experiment_hash=h,sequence=old['sequence']+1 if old else 1,previous_hash=old['hash'] if old else None,
               kind=kind,payload=payload,recorded_ms=int(self.clock()*1000))
        db.execute('INSERT INTO events VALUES(?,?,?,?)',(h,d['sequence'],fingerprint(d),FrozenRecord.create(d).serialized))

    @staticmethod
    def _audit(h,rows):
        previous=None; result=[]
        for i,row in enumerate(rows,1):
            d=json.loads(row['document'])
            if fingerprint(d)!=row['hash'] or row['sequence']!=i or d['sequence']!=i or d['previous_hash']!=previous or d['experiment_hash']!=h:
                raise ValidationError('Corrupt C12 audit chain')
            previous=row['hash']; result.append(dict(event_hash=previous,**d))
        if not result or result[0]['kind']!='registered': raise ValidationError('Missing C12 registration audit')
        return result

    def events(self,h):
        self.manifest(h)
        with self.connection() as db: rows=db.execute('SELECT sequence,hash,document FROM events WHERE experiment=? ORDER BY sequence',(h,)).fetchall()
        return self._audit(h,rows)

    def manifest(self,h):
        with self.connection() as db: r=db.execute('SELECT document FROM experiments WHERE hash=?',(h,)).fetchone()
        if r is None: raise ValidationError('Unknown research experiment')
        d=json.loads(r[0])
        if fingerprint(d)!=h: raise ValidationError('Corrupt experiment manifest')
        Experiment.from_dict(d['experiment'])
        return dict(experiment_hash=h,**d)

    def artifact(self,h):
        with self.connection() as db: r=db.execute('SELECT document FROM artifacts WHERE hash=?',(h,)).fetchone()
        if r is None: raise ValidationError('Unknown research artifact')
        d=json.loads(r[0])
        if fingerprint(d)!=h: raise ValidationError('Corrupt research artifact')
        return d

    def register(self,experiment):
        experiment=experiment if isinstance(experiment,Experiment) else Experiment.from_dict(experiment)
        record=FrozenRecord.create(dict(schema_version=1,component='C12',experiment=experiment.document(),code_hash=code_hash(),python=platform.python_version()))
        h=record.digest; a=experiment.holdout.split.test.start_ms; b=experiment.holdout.split.test.end_ms
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM experiments WHERE hash=?',(h,)).fetchone(): return self.manifest(h)
            family=db.execute('SELECT * FROM families WHERE name=?',(experiment.family,)).fetchone()
            if family and (family['budget']!=experiment.family_trial_budget or family['historical']!=experiment.historical_trials):
                raise ValidationError('Family budget and historical trial count cannot be reset')
            prior=db.execute('SELECT document FROM experiments WHERE family=?',(experiment.family,)).fetchall()
            used=experiment.historical_trials+sum(len(json.loads(r[0])['experiment']['variants']) for r in prior)
            if used+len(experiment.variants)>experiment.family_trial_budget: raise ValidationError('Cumulative family trial budget exhausted')
            # Global time reservation is deliberately conservative for this single crypto research scope.
            if db.execute('SELECT 1 FROM holdouts WHERE start_ms<? AND end_ms>?',(b,a)).fetchone():
                raise ValidationError('Holdout period already reserved or consumed; a new experiment cannot reseal it')
            for r in db.execute('SELECT document FROM experiments'):
                old=Experiment.from_dict(json.loads(r[0])['experiment'])
                old_start=old.holdout.split.test.start_ms; old_end=old.holdout.split.test.end_ms
                dev_start=min(f.split.train.start_ms for f in (*experiment.folds,experiment.holdout))
                dev_end=experiment.holdout.split.train.cutoff_ms
                old_dev_start=min(f.split.train.start_ms for f in (*old.folds,old.holdout))
                old_dev_end=old.holdout.split.train.cutoff_ms
                if max(dev_start,old_start)<min(dev_end,old_end) or max(old_dev_start,a)<min(old_dev_end,b):
                    raise ValidationError('Development history overlaps a reserved holdout; use a separate explicitly contaminated research registry')
            db.execute('INSERT OR IGNORE INTO families VALUES(?,?,?)',(experiment.family,experiment.family_trial_budget,experiment.historical_trials))
            db.execute('INSERT INTO experiments VALUES(?,?,?)',(h,experiment.family,record.serialized))
            db.execute('INSERT INTO holdouts VALUES(?,?,?)',(h,a,b))
            self._event(db,h,'registered',dict(variants=[v.name for v in experiment.variants],prior_research=experiment.prior_research,
                trials_reserved=len(experiment.variants),historical_trials=experiment.historical_trials,family_used=used+len(experiment.variants),family_budget=experiment.family_trial_budget))
        return self.manifest(h)

    def jobs(self,h):
        self.manifest(h)
        with self.connection() as db:
            # Audit and job indexes must describe the same committed snapshot.
            # Separate reads can falsely signal corruption during a concurrent commit.
            db.execute('BEGIN')
            audit=db.execute('SELECT sequence,hash,document FROM events WHERE experiment=? ORDER BY sequence',(h,)).fetchall()
            rows=db.execute('SELECT * FROM jobs WHERE experiment=? ORDER BY key',(h,)).fetchall()
        events=self._audit(h,audit)
        result=[]
        if {e['payload']['key'] for e in events if e['kind']=='job_completed'}-{r['key'] for r in rows}:
            raise ValidationError('Completed research job missing from registry')
        for r in rows:
            d=dict(r)
            matching=[e for e in events if e['kind']=='job_completed' and e['payload']['key']==d['key']]
            if d['status']=='completed':
                self.artifact(d['artifact'])
                if not matching or matching[-1]['payload']['artifact_hash']!=d['artifact']: raise ValidationError('Job artifact differs from audit journal')
            elif matching: raise ValidationError('Completed research job cannot be reset')
            result.append(d)
        return result

    def _get(self,h,key):
        rows=[r for r in self.jobs(h) if r['key']==key]
        return self.artifact(rows[0]['artifact']) if rows and rows[0]['status']=='completed' else None

    def _job(self,h,key,operation):
        old=self._get(h,key)
        if old is not None: return old
        with self.connection() as db:
            row=db.execute('SELECT attempts FROM jobs WHERE experiment=? AND key=?',(h,key)).fetchone()
            if not row and db.execute('SELECT COUNT(*) FROM jobs WHERE experiment=?',(h,)).fetchone()[0]>=1000: raise ValidationError('C12 job budget exceeded')
            attempt=row[0]+1 if row else 1
            db.execute("INSERT INTO jobs VALUES(?,?,'running',?,NULL,NULL) ON CONFLICT(experiment,key) DO UPDATE SET status='running',attempts=excluded.attempts,error=NULL",(h,key,attempt))
            self._event(db,h,'job_started',dict(key=key,attempt=attempt))
        try:
            artifact=FrozenRecord.create(operation())
            if len(artifact.serialized)>50000000: raise ValidationError('C12 artifact byte budget exceeded')
            with self.connection() as db:
                db.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?)',(artifact.digest,artifact.serialized))
                db.execute("UPDATE jobs SET status='completed',artifact=?,error=NULL WHERE experiment=? AND key=?",(artifact.digest,h,key))
                self._event(db,h,'job_completed',dict(key=key,artifact_hash=artifact.digest,attempt=attempt))
            return artifact.document()
        except Exception as exc:
            with self.connection() as db:
                db.execute("UPDATE jobs SET status='failed',error=? WHERE experiment=? AND key=?",(str(exc),h,key))
                self._event(db,h,'job_failed',dict(key=key,attempt=attempt,error_type=type(exc).__name__,error=str(exc)))
            raise

    def _runner(self,h,simulations):
        m=self.manifest(h)
        if Path(self.path).resolve()==Path(simulations.path).resolve(): raise ValidationError('C11 and C12 stores must differ')
        if m['code_hash']!=code_hash() or m['python']!=platform.python_version(): raise ValidationError('Experiment code/runtime changed; register a new counted trial')
        self.events(h)
        experiment=Experiment.from_dict(m['experiment']); pins=experiment.source_report_hashes.document(); store=self
        development_runs={r for v in experiment.variants for r in v.development_runs}
        class Sources:
            path=simulations.path
            def __getattr__(self,name): return getattr(simulations,name)
            def summary(self,run):
                if run in development_runs:
                    source=simulations.manifest(run)
                    if source['decision_window_ms'][1]>experiment.holdout.split.test.start_ms or source['dataset']['as_of_ms']>experiment.holdout.split.test.start_ms:
                        raise ValidationError('Development source contains sealed-period decisions or later revisions')
                result=simulations.summary(run)
                if pins.get(run)!=result['report_hash']:
                    raise ValidationError('C11 report differs from frozen evidence; run IDs alone are store-local')
                return result
        checked=Sources()
        # Cached jobs must not silently accept a different development database.
        for run in sorted(development_runs): checked.summary(run)
        class Jobs:
            def __init__(self): self.simulations=checked
            def __call__(self,key,operation): return store._job(h,key,operation)
        return experiment,Jobs()

    def run(self,h,simulations):
        with self._lock():
            e,jobs=self._runner(h,simulations)
            return jobs('report/development',lambda:engine.development(e,jobs))

    def open_holdout(self,h,simulations,reason):
        from .contracts import text
        text(reason)
        with self._lock():
            e,jobs=self._runner(h,simulations); development=self._get(h,'report/development')
            if development is None or not development['ready']: raise ValidationError('Passing frozen development validation required before holdout access')
            events=self.events(h); opened=[x for x in events if x['kind']=='holdout_opened']
            expected=fingerprint(development)
            if opened and opened[0]['payload']['development_hash']!=expected: raise ValidationError('Holdout already bound to another frozen development policy')
            if not opened:
                with self.connection() as db: self._event(db,h,'holdout_opened',dict(development_hash=expected,reason=reason,
                    winner=development['final_selection']['winner'],model_hash=development['final_training']['model_hash'],attestation=e.holdout_attestation,status=e.holdout_status))
            # Holdout content is checked only after the one-way access journal.
            for run in sorted({r for v in e.variants for r in v.holdout_runs}): jobs.simulations.summary(run)
            # Access stays consumed if a subsequent job fails; same frozen job can resume.
            result=jobs('report/holdout',lambda:engine.holdout(e,development,jobs))
            jobs('release/decision',lambda:self._release(h,e,development,result))
            return result

    def _release(self,h,experiment,development,holdout):
        trained=development['final_training']; winner=development['final_selection']['winner']
        variant=next(v for v in experiment.variants if v.name==winner)
        return dict(schema_version=1,component='C12',kind='frozen_research_release',experiment_hash=h,
            development_hash=fingerprint(development),holdout_hash=fingerprint(holdout),research_status=holdout['research_status'],
            ready=holdout['ready'],reasons=holdout['reasons'],variant=variant.document(),model_hash=trained['model_hash'],model=trained['model'],
            training_snapshot_hash=trained['snapshot_hash'],protocols=trained['fit']['protocols'],code_hash=self.manifest(h)['code_hash'],
            python=self.manifest(h)['python'],live_approved=False,remaining_gates=holdout['remaining_gates'])

    def release(self,h):
        self.events(h); result=self._get(h,'release/decision')
        if result is None: raise ValidationError('No completed frozen holdout decision')
        return dict(release_hash=fingerprint(result),**result)

    def decision(self,h):
        self.events(h); d=self._get(h,'report/development'); final=self._get(h,'report/holdout')
        if d is None: return dict(experiment_hash=h,status='not_evaluated',ready=False,live_approved=False)
        release=self._get(h,'release/decision') if final else None
        source=final or d; status=final['research_status'] if final else 'awaiting_holdout' if d['ready'] else 'rejected_development'
        if final and release is None: status='incomplete_release'
        result=dict(component='C12',kind='research_decision',experiment_hash=h,status=status,ready=bool(final and final['ready'] and release),
                    development_hash=fingerprint(d),holdout_hash=None if final is None else fingerprint(final),release_hash=None if release is None else fingerprint(release),reasons=source['reasons']+(['frozen_release_incomplete'] if final and release is None else []),
                    selected_variant=d['final_selection']['winner'],model_hash=None if d['final_training'] is None else d['final_training']['model_hash'],
                    live_approved=False,scope='Independent-signal research only; C13/C14/C15 and audited representative real-market evidence required')
        return dict(decision_hash=fingerprint(result),**result)

    def ledger(self,family):
        with self.connection() as db:
            f=db.execute('SELECT * FROM families WHERE name=?',(family,)).fetchone()
            rows=db.execute('SELECT hash FROM experiments WHERE family=? ORDER BY hash',(family,)).fetchall()
        if f is None: raise ValidationError('Unknown research family')
        experiments=[]
        for r in rows:
            m=self.manifest(r[0]); experiments.append(dict(experiment_hash=r[0],variants=m['experiment']['variants'],decision=self.decision(r[0])))
        used=f['historical']+sum(len(e['variants']) for e in experiments)
        return dict(family=family,trial_budget=f['budget'],historical_trials=f['historical'],used_trials=used,remaining_trials=f['budget']-used,experiments=experiments)
