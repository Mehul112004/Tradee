from contextlib import redirect_stdout,redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from tradee.cli import main
from tradee.c13 import AccountSnapshot
from tests.c13_support import START


class PortfolioCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
        self.args=['--db',str(self.root/'c01.db'),'portfolio','--market-db',str(self.root/'c02.db'),'--simulation-db',str(self.root/'c11.db'),'--estimator-db',str(self.root/'c10.db'),'--portfolio-db',str(self.root/'c13.db')]
    def call(self,*args):
        out=io.StringIO(); err=io.StringIO()
        with redirect_stdout(out),redirect_stderr(err): status=main([*self.args,*args])
        return status,json.loads(out.getvalue() or err.getvalue())
    def test_explain_is_offline_and_exposes_explicit_paper_limits(self):
        code,d=self.call('explain'); self.assertEqual(code,0); self.assertEqual(d['component'],'C13'); self.assertEqual(d['policy']['leverage'],1)
        self.assertFalse((self.root/'c13.db').exists())
    def test_account_create_retrieve_and_explicit_cas_update(self):
        p=self.root/'snapshot.json'; p.write_text(json.dumps(AccountSnapshot(START,START,'1000','1000').document()))
        code,a=self.call('account-create','paper','--snapshot',str(p)); self.assertEqual(code,0)
        self.assertEqual(self.call('account','paper'),(0,a))
        self.assertEqual(self.call('account-update','paper','--snapshot',str(p),'--expected',a['snapshot_hash'])[0],0)
    def test_missing_hash_and_input_stores_return_json_errors(self):
        for args in (('summary','0'*64),('manifest','0'*64),('account','missing'),('replay','--sources','missing','--models','0'*64)):
            code,d=self.call(*args); self.assertEqual(code,1); self.assertIn('error',d)
    def test_invalid_risk_snapshot_does_not_create_account(self):
        p=self.root/'bad.json'; p.write_text('{"unknown":1}')
        self.assertEqual(self.call('account-create','p','--snapshot',str(p))[0],1)
        self.assertEqual(self.call('account','p')[0],1)
    def test_database_aliases_are_rejected(self):
        self.args=['--db',str(self.root/'same'),'portfolio','--portfolio-db',str(self.root/'same')]
        self.assertEqual(self.call('account','p')[0],1)
