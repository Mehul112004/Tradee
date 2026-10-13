from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from tradee.cli import main
from tradee.c07.cli import collection
from tradee.c01 import ValidationError


class ExecutionCliTests(unittest.TestCase):
    def invoke(self,args):
        out,err=StringIO(),StringIO()
        with redirect_stdout(out),redirect_stderr(err): code=main(args)
        return code,json.loads(out.getvalue() or err.getvalue())

    def test_explain_without_creating_databases(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'absent.sqlite3'
            code,doc=self.invoke(['--db',str(path),'execution','explain'])
            self.assertEqual(code,0); self.assertEqual(doc['component'],'C07'); self.assertEqual(doc['currency'],'USDT')
            self.assertFalse(path.exists())

    def test_missing_and_aliased_inputs_return_json_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'absent.sqlite3')
            for args in (['--db',path,'execution','--market-db',path,'run','missing','--intents','missing','--fees','missing'],
                         ['--db',path,'execution','run','missing','--intents','missing','--fees','missing']):
                code,doc=self.invoke(args); self.assertEqual(code,1); self.assertIn('error',doc)
            self.assertFalse(Path(path).exists())

    def test_strict_collection_schema_and_boolean_version(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.json'
            for doc in ({'schema_version':True,'intents':[]},{'schema_version':2,'intents':[]},
                        {'schema_version':1,'intents':{}},{'schema_version':1,'intents':[],'surprise':0}):
                path.write_text(json.dumps(doc))
                with self.assertRaises(ValidationError): collection(path,'intents')
