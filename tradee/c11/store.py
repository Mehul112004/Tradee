"""Atomic immutable completed simulation artifacts, including failed-evidence runs."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3

from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c08 import CandidateConfig
from tradee.c08.metadata import capture
from .engine import Simulator

APP_ID=0x54523131
KINDS=('candidate_decision','feature','lineage','lifecycle_manifest','transition','outcome_revision','sample')


class SimulationStore:
    def __init__(self,path='data/c11.sqlite3',forbidden_paths=()):
        if str(path)==':memory:' or Path(path).resolve() in {Path(p).resolve() for p in forbidden_paths}:
            raise ValidationError('C11 requires its own persistent database')
        self.path=str(path); Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connection() as db:
            tables=db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if (tables and db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID) or db.execute('PRAGMA user_version').fetchone()[0] not in (0,1):
                raise ValidationError('Not a supported C11 database')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS runs(hash TEXT PRIMARY KEY,document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reports(hash TEXT PRIMARY KEY,run_hash TEXT NOT NULL UNIQUE REFERENCES runs(hash),document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS artifacts(hash TEXT PRIMARY KEY,run_hash TEXT NOT NULL REFERENCES runs(hash),
                    sequence INTEGER NOT NULL,kind TEXT NOT NULL,scenario TEXT,document TEXT NOT NULL,UNIQUE(run_hash,sequence));
                CREATE INDEX IF NOT EXISTS artifact_kind ON artifacts(run_hash,kind,scenario,sequence);
            ''')
            db.execute(f'PRAGMA application_id={APP_ID}'); db.execute('PRAGMA user_version=1')

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path,timeout=15); db.row_factory=sqlite3.Row; db.execute('PRAGMA foreign_keys=ON')
        try:
            with db: yield db
        finally: db.close()

    @staticmethod
    def _verified(row):
        if row is None: raise ValidationError('Unknown simulation record')
        d=json.loads(row['document'])
        if fingerprint(d)!=row['hash']: raise ValidationError('Corrupt simulation record')
        return d

    def _read(self,table,h):
        if table not in ('runs','reports','artifacts'): raise ValidationError('Unknown simulation table')
        with self.connection() as db: row=db.execute(f'SELECT hash,document FROM {table} WHERE hash=?',(h,)).fetchone()
        return self._verified(row)

    def manifest(self,h): return {'run_hash':h,**self._read('runs',h)}
    def report(self,h): return {'report_hash':h,**self._read('reports',h)}
    def artifact(self,h): return {'artifact_hash':h,**self._read('artifacts',h)}

    def records(self,h,kind=None,scenario=None,after_sequence=0,limit=100):
        if (kind is not None and kind not in KINDS) or type(after_sequence) is not int or after_sequence<0 or type(limit) is not int or not 1<=limit<=1000:
            raise ValidationError('Invalid simulation artifact page')
        self.manifest(h)
        query='SELECT hash,document FROM artifacts WHERE run_hash=? AND sequence>?'; args=[h,after_sequence]
        for field,value in (('kind',kind),('scenario',scenario)):
            if value is not None: query+=' AND '+field+'=?'; args.append(value)
        query+=' ORDER BY sequence LIMIT ?'; args.append(limit+1)
        with self.connection() as db: rows=db.execute(query,args).fetchall()
        docs=[dict(artifact_hash=r['hash'],**self._verified(r)) for r in rows[:limit]]
        return dict(run_hash=h,records=docs,has_more=len(rows)>limit,next_after_sequence=docs[-1]['sequence'] if docs else after_sequence)

    def summary(self,h):
        self.manifest(h)
        with self.connection() as db:
            row=db.execute('SELECT hash,document FROM reports WHERE run_hash=?',(h,)).fetchone()
            artifacts=db.execute('SELECT hash,sequence,kind,scenario,document FROM artifacts WHERE run_hash=? ORDER BY sequence',(h,)).fetchall()
        d=self._verified(row)
        if (fingerprint([a['hash'] for a in artifacts])!=d['artifact_manifest_hash'] or
                [a['sequence'] for a in artifacts]!=list(range(1,len(artifacts)+1))): raise ValidationError('Incomplete simulation artifact inventory')
        # Validate payloads as well as indexed hashes, including cached reruns.
        for a in artifacts:
            artifact=self._verified(a)
            if artifact['payload_hash']!=fingerprint(artifact['payload']) or artifact['run_hash']!=h or artifact['sequence']!=a['sequence'] or artifact['kind']!=a['kind'] or artifact['scenario']!=a['scenario']:
                raise ValidationError('Corrupt simulation artifact envelope')
        from collections import Counter
        if dict(sorted(Counter(a['kind'] for a in artifacts).items()))!=d['artifact_inventory']:
            raise ValidationError('Simulation artifact counts do not reconcile')
        return dict(run_hash=h,report_hash=row['hash'],completed=d['completed'],ready=d['ready'],has_mature_evidence=d['has_mature_evidence'],
            metrics=d['metrics'],candidate_coverage=d['candidate_coverage'],regular_pnl=d['regular_pnl'],artifact_inventory=d['artifact_inventory'])

    def commit(self,result):
        h=result.manifest.digest; report=result.report.document(); manifest=result.manifest.document()
        if report.get('run_hash')!=h or report.get('completed') is not True or report['artifact_manifest_hash']!=fingerprint([a.digest for a in result.artifacts]):
            raise ValidationError('Invalid completed simulation result')
        from collections import Counter
        from .analysis import metrics,attribution
        if (report['dataset_hash']!=manifest['dataset']['dataset_hash'] or report['event_count']!=manifest['dataset']['event_count'] or
                report['metrics']!=metrics(report['trades']) or report['attribution']!=attribution(report['trades'])):
            raise ValidationError('Simulation report does not reconcile to pinned inputs and ledger')
        selected=Counter()
        if dict(sorted(Counter(a.document()['kind'] for a in result.artifacts).items()))!=report['artifact_inventory']:
            raise ValidationError('Simulation artifact inventory mismatch')
        for idx,a in enumerate(result.artifacts,1):
            d=a.document()
            if d['run_hash']!=h or d['sequence']!=idx or d['kind'] not in KINDS or d['payload_hash']!=fingerprint(d['payload']):
                raise ValidationError('Invalid simulation artifact')
            if d['kind']=='candidate_decision' and d['payload']['selected']: selected[d['scenario']]+=1
        names={s['name'] for s in manifest['scenarios']}
        trades=Counter(t['scenario'] for t in report['trades'])
        if set(report['candidate_coverage'])!=names or set(trades)-names or len({(t['scenario'],t['trade_id']) for t in report['trades']})!=len(report['trades']):
            raise ValidationError('Invalid simulation scenario/trade inventory')
        for name in names:
            c=report['candidate_coverage'][name]
            if c['selected']!=selected[name] or c['selected']!=trades[name] or c['event_count']!=report['event_count'] or c['input_cursor']!=report['input_cursor'] or c['input_prefix_hash']!=report['input_prefix_hash']:
                raise ValidationError('Simulation candidate/trade/source inventories differ')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT hash FROM reports WHERE run_hash=?',(h,)).fetchone()
            if old and old[0]!=result.report.digest: raise ValidationError('Conflicting completed pinned simulation')
            db.execute('INSERT OR IGNORE INTO runs VALUES(?,?)',(h,result.manifest.serialized))
            for a in result.artifacts:
                d=a.document()
                db.execute('INSERT OR IGNORE INTO artifacts VALUES(?,?,?,?,?,?)',(a.digest,h,d['sequence'],d['kind'],d['scenario'],a.serialized))
            db.execute('INSERT OR IGNORE INTO reports VALUES(?,?,?)',(result.report.digest,h,result.report.serialized))
        return self.summary(h)

    def run(self,market,dataset_hash,scenarios,fees,execution,candidates=None,funding=None,calendars=(),config=None):
        dataset=market.dataset(dataset_hash)
        candidates=candidates or CandidateConfig(execution.enabled_symbols,execution.metadata_mode,execution.max_metadata_age_ms)
        snapshots,versions=capture(market.registry,dataset,candidates)
        simulator=Simulator(dataset,scenarios,snapshots,versions,fees,execution,candidates,funding,calendars,config)
        with self.connection() as db: exists=db.execute('SELECT hash FROM reports WHERE run_hash=?',(simulator.manifest.digest,)).fetchone()
        if exists: return self.summary(simulator.manifest.digest)
        result=simulator.run(lambda:market.replay(dataset_hash))
        return self.commit(result)

    def compare(self,baseline_hash,variant_hash):
        """Matched cost/delay sensitivity, with changed coverage kept visible."""
        a=self.manifest(baseline_hash); b=self.manifest(variant_hash)
        ignored={'run_hash','fees','execution'}
        if {k:v for k,v in a.items() if k not in ignored}!={k:v for k,v in b.items() if k not in ignored}:
            raise ValidationError('Cost sensitivity requires the same dataset, hypotheses, policies, code and decision window')
        x=self.summary(baseline_hash); y=self.summary(variant_hash)
        left=self.report(x['report_hash']); right=self.report(y['report_hash'])
        one={(t['scenario'],t['candidate_id']):t for t in left['trades'] if t['ready']}
        two={(t['scenario'],t['candidate_id']):t for t in right['trades'] if t['ready']}
        common=sorted(set(one)&set(two))
        from decimal import Decimal
        from tradee.c07.math import exact
        from tradee.c06.contracts import decimal_text
        from .contracts import SimulationRecord
        with exact(): delta=sum((Decimal(two[k]['net_usdt'])-Decimal(one[k]['net_usdt']) for k in common),Decimal(0))
        d=dict(schema_version=1,baseline_run_hash=baseline_hash,variant_run_hash=variant_hash,
            baseline_report_hash=x['report_hash'],variant_report_hash=y['report_hash'],
            changed_inputs={k:dict(baseline=a[k],variant=b[k]) for k in ('fees','execution') if a[k]!=b[k]},
            paired_mature_outcomes=len(common),paired_mature_net_delta_usdt=decimal_text(delta) if common else None,
            lost_mature_outcomes=len(set(one)-set(two)),gained_mature_outcomes=len(set(two)-set(one)),
            baseline_metrics=x['metrics'],variant_metrics=y['metrics'],
            note='Variant minus baseline for matched mature candidates only; lost/gained evidence is reported separately. Descriptive sensitivity, no automated strategy selection.')
        return dict(comparison_hash=SimulationRecord.create(d).digest,**d)
