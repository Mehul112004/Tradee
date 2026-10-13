import json
import sqlite3
from tradee.c01 import ValidationError
from tradee.c06 import FundingStore, FundingEngine, PositionTimeline, SettlementCalendar, FundingConfig
from tests.c02_support import DataCase, START

HOUR=3600000


class FundingPersistenceTests(DataCase):
    def prepared(self):
        self.now=START+7*HOUR
        rows=[dict(symbol='BTCUSDT',fundingTime=START+offset*HOUR,fundingRate=rate,markPrice=price)
              for offset,rate,price in ((1,'0.001','100'),(2,'-0.002','120'),(4,'0','110'))]
        self.store.ingest_rest(json.dumps(rows),'BTCUSDT','funding')
        d=self.store.snapshot(['BTCUSDT'],START,START+6*HOUR,kinds=('funding',))
        ident=self.store.binding('BTCUSDT')['instrument_id']
        p=PositionTimeline('long',ident,'BTCUSDT','long',[dict(at_ms=START+60000,quantity='2'),
            dict(at_ms=START+2*HOUR-60000,quantity='1'),dict(at_ms=START+4*HOUR-60000,quantity='0')])
        c=SettlementCalendar(ident,'BTCUSDT',START,START+6*HOUR,[START+HOUR,START+2*HOUR,START+4*HOUR],'test:explicit-calendar')
        return d,[p],[c],FundingConfig(),FundingStore(self.root/'c06.sqlite3',clock=lambda:123)

    def test_actual_c02_replay_resume_and_idempotency(self):
        d,p,c,config,s=self.prepared(); a=FundingEngine(d,p,c,config)
        events=list(self.store.replay(d['dataset_hash'])); a.push(events[0]); s.commit(a,a.report(events[0]['available_ms']))
        result=s.run(self.store,d['dataset_hash'],p,c,config,batch_size=1)
        self.assertTrue(result['ready']); self.assertEqual(result['positions'][0]['total_cashflow_usdt'],'0.04')
        self.assertEqual(s.run(self.store,d['dataset_hash'],p,c,config,batch_size=1),result)
        b=FundingEngine(d,p,c,config)
        for e in events: b.push(e)
        self.assertEqual(s.report(result['report_hash'])['input_prefix_hash'],b.prefix_hash)
        with s.connection() as db:
            self.assertEqual({r[0] for r in db.execute('SELECT computed_at_ms FROM reports')},{123000})

    def test_injected_write_failure_rolls_back_reports_and_checkpoint(self):
        d,p,c,config,s=self.prepared(); a=FundingEngine(d,p,c,config)
        events=list(self.store.replay(d['dataset_hash'])); a.push(events[0]); s.commit(a,a.report(events[0]['available_ms']))
        before=s.load_checkpoint(a.manifest.digest)
        with s.connection() as db:
            db.execute("CREATE TRIGGER fail_checkpoint BEFORE INSERT ON checkpoints BEGIN SELECT RAISE(ABORT,'injected crash'); END")
        a.push(events[1]); report=a.report(events[1]['available_ms'])
        with self.assertRaises(sqlite3.IntegrityError): s.commit(a,report)
        self.assertEqual(s.summary(a.manifest.digest)['reports'],1)
        self.assertEqual(s.load_checkpoint(a.manifest.digest),before)
        with s.connection() as db: db.execute('DROP TRIGGER fail_checkpoint')
        s.commit(a,report); self.assertEqual(s.summary(a.manifest.digest)['reports'],2)

    def test_corruption_is_detected(self):
        d,p,c,config,s=self.prepared(); result=s.run(self.store,d['dataset_hash'],p,c,config)
        with s.connection() as db:
            db.execute("UPDATE checkpoints SET document='{}'")
            db.execute("UPDATE reports SET document='{}'")
        with self.assertRaises(ValidationError): s.load_checkpoint(result['run_hash'])
        with self.assertRaises(ValidationError): s.report(result['report_hash'])

    def test_alias_and_wrong_schema_are_rejected(self):
        d,p,c,config,s=self.prepared()
        for path in (self.registry.path,self.store.path):
            with self.assertRaises(ValidationError): FundingStore(path)
        with self.assertRaises(ValidationError): FundingStore(self.root/'new.sqlite3',forbidden_paths=[self.root/'new.sqlite3'])

    def test_prior_decision_artifact_excludes_later_settlement_evidence(self):
        d,p,c,config,s=self.prepared()
        result=s.run(self.store,d['dataset_hash'],p,c,config,decision_ms=START+2*HOUR)
        self.assertFalse(result['ready']); doc=s.report(result['report_hash'])
        self.assertEqual(doc['positions'][0]['known_cashflow_subtotal_usdt'],'0')
        self.assertEqual([e['status'] for e in doc['positions'][0]['cashflows']],['missing_settlement','missing_settlement'])

    def test_immutable_dataset_does_not_change_after_correction(self):
        d,p,c,config,s=self.prepared(); old=s.run(self.store,d['dataset_hash'],p,c,config)
        self.now+=1
        self.store.ingest_rest(json.dumps([dict(symbol='BTCUSDT',fundingTime=START+HOUR,fundingRate='0.0015',markPrice='100')]),'BTCUSDT','funding')
        new_d=self.store.snapshot(['BTCUSDT'],START,START+6*HOUR,kinds=('funding',))
        newer=s.run(self.store,new_d['dataset_hash'],p,c,config)
        self.assertEqual(newer['positions'][0]['total_cashflow_usdt'],'-0.06')
        self.assertEqual(s.run(self.store,d['dataset_hash'],p,c,config),old)
        self.assertNotEqual(newer['run_hash'],old['run_hash'])

    def test_unsupported_position_metadata_is_rejected(self):
        d,p,c,config,s=self.prepared(); doc=p[0].document(); doc['instrument_id']+='-unknown'
        with self.assertRaises(ValidationError): s.run(self.store,d['dataset_hash'],[doc],c,config)

    def test_persisted_cursor_cannot_go_backward_or_conflict(self):
        d,p,c,config,s=self.prepared(); a=FundingEngine(d,p,c,config)
        events=list(self.store.replay(d['dataset_hash'])); a.push(events[0]); first=a.checkpoint()
        s.commit(a,a.report(events[0]['available_ms']))
        a.push(events[1]); s.commit(a,a.report(events[1]['available_ms']))
        old=FundingEngine.restore(d,p,c,config,a.decision_ms,first)
        with self.assertRaises(ValidationError): s.commit(old,old.report(events[0]['available_ms']))
        a.prefix_hash='f'*64
        with self.assertRaises(ValidationError): s.commit(a,a.report(events[1]['available_ms']))

    def test_unknown_hashes_and_invalid_batch_sizes_fail(self):
        d,p,c,config,s=self.prepared()
        for method in (s.manifest,s.report,s.summary):
            with self.assertRaises(ValidationError): method('missing')
        for batch in (True,0,-1):
            with self.assertRaises(ValidationError): s.run(self.store,d['dataset_hash'],p,c,config,batch_size=batch)
