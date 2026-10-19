from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from tradee.c01 import Registry,ValidationError
from tradee.c02 import MarketStore
from tradee.c08 import CandidateStore,CandidateConfig,StrategySpec
from tradee.c09 import LifecycleStore,TradeIntent,TradePolicy,LifecycleEngine
from tradee.c08.metadata import capture
from tests.c09_support import *


class LifecyclePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name); self.now=START
        self.registry=Registry(self.root/'c01.sqlite3',clock=lambda:self.now/1000); self.registry.ingest(json.dumps(metadata()[0]))
        self.market=MarketStore(self.registry,self.root/'c02.sqlite3',clock=lambda:self.now/1000)
        for index,close in enumerate(('100','100','102')):
            self.now=START+(index+1)*MINUTE; d=candle_event(index,close)['data']
            row=[d[k] for k in ('open_ms','open','high','low','close','volume','close_ms','quote_volume','trades','taker_base','taker_quote')]+['0']
            self.market.ingest_rest(json.dumps([row]),'BTCUSDT')
        self.ingest_ws('mark',DETECT+1000,'102'); self.ingest_ws('quote',DETECT+1000,'102')
        self.ingest_ws('mark',DETECT+30000,'105'); self.ingest_ws('trade',DETECT+30000,'105'); self.ingest_ws('quote',DETECT+30000,'105')
        self.ds=self.market.snapshot(['BTCUSDT'],START,START+4*MINUTE,kinds=('candle','quote','mark','trade','funding'))
        self.candidates=CandidateStore(self.root/'c08.sqlite3'); self.strategy=StrategySpec(timeframe='1m',lookback_bars=2,entry_window_ms=60000)
        run=self.candidates.run(self.market,self.ds['dataset_hash'],self.strategy,CandidateConfig())
        record=self.candidates.records(run['run_hash'],status='emitted')['records'][0]
        self.intent=TradeIntent(record['candidate'],self.candidates.feature(record['feature_snapshot_hash']),'1',TradePolicy().document())
        self.execution=ExecutionConfig(manual_delay_ms=0,max_spread_bps='25'); self.fees=FeeSchedule('0.0005','0.0002','synthetic')
        self.store=LifecycleStore(self.root/'c09.sqlite3',clock=lambda:123)

    def ingest_ws(self,kind,stamp,price):
        self.now=stamp
        if kind=='mark': raw=dict(e='markPriceUpdate',E=stamp,s='BTCUSDT',p=price,i=price,r='0.001',T=DETECT+3600000)
        elif kind=='quote': raw=dict(e='bookTicker',E=stamp,T=stamp,s='BTCUSDT',u=stamp,b=str(Decimal(price)-Decimal('0.1')),a=str(Decimal(price)+Decimal('0.1')),B='10',A='10')
        else: raw=dict(e='aggTrade',E=stamp,T=stamp,s='BTCUSDT',a=stamp,f=stamp,l=stamp,p=price,q='1',m=False)
        self.market.ingest_ws(json.dumps(raw))

    def run_case(self,**kw):
        return self.store.run(self.market,self.ds['dataset_hash'],[self.intent],self.fees,self.execution,calendars=[calendar()],**kw)

    def engine(self):
        snapshots,versions=capture(self.registry,self.ds,CandidateConfig())
        return LifecycleEngine(self.ds,[self.intent],snapshots,versions,self.fees,self.execution,calendars=[calendar()])

    def test_actual_candidates_to_c07_fills_c06_funding_and_c09_net_report(self):
        result=self.run_case(batch_size=1); self.assertTrue(result['completed']); self.assertTrue(result['ready'])
        self.assertEqual(result['trades'][0]['net_usdt'],'2.4965')
        self.assertEqual(self.run_case(batch_size=3),result)
        report=self.store.report(result['report_hash']); self.assertEqual(len(report['trades'][0]['state']['ledger']),2)
        with self.store.connection() as db: self.assertEqual({r[0] for r in db.execute('SELECT computed_at_ms FROM reports')},{123000})

    def test_sql_failure_rolls_back_ledger_report_and_checkpoint_and_resumes(self):
        a=self.engine(); inputs=list(self.market.replay(self.ds['dataset_hash'])); pending=[]
        for e in inputs[:5]: pending.extend(a.advance(e))
        self.store.commit(a,pending,a.report()); before=self.store.load_checkpoint(a.manifest.digest)
        with self.store.connection() as db:
            db.execute("CREATE TRIGGER crash BEFORE INSERT ON checkpoints BEGIN SELECT RAISE(ABORT,'injected failure'); END")
            counts={t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('reports','transitions')}
        pending=[]
        for e in inputs[5:]: pending.extend(a.advance(e))
        with self.assertRaises(sqlite3.IntegrityError): self.store.commit(a,pending,a.report())
        self.assertEqual(self.store.load_checkpoint(a.manifest.digest),before)
        with self.store.connection() as db:
            self.assertEqual({t:db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in counts},counts); db.execute('DROP TRIGGER crash')
        self.assertEqual(self.run_case()['trades'][0]['net_usdt'],'2.4965')

    def test_new_dataset_vintage_keeps_pinned_report_and_ledgers_immutable(self):
        old=self.run_case(); report=self.store.report(old['report_hash'])
        self.ingest_ws('quote',DETECT+31000,'106')
        self.assertEqual(self.run_case(),old); self.assertEqual(self.store.report(old['report_hash']),report)

    def test_corrupt_report_manifest_checkpoint_and_inventory_rejected(self):
        result=self.run_case()
        with self.store.connection() as db:
            db.execute("UPDATE reports SET document='{}'"); db.execute("UPDATE runs SET document='{}'"); db.execute("UPDATE checkpoints SET document='{}'")
        for method,key in ((self.store.report,result['report_hash']),(self.store.manifest,result['run_hash']),(self.store.load_checkpoint,result['run_hash'])):
            with self.assertRaises(ValidationError): method(key)

    def test_database_alias_unknown_artifacts_and_invalid_batch_fail_closed(self):
        for p in (self.registry.path,self.market.path,self.candidates.path,':memory:'):
            with self.assertRaises(ValidationError): LifecycleStore(p)
        for method in (self.store.report,self.store.manifest,self.store.summary):
            with self.assertRaises(ValidationError): method('missing')
        for batch in (0,True,-1):
            with self.assertRaises(ValidationError): self.run_case(batch_size=batch)

    def test_missing_transition_blocks_checkpoint_commit(self):
        a=self.engine(); pending=[]
        for e in list(self.market.replay(self.ds['dataset_hash']))[:5]: pending.extend(a.advance(e))
        with self.assertRaises(ValidationError): self.store.commit(a,[],a.report())
        self.assertIsNone(self.store.load_checkpoint(a.manifest.digest))

    def test_incomplete_input_cannot_be_marked_complete(self):
        a=self.engine(); pending=[]
        for e in list(self.market.replay(self.ds['dataset_hash']))[:5]: pending.extend(a.advance(e))
        tail,report=a.finish(a.evaluated_ms)
        with self.assertRaises(ValidationError): self.store.commit(a,pending+tail,report)

    def test_deleted_transition_is_not_silently_counted_as_complete(self):
        result=self.run_case()
        with self.store.connection() as db: db.execute('DELETE FROM transitions WHERE sequence=1')
        with self.assertRaises(ValidationError): self.store.summary(result['run_hash'])
        with self.assertRaises(ValidationError): self.run_case()
