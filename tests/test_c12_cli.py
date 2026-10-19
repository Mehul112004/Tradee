from contextlib import redirect_stdout,redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from tradee.cli import main
from tests.c12_support import plan


class ResearchCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
        self.args=['--db',str(self.root/'c01.db'),'research','--simulation-db',str(self.root/'c11.db'),'--research-db',str(self.root/'c12.db')]
    def call(self,*args):
        out=io.StringIO(); err=io.StringIO()
        with redirect_stdout(out),redirect_stderr(err): status=main([*self.args,*args])
        return status,json.loads(out.getvalue() or err.getvalue())
    def register(self):
        p=self.root/'plan.json'; p.write_text(json.dumps(plan())); status,d=self.call('register','--manifest',str(p)); self.assertEqual(status,0); return d['experiment_hash']
    def test_explain_register_manifest_events_ledger_and_exit_codes(self):
        self.assertEqual(self.call('explain')[0],0); h=self.register()
        for command,arg in (('manifest',h),('events',h),('ledger','range'),('jobs',h)):
            self.assertEqual(self.call(command,arg)[0],0)
        status,d=self.call('decision',h); self.assertEqual(status,2); self.assertEqual(d['status'],'not_evaluated')
    def test_unknown_hash_missing_sources_and_release_are_errors(self):
        h=self.register()
        for args in (('manifest','0'*64),('run',h),('release',h),('open-holdout',h,'--reason','premature')):
            self.assertEqual(self.call(*args)[0],1)
    def test_invalid_manifest_is_not_registered(self):
        p=self.root/'invalid.json'; p.write_text('{"unknown":1}')
        self.assertEqual(self.call('register','--manifest',str(p))[0],1)
    def test_store_paths_must_differ(self):
        self.args=['--db',str(self.root/'same'),'research','--research-db',str(self.root/'same')]
        self.assertEqual(self.call('manifest','0'*64)[0],1)
