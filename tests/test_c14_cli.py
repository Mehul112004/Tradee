from contextlib import redirect_stdout,redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tradee.cli import main
from tradee.c14 import SignalStore
from tests.c14_support import deployment,cycle,STAMP


class SignalCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=Path(self.tmp.name)
        self.args=['--db',str(self.root/'c01.db'),'signals','--market-db',str(self.root/'c02.db'),'--simulation-db',str(self.root/'c11.db'),
            '--research-db',str(self.root/'c12.db'),'--portfolio-db',str(self.root/'c13.db'),'--signal-db',str(self.root/'c14.db')]
    def call(self,*args):
        out=io.StringIO(); err=io.StringIO()
        with redirect_stdout(out),redirect_stderr(err): code=main([*self.args,*map(str,args)])
        return code,json.loads(out.getvalue() or err.getvalue())
    def create(self):
        s=SignalStore(self.root/'c14.db'); s.create(deployment()); return s
    def test_explain_is_offline_and_shadow_by_default(self):
        code,d=self.call('explain'); self.assertEqual(code,0); self.assertEqual(d['runtime']['mode'],'shadow'); self.assertFalse((self.root/'c14.db').exists())
    def test_pending_and_stale_status_return_unready_exit_code(self):
        s=self.create(); self.assertEqual(self.call('status','paper','--at-ms',STAMP)[0],2)
        s.publish('paper',0,cycle(s),0); self.assertEqual(self.call('status','paper','--at-ms',STAMP)[0],0)
        self.assertEqual(self.call('status','paper','--at-ms',STAMP+5000)[0],2)
    def test_read_commands_return_local_evidence_without_network(self):
        s=self.create(); h=s.publish('paper',0,cycle(s),0)
        for args in (('session','paper'),('events','paper'),('list','paper'),('signal','c'*64),('artifact',h['cycle_hash'])):
            self.assertEqual(self.call(*args)[0],0)
    def test_pause_resume_and_recovery_are_explicit(self):
        self.create()
        self.assertEqual(self.call('pause','paper','--reason','maintenance','--at-ms',STAMP)[0],0)
        self.assertEqual(self.call('resume','paper','--reason','restored','--at-ms',STAMP+1)[0],0)
        self.assertEqual(self.call('recover','paper','--at-ms',STAMP+1)[0],0)
    def test_missing_sources_or_records_return_json_errors(self):
        for args in (('session','unknown'),('artifact','x'),('tick','paper','--at-ms',STAMP),('send','paper','--send-paper')):
            code,d=self.call(*args); self.assertEqual(code,1); self.assertIn('error',d)
    def test_aliasing_stores_is_rejected(self):
        self.args=['--db',str(self.root/'same'),'signals','--signal-db',str(self.root/'same')]
        self.assertEqual(self.call('session','paper')[0],1)
    def test_unverified_deployment_or_invalid_reconciliation_is_not_accepted(self):
        p=self.root/'bad.json'; p.write_text('{"name":"bad"}')
        self.assertEqual(self.call('create','--spec',p,'--experiment','a'*64,'--portfolio-run','b'*64)[0],1)
        self.create(); self.assertEqual(self.call('reconcile','c'*64,'--decision','sent','--evidence','unverified')[0],1)

    def test_explicit_telegram_connectivity_diagnostic_is_one_attempt_without_db(self):
        from tradee.c14 import DeliveryResult
        from tests.c14_support import BOT,CHAT
        with patch('tradee.c14.cli.TelegramTransport') as transport:
            transport.return_value.send.return_value=DeliveryResult('sent','telegram_accepted',9)
            code,d=self.call('telegram-test','--bot-id',BOT,'--chat-id',CHAT,'--test-id','manual_smoke','--send-paper')
            self.assertEqual(code,0); self.assertTrue(d['ready']); self.assertFalse(d['live_approved'])
            transport.return_value.send.assert_called_once(); self.assertIn('NO TRADE INSTRUCTION',transport.return_value.send.call_args.args[1])
        self.assertFalse((self.root/'c14.db').exists())
    def test_missing_credentials_cannot_trigger_external_smoke(self):
        from tests.c14_support import BOT,CHAT
        with patch.dict('os.environ',{},clear=True):
            code,d=self.call('telegram-test','--bot-id',BOT,'--chat-id',CHAT,'--test-id','manual_smoke','--send-paper')
        self.assertEqual(code,1); self.assertIn('credential',d['error']); self.assertFalse((self.root/'c14.db').exists())
