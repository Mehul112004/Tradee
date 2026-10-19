from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from tradee.cli import main


class ExpectancyCliTests(unittest.TestCase):
    def invoke(self,args):
        out,err=StringIO(),StringIO()
        with redirect_stdout(out),redirect_stderr(err): code=main(args)
        return code,json.loads(out.getvalue() or err.getvalue())

    def test_explain_creates_no_database_or_network_dependency(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'absent.db'; code,d=self.invoke(['--db',str(p),'expectancy','explain'])
            self.assertEqual(code,0); self.assertEqual(d['component'],'C10'); self.assertFalse(p.exists())

    def test_missing_and_aliased_simulation_sources_return_json(self):
        with tempfile.TemporaryDirectory() as folder:
            p=str(Path(folder)/'missing.db')
            for args in (['--db',p,'expectancy','--simulation-db',p,'fit','--runs','missing','--window','missing'],
                         ['--db',p,'expectancy','--simulation-db',p,'--estimator-db',str(Path(folder)/'e.db'),'fit','--runs','missing','--window','missing']):
                code,d=self.invoke(args); self.assertEqual(code,1); self.assertIn('error',d)
            self.assertFalse(Path(p).exists())
