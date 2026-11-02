import json
import subprocess
import sys

from tests.c02_support import DataCase, START, row


class ObservationCliTests(DataCase):
    def invoke(self, command, *args):
        result = subprocess.run([sys.executable, '-m', 'tradee', '--db', self.registry.path,
                                 command, '--market-db', self.store.path,
                                 '--observation-db', str(self.root/(command+'.sqlite3')), *map(str, args)],
                                capture_output=True, text=True, timeout=30)
        return result.returncode, json.loads(result.stdout or result.stderr)

    def test_explanations_need_no_database_and_define_no_strategy(self):
        for command in ('context', 'structure'):
            code, doc = self.invoke(command, 'explain')
            self.assertEqual(code, 0)
            self.assertEqual(doc['purpose'], 'measurements_only')
            self.assertFalse((self.root/(command+'.sqlite3')).exists())

    def test_raw_run_queries_and_invalid_inputs(self):
        self.ingest([row(START+i*60000) for i in range(5)])
        dataset = self.store.snapshot(['BTCUSDT'], START, START+5*60000, mode='modeled', delay_ms=0)
        for command in ('context', 'structure'):
            with self.subTest(command=command):
                path = self.root/(command+'.json'); path.write_text(json.dumps(dict(timeframes=['1m'])))
                args = ('run', dataset['dataset_hash'], '--config', path)
                code, summary = self.invoke(command, *args)
                self.assertEqual(code, 0)
                self.assertEqual(summary['snapshots'], 5)
                self.assertEqual(self.invoke(command, *args), (0, summary))
                self.assertEqual(self.invoke(command, 'summary', summary['run_hash']), (0, summary))
                code, page = self.invoke(command, 'records', summary['run_hash'], '--limit', '2')
                self.assertEqual(code, 0)
                self.assertEqual(len(page['records']), 2)
                self.assertEqual(self.invoke(command, 'records', summary['run_hash'], '--limit', '0')[0], 1)
                path.write_text('{"entry_rule":"sweep"}')
                code, doc = self.invoke(command, *args)
                self.assertEqual(code, 1)
                self.assertIn('Unknown observation configuration', doc['error'])
