"""Shared replay/persistence plumbing for measurement-only C04/C05 engines."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path

from tradee.c01 import Registry, ValidationError
from tradee.c01.domain import canonical, fingerprint
from tradee.c02 import MarketStore
from tradee.c03 import FeatureEngine
from tradee.c03.contracts import RunManifest
from tradee.c03.store import FeatureStore


class ConfigDocument:
    def document(self):
        return json.loads(canonical(asdict(self)))

    @property
    def config_hash(self):
        return fingerprint(self.document())

    @classmethod
    def from_dict(cls, doc):
        if not isinstance(doc, dict) or set(doc) - set(cls.__dataclass_fields__):
            raise ValidationError('Unknown observation configuration fields or invalid object')
        return cls(**doc)


def timeframes(values):
    from tradee.c03.catalog import TIMEFRAMES
    if (not isinstance(values, (list, tuple)) or not values
            or any(not isinstance(v, str) or v not in TIMEFRAMES for v in values)):
        raise ValidationError('Explicit supported observation timeframes required')
    return tuple(dict.fromkeys(values))


class ObservationEngine:
    """One C03 child; outputs carry its evidence and never create candidates."""
    def __init__(self, dataset, config):
        self.config = config
        self.dataset = deepcopy(dataset)
        self.features = FeatureEngine(dataset, config.feature_config())
        self.manifest = RunManifest.create(dict(
            schema_version=1, component=self.COMPONENT, checkpoint_schema=1,
            dataset=dataset, config=config.document(), config_hash=config.config_hash,
            feature_manifest=self.features.manifest.document(),
            definitions=self.definitions(), purpose='measurements_only; no strategy or trade policy'))

    @property
    def cursor(self):
        return self.features.cursor

    @property
    def lineages(self):
        return self.features.lineages

    def envelope(self, feature):
        doc = feature.document()
        return dict(schema_version=1, component=self.COMPONENT, run_hash=self.manifest.digest,
                    config_hash=self.config.config_hash, dataset_hash=self.dataset['dataset_hash'],
                    instrument_id=doc['instrument_id'], timeframe=doc['timeframe'],
                    target_open_ms=doc['target_open_ms'], target_end_ms=doc['target_end_ms'],
                    evaluation_as_of_ms=doc['evaluation_as_of_ms'], trigger=doc['trigger'],
                    input_cursor=doc['input_cursor'], input_prefix_hash=doc['input_prefix_hash'],
                    availability_basis=doc['availability_basis'], lineage_hash=doc['lineage_hash'],
                    feature_snapshot_hash=feature.digest, feature_snapshot=doc)

    def checkpoint(self):
        child = self.features.checkpoint()
        return dict(schema_version=1, run_hash=self.manifest.digest, cursor=child['cursor'],
                    prefix_hash=child['prefix_hash'], evaluated_through_ms=child['evaluated_through_ms'],
                    event_count=child['event_count'], feature_checkpoint=child)

    @classmethod
    def restore(cls, dataset, config, checkpoint):
        obj = cls(dataset, config)
        if checkpoint.get('schema_version') != 1 or checkpoint.get('run_hash') != obj.manifest.digest:
            raise ValidationError('Incompatible observation checkpoint')
        child = checkpoint.get('feature_checkpoint')
        if not isinstance(child, dict) or any(
                canonical(checkpoint.get(k)) != canonical(child.get(k))
                for k in ('cursor', 'prefix_hash', 'evaluated_through_ms', 'event_count')):
            raise ValidationError('Observation checkpoint disagrees with its feature prefix')
        obj.features = FeatureEngine.restore(dataset, config.feature_config(), child)
        return obj

    def run(self, events):
        for event in events:
            yield from self.advance(event)


class ObservationStore(FeatureStore):
    def run(self, market, dataset_hash, config, batch_size=256):
        result = super().run(market, dataset_hash, config, batch_size)
        if not result['completed']:
            raise ValidationError('Observation replay did not consume the full pinned dataset')
        return result

    def summary(self, run_hash):
        result = super().summary(run_hash)
        checkpoint = self.load_checkpoint(run_hash)
        dataset = self.manifest(run_hash)['dataset']
        result.update(component=self.COMPONENT, event_count=checkpoint['event_count'],
                      completed=checkpoint['event_count'] == dataset.get('event_count'),
                      purpose='measurements_only')
        return result

    def records(self, run_hash, limit=100, after=0):
        if type(limit) is not int or not 1 <= limit <= 1000 or type(after) is not int or after < 0:
            raise ValidationError('Invalid observation pagination')
        self.manifest(run_hash)
        with self.connection() as db:
            rows = db.execute('SELECT rowid,hash FROM snapshots WHERE run_hash=? AND rowid>? ORDER BY rowid LIMIT ?',
                              (run_hash, after, limit + 1)).fetchall()
        records = [dict(sequence=r['rowid'], **self.snapshot(r['hash'])) for r in rows[:limit]]
        return dict(run_hash=run_hash, records=records,
                    next_sequence=records[-1]['sequence'] if len(rows) > limit else None)


def register_commands(sub, command, component, help_text):
    parser = sub.add_parser(command, help=help_text)
    parser.add_argument('--market-db', default='data/c02.sqlite3')
    parser.add_argument('--observation-db', default=f'data/{component}.sqlite3')
    commands = parser.add_subparsers(dest='observation_command', required=True)
    commands.add_parser('explain')
    run = commands.add_parser('run'); run.add_argument('dataset_hash')
    run.add_argument('--config', default=f'configs/{component}_observations.json')
    run.add_argument('--batch-size', type=int, default=256)
    for name in ('snapshot', 'manifest', 'lineage', 'summary', 'records'):
        p = commands.add_parser(name); p.add_argument('hash')
        if name == 'records':
            p.add_argument('--limit', type=int, default=100)
            p.add_argument('--after-sequence', type=int, default=0)


def execute_command(args, config_type, store_type, engine_type):
    if args.observation_command == 'explain':
        return dict(component=engine_type.COMPONENT, definitions=engine_type.definitions(),
                    defaults=config_type().document(), purpose='measurements_only')
    paths = [Path(p).resolve() for p in (args.db, args.market_db, args.observation_db)]
    if len(set(paths)) != 3:
        raise ValidationError('Registry, market and observation database paths must differ')
    if args.observation_command == 'run':
        config = config_type.from_dict(json.loads(Path(args.config).read_text()))
        if not Path(args.db).is_file() or not Path(args.market_db).is_file():
            raise ValidationError('Existing C01 and C02 databases are required')
        market = MarketStore(Registry(args.db), args.market_db)
        store = store_type(args.observation_db, forbidden_paths=(args.db, args.market_db))
        return store.run(market, args.dataset_hash, config, batch_size=args.batch_size)
    store = store_type(args.observation_db, forbidden_paths=(args.db, args.market_db))
    if args.observation_command == 'records':
        return store.records(args.hash, args.limit, args.after_sequence)
    return getattr(store, args.observation_command)(args.hash)
