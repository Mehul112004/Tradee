"""Keyed current-value ledger: fill fees once, funding revisions replace amounts."""
from decimal import Decimal
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c06.contracts import decimal_text
from tradee.c07.math import exact,ratio


def book_fill(state,fill,reason,initial=False):
    key=fill['fill_key']; revision=fill['revision_hash']
    if key in state['ledger']:
        if state['ledger'][key]['revision_hash']==revision: return False
        raise ValidationError('Cannot revise an already executed paper fill')
    with exact():
        q,p=Decimal(fill['quantity']),Decimal(fill['price']); remaining=Decimal(state['remaining_quantity'])
        if q<=0 or (not initial and q>remaining): raise ValidationError('Invalid ledger fill quantity')
        gross=Decimal(0) if initial else (1 if state['side']=='long' else -1)*(p-Decimal(state['entry_price']))*q
        state['ledger'][key]=dict(kind='entry' if initial else 'exit',revision_hash=revision,amount_usdt=decimal_text(gross-Decimal(fill['fee_usdt'])),
            gross_usdt=decimal_text(gross),fee_usdt=fill['fee_usdt'],quantity=fill['quantity'],price=fill['price'],at_ms=fill['execution_as_of_ms'],reason=reason,
            source_event_id=fill['source_event_id'])
        if initial:
            state['initial_quantity']=fill['quantity']; state['entry_price']=fill['price']; state['entry_ms']=fill['execution_as_of_ms']
            remaining=q
        else: remaining-=q
        state['remaining_quantity']=decimal_text(remaining)
    stamp=fill['execution_as_of_ms']
    changes=state['quantity_changes']
    if changes and changes[-1]['at_ms']==stamp: raise ValidationError('Two quantity changes in one millisecond are ambiguous')
    changes.append(dict(at_ms=stamp,quantity=state['remaining_quantity']))
    return True


def reconcile_funding(state,position):
    current={e['cashflow_key']:e for e in position['cashflows']}
    for key,e in current.items():
        old=state['ledger'].get(key)
        doc=dict(kind='funding',revision_hash=e['revision_hash'],amount_usdt=e['amount_usdt'],status=e['status'],at_ms=e['funding_time_ms'],
                 source_event_id=e['source_event_id'])
        if old!=doc: state['ledger'][key]=doc
    return position['total_cashflow_usdt']


def outcome(state,funding,known_ms,complete_prefix):
    fills=[v for v in state['ledger'].values() if v['kind'] in ('entry','exit')]
    with exact():
        gross=sum((Decimal(v['gross_usdt']) for v in fills),Decimal(0))
        fees=sum((Decimal(v['fee_usdt']) for v in fills),Decimal(0))
        subtotal=sum((Decimal(v['amount_usdt']) for v in state['ledger'].values() if v['amount_usdt'] is not None),Decimal(0))
        risk=None if state['entry_price'] is None else abs(Decimal(state['entry_price'])-Decimal(state['levels']['stop']))*Decimal(state['initial_quantity'])
        closed=state['status']=='closed'
        net=None if not closed or funding is None else gross-fees+Decimal(funding)
        reliable=closed and net is not None and not state['ambiguity_flags'] and complete_prefix
        revision=fingerprint(dict(ledger=state['ledger'],status=state['status'],ambiguity=state['ambiguity_flags'],funding=funding))
        if reliable and state['outcome_revision_hash']!=revision:
            state['outcome_revision_hash']=revision; state['outcome_known_ms']=known_ms
        if not reliable:
            state['outcome_revision_hash']=None; state['outcome_known_ms']=None
        return dict(trade_id=state['trade_id'],status=state['status'],remaining_quantity=state['remaining_quantity'],entry_ms=state['entry_ms'],
            exit_ms=state['exit_ms'],label_start_ms=state['entry_ms'],label_end_ms=state['exit_ms'],
            outcome_known_ms=state['outcome_known_ms'],outcome_revision_hash=state['outcome_revision_hash'],ready=reliable,
            holding_ms=None if state['entry_ms'] is None or state['exit_ms'] is None else state['exit_ms']-state['entry_ms'],
            gross_realized_usdt=decimal_text(gross),fees_usdt=decimal_text(fees),funding_usdt=funding,
            known_net_subtotal_usdt=decimal_text(subtotal),net_usdt=None if net is None else decimal_text(net),
            risk_usdt=None if risk is None else decimal_text(risk),gross_r=None if risk is None else ratio(gross,risk),
            net_r=None if net is None or risk is None else ratio(net,risk),
            profitable=None if not reliable else net>0,target_before_stop=state['target_before_stop'],
            label_status='mature' if reliable else 'unfilled' if state['status'] in ('expired','cancelled') else 'unresolved',
            mfe_price=state['mfe_price'],mae_price=state['mae_price'],excursion_coverage='sampled trigger observations; not continuous extrema',
            mfe_r=None if risk is None else ratio((1 if state['side']=='long' else -1)*(Decimal(state['mfe_price'])-Decimal(state['entry_price']))*Decimal(state['initial_quantity']),risk),
            mae_r=None if risk is None else ratio((1 if state['side']=='long' else -1)*(Decimal(state['mae_price'])-Decimal(state['entry_price']))*Decimal(state['initial_quantity']),risk),
            ambiguity_flags=sorted(state['ambiguity_flags']),reason=state['exit_reason'],
            note='Fill prices already include execution shortfall; subtract fees once and add signed settled funding once.')
