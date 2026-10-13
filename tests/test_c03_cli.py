import json
import subprocess
import sys
from tests import test_c03_persistence
from tests.c02_support import DataCase


class FeatureCliTests(DataCase):
    prepared=test_c03_persistence.PersistenceTests.prepared

    def invoke(self,*args):
        result=subprocess.run([sys.executable,'-m','tradee','--db',self.registry.path,'features',
                               '--market-db',self.store.path,'--feature-db',str(self.root/'features.sqlite3'),*args],
                              capture_output=True,text=True,timeout=30)
        return result.returncode,json.loads(result.stdout or result.stderr)

    def test_catalog_explain_and_invalid_id(self):
        code,doc=self.invoke('list'); self.assertEqual(code,0); self.assertGreater(len(doc['features']),30)
        code,doc=self.invoke('explain','ema20_distance_atr14')
        self.assertEqual(code,0); self.assertIn('atr14',doc['evaluation_order'])
        code,doc=self.invoke('explain','unknown'); self.assertEqual(code,1); self.assertIn('error',doc)

    def test_complete_run_inspection_and_resume(self):
        d,c,_=self.prepared(); path=self.root/'config.json'; path.write_text(json.dumps(c.document()))
        code,summary=self.invoke('run',d['dataset_hash'],'--config',str(path))
        self.assertEqual(code,0); self.assertEqual(summary['snapshots'],8)
        self.assertEqual(self.invoke('run',d['dataset_hash'],'--config',str(path)),(0,summary))
        code,manifest=self.invoke('manifest',summary['run_hash']); self.assertEqual(code,0)
        self.assertEqual(manifest['dataset']['dataset_hash'],d['dataset_hash'])
        code,snapshot=self.invoke('snapshot',summary['latest'][0]['snapshot_hash'])
        self.assertEqual(code,0); self.assertTrue(snapshot['ready'])
        code,lineage=self.invoke('lineage',snapshot['lineage_hash']); self.assertEqual(code,0); self.assertTrue(lineage['events'])

    def test_bad_configuration(self):
        d,c,_=self.prepared(); path=self.root/'bad.json'; path.write_text('{"surprise":true}')
        code,doc=self.invoke('run',d['dataset_hash'],'--config',str(path))
        self.assertEqual(code,1); self.assertIn('error',doc)
