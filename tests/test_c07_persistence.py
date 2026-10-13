import json
import sqlite3
import tempfile
from pathlib import Path
import unittest

from tradee.c01 import Registry, Policy, ValidationError
from tradee.c02 import MarketStore
from tradee.c07 import ExecutionStore, ExecutionEngine, ExecutionConfig, ExecutionIntent, FeeSchedule
from tests.c07_support import START, metadata


class ExecutionPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.now=START
        self.registry=Registry(self.root/'c01.sqlite3',clock=lambda:self.now/1000)
        self.registry.ingest(json.dumps(metadata()[0]))
        self.market=MarketStore(self.registry,self.root/'c02.sqlite3',clock=lambda:self.now/1000)
        self.now+=1000
        self.market.ingest_ws(json.dumps(dict(e='markPriceUpdate',E=self.now,s='BTCUSDT',p='100',i='100',r='0.001',T=START+3600000)))
        self.market.ingest_ws(json.dumps(dict(e='bookTicker',E=self.now,T=self.now,s='BTCUSDT',u=1,b='99.9',a='100.1',B='10',A='10')))
        self.dataset=self.market.snapshot(['BTCUSDT'],START,START+600000,kinds=('quote','mark'))
        ident=self.market.binding('BTCUSDT')['instrument_id']
        self.intents=[ExecutionIntent('entry',ident,'BTCUSDT','buy','1',START,START+60000,'100',stop_price='99',holding_until_ms=START+3660000)]
        self.fees=FeeSchedule('0.0005','0.0002','test-assumption'); self.config=ExecutionConfig(manual_delay_ms=0)
        self.store=ExecutionStore(self.root/'c07.sqlite3',clock=lambda:123)

    def run_scenario(self,**kw):
        return self.store.run(self.market,self.dataset['dataset_hash'],self.intents,self.fees,self.config,**kw)

    def engine(self):
        u=self.registry.universe(Policy(self.config.enabled_symbols),self.now)
        v={d['version_hash']:self.registry.version(d['version_hash'])['spec'] for d in u['decisions'] if d['version_hash']}
        return ExecutionEngine(self.dataset,self.intents,u,v,self.fees,self.config)

    def test_actual_replay_resume_and_report_parity(self):
        a=self.engine(); events=list(self.market.replay(self.dataset['dataset_hash']))
        a.push(events[0]); self.store.commit(a,a.report(events[0]['available_ms']))
        result=self.run_scenario(batch_size=1); self.assertTrue(result['ready'])
        self.assertEqual(self.run_scenario(batch_size=1),result)
        a.push(events[1]); expected=a.report().document()
        saved=self.store.report(result['report_hash']); saved.pop('report_hash')
        self.assertEqual(saved,expected)
        self.assertEqual(saved['estimates'][0]['costs']['execution_plus_fee_cost_usdt'],'0.2501')
        with self.store.connection() as db:
            self.assertEqual({r[0] for r in db.execute('SELECT computed_at_ms FROM reports')},{123000})

    def test_failed_checkpoint_write_is_atomic(self):
        a=self.engine(); events=list(self.market.replay(self.dataset['dataset_hash']))
        a.push(events[0]); self.store.commit(a,a.report()); before=self.store.load_checkpoint(a.manifest.digest)
        with self.store.connection() as db:
            db.execute("CREATE TRIGGER fail_checkpoint BEFORE INSERT ON checkpoints BEGIN SELECT RAISE(ABORT,'injected crash'); END")
        a.push(events[1])
        with self.assertRaises(sqlite3.IntegrityError): self.store.commit(a,a.report())
        self.assertEqual(self.store.load_checkpoint(a.manifest.digest),before)
        self.assertEqual(self.store.summary(a.manifest.digest)['reports'],1)
        with self.store.connection() as db: db.execute('DROP TRIGGER fail_checkpoint')
        self.assertTrue(self.run_scenario()['ready'])

    def test_later_quote_and_metadata_do_not_rewrite_pinned_report(self):
        old=self.run_scenario(); saved=self.store.report(old['report_hash'])
        self.now+=1
        self.market.ingest_ws(json.dumps(dict(e='bookTicker',E=self.now,T=self.now,s='BTCUSDT',u=2,b='100',a='100.2',B='10',A='10')))
        newer=self.market.snapshot(['BTCUSDT'],START,START+600000,kinds=('quote','mark'))
        new=self.store.run(self.market,newer['dataset_hash'],self.intents,self.fees,self.config)
        self.assertEqual(new['estimates'][0]['fill']['price'],'100.3')
        self.registry.ingest(json.dumps(metadata()[0]))
        self.assertEqual(self.run_scenario(),old); self.assertEqual(self.store.report(old['report_hash']),saved)

    def test_previous_decision_excludes_quote_and_mark(self):
        result=self.run_scenario(decision_ms=START)
        self.assertFalse(result['ready']); self.assertIsNone(result['estimates'][0]['fill'])
        self.assertIn('missing_quote',result['estimates'][0]['reasons'])

    def test_changed_fee_or_config_creates_new_run(self):
        old=self.run_scenario()
        newer=self.store.run(self.market,self.dataset['dataset_hash'],self.intents,FeeSchedule('0.001','0','other'),self.config)
        self.assertNotEqual(old['run_hash'],newer['run_hash']); self.assertEqual(newer['estimates'][0]['fill']['fee_usdt'],'0.1002')

    def test_fractional_second_metadata_budget_is_not_truncated(self):
        config=ExecutionConfig(manual_delay_ms=0,max_metadata_age_ms=1500)
        result=self.store.run(self.market,self.dataset['dataset_hash'],self.intents,self.fees,config)
        self.assertTrue(result['ready'])

    def test_corruption_is_detected_in_every_stored_artifact(self):
        result=self.run_scenario()
        with self.store.connection() as db:
            db.execute("UPDATE checkpoints SET document='{}'"); db.execute("UPDATE reports SET document='{}'"); db.execute("UPDATE runs SET document='{}'")
        for method,key in ((self.store.load_checkpoint,'run_hash'),(self.store.report,'report_hash'),(self.store.manifest,'run_hash')):
            with self.assertRaises(ValidationError): method(result[key])

    def test_database_aliases_unknown_hash_and_bad_batch_fail(self):
        for p in (self.registry.path,self.market.path,':memory:'):
            with self.assertRaises(ValidationError): ExecutionStore(p)
        with self.assertRaises(ValidationError): ExecutionStore(self.root/'alias.sqlite3',forbidden_paths=[self.root/'alias.sqlite3'])
        for method in (self.store.manifest,self.store.report,self.store.summary):
            with self.assertRaises(ValidationError): method('missing')
        for batch in (True,0,-1):
            with self.assertRaises(ValidationError): self.run_scenario(batch_size=batch)

    def test_persisted_cursor_and_clock_cannot_move_backwards_or_conflict(self):
        a=self.engine(); events=list(self.market.replay(self.dataset['dataset_hash']))
        a.push(events[0]); first=a.checkpoint(); self.store.commit(a,a.report())
        a.push(events[1]); self.store.commit(a,a.report())
        old=ExecutionEngine.restore(a.dataset,a.intents,a.universe,a.versions,a.fees,a.config,a.features,a.decision_ms,first)
        with self.assertRaises(ValidationError): self.store.commit(old,old.report())
        a.prefix_hash='f'*64
        with self.assertRaises(ValidationError): self.store.commit(a,a.report())
