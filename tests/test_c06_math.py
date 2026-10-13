from decimal import Decimal, localcontext
import unittest

from tradee.c01 import ValidationError
from tradee.c06 import FundingConfig, PositionTimeline, QuantityChange, SettlementCalendar, cashflow
from tradee.c06.contracts import FundingRecord, total_amounts
from tests.c06_support import START, HOUR, IDENTITY, position, calendar


class FundingMathTests(unittest.TestCase):
    def test_signed_hand_calculated_cashflows(self):
        for side,rate,want in (('long','0.001','-0.2'),('short','0.001','0.2'),
                               ('long','-0.002','0.4'),('short','-0.002','-0.4'),('long','0','0')):
            with self.subTest(side=side,rate=rate): self.assertEqual(cashflow(side,'2','100',rate),want)
        self.assertEqual(cashflow('long','0','100','0.1'),'0')

    def test_fractional_precision_and_no_currency_rounding(self):
        self.assertEqual(cashflow('long','0.123456789','12345.6789','0.00000001'),'-0.000015241578750190521')
        self.assertEqual(total_amounts(['-0.2','0.24','0']),'0.04')
        with localcontext() as ctx:
            ctx.prec=3  # External Decimal context cannot silently change results.
            self.assertEqual(cashflow('long','0.123456789','12345.6789','0.00000001'),'-0.000015241578750190521')
            self.assertEqual(total_amounts(['0.0001','0.0002']),'0.0003')

    def test_high_precision_inputs_and_sum_cancellation(self):
        q='0.'+'1'*40; p='12345678901234567890'; r='0.'+'2'*40
        with localcontext() as ctx:
            ctx.prec=400; want=-(Decimal(q)*Decimal(p)*Decimal(r))
        self.assertEqual(Decimal(cashflow('long',q,p,r)),want)
        self.assertEqual(total_amounts(['10000000000000000000000000000000000000000','-10000000000000000000000000000000000000000','0.00000000001']),'0.00000000001')

    def test_invalid_numeric_inputs_are_rejected(self):
        for q,p,r in ((True,'100','0.1'),('-1','100','0.1'),('1','0','0.1'),('1','100',.1),('1','100','NaN'),('1e-51','100','0.1')):
            with self.subTest(q=q,p=p,r=r),self.assertRaises(ValidationError): cashflow('long',q,p,r)
        with self.assertRaises(ValidationError): cashflow('buy','1','100','0.1')

    def test_quantity_changes_and_carry_in_are_exact(self):
        p=position(changes=[{'at_ms':START-1,'quantity':'2'},{'at_ms':START+HOUR,'quantity':'1'},
                            {'at_ms':START+2*HOUR,'quantity':'0'}])
        self.assertEqual(p.quantity_at(START-2),'0')
        self.assertEqual(p.quantity_at(START),'2')
        self.assertEqual(p.quantity_at(START+HOUR),'1')
        self.assertEqual(p.quantity_at(START+2*HOUR),'0')

    def test_inclusive_boundary_guard_and_invalid_timelines(self):
        p=position()
        self.assertTrue(p.boundary_ambiguous(START+75000,15000))
        self.assertFalse(p.boundary_ambiguous(START+75001,15000))
        for changes in ([],[{'at_ms':START,'quantity':'1'},{'at_ms':START,'quantity':'0'}],
                        [{'at_ms':START,'quantity':'1'},{'at_ms':START+1,'quantity':'1'}]):
            with self.assertRaises(ValidationError): PositionTimeline('p',IDENTITY,'BTCUSDT','long',changes)
        with self.assertRaises(ValidationError): QuantityChange(True,'1')

    def test_calendar_does_not_assume_constant_funding_interval(self):
        c=calendar(); self.assertEqual(c.settlement_times_ms[2]-c.settlement_times_ms[1],2*HOUR)
        self.assertNotEqual(c.settlement_times_ms[1]-c.settlement_times_ms[0],2*HOUR)
        self.assertEqual(calendar(times=[]).settlement_times_ms,())
        for times in ([START+HOUR,START+HOUR],[START+2*HOUR,START+HOUR],[START-1]):
            with self.assertRaises(ValidationError): calendar(times=times)

    def test_config_and_schema_contracts(self):
        for doc in ({'boundary_policy':'guess'},{'boundary_guard_ms':14999},{'boundary_guard_ms':True},
                    {'max_mark_age_ms':0},{'surprise':True}):
            with self.assertRaises(ValidationError): FundingConfig.from_dict(doc)
        with self.assertRaises(ValidationError): PositionTimeline.from_dict({'side':'long'})
        with self.assertRaises(ValidationError): SettlementCalendar.from_dict({'bad':True})
        with self.assertRaises(ValidationError): PositionTimeline('p','bad','BTCUSDT','long',[{'at_ms':0,'quantity':'1'}])

    def test_immutable_inputs_and_record_aliases(self):
        changes=[dict(at_ms=START,quantity='2')]; p=position(changes=changes)
        changes[0]['quantity']='999'; self.assertEqual(p.changes[0].quantity,'2')
        data=p.document(); data['changes'][0]['quantity']='888'; self.assertEqual(p.quantity_at(START),'2')
        d={'a':{'b':1}}; r=FundingRecord.create(d); d['a']['b']=2
        r.document()['a']['b']=3; self.assertEqual(r.document()['a']['b'],1)
