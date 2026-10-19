from contextlib import redirect_stdout,redirect_stderr
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from tradee.cli import main
from tradee.c09.cli import collection
from tradee.c01 import ValidationError


class LifecycleCliTests(unittest.TestCase):
    def invoke(self,args):
        out,err=StringIO(),StringIO()
        with redirect_stdout(out),redirect_stderr(err): result=main(args)
        return result,json.loads(out.getvalue() or err.getvalue())

    def test_explain_is_offline_and_creates_no_database(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'absent.sqlite3'; code,doc=self.invoke(['--db',str(path),'lifecycle','explain'])
            self.assertEqual(code,0); self.assertEqual(doc['component'],'C09'); self.assertFalse(path.exists())

    def test_missing_and_aliased_input_stores_are_json_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'absent.sqlite3')
            for args in (['--db',path,'lifecycle','--market-db',path,'run','missing','--intents','missing','--fees','missing'],
                         ['--db',path,'lifecycle','run','missing','--intents','missing','--fees','missing']):
                code,doc=self.invoke(args); self.assertEqual(code,1); self.assertIn('error',doc)
            self.assertFalse(Path(path).exists())

    def test_collection_schemas_reject_boolean_versions_and_unknown_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.json'
            for d in ({'schema_version':True,'intents':[]},{'schema_version':1,'intents':{}},{'schema_version':1,'intents':[],'surprise':1}):
                path.write_text(json.dumps(d))
                with self.assertRaises(ValidationError): collection(path,'intents')
