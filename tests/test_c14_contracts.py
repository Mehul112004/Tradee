from dataclasses import replace
import unittest
from tradee.c01 import ValidationError
from tradee.c14 import RuntimeConfig,SessionSpec,DeliveryResult
from tests.c14_support import START,STAMP,BOT,CHAT


class SignalContractTests(unittest.TestCase):
    def test_runtime_roundtrip_and_explicit_paper_destination(self):
        c=RuntimeConfig(mode='paper_test',bot_id=BOT,chat_id=CHAT); self.assertEqual(RuntimeConfig.from_dict(c.document()),c)
        self.assertEqual(RuntimeConfig().mode,'shadow')
    def test_live_mode_and_implicit_destinations_rejected(self):
        for d in ({'mode':'live'},{'mode':'paper_test'},{'mode':'paper_test','bot_id':True,'chat_id':CHAT},{'chat_id':CHAT},{'mode':'paper_test','bot_id':BOT,'chat_id':'@someone'}):
            with self.subTest(d=d),self.assertRaises(ValidationError): RuntimeConfig.from_dict(d)
    def test_numeric_resource_and_throttle_bounds_are_strict(self):
        for d in ({'http_timeout_ms':True},{'max_events':0},{'max_cycle_bytes':50000001},{'max_attempts':11},{'lease_ms':3000},{'chat_interval_ms':2999},{'bot_interval_ms':39},{'source_settle_ms':60001},{'unknown':1}):
            with self.subTest(d=d),self.assertRaises(ValidationError): RuntimeConfig.from_dict(d)
    def test_session_windows_and_identifiers(self):
        s=SessionSpec('paper',START,START+720000,START-60000,180000); self.assertEqual(SessionSpec.from_dict(s.document()).document(),s.document())
        for d in ({'name':'../bad'},{'start_ms':START+1},{'end_ms':START},{'warmup_start_ms':START},{'tail_ms':1},{'runtime':{'mode':'live'}},{'runtime':False}):
            with self.subTest(d=d),self.assertRaises(ValidationError): SessionSpec.from_dict(dict(s.document(),**d))
    def test_delivery_receipts_cannot_claim_unverified_acceptance(self):
        for d in ({'status':'sent','reason':'accepted'},{'status':'ambiguous','reason':'unknown','message_id':1},{'status':'retry','reason':'raw https://botTOKEN'},{'status':'retry','reason':'rate_limited','retry_after_ms':86400001},{'status':'sent','reason':'accepted','message_id':True}):
            with self.subTest(d=d),self.assertRaises(ValidationError): DeliveryResult.from_dict(d)
        self.assertEqual(DeliveryResult.from_dict(DeliveryResult('sent','telegram_accepted',1).document()).message_id,1)
