from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from tradee.c01 import ValidationError
from tradee.c11 import SimulationStore,SimulationResult,SimulationRecord
from tests.c11_support import run,fixture


class SimulationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(); self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/'c11.sqlite3'; self.store=SimulationStore(self.path)

    def test_immutable_commit_read_and_idempotent_summary(self):
        r=run(); a=self.store.commit(r); b=SimulationStore(self.path).commit(r)
        self.assertEqual(a,b); self.assertEqual(self.store.report(a['report_hash'])['trades'][0]['net_usdt'],'2.4965')
        self.assertEqual(self.store.manifest(a['run_hash'])['component'],'C11')
        self.assertEqual(self.store.artifact(r.artifacts[0].digest)['payload_hash'],r.artifacts[0].document()['payload_hash'])

    def test_every_artifact_is_retrievable_with_stable_pagination(self):
        r=run(); self.store.commit(r); cursor=0; rows=[]
        while True:
            page=self.store.records(r.manifest.digest,after_sequence=cursor,limit=7); rows+=page['records']; cursor=page['next_after_sequence']
            if not page['has_more']: break
        self.assertEqual([a['artifact_hash'] for a in rows],[a.digest for a in r.artifacts])
        for kind in ('candidate_decision','feature','lineage','transition','outcome_revision','sample'):
            self.assertTrue(self.store.records(r.manifest.digest,kind=kind,scenario='range')['records'])
        for kw in ({'limit':0},{'limit':True},{'after_sequence':-1},{'kind':'bad'}):
            with self.assertRaises(ValidationError): self.store.records(r.manifest.digest,**kw)

    def test_failure_rolls_back_all_artifacts_and_new_process_style_retry(self):
        r=run()
        with self.store.connection() as db: db.execute("CREATE TRIGGER fail BEFORE INSERT ON reports BEGIN SELECT RAISE(ABORT,'injected publication failure'); END")
        with self.assertRaises(sqlite3.IntegrityError): self.store.commit(r)
        with self.store.connection() as db:
            for table in ('runs','reports','artifacts'): self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)
            db.execute('DROP TRIGGER fail')
        self.assertTrue(SimulationStore(self.path).commit(run())['ready'])

    def test_corrupt_and_deleted_artifacts_are_detected_on_cached_reads(self):
        r=run(); self.store.commit(r)
        with self.store.connection() as db: db.execute("UPDATE artifacts SET document='{}' WHERE sequence=1")
        with self.assertRaises(ValidationError): self.store.summary(r.manifest.digest)
        with self.store.connection() as db: db.execute('DELETE FROM artifacts WHERE sequence=1')
        with self.assertRaises(ValidationError): self.store.summary(r.manifest.digest)

    def test_corrupt_report_manifest_and_wrong_database_are_rejected(self):
        r=run(); self.store.commit(r)
        with self.store.connection() as db: db.execute("UPDATE reports SET document='{}'")
        with self.assertRaises(ValidationError): self.store.summary(r.manifest.digest)
        with self.store.connection() as db: db.execute("UPDATE runs SET document='{}'")
        with self.assertRaises(ValidationError): self.store.manifest(r.manifest.digest)
        path=Path(self.folder.name)/'other.sqlite3'
        db=sqlite3.connect(path)
        db.execute('CREATE TABLE alien(x)'); db.commit(); db.close()
        with self.assertRaises(ValidationError): SimulationStore(path)
        for p in (':memory:',str(self.path)):
            with self.assertRaises(ValidationError): SimulationStore(p,forbidden_paths=[self.path])

    def test_incomplete_or_conflicting_completed_result_rejected(self):
        r=run()
        with self.assertRaises(ValidationError): self.store.commit(SimulationResult(r.manifest,r.report,r.artifacts[:-1]))
        self.store.commit(r); doc=r.report.document(); doc['ready']=False
        with self.assertRaises(ValidationError): self.store.commit(SimulationResult(r.manifest,SimulationRecord.create(doc),r.artifacts))

    def test_cost_sensitivity_pairs_candidates_and_reports_lost_coverage(self):
        a=run(); self.store.commit(a)
        s,events=fixture(); s.fees=replace(s.fees,taker_rate='0.001')
        # Rebuild: all assumptions must enter the manifest, never mutate a live run.
        from tradee.c11 import Simulator
        b=Simulator(s.dataset,s.scenarios,s.snapshots,s.versions,s.fees,s.execution,calendars=s.calendars).run(lambda:iter(events))
        self.store.commit(b); d=self.store.compare(a.manifest.digest,b.manifest.digest)
        self.assertEqual(d['paired_mature_outcomes'],1); self.assertEqual(d['paired_mature_net_delta_usdt'],'-0.1035')
        self.assertEqual(set(d['changed_inputs']),{'fees'})
        c=run(execution=replace(s.execution,manual_delay_ms=120000)); self.store.commit(c)
        d=self.store.compare(a.manifest.digest,c.manifest.digest)
        self.assertEqual(d['paired_mature_outcomes'],0); self.assertIsNone(d['paired_mature_net_delta_usdt']); self.assertEqual(d['lost_mature_outcomes'],1)

    def test_sensitivity_cannot_compare_different_hypotheses_or_windows(self):
        from tradee.c11 import SimulationConfig
        a=run(); b=run(config=SimulationConfig(decision_start_ms=1788220980001))
        self.store.commit(a); self.store.commit(b)
        with self.assertRaises(ValidationError): self.store.compare(a.manifest.digest,b.manifest.digest)
