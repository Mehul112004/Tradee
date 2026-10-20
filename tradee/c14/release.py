"""Load a complete frozen research/portfolio bridge without granting live approval."""
import platform
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c03.contracts import FrozenRecord
from tradee.c06.engine import code_hash
from tradee.c10.engine import verified_model
from tradee.c13 import RiskPolicy,ReplayConfig
from tradee.c11 import Scenario
from .contracts import SessionSpec


def load_release(research,portfolios,simulations,experiment,portfolio_run,spec,calendars=()):
    spec=spec if isinstance(spec,SessionSpec) else SessionSpec.from_dict(spec)
    receipt=research.check_portfolio(experiment,portfolios,portfolio_run)
    release=research.release(experiment); p=portfolios.manifest(portfolio_run)
    if not release['ready'] or release['research_status']!='research_candidate' or not receipt['ready']: raise ValidationError('Passing frozen research release and portfolio compatibility receipt required')
    if release['live_approved'] is not False or receipt['promotion_authorized'] is not False: raise ValidationError('Unsupported promotion contract')
    if release['code_hash']!=code_hash() or release['python']!=platform.python_version(): raise ValidationError('Research runtime differs; regenerate a counted release')
    model=verified_model(release['model']); source=model.document()['fit']['sources'][0]
    if source['run_hash'] not in release['variant']['development_runs'] or simulations.summary(source['run_hash'])['report_hash']!=source['report_hash']:
        raise ValidationError('Frozen training source content differs from research release')
    m=simulations.manifest(source['run_hash'])
    scenarios=m['scenarios']
    if len(scenarios)!=1: raise ValidationError('C14 baseline requires a single frozen release/scenario; multi-release composition remains a research gate')
    if spec.start_ms<=max(p['dataset']['as_of_ms'],model.document()['available_ms']): raise ValidationError('Prospective paper session must begin after frozen final evidence')
    scenario=Scenario.from_dict(scenarios[0]); minimum=scenario.policy.max_holding_ms+scenario.policy.max_exit_wait_ms+60000
    if spec.tail_ms<minimum: raise ValidationError('Session tail must cover the holding/exit/funding observation horizon')
    risk=RiskPolicy.from_dict(p['policy']); replay=ReplayConfig.from_dict(p['config'])
    if replay.decision_start_ms is not None or replay.decision_end_ms is not None: raise ValidationError('Prospective baseline requires a frozen replay recipe with source-owned windows')
    from tradee.c06 import SettlementCalendar
    cals=[(c if isinstance(c,SettlementCalendar) else SettlementCalendar.from_dict(c)).document() for c in calendars]
    if len({c['instrument_id'] for c in cals})!=len(cals): raise ValidationError('Duplicate C14 settlement calendar')
    for c in cals:
        if c['start_ms']>spec.warmup_start_ms or c['end_ms']<spec.tail_end_ms: raise ValidationError('Frozen funding calendars must cover the full paper session/tail')
    return FrozenRecord.create(dict(schema_version=1,component='C14',kind='paper_deployment',spec=spec.document(),
        research=dict(experiment_hash=experiment,release_hash=release['release_hash'],model_hash=model.digest,compatibility_hash=fingerprint(receipt),portfolio_run_hash=portfolio_run),
        model=model.document(),scenario=scenario.document(),execution=m['execution'],fees=m['fees'],funding=m['funding'],candidates=m['candidates'],
        risk=risk.document(),replay=replay.document(),calendars=cals,code_hash=code_hash(),python=platform.python_version(),
        live_approved=False,promotion_authorized=False,scope='Prospective shadow paper policy and optional PAPER TEST fill notifications; no user entry instructions, actual fills or exchange orders'))
