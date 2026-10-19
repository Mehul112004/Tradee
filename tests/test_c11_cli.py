from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from tradee.cli import main


class SimulationCliTests(unittest.TestCase):
    def invoke(self,args):
        out,err=StringIO(),StringIO()
        with redirect_stdout(out),redirect_stderr(err): code=main(args)
        return code,json.loads(out.getvalue() or err.getvalue())

    def test_explain_is_offline_and_creates_no_database(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'absent.sqlite3'; code,doc=self.invoke(['--db',str(path),'simulate','explain'])
            self.assertEqual(code,0); self.assertEqual(doc['component'],'C11'); self.assertFalse(path.exists())

    def test_missing_and_aliased_inputs_return_json_without_creating_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'absent.sqlite3')
            for args in (['--db',path,'simulate','--market-db',path,'run','missing','--scenarios','missing','--fees','missing'],
                         ['--db',path,'simulate','run','missing','--scenarios','missing','--fees','missing']):
                code,doc=self.invoke(args); self.assertEqual(code,1); self.assertIn('error',doc)
            self.assertFalse(Path(path).exists())

    def test_shipped_configs_are_valid_and_both_families_are_explicit(self):
        from tradee.c09.cli import collection
        from tradee.c11 import Scenario,SimulationConfig
        root=Path(__file__).resolve().parents[1]
        specs=[Scenario.from_dict(d) for d in collection(root/'configs/c11_scenarios.json','scenarios')]
        self.assertEqual({s.strategy.family for s in specs},{'prior_range_breakout','ema_pullback_continuation'})
        SimulationConfig.from_dict(json.loads((root/'configs/c11_simulation.json').read_text()))
