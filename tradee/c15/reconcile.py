"""Re-execute pinned raw market inputs through the same production policies."""
from pathlib import Path
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c06 import FundingConfig
from tradee.c07 import FeeSchedule,ExecutionConfig
from tradee.c08 import CandidateConfig
from tradee.c08.metadata import capture
from tradee.c11 import Simulator,Scenario,SimulationConfig
from tradee.c13 import PortfolioReplay,RiskPolicy,ReplayConfig
from tradee.c14 import SessionSpec
from tradee.c14.pipeline import source_prefix
from .source import verified_cycle


def reconcile(monitor,name,market,when,report_hash=None):
    head,source,p=monitor._source(name,when)
    if Path(market.path).resolve() in {Path(s.path).resolve() for s in (monitor.store,monitor.signals,monitor.simulations,monitor.portfolios)}: raise ValidationError('Separate C02 reconciliation input required')
    key=head['report_hash'] if report_hash is None else report_hash
    r=monitor.store.artifact(key)
    if r.get('manifest_hash')!=head['manifest_hash'] or r.get('kind')!='forward_report' or r['observed_ms']>when: raise ValidationError('C15 replay/report mismatch')
    if r['source']['cycle_hash'] is None: raise ValidationError('A recorded C14 cycle is required for reconciliation')
    try:
        checks=_rebuild(monitor,source,market,r)
        reasons=[] if all(checks.values()) else ['replay_content_mismatch']
    except ValidationError:
        checks=dict(verified_replay_completed=False); reasons=['replay_evidence_unverifiable']
    return monitor.store.reconciliation(name,dict(component='C15',kind='forward_replay_reconciliation',report_hash=key,cycle_hash=r['source']['cycle_hash'],at_ms=when,
        checks=checks,reasons=reasons,ready=all(checks.values()),live_approved=False,scope='Reproducibility under the same paper model; not validation against actual fills.'))


def _rebuild(monitor,source,market,r):
    c=monitor.signals.artifact(r['source']['cycle_hash']); m=source['head']['manifest']; spec=SessionSpec.from_dict(m['spec']); cfg=spec.runtime
    verified_cycle(dict(cycle_hash=fingerprint(c),cycle=c),m,monitor.simulations,monitor.portfolios)
    ds=market.dataset(c['dataset']['dataset_hash']); events=list(market.replay(ds['dataset_hash']))
    if len(events)>cfg.max_events: raise ValidationError('C15 replay event budget exceeded')
    prefix=ds==c['dataset'] and len(events)==c['source_count'] and source_prefix(events)==c['source_prefix_hash']
    cc=CandidateConfig.from_dict(m['candidates']); snapshots,versions=capture(market.registry,ds,cc)
    settings=SimulationConfig(decision_start_ms=spec.start_ms,decision_end_ms=min(spec.end_ms,c['as_of_ms']+1),sample_interval_ms=m['replay']['sample_interval_ms'],max_candidates=cfg.max_candidates,max_artifacts=cfg.max_artifacts)
    simulator=Simulator(ds,[Scenario.from_dict(m['scenario'])],snapshots,versions,FeeSchedule.from_dict(m['fees']),ExecutionConfig.from_dict(m['execution']),cc,FundingConfig.from_dict(m['funding']),m['calendars'],settings)
    rebuilt=simulator.run(lambda:iter(events))
    output=PortfolioReplay(monitor.simulations,{c['simulation']['run_hash']:c['simulation']['report_hash']},[m['model']],events,RiskPolicy.from_dict(m['risk']),ReplayConfig.from_dict(m['replay'])).run()
    checks=dict(raw_prefix=prefix,simulation_manifest=rebuilt.manifest.digest==c['simulation']['run_hash'],simulation_report=rebuilt.report.digest==c['simulation']['report_hash'],
                portfolio_manifest=output[0].digest==c['portfolio']['run_hash'],portfolio_report=output[1].digest==c['portfolio']['report_hash'])
    return checks
