from dataclasses import replace
import unittest
from tradee.c01 import ValidationError
from tradee.c03.catalog import BASELINE, CATALOG, FeatureConfig, definition, resolve
from tradee.c03.contracts import FeatureSnapshot, FeatureValue


class CatalogTests(unittest.TestCase):
    def test_baseline_has_fourteen_outputs_and_shared_dependencies(self):
        self.assertEqual(len(BASELINE),14)
        graph=resolve(BASELINE)
        self.assertEqual(graph.count('atr14'),1)
        self.assertLess(graph.index('ema20'),graph.index('ema20_distance_atr14'))

    def test_definition_hash_changes_with_formula_or_seed(self):
        original=definition('ema20')
        self.assertNotEqual(original.definition_hash,replace(original,formula='changed').definition_hash)
        self.assertNotEqual(original.definition_hash,replace(original,smoothers=((20,1,'ema',0),)).definition_hash)

    def test_dependency_cycles_fail(self):
        bad=replace(definition('ema20'),dependencies=('ema20',))
        with self.assertRaises(ValidationError):
            resolve(['ema20'],lookup=lambda _:bad)

    def test_config_is_copied_and_invalid_fields_fail(self):
        features=['rsi14']; config=FeatureConfig(features=features)
        features.append('atr14'); self.assertEqual(config.features,('rsi14',))
        for bad in ({'features':'rsi14'},{'features':['adx14']},{'timeframes':['7m']},
                    {'require_stable':1},{'seed_threshold':float('nan')},{'seed_threshold':0},
                    {'max_quote_age_ms':True},{'output_start_ms':10,'output_end_ms':5},
                    {'required_features':['missing']},{'surprise':True}):
            with self.subTest(bad=bad),self.assertRaises(ValidationError):
                FeatureConfig.from_dict(bad)

    def test_numeric_policy_and_units_inspectable(self):
        self.assertEqual(definition('spread_bps').units,'bps')
        self.assertIn('population',definition('bb20_upper').numeric_policy)
        with self.assertRaises(ValidationError):
            definition('simple_return_0')

    def test_snapshot_aliasing_and_value_contract(self):
        doc={'values':{'a':1}}; snap=FeatureSnapshot.create(doc)
        doc['values']['a']=2
        returned=snap.document(); returned['values']['a']=3
        self.assertEqual(snap.document()['values']['a'],1)
        with self.assertRaises(ValueError):
            FeatureValue(None,'valid',1,1)
        with self.assertRaises(ValueError):
            FeatureValue(float('nan'),'valid',1,1)
