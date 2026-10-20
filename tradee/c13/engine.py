"""Pure deterministic batch allocation; callers own atomic reservation/fill state."""
from collections import defaultdict
from decimal import Decimal
from fractions import Fraction
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c03.contracts import FrozenRecord
from tradee.c06.contracts import decimal_text
from tradee.c07.math import exact,ratio
from tradee.c10.engine import estimate
from .contracts import AccountSnapshot,Offer,RiskPolicy,Reservation
from .risk import inspect,fresh_mark,limits


def allocate(state,offers,policy,recheck,evaluation_ms=None):
    state=state if isinstance(state,AccountSnapshot) else AccountSnapshot.from_dict(state)
    policy=policy if isinstance(policy,RiskPolicy) else RiskPolicy.from_dict(policy)
    offers=tuple(o if isinstance(o,Offer) else Offer.from_dict(o) for o in offers)
    if len(offers)>policy.max_offers or len({o.offer_id for o in offers})!=len(offers) or len({(o.intent.trade_id,o.request.document()['scenario']['horizon']) for o in offers})!=len(offers): raise ValidationError('Distinct bounded portfolio offers required')
    when=(offers[0].request.evaluation_ms if offers else state.as_of_ms) if evaluation_ms is None else evaluation_ms
    from tradee.c02.domain import integer
    integer(when,'allocation decision')
    before=inspect(state,when,policy); virtual=list(before.pop('rows')); equity=None if before['equity_usdt'] is None else Decimal(before['equity_usdt'])
    reservations=list(before['active_reservations']); seen=set(state.seen_candidates)|{p.candidate_id for p in state.positions}|{r.candidate_id for r in state.reservations}
    results={}; eligible=defaultdict(list); assets=policy.asset_risks.document()
    for offer in sorted(offers,key=lambda o:o.offer_id):
        q=offer.request.document(); c=q['candidate']; intent=offer.intent; reasons=list(before['reasons'])
        if q['evaluation_ms']!=when: raise ValidationError('Offer evaluation must equal the account decision clock')
        if c['candidate_id'] in seen: reasons.append('candidate_already_reserved_or_seen')
        if c['symbol'] not in assets: reasons.append('missing_asset_risk_assignment')
        prediction=estimate(offer.model,offer.request).document()
        if not prediction['eligible']: reasons.extend(['expectancy_not_eligible',*prediction['reasons']])
        d=dict(offer_id=offer.offer_id,candidate_id=c['candidate_id'],quantity=intent.quantity,model_hash=offer.model.digest,
            status='rejected',reasons=sorted(set(reasons)),prediction=prediction,execution=None,reservation=None,trade_intent=None,score=None)
        results[offer.offer_id]=d
        if reasons: continue
        execution=recheck(offer,when); execution=execution.document() if isinstance(execution,FrozenRecord) else dict(execution)
        d['execution']=execution
        if execution.get('intent_id')!=offer.execution_intent.intent_id or execution.get('instrument_id')!=c['instrument_id'] or execution.get('evaluation_as_of_ms')!=when:
            raise ValidationError('Execution recheck does not match the current offer')
        if not execution.get('ready'):
            d['reasons']=['execution_recheck_failed',*execution.get('reasons',[])]; continue
        fill=execution.get('fill')
        if (not fill or fingerprint({k:v for k,v in fill.items() if k!='revision_hash'})!=fill.get('revision_hash') or fill['quantity']!=intent.quantity or
                fill['side']!=offer.execution_intent.side or fill['execution_as_of_ms']!=when): raise ValidationError('Invalid exact-quantity execution evidence')
        mark=fresh_mark(state,c['instrument_id'],when,policy)
        if mark is None: d['reasons']=['missing_fresh_candidate_mark']; continue
        if execution.get('price_context',{}).get('mark_source_event_id')!=mark.event_id:
            d['reasons']=['account_mark_context_changed_refresh_snapshot']; continue
        with exact():
            quantity=Decimal(intent.quantity); price=Decimal(fill['price']); stop=Decimal(intent.levels()['stop']); mp=Decimal(mark.price); sign=1 if c['side']=='long' else -1
            if price<=0 or Decimal(fill['fee_usdt'])!=quantity*price*Decimal(q['fees']['taker_rate']): raise ValidationError('Entry fee differs from exact C07 taker cost protocol')
            if sign*(price-stop)<=0: d['reasons']=['entry_stop_invalid']; continue
            fee=Decimal(q['fees']['taker_rate']); worst=max(price,mp,stop); gap=Decimal(policy.stop_gap_bps)/10000
            risk=quantity*((price-stop)*sign+worst*(gap+fee))+Decimal(fill['fee_usdt'])
            notional=quantity*max(price,mp); collateral=notional+Decimal(fill['fee_usdt'])+quantity*worst*fee
            row=dict(instrument_id=c['instrument_id'],candidate_id=c['candidate_id'],symbol=c['symbol'],horizon=q['scenario']['horizon'],group=assets[c['symbol']]['group'],
                beta=Decimal(assets[c['symbol']]['beta']),sign=sign,risk=risk,notional=notional,collateral=collateral,closing_fee=quantity*worst*fee)
            lower=Decimal(prediction['uncertainty']['lower_mean_net_r']); economic_risk=quantity*abs(price-stop)
            score=Fraction(lower)*Fraction(economic_risk)*3600000/(Fraction(collateral)*intent.policy.max_holding_ms)
            d['score']=dict(objective='lower net R × actual entry stop risk / fully reserved collateral / maximum holding hours',
                value=ratio(Decimal(score.numerator),Decimal(score.denominator)),numerator=str(score.numerator),denominator=str(score.denominator))
            eligible[(c['candidate_id'],intent.policy.policy_hash,q['scenario']['horizon'])].append((offer,d,row,score))
    # The smallest eligible size anchors candidate rank; size selection then uses
    # the largest compatible tested quantity that fits remaining shared budgets.
    groups=[]
    for key,items in eligible.items():
        cid=key[0]
        identities={(i[0].intent.candidate.document()['strategy_hash'],i[0].intent.policy.policy_hash,i[0].request.document()['scenario']['horizon']) for i in items}
        if len(identities)!=1 or len({i[0].intent.quantity for i in items})!=len(items): raise ValidationError('One scenario and model per candidate/quantity required')
        anchor=min(items,key=lambda i:Decimal(i[0].intent.quantity)); detected=anchor[0].intent.candidate.document()['detected_ms']
        groups.append((anchor[3],detected,cid,items))
    rank=0
    for _,_,cid,items in sorted(groups,key=lambda g:(-g[0],g[1],g[2])):
        rank+=1; chosen=False
        for offer,d,row,_ in sorted(items,key=lambda i:Decimal(i[0].intent.quantity).copy_negate()):
            d['rank']=rank
            if chosen: d['reasons']=['alternate_quantity_not_selected']; continue
            if cid in seen: d['reasons']=['candidate_already_selected']; continue
            if any(r['instrument_id']==row['instrument_id'] for r in virtual): d['reasons']=['instrument_already_exposed_across_strategies_or_horizons']; continue
            with exact():
                spendable=min(equity,Decimal(state.cash_usdt))
                reasons=[]
                if row['risk']>spendable*Decimal(policy.per_trade_risk_fraction): reasons.append('per_trade_stop_risk_limit')
                measured=limits(virtual+[row],equity,Decimal(state.cash_usdt),policy); reasons.extend(measured['reasons'])
            if reasons: d['reasons']=sorted(set(reasons)); continue
            c=offer.intent.candidate.document()
            reservation=Reservation(cid,c['instrument_id'],c['symbol'],c['side'],offer.intent.quantity,decimal_text(row['risk']),decimal_text(row['notional']),decimal_text(row['collateral']),
                offer.request.document()['scenario']['horizon'],when,c['expires_ms'],closing_fee_usdt=decimal_text(row['closing_fee'])).document()
            d.update(status='admitted',reasons=[],reservation=reservation,trade_intent=offer.intent.document())
            reservations.append(reservation); virtual.append(row); seen.add(cid); chosen=True
    after=None if equity is None else limits(virtual,equity,Decimal(state.cash_usdt),policy)
    return FrozenRecord.create(dict(schema_version=1,component='C13',kind='allocation_batch',policy_hash=policy.policy_hash,
        account_snapshot_hash=fingerprint(state.document()),as_of_ms=when,decisions=[results[k] for k in sorted(results)],risk_before=before,risk_after=after,
        reservations_after=reservations,seen_candidates_after=sorted(seen),ready=any(d['status']=='admitted' for d in results.values()),live_approved=False,
        note='Proposals reserve shared risk; they are not fills, orders, alerts or actual account changes. Caller must atomically compare-and-swap the snapshot before reserving. Fully collateralized paper limits; no exchange liquidation model.'))
