from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from tradee.cli import main
from tradee.c06.cli import load_collection
from tradee.c06 import PositionTimeline
from tradee.c01 import ValidationError


class FundingCliTests(unittest.TestCase):
    def invoke(self,args):
        out,err=StringIO(),StringIO()
        with redirect_stdout(out),redirect_stderr(err): code=main(args)
        return code,json.loads(out.getvalue() or err.getvalue())

    def test_explain_does_not_require_databases(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'absent.sqlite3')
            code,doc=self.invoke(['--db',path,'funding','explain'])
            self.assertEqual(code,0); self.assertEqual(doc['currency'],'USDT')
            self.assertFalse(Path(path).exists())

    def test_missing_inputs_and_aliased_paths_fail_as_json(self):
        with tempfile.TemporaryDirectory() as folder:
            db=str(Path(folder)/'missing.sqlite3')
            for args in (['--db',db,'funding','--market-db',db,'run','missing','--positions','missing.json'],
                         ['--db',db,'funding','run','missing','--positions','missing.json']):
                code,doc=self.invoke(args)
                self.assertEqual(code,1); self.assertIn('error',doc)

    def test_collection_schema_errors_are_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.json'
            for doc in ({'schema_version':True,'positions':[]},{'schema_version':2,'positions':[]},
                        {'schema_version':1,'positions':{},'surprise':0},{'schema_version':1,'positions':[{'unknown':True}]}):
                path.write_text(json.dumps(doc))
                with self.assertRaises(ValidationError): load_collection(path,'positions',PositionTimeline)
