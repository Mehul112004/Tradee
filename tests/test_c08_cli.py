from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from tradee.cli import main


class CandidateCliTests(unittest.TestCase):
    def invoke(self,args):
        out,err=StringIO(),StringIO()
        with redirect_stdout(out),redirect_stderr(err): code=main(args)
        return code,json.loads(out.getvalue() or err.getvalue())

    def test_catalog_and_explain_are_offline_without_database_side_effects(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'absent.sqlite3')
            code,doc=self.invoke(['--db',path,'candidates','list']); self.assertEqual(code,0); self.assertEqual(len(doc['strategies']),2)
            for s in doc['strategies']:
                code,explained=self.invoke(['--db',path,'candidates','explain',s['spec']['family']])
                self.assertEqual(code,0); self.assertIn('strategy_hash',explained)
            self.assertFalse(Path(path).exists())

    def test_missing_and_aliased_stores_return_json_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'absent.sqlite3')
            for args in (['--db',path,'candidates','--market-db',path,'run','missing','--strategy','missing.json'],
                         ['--db',path,'candidates','run','missing','--strategy','missing.json']):
                code,doc=self.invoke(args); self.assertEqual(code,1); self.assertIn('error',doc)
