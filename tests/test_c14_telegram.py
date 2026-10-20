import io
import json
import socket
import ssl
import unittest
from urllib.error import HTTPError,URLError
from tradee.c01 import ValidationError
from tradee.c14 import TelegramTransport
from tests.c14_support import BOT,CHAT

TOKEN=str(BOT)+':'+'A'*32
TEXT='PAPER TEST — NO TRADE INSTRUCTION\nSignal: test'


class Response(io.BytesIO):
    def __init__(self,status,doc): super().__init__(doc if isinstance(doc,bytes) else json.dumps(doc).encode()); self.code=status
class Opener:
    def __init__(self,response): self.response=response; self.calls=[]
    def open(self,req,timeout):
        self.calls.append((req,timeout))
        if isinstance(self.response,BaseException): raise self.response
        return self.response


class TelegramTransportTests(unittest.TestCase):
    def send(self,doc,status=200):
        self.opener=Opener(Response(status,doc)); return TelegramTransport(TOKEN,BOT,self.opener).send(CHAT,TEXT,3000)
    def test_plain_tls_fixed_host_and_confirmed_chat_message_text(self):
        r=self.send(dict(ok=True,result=dict(message_id=12,chat=dict(id=CHAT),text=TEXT)))
        self.assertEqual(r.status,'sent'); req,timeout=self.opener.calls[0]; self.assertEqual(req.full_url,'https://api.telegram.org/bot'+TOKEN+'/sendMessage'); self.assertEqual(timeout,3)
        d=json.loads(req.data); self.assertEqual(d,dict(chat_id=CHAT,text=TEXT,disable_notification=True,protect_content=True)); self.assertNotIn('parse_mode',d)
    def test_invalid_credentials_and_identity_are_redacted(self):
        for token,bot in ((None,BOT),('bad',BOT),(TOKEN,BOT+1)):
            with self.assertRaises(ValidationError) as e: TelegramTransport(token,bot)
            self.assertNotIn(TOKEN,str(e.exception))
        self.assertNotIn(TOKEN,repr(TelegramTransport(TOKEN,BOT)))
    def test_acceptance_requires_exact_destination_text_and_positive_message_id(self):
        for m in (dict(message_id=1,chat=dict(id=CHAT+1),text=TEXT),dict(message_id=1,chat=dict(id=CHAT),text='different'),dict(message_id=True,chat=dict(id=CHAT),text=TEXT),{}):
            with self.subTest(m=m): self.assertEqual(self.send(dict(ok=True,result=m)).status,'ambiguous')
    def test_explicit_rate_limit_is_only_safe_server_retry(self):
        r=self.send(dict(ok=False,error_code=429,parameters=dict(retry_after=7)),429)
        self.assertEqual((r.status,r.retry_after_ms),('retry',7000))
        self.assertEqual(self.send(dict(ok=False,error_code=429),429).status,'ambiguous')
    def test_client_rejection_permanent_and_server_errors_ambiguous(self):
        for code in (400,401,403): self.assertEqual(self.send(dict(ok=False,error_code=code),code).status,'failed')
        for code in (301,500,502): self.assertEqual(self.send(dict(ok=False,error_code=code),code).status,'ambiguous')
    def test_malformed_and_oversize_bodies_never_imply_not_sent(self):
        for raw in (b'not json',b'x'*65537,b'[]',b'{"ok":1}',b'{"ok":true,"result":[]}'):
            self.assertEqual(self.send(raw).status,'ambiguous')
    def test_definite_connection_failure_can_retry_unknown_timeout_cannot(self):
        for exc,status in ((URLError(socket.gaierror()),'retry'),(URLError(ConnectionRefusedError()),'retry'),(URLError(ssl.SSLCertVerificationError()),'failed'),(TimeoutError(),'ambiguous'),(URLError(TimeoutError()),'ambiguous'),(RuntimeError(TOKEN),'ambiguous')):
            r=TelegramTransport(TOKEN,BOT,Opener(exc)).send(CHAT,TEXT,3000); self.assertEqual(r.status,status); self.assertNotIn(TOKEN,json.dumps(r.document()))
    def test_http_error_body_is_classified_without_leaking_request_url(self):
        error=HTTPError('https://api.telegram.org/bot'+TOKEN,429,'secret',{},io.BytesIO(b'{"ok":false,"error_code":429,"parameters":{"retry_after":2}}'))
        r=TelegramTransport(TOKEN,BOT,Opener(error)).send(CHAT,TEXT,3000); self.assertEqual(r.status,'retry'); self.assertNotIn(TOKEN,json.dumps(r.document()))
    def test_message_length_timeout_and_destination_are_bounded(self):
        t=TelegramTransport(TOKEN,BOT,Opener(None))
        for chat,text,timeout in ((CHAT,'',3000),(CHAT,'x'*4097,3000),(0,TEXT,3000),(CHAT,TEXT,0)):
            with self.assertRaises(ValidationError): t.send(chat,text,timeout)
