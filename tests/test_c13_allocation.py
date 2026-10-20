from copy import deepcopy
from dataclasses import replace
from decimal import localcontext
import tempfile
import unittest
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c13 import allocate,AccountSnapshot,Offer
from tests.c13_support import setup,batch,policy


class AllocationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.ss,cls.pins,cls.model,cls.events=setup(cls.tmp.name)
        cls.state,cls.offers,execute=batch(cls.ss,cls.pins,cls.model,cls.events)
        cls.execute=staticmethod(execute)
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()
    def run_batch(self,state=None,offers=None,p=None,execute=None):
        return allocate(state or self.state,self.offers if offers is None else offers,p or policy(),execute or self.execute).document()
    def changed(self,**kw): return AccountSnapshot.from_dict(dict(self.state.document(),**kw))
    def admitted(self,d): return [a for a in d['decisions'] if a['status']=='admitted']
    def test_shared_cash_selects_two_tested_sizes_without_scaling(self):
        d=self.run_batch(); a=self.admitted(d)
        self.assertEqual(sorted(x['quantity'] for x in a),['0.5','1'])
        self.assertEqual(len({x['reservation']['instrument_id'] for x in a}),2)
        self.assertEqual(d['risk_after']['gross_notional_usdt'],'153.3')
        self.assertFalse(d['risk_after']['reasons']); self.assertFalse(d['live_approved'])
    def test_permutations_and_decimal_context_preserve_batch_hash(self):
        a=self.run_batch()
        with localcontext() as ctx:
            ctx.prec=3; b=self.run_batch(offers=list(reversed(self.offers)))
        self.assertEqual(a,b)
    def test_horizons_compete_for_same_candidate_and_instrument(self):
        d=self.run_batch(); a=self.admitted(d)
        self.assertEqual({v['reservation']['horizon'] for v in a},{'intraday'})
        self.assertTrue(any('candidate_already_selected' in v['reasons'] for v in d['decisions']))
    def test_position_slots_limit_shared_book(self):
        d=self.run_batch(p=policy(max_positions=1)); self.assertEqual(len(self.admitted(d)),1)
        self.assertTrue(any('position_slot_limit' in a['reasons'] for a in d['decisions']))
    def test_each_budget_can_independently_block_new_risk(self):
        cases=[('per_trade_risk_fraction','per_trade_stop_risk_limit'),('total_risk_fraction','total_stop_risk_limit'),
            ('group_risk_fraction','correlation_group_risk_limit'),('horizon_risk_fraction','horizon_risk_limit'),
            ('gross_notional_fraction','gross_notional_limit'),('group_notional_fraction','correlation_group_notional_limit'),
            ('absolute_beta_notional_fraction','absolute_beta_limit'),('collateral_fraction','collateral_limit'),('max_stress_loss_fraction','joint_stress_limit')]
        for key,reason in cases:
            with self.subTest(key=key):
                d=self.run_batch(p=policy(**{key:'0.00001'})); self.assertFalse(d['ready']); self.assertTrue(any(reason in a['reasons'] for a in d['decisions']))
    def test_unknown_account_coverage_never_calls_executor(self):
        for kw in ({'funding_known':False},{'external_orders_known':False}):
            d=self.run_batch(state=self.changed(**kw),execute=lambda *a:self.fail('Unknown account reached execution'))
            self.assertFalse(d['ready'])
    def test_missing_or_changed_mark_context_is_rejected(self):
        for marks,reason in (([],'missing_fresh_candidate_mark'),([dict(m,event_id=m['event_id']+1000) for m in self.state.document()['marks']],'account_mark_context_changed_refresh_snapshot')):
            d=self.run_batch(state=self.changed(marks=marks)); self.assertFalse(d['ready']); self.assertTrue(any(reason in a['reasons'] for a in d['decisions']))
    def test_quantity_without_matching_training_protocol_cannot_borrow_estimate(self):
        q=self.offers[0].request.document(); q['scenario']['quantity']='0.7'
        offer=Offer(q,self.model.document()); d=self.run_batch(offers=[offer],execute=lambda *a:self.fail('Untested size executed'))
        self.assertFalse(d['ready']); self.assertIn('expectancy_not_eligible',d['decisions'][0]['reasons'])
    def test_low_expectancy_and_declared_admission_buffer_block_without_execution(self):
        # This is a separately fitted model policy, not a changed prediction.
        from tradee.c10 import fit,publish
        from tradee.c10.source import snapshot
        from tests.c10_support import config,window
        training=self.model.document()['fit']['sources'][0]['run_hash']
        cfg=config(lower_bound_buffer_r='100'); model=publish(fit(snapshot(self.ss,[training],window(),cfg),cfg),window().cutoff_ms,'modeled')
        offers=[Offer(o.request.document(),model.document()) for o in self.offers]
        self.assertFalse(self.run_batch(offers=offers,execute=lambda *a:self.fail('Ineligible estimate executed'))['ready'])
    def test_seen_identity_blocks_repeat_even_if_reservations_expire(self):
        d=self.run_batch(); state=self.changed(seen_candidates=d['seen_candidates_after'])
        self.assertFalse(self.run_batch(state=state)['ready'])
    def test_ready_execution_must_match_identity_quantity_fee_and_hash(self):
        for field,value in (('intent_id','wrong'),('evaluation_as_of_ms',0),('quantity','2'),('fee_usdt','0')):
            def bad(o,t):
                d=self.execute(o,t).document()
                if field in ('intent_id','evaluation_as_of_ms'): d[field]=value
                else:
                    d['fill'][field]=value
                    d['fill']['revision_hash']=fingerprint({k:v for k,v in d['fill'].items() if k!='revision_hash'})
                return d
            with self.subTest(field=field),self.assertRaises(ValidationError): self.run_batch(execute=bad)
    def test_failed_current_execution_suppresses_previously_executable_offer(self):
        def failed(o,t):
            d=self.execute(o,t).document(); d.update(ready=False,fill=None,reasons=['stale_quote']); return d
        d=self.run_batch(execute=failed); self.assertFalse(d['ready']); self.assertEqual(d['reservations_after'],[])
    def test_duplicate_and_over_budget_offers_fail_explicitly(self):
        for offers,p in ((self.offers*2,policy()),(self.offers,policy(max_offers=1))):
            with self.assertRaises(ValidationError): self.run_batch(offers=offers,p=p)
    def test_mixed_decision_clocks_fail(self):
        q=self.offers[0].request.document(); q['evaluation_ms']+=1
        with self.assertRaises(ValidationError): allocate(self.state,[Offer(q,self.model.document())],policy(),self.execute,evaluation_ms=self.state.as_of_ms)
    def test_empty_batch_is_auditable_and_has_no_admission(self):
        d=self.run_batch(offers=[]); self.assertFalse(d['ready']); self.assertEqual(d['decisions'],[])
