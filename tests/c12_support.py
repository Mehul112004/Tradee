"""Real C11 labels for nested C12 tests; deliberately small engineering gates."""
from pathlib import Path
from tradee.c11 import Simulator, SimulationStore
from tradee.c07 import ExecutionConfig, FeeSchedule
from tradee.c08 import CandidateConfig
from tradee.c06 import FundingConfig
from tradee.c11 import SimulationConfig
from tradee.c12 import EvidencePolicy
from tests.c10_support import START, BIN, simulation, config


def split(name, train_end, a, b, *, train_start=0, gap=0):
    return dict(name=name,train=dict(start_ms=START+train_start*BIN,end_ms=START+train_end*BIN,cutoff_ms=START+train_end*BIN),
                test=dict(start_ms=START+a*BIN,end_ms=START+b*BIN,cutoff_ms=START+b*BIN),purge_gap_ms=gap)


def plan(dev='a'*64, hold='b'*64, stress_dev='c'*64, stress_hold='d'*64, **kw):
    cfg=config().document()
    variants=[]
    for name,buffer,neighbor in (('a','0',None),('b','0.1','a')):
        variants.append(dict(name=name,hypothesis='Long prior-range breakout; frozen estimator buffer grid',development_runs=[dev],holdout_runs=[hold],
            estimator={**cfg,'lower_bound_buffer_r':buffer},rationale='Predeclared buffer neighborhood',parameters={'buffer_r':buffer},neighbor_of=neighbor))
        variants.append(dict(name=name+'_cost',hypothesis='Double assumed execution fees',development_runs=[stress_dev],holdout_runs=[stress_hold],
            estimator=cfg,rationale='Adverse taker/maker fee stress',parameters={'fee_multiplier':2},stress_of=name))
    policy=EvidencePolicy(bin_ms=BIN,block_bins=1,bootstrap_replicates=200,min_candidates=6,min_eligible_mature=6,min_occupied_spans=6).document()
    d=dict(name='engineering',family='range',thesis='Nested engineering baseline, no real-market edge claim',prior_research='TBot and all previously inspected data are development; synthetic fixture only',
        historical_trials=0,family_trial_budget=4,source_report_hashes={h:'e'*64 for h in (dev,hold,stress_dev,stress_hold)},variants=variants,
        folds=[dict(split=split('outer1',24,24,32),inner=[split('inner1',12,12,20)]),
               dict(split=split('outer2',36,36,44),inner=[split('inner2',20,20,28)])],
        holdout=dict(split=split('sealed',48,48,60),inner=[split('finalinner',28,28,40)]),
        holdout_status='uninspected',holdout_attestation='Synthetic fixture generated mechanically; later outcome data not consulted by selector',policy=policy)
    d.update(kw); return d


def stress(result, events):
    m=result.manifest.document()
    return Simulator(m['dataset'],m['scenarios'],m['metadata_snapshots'],m['metadata_versions'],
        FeeSchedule('0.001','0.0004','synthetic doubled fee stress'),ExecutionConfig.from_dict(m['execution']),
        CandidateConfig.from_dict(m['candidates']),FundingConfig.from_dict(m['funding']),m['calendars'],SimulationConfig.from_dict(m['config'])).run(lambda:iter(events))


def sources(root, *, holdout_positive=True, unknown_holdout=False):
    ss=SimulationStore(Path(root)/'c11.sqlite3')
    result,events=simulation(n=48); dev=ss.commit(result)['run_hash']; sd=ss.commit(stress(result,events))['run_hash']
    result,events=simulation(n=12,start=START+48*BIN,positive=holdout_positive,unknown_funding=unknown_holdout)
    hold=ss.commit(result)['run_hash']; sh=ss.commit(stress(result,events))['run_hash']
    d=plan(dev,hold,sd,sh); d['source_report_hashes']={h:ss.summary(h)['report_hash'] for h in (dev,hold,sd,sh)}
    return ss,d


def rows(n=12, *, start=START, unknown=False):
    return [dict(protocol_hash='p',candidate_id=str(i),detected_ms=start+i*BIN,symbol='BTCUSDT' if i%2 else 'ETHUSDT',fold='first' if i<n//2 else 'second',
        prediction=dict(ready=True,eligible=True),outcome_status='unresolved' if unknown else 'mature',net_r=None if unknown else ('1' if i%2 else '2'),
        label_start_ms=start+i*BIN+1000,label_end_ms=start+i*BIN+40000) for i in range(n)]
