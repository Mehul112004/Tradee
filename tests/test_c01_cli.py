"""Operator contracts and polling lifecycle, using isolated databases."""

from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tradee.cli import main, timestamp
from tradee.c01 import ProviderError
from tests.support import FIXTURE_PATH


class CliLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.args = ['--db', str(Path(self.temp.name) / 'registry.sqlite3')]

    def run_cli(self, args):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(self.args + args)
        return code, out.getvalue(), err.getvalue()

    def test_health_becomes_ready_after_offline_import(self):
        self.assertEqual(self.run_cli(['health'])[0], 2)
        code, out, err = self.run_cli(['import', str(FIXTURE_PATH)])
        self.assertEqual((code, err), (0, ''))
        self.assertEqual(json.loads(out)['symbols'], 3)
        code, out, err = self.run_cli(['health'])
        self.assertEqual((code, err), (0, ''))
        self.assertTrue(json.loads(out)['ready'])

    def test_operator_errors_are_json_and_nonzero(self):
        for args in (['import', str(Path(self.temp.name) / 'missing.json')],
                     ['snapshot', 'missing'], ['version', 'missing'],
                     ['--max-age-seconds', '0', 'health'], ['--enabled', '', 'health'],
                     ['watch', '--interval-seconds', '0'],
                     ['universe', '--as-of', '2026-09-19T12:00:00']):
            with self.subTest(args=args):
                code, out, err = self.run_cli(args)
                self.assertEqual((code, out), (1, ''))
                self.assertIsInstance(json.loads(err)['error'], str)

    def test_timezone_equivalent_inputs(self):
        self.assertEqual(timestamp('2026-09-19T12:00:00Z'), timestamp('2026-09-19T17:30:00+05:30'))
        with self.assertRaises(ValueError):
            timestamp('2026-09-19T12:00:00')

    def test_watch_refreshes_immediately_then_waits_and_interrupts(self):
        with patch('tradee.cli.Registry.refresh', return_value={'ok': True}) as refresh, \
             patch('tradee.cli.time.sleep', side_effect=KeyboardInterrupt) as sleep:
            code, out, err = self.run_cli(['watch', '--interval-seconds', '20'])
        self.assertEqual((code, err), (130, ''))
        self.assertEqual(json.loads(out), {'ok': True})
        refresh.assert_called_once()
        sleep.assert_called_once_with(20)

    def test_watch_halts_on_permanent_provider_error(self):
        with patch('tradee.cli.Registry.refresh', side_effect=ProviderError('banned', halt_polling=True)) as refresh, \
             patch('tradee.cli.time.sleep') as sleep:
            code, out, err = self.run_cli(['watch'])
        self.assertEqual((code, out), (1, ''))
        self.assertEqual(json.loads(err)['error'], 'banned')
        refresh.assert_called_once()
        sleep.assert_not_called()

    def test_watch_respects_server_cooldown_and_recovers(self):
        effects = [ProviderError('rate limited', retry_after_seconds=120), {'ok': True}]
        with patch('tradee.cli.Registry.refresh', side_effect=effects) as refresh, \
             patch('tradee.cli.time.sleep', side_effect=[None, KeyboardInterrupt]) as sleep:
            code, out, err = self.run_cli(['watch', '--interval-seconds', '10'])
        self.assertEqual(code, 130)
        self.assertEqual(json.loads(out), {'ok': True})
        self.assertEqual(json.loads(err)['error'], 'rate limited')
        self.assertEqual(refresh.call_count, 2)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [120, 10])

    def test_watch_recovers_after_validation_failure(self):
        with patch('tradee.cli.Registry.refresh', side_effect=[ValueError('bad metadata'), {'ok': True}]), \
             patch('tradee.cli.time.sleep', side_effect=[None, KeyboardInterrupt]) as sleep:
            code, out, err = self.run_cli(['watch'])
        self.assertEqual(code, 130)
        self.assertEqual(json.loads(out), {'ok': True})
        self.assertEqual(json.loads(err)['error'], 'bad metadata')
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [900, 900])

    def test_real_module_entrypoint_persists_between_processes(self):
        def invoke(*args):
            return subprocess.run([sys.executable, '-m', 'tradee', *self.args, *args],
                                  capture_output=True, text=True, timeout=15,
                                  cwd=Path(__file__).resolve().parents[1])
        imported = invoke('import', str(FIXTURE_PATH.resolve()))
        self.assertEqual(imported.returncode, 0, imported.stderr)
        saved = invoke('universe', '--save', '--members-only')
        self.assertEqual(saved.returncode, 0, saved.stderr)
        document = json.loads(saved.stdout)
        self.assertEqual(document['members'], ['BTCUSDT', 'ETHUSDT'])
        loaded = invoke('snapshot', document['snapshot_hash'])
        self.assertEqual(loaded.returncode, 0, loaded.stderr)
        self.assertEqual(json.loads(loaded.stdout)['members'], document['members'])
