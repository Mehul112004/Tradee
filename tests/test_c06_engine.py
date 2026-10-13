from copy import deepcopy
import json
import unittest
from tradee.c01 import ValidationError
from tradee.c06 import FundingEngine, FundingConfig
from tests.c06_support import dataset, position, calendar, funding, mark, START, HOUR, IDENTITY


def engine(positions=None,calendars=None,config=None):
    return FundingEngine(dataset(),positions if positions is not None else [position()],
                         [calendar()] if calendars is None else calendars,config)


class FundingEngineTests(unittest.TestCase):
    def test_partial_exit_and_variable_settlement_times_golden_totals(self):
        p=position(changes=[dict(at_ms=START+60000,quantity='2'),dict(at_ms=START+2*HOUR-60000,quantity='1'),
                            dict(at_ms=START+4*HOUR-60000,quantity='0')])
        a=engine([p,position('short','short','3')])
        for e in (funding(1,START+HOUR),funding(2,START+2*HOUR,'-0.002','120'),funding(3,START+4*HOUR,'0','110')):
            a.push(e)
        r=a.report().document(); self.assertTrue(r['ready'])
        self.assertEqual([p['total_cashflow_usdt'] for p in r['positions']],['0.04','-0.42'])
        self.assertEqual(r['positions'][0]['cashflows'][2]['status'],'not_exposed')

    def test_missing_calendar_total_is_null_not_zero(self):
        a=engine(calendars=[]); a.push(funding(1,START+HOUR))
        p=a.report().document()['positions'][0]
        self.assertFalse(p['ready']); self.assertIsNone(p['total_cashflow_usdt'])
        self.assertEqual(p['known_cashflow_subtotal_usdt'],'-0.2')
        self.assertEqual(p['coverage_status'],'unknown_schedule')

    def test_expected_missing_settlement_and_zero_rate_are_distinct(self):
        a=engine(); a.push(funding(1,START+HOUR,'0'))
        r=a.report().document()['positions'][0]
        self.assertEqual(r['cashflows'][0]['amount_usdt'],'0')
        self.assertEqual(r['cashflows'][1]['status'],'missing_settlement')
        self.assertIsNone(r['total_cashflow_usdt'])

    def test_no_exposure_does_not_need_settled_rate(self):
        p=position(changes=[dict(at_ms=START-2*HOUR,quantity='1'),dict(at_ms=START-HOUR,quantity='0')])
        a=engine([p]); r=a.report().document()['positions'][0]
        self.assertTrue(r['ready']); self.assertEqual(r['total_cashflow_usdt'],'0')
        self.assertTrue(all(e['status']=='not_exposed' for e in r['cashflows']))

    def test_strict_settlement_boundary_is_ambiguous_nominal_is_explicit(self):
        p=position(changes=[dict(at_ms=START+HOUR+5000,quantity='2')])
        a=engine([p]); a.push(funding(1,START+HOUR)); r=a.report(START+HOUR+10000).document()['positions'][0]
        self.assertEqual(r['cashflows'][0]['status'],'boundary_ambiguous'); self.assertIsNone(r['total_cashflow_usdt'])
        b=engine([p],config=FundingConfig(boundary_policy='nominal')); b.push(funding(1,START+HOUR))
        self.assertEqual(b.report(START+HOUR+10000).document()['positions'][0]['total_cashflow_usdt'],'0')

    def test_same_timestamp_open_close_in_nominal_policy(self):
        for quantity,want in (('2','-0.2'),('0','0')):
            changes=[dict(at_ms=START+HOUR,quantity=quantity)]
            if quantity=='0': changes.insert(0,dict(at_ms=START,quantity='2'))
            a=engine([position(changes=changes)],config=FundingConfig(boundary_policy='nominal'))
            a.push(funding(1,START+HOUR))
            self.assertEqual(a.report(START+HOUR).document()['positions'][0]['total_cashflow_usdt'],want)

    def test_late_revision_never_mutates_prior_report_or_doubles_charge(self):
        a=engine(calendars=[calendar(times=[START+HOUR])]); first=funding(1,START+HOUR)
        a.push(first); old=a.report(START+HOUR); frozen=old.serialized
        later=funding(2,START+HOUR,'0.0015',available=START+HOUR+100)
        a.push(later); new=a.report(START+HOUR+100)
        e1=old.document()['positions'][0]['cashflows'][0]; e2=new.document()['positions'][0]['cashflows'][0]
        self.assertEqual(e1['cashflow_key'],e2['cashflow_key'])
        self.assertNotEqual(e1['revision_hash'],e2['revision_hash'])
        self.assertEqual(e2['amount_usdt'],'-0.3')
        self.assertEqual(len(new.document()['positions'][0]['cashflows']),1)
        self.assertEqual(old.serialized,frozen)
        self.assertFalse(a.push(later))
        with self.assertRaises(ValidationError): a.push(first)

    def test_same_millisecond_availability_is_exact_prefix(self):
        a=engine(calendars=[calendar(times=[START+HOUR])])
        a.push(funding(1,START+HOUR,available=START+2*HOUR))
        first=a.report(START+2*HOUR)
        a.push(funding(2,START+HOUR,'0.002',available=START+2*HOUR))
        second=a.report(START+2*HOUR)
        self.assertEqual(first.document()['positions'][0]['total_cashflow_usdt'],'-0.2')
        self.assertEqual(second.document()['positions'][0]['total_cashflow_usdt'],'-0.4')

    def test_estimates_only_use_mark_prefix_never_settled_future_rate(self):
        a=engine(); a.push(mark(1,START+HOUR-1000,rate='0.003',next_ms=START+HOUR))
        before=a.context(a.positions[0],START+HOUR-1000)
        self.assertEqual(before['estimated_cashflow_usdt'],'-0.6')
        a.push(funding(2,START+HOUR,rate='0.02'))
        after=a.context(a.positions[0],START+HOUR)
        self.assertEqual(after['status'],'expired_estimate'); self.assertIsNone(after['estimated_cashflow_usdt'])
        self.assertEqual(before['rate'],'0.003')

    def test_mark_freshness_boundary_and_late_old_observation(self):
        a=engine(); a.push(mark(1,START+HOUR))
        a.push(mark(2,START+HOUR-1000,rate='0.9',available=START+HOUR+100))
        self.assertEqual(a.context(a.positions[0],START+HOUR+4999)['rate'],'0.003')
        self.assertEqual(a.context(a.positions[0],START+HOUR+5000)['status'],'stale_estimate')

    def test_future_quantity_change_does_not_enter_estimate(self):
        p=position(changes=[dict(at_ms=START,quantity='1'),dict(at_ms=START+2*HOUR,quantity='999')])
        a=engine([p]); a.push(mark(1,START+HOUR,next_ms=START+3*HOUR))
        self.assertEqual(a.context(p,START+HOUR)['estimated_cashflow_usdt'],'-0.3')

    def test_schedule_conflict_and_incomplete_calendar_bounds(self):
        for c,want in ((calendar(times=[]),'schedule_conflict'),(calendar(start=START+1),'unknown_schedule')):
            a=engine(calendars=[c]); a.push(funding(1,START+HOUR))
            self.assertEqual(a.report().document()['positions'][0]['coverage_status'],want)

    def test_different_instrument_identity_is_not_stitched(self):
        a=engine(); a.push(funding(1,START+HOUR,identity=IDENTITY+'-relisted'))
        self.assertEqual(a.report().document()['positions'][0]['known_cashflow_subtotal_usdt'],'0')
        self.assertFalse(a.report().document()['ready'])

    def test_checkpoint_parity_at_every_split_including_correction(self):
        events=[mark(1,START+100),funding(2,START+HOUR),funding(3,START+2*HOUR,'-0.002','120'),
                funding(4,START+HOUR,'0.0015',available=START+3*HOUR),mark(5,START+3*HOUR)]
        uninterrupted=engine()
        for e in events: uninterrupted.push(e)
        want=uninterrupted.report().serialized
        for split in range(len(events)+1):
            a=engine()
            for e in events[:split]: a.push(e)
            b=FundingEngine.restore(a.dataset,a.positions,a.calendars,a.config,a.decision_ms,json.loads(json.dumps(a.checkpoint())))
            for e in events[split:]: b.push(e)
            self.assertEqual(b.report().serialized,want)

    def test_future_prefix_bad_event_and_mixed_availability_rejected(self):
        a=engine(); a.push(funding(1,START+HOUR))
        with self.assertRaises(ValidationError): a.report(START+HOUR-1)
        for field,bad in (('availability_basis','modeled'),('final',False),('key','bad'),('id',True)):
            e=funding(2,START+2*HOUR); e[field]=bad
            with self.assertRaises(ValidationError): a.push(e)
        self.assertEqual(a.event_count,1)

    def test_bad_checkpoint_or_config_mismatch_rejected(self):
        a=engine(); a.push(funding(1,START+HOUR)); original=a.checkpoint()
        for field,bad in (('run_hash','bad'),('cursor',None),('event_count',-1),('last_event_hash','f'*64),('latest',None)):
            cp=deepcopy(original); cp[field]=bad
            with self.assertRaises(ValidationError): FundingEngine.restore(a.dataset,a.positions,a.calendars,a.config,a.decision_ms,cp)
        with self.assertRaises(ValidationError):
            FundingEngine.restore(a.dataset,a.positions,a.calendars,FundingConfig(boundary_policy='nominal'),a.decision_ms,original)

    def test_report_window_excludes_future_expected_settlements(self):
        a=engine(); a.push(funding(1,START+HOUR))
        r=a.report(START+HOUR).document()['positions'][0]
        self.assertTrue(r['ready']); self.assertEqual(len(r['cashflows']),1)

    def test_modeled_funding_and_duplicate_position_ids_are_rejected(self):
        d=dataset(); d['mode']='modeled'
        with self.assertRaises(ValidationError): FundingEngine(d)
        with self.assertRaises(ValidationError): engine([position(),position()])

    def test_cashflow_revision_identity_is_stable_across_evaluation_times(self):
        a=engine(calendars=[calendar(times=[START+HOUR])]); a.push(funding(1,START+HOUR))
        first=a.report(START+HOUR).document()['positions'][0]['cashflows'][0]
        second=a.report(START+HOUR+1).document()['positions'][0]['cashflows'][0]
        self.assertEqual(first['revision_hash'],second['revision_hash'])
        self.assertNotEqual(first['recognition_as_of_ms'],second['recognition_as_of_ms'])

    def test_closed_position_and_forecast_do_not_create_extra_settled_charge(self):
        p=position(changes=[dict(at_ms=START,quantity='1'),dict(at_ms=START+HOUR+60000,quantity='0')])
        a=engine([p],calendars=[calendar(times=[START+HOUR])]); a.push(funding(1,START+HOUR))
        a.push(mark(2,START+2*HOUR,rate='0.99',next_ms=START+3*HOUR))
        r=a.report(START+2*HOUR).document()['positions'][0]
        self.assertEqual(r['total_cashflow_usdt'],'-0.1')
        self.assertEqual(r['estimate']['estimated_cashflow_usdt'],'0')
        self.assertEqual(len(r['cashflows']),1)

    def test_appended_future_evidence_cannot_rewrite_prior_report(self):
        a=engine(); a.push(funding(1,START+HOUR)); original=a.report(START+HOUR).serialized
        a.push(funding(2,START+2*HOUR,'0.5'))
        with self.assertRaises(ValidationError): a.report(START+HOUR)
        b=engine(); b.push(funding(1,START+HOUR))
        self.assertEqual(b.report(START+HOUR).serialized,original)

    def test_event_cannot_cross_run_horizon_or_omit_provenance(self):
        a=engine()
        for bad in (funding(1,START+HOUR,available=START+8*HOUR),
                    dict(funding(1,START+HOUR),raw_sha256='bad'),dict(funding(1,START+HOUR),schema_version=True)):
            with self.assertRaises(ValidationError): a.push(bad)
        self.assertEqual(a.event_count,0)
