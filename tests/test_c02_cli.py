from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from unittest.mock import patch

from tradee.cli import main
from tests.c02_support import DataCase, START, row


class DataCliTests(DataCase):
    def call(self, *args):
        out, err = StringIO(), StringIO()
        with patch('tradee.cli.Registry', return_value=self.registry), \
             patch('tradee.c02.cli.MarketStore', return_value=self.store), redirect_stdout(out), redirect_stderr(err):
            code = main(['data', *args])
        return code, out.getvalue(), err.getvalue()

    def test_import_snapshot_replay_and_bars_roundtrip(self):
        file = self.root/'candles.json'; file.write_text(json.dumps([row()]))
        self.assertEqual(self.call('import-rest', 'BTCUSDT', str(file))[0], 0)
        code, out, err = self.call('snapshot', '--symbols', 'BTCUSDT', '--start', '2027-01-15T08:00:00Z',
                                   '--end', '2027-01-15T08:01:00Z', '--mode', 'modeled', '--delay-ms', '100')
        self.assertEqual((code, err), (0, ''))
        digest = json.loads(out)['dataset_hash']
        self.assertEqual(self.call('dataset', digest)[0], 0)
        code, out, err = self.call('replay', digest)
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(json.loads(out)['available_ms'], START+60100)
        code, out, err = self.call('bars', digest, '--minutes', '1')
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(len(json.loads(out)), 1)

    def test_quality_nonready_exit_and_invalid_modeled_policy(self):
        digest = self.snapshot()
        code, out, err = self.call('quality', digest)
        self.assertEqual((code, err), (2, ''))
        self.assertFalse(json.loads(out)['ready'])
        code, out, err = self.call('snapshot', '--symbols', 'BTCUSDT', '--start', '2027-01-15T08:00:00Z',
                                   '--end', '2027-01-15T08:01:00Z', '--mode', 'modeled')
        self.assertEqual((code, out), (1, ''))
        self.assertIn('delay_ms', json.loads(err)['error'])

    def test_failed_import_reports_json_error(self):
        code, out, err = self.call('import-rest', 'BTCUSDT', str(self.root/'missing'))
        self.assertEqual((code, out), (1, ''))
        self.assertIn('error', json.loads(err))

    def test_real_module_entrypoint_end_to_end(self):
        from datetime import datetime, timezone
        from pathlib import Path
        import subprocess
        import sys
        import time
        from tests.support import FIXTURE_PATH
        root = Path(__file__).resolve().parents[1]
        db, market = str(self.root/'actual_c01.db'), str(self.root/'actual_c02.db')
        def invoke(*args):
            result = subprocess.run([sys.executable, '-m', 'tradee', '--db', db, *args], cwd=root,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        invoke('import', str(FIXTURE_PATH.resolve()))
        start = int(time.time()*1000)//60000*60000-600000
        file = self.root/'actual.json'; file.write_text(json.dumps([row(start)]))
        prefix = ['data', '--market-db', market]
        invoke(*prefix, 'import-rest', 'BTCUSDT', str(file))
        iso = lambda stamp: datetime.fromtimestamp(stamp/1000, timezone.utc).isoformat()
        ds = invoke(*prefix, 'snapshot', '--symbols', 'BTCUSDT', '--start', iso(start), '--end', iso(start+60000),
                    '--mode', 'modeled', '--delay-ms', '500')
        event = invoke(*prefix, 'replay', ds['dataset_hash'])
        self.assertEqual(event['available_ms'], start+60500)
        self.assertEqual(event['data']['close'], '101')
