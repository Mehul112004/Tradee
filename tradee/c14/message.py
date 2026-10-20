"""Plain, bounded, reproducible paper-fill notices, never actionable entry advice."""
from datetime import datetime,timezone
from tradee.c01 import ValidationError


def utc(ms): return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')


def format_notice(manifest,signal,guard):
    c=signal['candidate']; intent=signal['trade_intent']; fill=signal['decision']['execution']['fill']; levels=signal['paper_outcome']['state']['levels']
    prediction=guard['prediction']; lower=prediction['uncertainty']['lower_mean_net_r']; refs=manifest['research']; costs=guard['execution']['costs']
    lines=['PAPER TEST — NO TRADE INSTRUCTION',f"{c['symbol']} {c['side'].upper()} | {c['timeframe']} | {manifest['scenario']['horizon']}",
        f"Setup: {c['hypothesis_family']}",f"Evaluated paper fill: {fill['price']} USDT | size {fill['quantity']}",f"Paper fill time: {utc(signal['entry_ms'])}",
        f"Planned stop: {levels['stop']} | target: {levels['target']}",f"Reference/trigger: {c['reference_price']} / {c['breakout_level']}",
        f"Notice expires: {utc(signal['expires_ms'])}",f"Setup entry window ends: {utc(c['expires_ms'])}",
        f"Lower mean net R: {lower} (conditional research estimate; not a probability)",
        f"Entry-leg execution + fee estimate: {costs['execution_plus_fee_cost_usdt']} USDT",f"Known paper funding: {signal['paper_outcome']['funding_usdt']} USDT",
        'A recorded paper fill is not a user fill. Stops and simulated fills are not guaranteed.',
        'Research compatibility only; portfolio promotion and actionable live signals remain unavailable.',
        'Signal: '+signal['signal_id'],'Model: '+refs['model_hash'],'Research release: '+refs['release_hash'],
        'Fresh check: '+utc(guard['checked_ms'])]
    text='\n'.join(lines)
    if len(text)>4096: raise ValidationError('Paper notice exceeds Telegram text limit')
    return text
