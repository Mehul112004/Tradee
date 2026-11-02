"""Actual-process raw-input verification of EMA200, C04 and C05 foundations."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
START = 1788220800000  # 2026-09-01 00:00 UTC
MINUTE = 60000


def run_e2e(folder):
    root = Path(folder).resolve(); root.mkdir(parents=True, exist_ok=True)
    if any(root.glob('*.sqlite3')):
        raise ValueError('Verification requires a fresh output directory')
    commands = []

    def write(name, doc):
        path = root/name; path.write_text(json.dumps(doc, indent=2)+'\n'); return path

    def invoke(*args, expected=0):
        result = subprocess.run([sys.executable, '-m', 'tradee', '--db', str(root/'c01.sqlite3'), *map(str, args)],
                                cwd=ROOT, capture_output=True, text=True, timeout=60)
        if result.returncode != expected:
            raise AssertionError(result.stderr or result.stdout)
        commands.append(dict(args=list(map(str, args)), exit_code=result.returncode))
        return json.loads(result.stdout or result.stderr)

    def data(*args):
        return invoke('data', '--market-db', root/'c02.sqlite3', *args)

    def observe(command, *args, expected=0):
        return invoke(command, '--market-db', root/'c02.sqlite3',
                      '--observation-db', root/(command+'.sqlite3'), *args, expected=expected)

    invoke('import', ROOT/'tests/fixtures/exchange_info.json')
    closes = [Decimal('100') + Decimal(i % 11)/10 for i in range(1589)]
    closes[1584] = Decimal(115)
    candles = [[START+i*MINUTE, str(c), str(c+1), str(c-1), str(c), '1000', START+(i+1)*MINUTE-1,
                str(c*1000), 5, '700', str(c*700), '0'] for i, c in enumerate(closes)]
    data('import-rest', 'BTCUSDT', write('candles.json', candles))
    iso = lambda stamp: datetime.fromtimestamp(stamp/1000, timezone.utc).isoformat()
    dataset = data('snapshot', '--symbols', 'BTCUSDT', '--kinds', 'candle', '--start', iso(START),
                   '--end', iso(START+len(candles)*MINUTE), '--mode', 'modeled', '--delay-ms', '0')
    context_config = write('context_config.json', dict(timeframes=['1m'], output_start_ms=START+1580*MINUTE))
    structure_config = write('structure_config.json', dict(timeframes=['1m'], output_start_ms=START+1580*MINUTE))
    for command in ('context', 'structure'):
        if observe(command, 'explain')['purpose'] != 'measurements_only':
            raise AssertionError('Unexpected strategy surface')

    # A real SQL failure leaves the committed raw prefix intact; a fresh CLI
    # process then resumes through modeled replay IDs without losing outputs.
    from tradee.c05 import StructureStore
    structure_store = StructureStore(root/'structure.sqlite3')
    with structure_store.connection() as db:
        db.execute("CREATE TRIGGER injected BEFORE INSERT ON snapshots WHEN (SELECT COUNT(*) FROM checkpoints)>0 BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    failure = observe('structure', 'run', dataset['dataset_hash'], '--config', structure_config,
                      '--batch-size', '512', expected=1)
    if 'injected failure' not in failure.get('error', ''):
        raise AssertionError('Expected storage failure was not reported')
    with structure_store.connection() as db:
        if db.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] != 0:
            raise AssertionError('Failed snapshot batch was partially committed')
        db.execute('DROP TRIGGER injected')
    structure = observe('structure', 'run', dataset['dataset_hash'], '--config', structure_config)
    context = observe('context', 'run', dataset['dataset_hash'], '--config', context_config)
    for command, config, summary in (('structure', structure_config, structure), ('context', context_config, context)):
        if not summary['completed'] or summary['snapshots'] != 9:
            raise AssertionError('Output range reset warm-up or lost snapshots')
        if observe(command, 'run', dataset['dataset_hash'], '--config', config) != summary:
            raise AssertionError('Rerun was not idempotent')
        manifest = observe(command, 'manifest', summary['run_hash'])
        if manifest['dataset']['dataset_hash'] != dataset['dataset_hash']:
            raise AssertionError('Missing pinned source identity')
    last_context = observe('context', 'snapshot', context['latest'][0]['snapshot_hash'])
    values = last_context['feature_snapshot']['values']
    if not last_context['ready'] or values['spread_bps']['status'] != 'missing_source':
        raise AssertionError('Stable EMA context or optional quote policy failed')
    with localcontext() as ctx:
        ctx.prec = 60
        ema = sum(closes[:200])/200
        for close in closes[200:]:
            ema += Decimal(2)/201*(close-ema)
    if not math.isclose(values['ema200']['value'], float(ema), rel_tol=1e-12):
        raise AssertionError('EMA differs from independent decimal recurrence')
    last_structure = observe('structure', 'snapshot', structure['latest'][0]['snapshot_hash'])
    high = next(l for l in last_structure['levels'] if l['kind'] == 'previous_day' and l['side'] == 'high')
    if high['price'] != '102' or high['known_ms'] != START+1440*MINUTE:
        raise AssertionError('Previous UTC day includes future prices or incomplete evidence')
    swing = next(l for l in last_structure['levels'] if l['kind'] == 'swing' and l['anchor_ms'] == START+1584*MINUTE)
    if swing['price'] != '116' or swing['confirmed_ms'] != START+1587*MINUTE:
        raise AssertionError('Swing confirmation lag was lost')
    if last_structure['coverage']['previous_week'] != 'anchor_incomplete':
        raise AssertionError('Missing week history was fabricated')
    page = observe('structure', 'records', structure['run_hash'], '--limit', '3')
    second = observe('structure', 'records', structure['run_hash'], '--limit', '3', '--after-sequence', page['next_sequence'])
    if [r['sequence'] for r in second['records']] != [4, 5, 6]:
        raise AssertionError('Pagination skipped evidence')
    observe('structure', 'lineage', last_structure['lineage_hash'])
    if any(k in last_structure for k in ('candidate', 'entry', 'stop', 'target', 'side')):
        raise AssertionError('A strategy was introduced into the prerequisites')
    result = dict(passed=True, commands=len(commands), context=context, structure=structure,
                  independent_ema200=str(ema), previous_day_high=high, confirmed_swing=swing,
                  artifacts_directory=str(root), checks=[
                      'raw C01/C02 imports through actual CLI processes', 'independent Decimal EMA200 oracle',
                      'full default stabilization with output-only range', 'complete UTC previous-day evidence',
                      'right-bar swing confirmation', 'explicit missing week/quote coverage',
                      'atomic SQL failure and new-process resume', 'idempotency and pagination',
                      'measurement-only scope'])
    write('e2e_report.json', result); write('e2e_commands.json', commands)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path); args = parser.parse_args()
    if args.output:
        result = run_e2e(args.output)
    else:
        with tempfile.TemporaryDirectory(prefix='tradee-structure-prerequisites-') as folder:
            result = run_e2e(folder)
            result['artifacts_directory'] = 'temporary artifacts removed after verification'
    print(json.dumps(result, indent=2))
