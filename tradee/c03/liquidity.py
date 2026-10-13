"""Best-quote diagnostics; no depth or fill claims."""
from decimal import Decimal, localcontext
from .rolling import finite


def quote_values(quote, decision_ms, max_age_ms, basis):
    if quote is None:
        return {}, 'missing_source'
    age = decision_ms-quote['event_ms']
    ages = {'quote_event_age_ms': float(age)}
    if basis == 'recorded':
        ages['quote_receipt_age_ms'] = float(decision_ms-quote['received_ms'])
    if age >= max_age_ms:
        return ages, 'stale_input'
    with localcontext() as ctx:
        ctx.prec = 120
        b,a,B,A = (Decimal(quote['data'][k]) for k in ('bid','ask','bid_qty','ask_qty'))
        mid = (a+b)/2
        result = dict(mid_price=finite(mid), spread_bps=finite(10000*(a-b)/mid),
                      top_bid_quote_notional=finite(b*B), top_ask_quote_notional=finite(a*A), **ages)
        if B+A:
            result['top_base_imbalance'] = finite((B-A)/(B+A))
    return result, 'valid'
