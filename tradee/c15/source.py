"""Verified C14/C11/C13 evidence; outcomes stay owned by the shared C09 policy."""
from decimal import Decimal
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c06.contracts import decimal_text
from tradee.c07.math import exact
from tradee.c09 import TradeIntent
from tradee.c10.source import validate_outcome


def verified_cycle(entry,deployment,simulations,portfolios):
    c=entry['cycle']; m=deployment
    if c['deployment_hash']!=fingerprint(m) or fingerprint(c)!=entry['cycle_hash']: raise ValidationError('C15 cycle/deployment identity mismatch')
    a=simulations.summary(c['simulation']['run_hash']); b=portfolios.summary(c['portfolio']['run_hash'])
    if a!=c['simulation'] or b!=c['portfolio']: raise ValidationError('C15 source receipts differ from verified reports')
    manifest=simulations.manifest(a['run_hash'])
    if manifest['dataset']!=c['dataset'] or manifest['code_hash']!=m['code_hash']: raise ValidationError('C15 simulation producer/dataset differs from deployment')
    independent=simulations.report(a['report_hash'])['trades']; funded=portfolios.report(b['report_hash'])
    if funded['terminal_account']!=c['paper_account'] or funded['terminal_risk']!=c['paper_risk']: raise ValidationError('C15 paper book differs from funded replay')
    accepted={t['candidate_id']:t for t in funded['trades']}
    # C13 source keys end in trade_id; candidate identity is an explicit field.
    for s in c['signals']:
        t=accepted.get(s['candidate_id'])
        if (None if t is None else t['outcome'])!=s['paper_outcome']: raise ValidationError('C15 admitted outcome differs from shared C09 replay')
    return {t['candidate_id']:t for t in independent}


def outcome_row(signal,outcome,track,cycle_hash,cycle_ms,first,cutoff,lag,available_ms=None):
    """A new revision replaces a row in the current vintage, never prior reports."""
    s=signal; t=outcome
    if t is not None: validate_outcome(t,cycle_ms,cycle_ms+1,TradeIntent.from_dict(s['trade_intent']))
    known=None if t is None else t['outcome_known_ms']
    available=max(known or cycle_ms,cycle_ms) if available_ms is None else available_ms
    mature=bool(t and t['ready'] and known is not None and available+lag<cutoff)
    status='mature' if mature else 'unfilled' if t and t['status']=='unfilled' else 'unresolved' if t and t['status']=='unresolved' else 'pending'
    d=s['decision']; frozen=first.get('admission')
    prediction=(None if d is None else d.get('prediction')) if frozen is None else frozen['decision'].get('prediction')
    predicted=None if prediction is None else prediction.get('statistics',{}).get('mean_net_r')
    prospective=bool(frozen and t and frozen['as_of_ms']<=t['entry_ms'] and known is not None and frozen['as_of_ms']<known)
    economics={}
    if track=='portfolio' and d is not None and d.get('execution'):
        e=d['execution']; economics=dict(entry_costs=e.get('costs'),entry_funding_estimate=e.get('funding'),
            execution_delay_ms=e.get('elapsed_from_detection_ms'),modeled_fill=e.get('fill'),
            scope='Recorded-feed simulated execution; no measured exchange/user fills. Entry next-settlement estimate and full-hold settled funding have different horizons.')
        if t is not None:
            with exact():
                paper_fee=sum((Decimal(v['fee_usdt']) for v in t['state']['ledger'].values() if v['kind']=='entry'),Decimal(0))
                estimated_fee=Decimal(e['fill']['fee_usdt'])
                economics.update(entry_estimated_fee_usdt=decimal_text(estimated_fee),entry_paper_fee_usdt=decimal_text(paper_fee),
                    entry_fee_difference_usdt=decimal_text(paper_fee-estimated_fee),settled_hold_funding_usdt=t['funding_usdt'])
    if mature:
        with exact():
            if Decimal(t['net_usdt'])!=Decimal(t['gross_realized_usdt'])-Decimal(t['fees_usdt'])+Decimal(t['funding_usdt']): raise ValidationError('C15 net economics do not reconcile')
    return dict(signal_id=s['signal_id'],candidate_id=s['candidate_id'],symbol=s['candidate']['symbol'],side=s['candidate']['side'],
        family=s['candidate']['hypothesis_family'],track=track,detected_ms=s['detected_ms'],phase=s['phase'],
        decision=None if d is None else d['status'],prediction=prediction,predicted_mean_net_r=predicted,
        first_detected_cycle_hash=first['detection']['cycle_hash'],first_admission_cycle_hash=None if frozen is None else frozen['cycle_hash'],
        detection_to_first_cycle_ms=first['detection']['as_of_ms']-s['detected_ms'],
        decision_recorded_before_outcome=prospective,source_cycle_hash=cycle_hash,outcome_revision_hash=None if t is None else t['outcome_revision_hash'],
        outcome_available_ms=None if t is None else available,outcome_known_ms=known,
        label_start_ms=None if t is None else t['label_start_ms'],label_end_ms=None if t is None else t['label_end_ms'],
        status=status,net_usdt=t['net_usdt'] if mature else None,net_r=t['net_r'] if mature else None,
        gross_usdt=t['gross_realized_usdt'] if mature else None,fees_usdt=t['fees_usdt'] if mature else None,
        funding_usdt=t['funding_usdt'] if mature else None,economics=economics,
        outcome_source='hypothetical shared C09 policy',actual_user_fill=False)


def summarize(rows):
    from collections import Counter
    result={}
    for track in ('portfolio','independent'):
        subset=[r for r in rows if r['track']==track]; mature=[r for r in subset if r['status']=='mature']
        with exact():
            result[track]=dict(count=len(subset),statuses=dict(Counter(r['status'] for r in subset)),
                mature_net_usdt=decimal_text(sum((Decimal(r['net_usdt']) for r in mature),Decimal(0))),
                scope='Sum of mature paper labels only; unknown/open outcomes excluded. Independent signals do not share capital.' if track=='independent' else 'Mature admitted paper labels; use C13 wallet for open mark PnL and equity.')
    return result
