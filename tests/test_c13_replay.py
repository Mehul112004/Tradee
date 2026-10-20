from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
import tempfile
import unittest
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c10 import publish
from tradee.c10.engine import verified_model
from tradee.c03.contracts import FrozenRecord
from tradee.c13 import PortfolioReplay,ReplayConfig
from tradee.c13.replay import diagnostics
from tests.c13_support import setup,policy,make_source


class FundedReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.ss,cls.pins,cls.model,cls.events=setup(cls.tmp.name)
        cls.result=cls.engine().run()
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    @classmethod
    def engine(cls,**kw):
        return PortfolioReplay(**dict(dict(simulations=cls.ss,pins=cls.pins,models=[cls.model],events=cls.events,policy=policy(),config=ReplayConfig(initial_cash_usdt='320')),**kw))
    def test_golden_shared_fees_cash_and_positions(self):
        _,report,_=self.result; d=report.document()
        self.assertTrue(d['ready']); self.assertEqual(d['coverage']['admitted_positions'],6)
        self.assertEqual(d['metrics']['net_pnl_usdt'],'12.7335'); self.assertEqual(d['terminal_account']['cash_usdt'],'332.7335')
        self.assertEqual(d['terminal_account']['positions'],[]); self.assertIsNone(d['metrics']['sharpe'])
        self.assertEqual(sum((Decimal(x['outcome']['net_usdt']) for x in d['trades']),Decimal(0)),Decimal('12.7335'))
    def test_allocation_precedes_future_realized_return_and_only_admitted_ledgers_book(self):
        _,report,events=self.result; d=report.document(); allocations=[a.document()['payload'] for a in events if a.document()['kind']=='allocation']
        self.assertTrue(allocations)
        for a in allocations:
            for x in a['decisions']:
                self.assertNotIn('outcome',x)
                if x['status']=='admitted': self.assertEqual(x['execution']['fill']['execution_as_of_ms'],a['as_of_ms'])
        self.assertEqual(len(d['trades']),6); self.assertEqual(d['coverage']['inventoried_size_options'],18)
    def test_repeat_is_identical_and_engine_is_single_use(self):
        self.assertEqual(self.result[1].digest,self.engine().run()[1].digest)
        engine=self.engine(); engine.run()
        with self.assertRaises(ValidationError): engine.run()
    def test_changed_raw_content_or_truncated_ordered_prefix_is_rejected(self):
        changed=deepcopy(self.events); changed[0]['data']['close']='101'
        for events in (changed,self.events[:-1],list(reversed(self.events))):
            with self.assertRaisesRegex(ValidationError,'prefix|content'): self.engine(events=events)
    def test_pinned_source_report_cannot_be_substituted(self):
        with self.assertRaisesRegex(ValidationError,'frozen content'): self.engine(pins={next(iter(self.pins)):'0'*64})
    def test_publication_after_window_and_overlapping_model_bank_rejected(self):
        # Use the publication constructor so its internal receipt remains valid.
        f=FrozenRecord.create(self.model.document()['fit']); late=publish(f,self.events[-1]['available_ms'],'modeled')
        with self.assertRaisesRegex(ValidationError,'before decision'): self.engine(models=[late])
        with self.assertRaisesRegex(ValidationError,'One frozen model'): self.engine(models=[self.model,self.model])
    def test_event_candidate_sample_artifact_budgets_abort_instead_of_truncating(self):
        cases=[dict(config=ReplayConfig(initial_cash_usdt='320',max_events=1)),dict(config=ReplayConfig(initial_cash_usdt='320',max_candidates=1)),dict(policy=policy(max_samples=1)),dict(policy=policy(max_artifacts=1))]
        for kw in cases:
            with self.subTest(kw=kw),self.assertRaisesRegex(ValidationError,'budget'): self.engine(**kw).run()
    def test_missing_exact_models_rejects_every_size_without_fabricated_equity_gain(self):
        _,report,_=self.engine(models=[]).run(); d=report.document()
        self.assertFalse(d['ready']); self.assertEqual(d['metrics']['net_pnl_usdt'],'0'); self.assertEqual(d['coverage']['admitted_positions'],0)
    def test_unknown_funding_never_enters_book(self):
        result,events=make_source(n=3,start=self.result[0].document()['dataset']['start_ms'],unknown=True); s=self.ss.commit(result)
        _,report,_=self.engine(pins={s['run_hash']:s['report_hash']},events=events).run(); d=report.document()
        self.assertFalse(d['ready']); self.assertEqual(d['coverage']['admitted_positions'],0)
        self.assertIn('candidate_funding_coverage_unknown',d['coverage']['rejection_reasons'])
    def test_no_lookahead_when_later_execution_path_loses(self):
        start=self.result[0].document()['dataset']['start_ms']; result,events=make_source(n=3,start=start,positive=False); s=self.ss.commit(result)
        _,report,artifacts=self.engine(pins={s['run_hash']:s['report_hash']},events=events).run(); d=report.document()
        self.assertLess(Decimal(d['metrics']['net_pnl_usdt']),0)
        # At least the first contemporaneously eligible entry still occurs.
        self.assertGreater(d['coverage']['admitted_positions'],0)
        self.assertEqual(sorted(t['scenario']['quantity'] for t in d['trades'] if t['admitted_ms']==min(x['admitted_ms'] for x in d['trades'])),['0.5','1'])
    def test_actual_funding_revision_replaces_cashflow_after_position_closes(self):
        from tests.c13_support import funding_source
        source,events=funding_source(self.result[0].document()['dataset']['start_ms']); s=self.ss.commit(source)
        _,report,artifacts=self.engine(pins={s['run_hash']:s['report_hash']},events=events).run(); d=report.document()
        self.assertTrue(d['ready']); self.assertEqual(d['metrics']['net_pnl_usdt'],'11.8155')
        self.assertEqual(d['terminal_account']['cash_usdt'],'331.8155')
        self.assertEqual(sum((Decimal(t['outcome']['funding_usdt']) for t in d['trades']),Decimal(0)),Decimal('-0.918'))
        revisions=[e.document()['payload'] for e in artifacts if e.document()['kind']=='book_revision']
        self.assertTrue(any(r['outcome']['status']=='closed' and r['outcome']['funding_usdt']=='-0.204' for r in revisions))

    def test_open_end_tail_is_not_force_closed_and_stale_terminal_mark_is_unknown(self):
        from tradee.c11 import Simulator,Scenario,SimulationConfig
        from tradee.c07 import FeeSchedule,ExecutionConfig
        from tradee.c08 import CandidateConfig
        from tradee.c06 import FundingConfig
        original=self.result[0].document()['dataset']['start_ms']
        raw,events=make_source(n=3,start=original); m=raw.manifest.document()
        prefix=[e for e in events if e['available_ms']<=original+181000]
        for tail,known in ((182000,True),(190000,False)):
            ds=dict(m['dataset'],end_ms=original+tail,as_of_ms=original+tail,event_count=len(prefix),dataset_hash='tail-'+str(tail))
            source=Simulator(ds,[Scenario.from_dict(s) for s in m['scenarios']],m['metadata_snapshots'],m['metadata_versions'],FeeSchedule.from_dict(m['fees']),ExecutionConfig.from_dict(m['execution']),CandidateConfig.from_dict(m['candidates']),FundingConfig.from_dict(m['funding']),m['calendars'],SimulationConfig()).run(lambda:iter(prefix))
            s=self.ss.commit(source); _,report,_=self.engine(pins={s['run_hash']:s['report_hash']},events=prefix).run(); d=report.document()
            self.assertFalse(d['ready']); self.assertEqual(len(d['terminal_account']['positions']),2)
            self.assertEqual(d['metrics']['final_equity_usdt'] is not None,known)
            self.assertTrue(all(t['outcome']['exit_ms'] is None for t in d['trades']))

    def test_regular_return_grid_uses_shared_equity_and_missing_values_stay_unknown(self):
        samples=[dict(at_ms=0,equity_usdt='100'),dict(at_ms=1,equity_usdt='110'),dict(at_ms=2,equity_usdt=None),dict(at_ms=3,equity_usdt='99')]
        d=diagnostics(samples,'100',dict(equity_usdt='99'))
        self.assertEqual(d['total_return_fraction'],'-0.01'); self.assertIsNone(d['max_drawdown_usdt'])
        self.assertEqual(d['available_sample_drawdown_lower_bound_usdt'],'11')
        self.assertEqual([x['return_fraction'] for x in d['regular_arithmetic_returns']],[None,'0.1',None,None])
