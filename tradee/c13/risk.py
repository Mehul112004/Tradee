"""Exact USDT linear exposure, conservative collateral and joint shock accounting."""
from decimal import Decimal
from tradee.c07.math import exact,ratio
from tradee.c06.contracts import decimal_text


def fresh_mark(state,instrument,when,policy):
    m=next((m for m in state.marks if m.instrument_id==instrument),None)
    if m is None or m.event_ms>when or m.available_ms>when or when-m.event_ms>=policy.max_mark_age_ms or when-m.available_ms>=policy.max_mark_age_ms: return None
    return m


def limits(rows,equity,cash,policy):
    reasons=[]
    with exact():
        risk=sum((r['risk'] for r in rows),Decimal(0)); gross=sum((r['notional'] for r in rows),Decimal(0)); collateral=sum((r['collateral'] for r in rows),Decimal(0))
        beta=sum((r['notional']*r['beta'].copy_abs() for r in rows),Decimal(0))
        budget=min(equity,cash); shock=Decimal(policy.stress_shock_fraction)
        closing=sum((r['closing_fee'] for r in rows),Decimal(0))
        signed=sum((r['sign']*r['notional'] for r in rows),Decimal(0))
        stresses=dict(all_marks_down=-signed*shock-closing,all_marks_up=signed*shock-closing,
            adverse_each_position=-gross*shock-closing)
        groups={}; horizons={}
        for r in rows:
            g=groups.setdefault(r['group'],dict(risk=Decimal(0),notional=Decimal(0))); g['risk']+=r['risk']; g['notional']+=r['notional']
            horizons[r['horizon']]=horizons.get(r['horizon'],Decimal(0))+r['risk']
        if budget<=0: reasons.append('nonpositive_spendable_equity')
        if any(r['risk']>budget*Decimal(policy.per_trade_risk_fraction) for r in rows): reasons.append('per_trade_stop_risk_limit')
        if len(rows)>policy.max_positions: reasons.append('position_slot_limit')
        for value,cap,reason in ((risk,policy.total_risk_fraction,'total_stop_risk_limit'),(gross,policy.gross_notional_fraction,'gross_notional_limit'),
                                 (collateral,policy.collateral_fraction,'collateral_limit'),(beta,policy.absolute_beta_notional_fraction,'absolute_beta_limit')):
            if value>budget*Decimal(cap): reasons.append(reason)
        if any(g['risk']>budget*Decimal(policy.group_risk_fraction) for g in groups.values()): reasons.append('correlation_group_risk_limit')
        if any(g['notional']>budget*Decimal(policy.group_notional_fraction) for g in groups.values()): reasons.append('correlation_group_notional_limit')
        if any(v>budget*Decimal(policy.horizon_risk_fraction) for v in horizons.values()): reasons.append('horizon_risk_limit')
        worst=max([Decimal(0)]+[-v for v in stresses.values()])
        if worst>budget*Decimal(policy.max_stress_loss_fraction): reasons.append('joint_stress_limit')
        return dict(reasons=sorted(set(reasons)),gross_notional_usdt=decimal_text(gross),stop_risk_usdt=decimal_text(risk),
            collateral_reserved_usdt=decimal_text(collateral),free_collateral_usdt=decimal_text(max(Decimal(0),budget-collateral)),
            absolute_beta_notional_usdt=decimal_text(beta),worst_stress_loss_usdt=decimal_text(worst),
            stress_pnl_usdt={k:decimal_text(v) for k,v in stresses.items()},positions_and_reservations=len(rows),
            groups={k:{f:decimal_text(v) for f,v in g.items()} for k,g in groups.items()},horizon_risk_usdt={k:decimal_text(v) for k,v in horizons.items()},
            unsupported_margin_breach=equity<=0 or gross>equity or collateral>min(cash,equity))


def inspect(state,when,policy):
    reasons=[]; rows=[]; unknown=[]; unrealized=Decimal(0); assets=policy.asset_risks.document()
    if state.as_of_ms>when or state.available_ms>when: reasons.append('account_snapshot_not_available')
    elif when-state.as_of_ms>=policy.max_snapshot_age_ms or when-state.available_ms>=policy.max_snapshot_age_ms: reasons.append('account_snapshot_stale')
    if policy.risk_map_available_ms>when: reasons.append('risk_map_not_yet_available')
    if not state.funding_known: reasons.append('account_funding_unknown')
    if not state.external_orders_known: reasons.append('external_open_orders_unknown')
    if len(state.positions)+len(state.reservations)>policy.max_positions_in_state: reasons.append('account_position_budget_exceeded')
    with exact():
        gap=Decimal(policy.stop_gap_bps)/10000
        for p in state.positions:
            mark=fresh_mark(state,p.instrument_id,when,policy); assignment=assets.get(p.symbol)
            if mark is None or assignment is None:
                unknown.append(p.position_id); continue
            q=Decimal(p.quantity); price=Decimal(mark.price); entry=Decimal(p.entry_price); stop=Decimal(p.stop_price); fee=Decimal(p.exit_fee_rate); sign=1 if p.side=='long' else -1
            unrealized+=sign*(price-entry)*q; worst=max(price,stop)
            if sign*(price-stop)<=0: reasons.append('open_position_stop_crossed')
            rows.append(dict(instrument_id=p.instrument_id,candidate_id=p.candidate_id,symbol=p.symbol,horizon=p.horizon,group=assignment['group'],beta=Decimal(assignment['beta']),sign=sign,
                risk=q*(max(Decimal(0),sign*(price-stop))+worst*(gap+fee)),notional=q*price,
                collateral=q*max(price,entry)+q*worst*fee,closing_fee=q*worst*fee))
        active=[r for r in state.reservations if when<r.expires_ms]
        for r in active:
            assignment=assets.get(r.symbol)
            if assignment is None: unknown.append(r.candidate_id); continue
            rows.append(dict(instrument_id=r.instrument_id,candidate_id=r.candidate_id,symbol=r.symbol,horizon=r.horizon,group=assignment['group'],beta=Decimal(assignment['beta']),sign=1 if r.side=='long' else -1,
                risk=Decimal(r.risk_usdt),notional=Decimal(r.notional_usdt),collateral=Decimal(r.collateral_usdt),closing_fee=Decimal(r.closing_fee_usdt)))
        if unknown: reasons.append('missing_fresh_mark_or_asset_risk_assignment')
        if len({r['instrument_id'] for r in rows})!=len(rows): reasons.append('overlapping_instrument_reservations')
        equity=None if unknown or not state.funding_known else Decimal(state.cash_usdt)+unrealized
        measure=None if equity is None else limits(rows,equity,Decimal(state.cash_usdt),policy)
        if measure is not None:
            reasons.extend(measure['reasons']); peak=max(Decimal(state.peak_equity_usdt),equity)
            if peak-equity>peak*Decimal(policy.max_drawdown_fraction): reasons.append('drawdown_pause')
        return dict(ready=not reasons,reasons=sorted(set(reasons)),equity_usdt=None if equity is None else decimal_text(equity),cash_usdt=state.cash_usdt,
            unrealized_gross_usdt=None if unknown else decimal_text(unrealized),exposure=measure,unknown_positions=unknown,
            active_reservations=[r.document() for r in active],rows=rows)
