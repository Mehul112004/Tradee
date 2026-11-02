"""Quick analysis integration: scope, long warm-up, durable controls and C02 evidence."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock

from tradee.c01 import Registry,ValidationError
from tradee.pilots.contracts import BAR,HOUR,DAY,FAMILIES,WARMUP_BARS
from backend.tradee_web.analysis import AnalysisStore,validate_spec
from backend.tradee_web.analysis_live import C02LiveFeed
from backend.tradee_web.config import Settings,Profile,KINDS
from backend.tradee_web.pilot_analysis import evaluate_pilots,save_attempts,claim_bundle
from .analysis_support import candle


def spec(): return dict(name='Pilot',symbols=['BTCUSDT'],timeframe='15m',strategies=list(FAMILIES),mode='history',history_bars=100,telegram=False)


class NativeAdapter(unittest.TestCase):
    def test_scope_and_no_research_release_required(self):
        self.assertEqual(validate_spec(spec())['strategies'],sorted(FAMILIES))
        for change in ({'timeframe':'1m'},{'symbols':['DOGEUSDT']}):
            with self.assertRaisesRegex(ValidationError,'15m'): validate_spec(dict(spec(),**change))

    def test_long_history_warms_hourly_context_and_preserves_modeled_label(self):
        rows=[dict(candle(i*BAR,BAR),available_ms=10**12) for i in range(WARMUP_BARS)]
        output=evaluate_pilots(rows,spec(),0,symbol='BTCUSDT',tick_size='.01')
        self.assertTrue(all(output['readiness'].values()))
        self.assertEqual(output['pilot']['hourly_bars'],1700)
        self.assertEqual(output['pilot']['availability'],'modeled historical clock')
        self.assertEqual(output['setups'],[]); self.assertEqual(len(output['features']),500)
        self.assertTrue(all(r['available_ms']==10**12 for r in rows))

    def test_cold_live_bootstrap_does_not_backdate_knowledge_or_attempts(self):
        end=WARMUP_BARS*BAR; now=end+1000
        rows=[dict(candle(i*BAR,BAR),available_ms=now) for i in range(WARMUP_BARS)]
        value=spec(); value['mode']='live'
        output=evaluate_pilots(rows,value,end-100*BAR,symbol='BTCUSDT',tick_size='.01',live_start_ms=now)
        e=output['_engine']
        self.assertEqual(e.attempt_log,[]); self.assertEqual(output['setups'],[])
        self.assertTrue(all(l['known_ms']==now for l in e.context.levels))

    def test_restart_rebuild_and_prefix_extension_are_identical(self):
        rows=[candle(i*BAR,BAR) for i in range(200)]
        a=evaluate_pilots(rows[:150],spec(),0,symbol='BTCUSDT',tick_size='.01')['_engine']
        for r in rows[150:]: a.advance(r)
        b=evaluate_pilots(rows,spec(),0,symbol='BTCUSDT',tick_size='.01')['_engine']
        self.assertEqual(a.context.prefix,b.context.prefix)
        self.assertEqual(a.context.exec.ema[200].document(),b.context.exec.ema[200].document())


class WorkspaceControls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store=AnalysisStore(Path(self.tmp.name)/'analysis.sqlite3')

    def signal(self,end,**kw):
        return dict(dict(id=str(end),symbol='BTCUSDT',strategy=FAMILIES[1],side='long',seed_ms=end-BAR,end_ms=end,level_id=None,family_tags=[FAMILIES[1]]),**kw)

    def test_cooldown_cap_and_session_rename_cannot_reset_ledger(self):
        with self.store.connection() as db:
            self.assertIsNone(claim_bundle(db,'local','one',self.signal(2*DAY)))
            self.assertEqual(claim_bundle(db,'local','two',self.signal(2*DAY+BAR)),'cooldown')
            self.assertIsNone(claim_bundle(db,'local','two',self.signal(2*DAY+4*BAR)))
            self.assertIsNone(claim_bundle(db,'local','three',self.signal(2*DAY+8*BAR)))
            self.assertEqual(claim_bundle(db,'local','four',self.signal(2*DAY+12*BAR)),'family_cap')
            self.assertEqual(claim_bundle(db,'local','four',self.signal(2*DAY+12*BAR,family_tags=[FAMILIES[0],FAMILIES[1]],strategy=FAMILIES[0])),'family_cap')
            self.assertIsNone(claim_bundle(db,'other','four',self.signal(2*DAY+12*BAR)))

    def test_seed_attempt_is_owned_even_without_an_alert(self):
        attempt=dict(level_id='level',side='long',day=2,seed_ms=2*DAY,family=FAMILIES[0])
        with self.store.connection() as db:
            save_attempts(db,'local','one','BTCUSDT',[attempt])
            save_attempts(db,'local','two','BTCUSDT',[dict(attempt,seed_ms=2*DAY+BAR)])
            signal=self.signal(2*DAY+2*BAR,strategy=FAMILIES[0],level_id='level',seed_ms=2*DAY)
            self.assertEqual(claim_bundle(db,'local','two',signal),'opportunity_consumed')
            self.assertIsNone(claim_bundle(db,'local','one',signal))


class C02ExecutionEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); root=Path(self.tmp.name)
        self.now=1800000003000; self.clock=lambda:self.now/1000
        self.settings=Settings((Profile('local','Local',{k:str(root/f'{k}.sqlite3') for k in KINDS}),),state_path=root/'web.sqlite3')
        raw=(Path(__file__).resolve().parents[2]/'tests/fixtures/exchange_info.json').read_text()
        Registry(root/'c01.sqlite3',clock=self.clock).ingest(raw,'synthetic:pilot test')
        value=spec(); value['mode']='live'
        self.feed=C02LiveFeed(self.settings,'local',dict(spec=value),self.now-3000,threading.Event(),clock=self.clock,rest=Mock())
        self.addCleanup(self.feed.close)

    def push(self,kind,**fields):
        data=dict(e=kind,s='BTCUSDT',E=self.now,T=self.now); data.update(fields)
        self.feed.collector.process(json.dumps(data),'wss://synthetic/pilot',self.now)

    def trade(self,key,when,price='100'):
        self.feed.collector.process(json.dumps(dict(e='aggTrade',s='BTCUSDT',E=when,T=when,a=key,f=key,l=key,p=price,q='1',m=False)),'wss://synthetic/pilot',self.now)

    def test_real_collector_records_quotes_marks_and_sequence_checked_trade_path(self):
        self.assertEqual(set(self.feed.collector.kinds),{'candle','trade','quote','mark'})
        start=self.now-1000
        self.push('bookTicker',u=1,b='99.99',B='2',a='100.01',A='2')
        self.push('markPriceUpdate',p='100',i='100',r='.0001',T=self.now+8*HOUR)
        self.trade(1,start-1); self.trade(2,start+1); self.trade(3,self.now)
        evidence=self.feed.execution_evidence('BTCUSDT',start)
        self.assertEqual(evidence['quote']['bid'],'99.99'); self.assertEqual(evidence['mark']['mark_price'],'100')
        self.assertTrue(evidence['path']['continuous']); self.assertEqual(evidence['path']['start_ms'],start)
        self.trade(5,self.now)
        self.assertIsNone(self.feed.execution_evidence('BTCUSDT',start)['path'])
        with self.feed.store.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM events WHERE kind='quote'").fetchone()[0],1)
        self.feed.store.log(action='disconnected',route='market')
        self.assertIsNone(self.feed.execution_evidence('BTCUSDT',start)['quote'])


if __name__=='__main__': unittest.main()
