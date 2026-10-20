from contextlib import redirect_stdout,redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tradee.cli import main
from tradee.c11 import SimulationStore
from tradee.c13 import PortfolioStore
from tradee.c14 import SignalStore
from tradee.c15 import MonitorStore
from tests.c14_support import deployment
from tests.test_c15_store import manifest


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)

    def call(self,*args):
        out=io.StringIO(); err=io.StringIO()
        with redirect_stdout(out),redirect_stderr(err): code=main(list(map(str,args)))
        return code,json.loads(out.getvalue() or err.getvalue())

    def args(self):
        return ['--db',self.root/'c01','monitor','--market-db',self.root/'c02','--simulation-db',self.root/'c11',
            '--portfolio-db',self.root/'c13','--signal-db',self.root/'c14','--monitor-db',self.root/'c15']

    def stores(self):
        SimulationStore(self.root/'c11'); PortfolioStore(self.root/'c13'); SignalStore(self.root/'c14').create(deployment())

    def test_explain_is_offline_without_creating_files(self):
        code,r=self.call(*self.args(),'explain'); self.assertEqual(code,0); self.assertEqual(r['component'],'C15')
        self.assertEqual(list(self.root.iterdir()),[])

    def test_missing_operational_inputs_do_not_create_monitor_store(self):
        code,_=self.call(*self.args(),'observe','missing','--at-ms',1)
        self.assertEqual(code,1); self.assertFalse((self.root/'c15').exists())

    def test_read_commands_require_existing_store(self):
        code,_=self.call(*self.args(),'status','missing'); self.assertEqual(code,1); self.assertFalse((self.root/'c15').exists())

    def test_status_and_events_are_available_without_input_databases(self):
        store=MonitorStore(self.root/'c15'); store.register(manifest())
        code,r=self.call(*self.args(),'status','forward'); self.assertEqual(code,0); self.assertIsNone(r['report'])
        code,r=self.call(*self.args(),'events','forward'); self.assertEqual(r[0]['kind'],'registered')

    def test_export_rejects_missing_observation(self):
        MonitorStore(self.root/'c15').register(manifest())
        code,_=self.call(*self.args(),'export','forward'); self.assertEqual(code,1)

    def test_same_database_is_rejected(self):
        args=self.args(); args[args.index('--monitor-db')+1]=self.root/'c14'
        code,_=self.call(*args,'observe','forward','--at-ms',1); self.assertEqual(code,1)

    def test_observe_returns_health_exit_code_without_automatic_pause(self):
        self.stores(); report=dict(report_hash='a'*64,ready=False,pause_requested=True,health=dict(already_paused=False),observed_ms=100)
        with patch('tradee.c15.cli.ForwardMonitor') as factory:
            factory.return_value.observe.return_value=report
            factory.return_value.apply_pause.return_value=dict(paused=True)
            code,r=self.call(*self.args(),'observe','forward','--at-ms',100)
            self.assertEqual(code,2); factory.return_value.apply_pause.assert_not_called()
            code,r=self.call(*self.args(),'observe','forward','--at-ms',100,'--apply-pauses')
            factory.return_value.apply_pause.assert_called_once_with('forward','a'*64,100)

    def test_watch_one_iteration_and_invalid_interval(self):
        self.stores(); report=dict(report_hash='a'*64,ready=True,pause_requested=False,health={},observed_ms=100)
        with patch('tradee.c15.cli.ForwardMonitor') as factory:
            factory.return_value.observe.return_value=report
            out=io.StringIO()
            with redirect_stdout(out): code=main(list(map(str,[*self.args(),'watch','forward','--max-cycles',1])))
            self.assertEqual(code,0); lines=out.getvalue().splitlines(); self.assertIn('report_hash',lines[0]); factory.return_value.apply_pause.assert_not_called()
            code,_=self.call(*self.args(),'watch','forward','--interval-seconds',0); self.assertEqual(code,1)

