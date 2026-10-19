"""Exact descriptive attribution and regular independent-scenario P&L marks."""
from collections import Counter
from decimal import Decimal

from tradee.c01 import ValidationError
from tradee.c06.contracts import decimal_text
from tradee.c07.math import exact, ratio


def total(rows, field):
    return sum((Decimal(r[field]) for r in rows), Decimal(0))


def metrics(trades):
    mature=[t for t in trades if t['ready']]
    filled=[t for t in trades if t['entry_ms'] is not None]
    values=sorted(Decimal(t['net_r']) for t in mature)
    with exact():
        wins=sum((Decimal(t['net_usdt']) for t in mature if Decimal(t['net_usdt'])>0), Decimal(0))
        losses=-sum((Decimal(t['net_usdt']) for t in mature if Decimal(t['net_usdt'])<0), Decimal(0))
        subtotal=total(mature, 'net_usdt')
        return dict(candidates=len(trades), filled=len(filled), closed=sum(t['status']=='closed' for t in trades),
            mature=len(mature), unfilled=sum(t['label_status']=='unfilled' for t in trades),
            unresolved=sum(t['label_status']=='unresolved' for t in trades),
            net_usdt=decimal_text(subtotal) if all(t['ready'] or t['label_status']=='unfilled' for t in trades) else None,
            mature_net_subtotal_usdt=decimal_text(subtotal), gross_realized_usdt=decimal_text(total(trades, 'gross_realized_usdt')),
            fees_usdt=decimal_text(total(trades, 'fees_usdt')),
            mature_funding_usdt=decimal_text(total(mature, 'funding_usdt')),
            win_fraction=ratio(Decimal(sum(t['profitable'] for t in mature)), Decimal(len(mature))),
            mean_net_usdt=ratio(subtotal, Decimal(len(mature))),
            mean_net_r=ratio(total(mature, 'net_r'), Decimal(len(mature))),
            profit_factor=ratio(wins, losses), positive_net_usdt=decimal_text(wins), negative_net_usdt=decimal_text(losses),
            net_r_order_statistics=dict(minimum=decimal_text(values[0]) if values else None,
                p05=decimal_text(values[(len(values)*5+99)//100-1]) if values else None,
                median_lower=decimal_text(values[(len(values)-1)//2]) if values else None,
                maximum=decimal_text(values[-1]) if values else None),
            interpretation='Descriptive mature-only outcomes with explicit coverage; overlapping independent scenarios are dependent observations, not a forecast or portfolio return.')


def attribution(trades):
    costs={k:Decimal(0) for k in ('delay_drift_usdt', 'spread_crossing_usdt', 'extra_slippage_and_rounding_usdt', 'implementation_shortfall_usdt', 'fee_usdt')}
    ledger_gross=Decimal(0); ledger_fees=Decimal(0); ledger_funding=Decimal(0)
    with exact():
        for t in trades:
            state=t['state']; ledger=state['ledger']
            attempts={a['estimate']['fill']['fill_key']:a['estimate'] for a in state['attempts'] if a['estimate'].get('fill')}
            entries=[v for v in ledger.values() if v['kind']=='entry']; exits=[v for v in ledger.values() if v['kind']=='exit']
            if entries:
                if len(entries)!=1 or Decimal(entries[0]['quantity'])-sum((Decimal(v['quantity']) for v in exits),Decimal(0))!=Decimal(state['remaining_quantity']):
                    raise ValidationError('Simulation quantity reconciliation failed')
            for key, value in ledger.items():
                if value['kind']=='funding':
                    if value['amount_usdt'] is not None: ledger_funding+=Decimal(value['amount_usdt'])
                    continue
                a=attempts.get(key)
                if a is None or a['fill']['revision_hash']!=value['revision_hash']: raise ValidationError('Simulation fill has no matching execution estimate')
                for k in costs: costs[k]+=Decimal(a['costs'][k])
                if Decimal(a['costs']['delay_drift_usdt'])+Decimal(a['costs']['spread_crossing_usdt'])+Decimal(a['costs']['extra_slippage_and_rounding_usdt'])!=Decimal(a['costs']['implementation_shortfall_usdt']):
                    raise ValidationError('Execution shortfall reconciliation failed')
                ledger_gross+=Decimal(value['gross_usdt']); ledger_fees+=Decimal(value['fee_usdt'])
            if total([t], 'gross_realized_usdt')!=sum((Decimal(v['gross_usdt']) for v in entries+exits), Decimal(0)) or total([t], 'fees_usdt')!=sum((Decimal(v['fee_usdt']) for v in entries+exits), Decimal(0)):
                raise ValidationError('Simulation report does not reconcile to fills')
            if t['net_usdt'] is not None and Decimal(t['net_usdt'])!=Decimal(t['gross_realized_usdt'])-Decimal(t['fees_usdt'])+Decimal(t['funding_usdt']):
                raise ValidationError('Simulation net reconciliation failed')
        if costs['fee_usdt']!=ledger_fees: raise ValidationError('Simulation fee attribution failed')
        return dict(reconciled=True, gross_realized_usdt=decimal_text(ledger_gross), fees_usdt=decimal_text(ledger_fees),
            known_funding_subtotal_usdt=decimal_text(ledger_funding), execution={k:decimal_text(v) for k,v in costs.items()},
            exit_reasons=dict(sorted(Counter(t['reason'] or 'no_exit' for t in trades).items())),
            ambiguity_flags=dict(sorted(Counter(flag for t in trades for flag in t['ambiguity_flags']).items())),
            note='Implementation shortfall is explanatory and already embedded in fills; never subtract it again. Known funding subtotal is not certified complete funding.')


def valuation(engine, report, when, config):
    """Use only observed fresh marks, or the explicitly declared C07 bar proxy.

    Gross unrealized value excludes hypothetical liquidation costs. Actual paid
    fees and C06 settled funding are booked separately; no forecast funding.
    """
    missing=[]; unrealized=Decimal(0); sources=[]
    with exact():
        for t in report['trades']:
            s=t['state']; q=Decimal(s['remaining_quantity'])
            if not q: continue
            e=(engine.market.candles.get(s['instrument_id']) if engine.execution.market_model=='modeled_bar'
               else engine.market.funding.marks.get(s['instrument_id']))
            stamp=None if e is None else (e['data']['close_ms']+1 if e['kind']=='candle' else e['event_ms'])
            if e is None or not e['final'] or stamp>when or e['available_ms']>when or when-stamp>=config.max_valuation_age_ms or when-e['available_ms']>=config.max_valuation_age_ms:
                missing.append(s['trade_id']); continue
            mark=Decimal(e['data']['close'] if e['kind']=='candle' else e['data']['mark_price'])
            unrealized+=(1 if s['side']=='long' else -1)*(mark-Decimal(s['entry_price']))*q
            sources.append(dict(trade_id=s['trade_id'],event_id=e['id'],event_ms=stamp,available_ms=e['available_ms'],price=decimal_text(mark),
                basis='explicit_bar_close_proxy' if e['kind']=='candle' else 'recorded_mark'))
        gross=total(report['trades'], 'gross_realized_usdt'); fees=total(report['trades'], 'fees_usdt')
        funding_known=all(t['funding_usdt'] is not None for t in report['trades'])
        funding=sum((Decimal(t['funding_usdt']) for t in report['trades'] if t['funding_usdt'] is not None), Decimal(0))
        known_cash=sum((Decimal(t['known_net_subtotal_usdt']) for t in report['trades']),Decimal(0))
        return dict(at_ms=when, gross_realized_usdt=decimal_text(gross), fees_usdt=decimal_text(fees),
            funding_usdt=decimal_text(funding) if funding_known else None,
            unrealized_gross_usdt=decimal_text(unrealized) if not missing else None,
            pnl_usdt=decimal_text(gross-fees+funding+unrealized) if not missing and funding_known else None,
            known_cash_subtotal_usdt=decimal_text(known_cash), missing_marks=missing, mark_sources=sources,
            open_trades=sum(Decimal(t['remaining_quantity'])>0 for t in report['trades']),
            input_cursor=engine.cursor, input_prefix_hash=engine.prefix_hash,
            note='Independent gross mark valuation plus booked cash flows; no shared capital or estimated closing fee/spread.')


def regular_diagnostics(samples):
    peak=Decimal(0); drawdown=Decimal(0); missing=0
    with exact():
        for s in samples:
            if s['pnl_usdt'] is None: missing+=1; continue
            value=Decimal(s['pnl_usdt']); peak=max(peak,value); drawdown=max(drawdown,peak-value)
    return dict(samples=len(samples), missing_samples=missing, complete=not missing,
        max_pnl_drawdown_usdt=decimal_text(drawdown) if samples and not missing else None,
        available_sample_drawdown_lower_bound_usdt=decimal_text(drawdown) if samples else None,
        portfolio_equity=None, annualized_return=None, sharpe=None,
        note='Regular independent-scenario P&L diagnostic; the zero-P&L initial baseline is included. No portfolio capital/return series or leverage model exists.')
