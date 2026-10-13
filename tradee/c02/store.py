"""Append-only market observations, immutable datasets and availability-time replay."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from zipfile import BadZipFile

from tradee.c01 import Policy, ValidationError
from tradee.c01.domain import canonical, fingerprint, symbol_name
from .domain import MINUTE, KINDS, integer, parse_ws, rest_rows

APP_ID = 0x54524432


class MarketStore:
    def __init__(self, registry, path='data/c02.sqlite3', clock=time.time):
        if Path(path).resolve() == Path(registry.path).resolve() or str(path) == ':memory:':
            raise ValidationError('C02 requires a separate persistent database')
        self.registry, self.path, self.clock = registry, str(path), clock
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            app = db.execute('PRAGMA application_id').fetchone()[0]
            version = db.execute('PRAGMA user_version').fetchone()[0]
            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            if (tables and app != APP_ID) or version not in (0, 1):
                raise ValidationError('Not a supported C02 database')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS raw_observations (
                    id INTEGER PRIMARY KEY, source TEXT NOT NULL, received_ms INTEGER NOT NULL,
                    raw BLOB NOT NULL, sha256 TEXT NOT NULL, accepted INTEGER NOT NULL, error TEXT);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, raw_id INTEGER NOT NULL REFERENCES raw_observations(id),
                    symbol TEXT NOT NULL, instrument_id TEXT NOT NULL, metadata_version TEXT NOT NULL,
                    kind TEXT NOT NULL, event_key TEXT NOT NULL, event_ms INTEGER NOT NULL,
                    received_ms INTEGER NOT NULL, available_ms INTEGER NOT NULL,
                    final INTEGER NOT NULL, semantic_hash TEXT NOT NULL, document TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS event_lookup ON events(symbol,kind,event_key,id);
                CREATE INDEX IF NOT EXISTS event_identity ON events(instrument_id,kind,event_key,final,id);
                CREATE INDEX IF NOT EXISTS event_range ON events(symbol,kind,event_ms,available_ms);
                CREATE INDEX IF NOT EXISTS event_availability ON events(available_ms,id);
                CREATE TABLE IF NOT EXISTS datasets (hash TEXT PRIMARY KEY, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS dataset_events (
                    dataset_hash TEXT REFERENCES datasets(hash), event_id INTEGER REFERENCES events(id),
                    available_ms INTEGER NOT NULL, PRIMARY KEY(dataset_hash,event_id));
                CREATE TABLE IF NOT EXISTS checkpoints (name TEXT PRIMARY KEY, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS collector_log (
                    id INTEGER PRIMARY KEY, observed_ms INTEGER NOT NULL, document TEXT NOT NULL);
            ''')
            db.execute(f'PRAGMA application_id={APP_ID}')
            db.execute('PRAGMA user_version=1')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def now(self):
        return integer(int(self.clock() * 1000), 'now')

    def binding(self, symbol):
        symbol_name(symbol)
        view = self.registry.universe(Policy((symbol,)))
        decision = next(d for d in view['decisions'] if d['symbol'] == symbol)
        if not decision['version_hash']:
            raise ValidationError(f'{symbol}: C01 metadata required before collection')
        version = self.registry.version(decision['version_hash'])
        spec = version['spec']
        if (not spec['scope_supported'] or 'identity_conflict' in spec['issues']
                or any(f'missing_or_invalid:{f}' in spec['issues'] for f in
                       ('baseAsset', 'quoteAsset', 'marginAsset', 'contractType', 'onboardDate'))):
            raise ValidationError(f'{symbol}: unsupported or ambiguous C01 identity')
        # Collection is independent of new-entry eligibility and metadata freshness.
        return dict(instrument_id=spec['instrument_id'], metadata_version=decision['version_hash'])

    def ingest(self, raw, source, parser, received_ms=None, checkpoint=None, binary=False):
        """Parse and append atomically; rejected payloads remain in raw quarantine.

        received_ms is for adapters that timestamp on receipt, not historical imports.
        A historical source's original availability is never inferred here.
        """
        raw_bytes = raw.encode('utf-8') if isinstance(raw, str) else raw
        if not isinstance(raw_bytes, bytes):
            raise ValidationError('Raw input must be text or bytes')
        received = self.now() if received_ms is None else integer(received_ms, 'received_ms')
        if received > self.now():
            raise ValidationError('Receipt cannot be in the future')
        digest = hashlib.sha256(raw_bytes).hexdigest()
        try:
            items = parser(raw_bytes if binary else raw_bytes.decode('utf-8'))
            if not isinstance(items, list):
                raise ValidationError('Parser must return a list of market events')
            bindings = {symbol: self.binding(symbol) for symbol in {e['symbol'] for e in items}}
            with self.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                prior = db.execute('SELECT MAX(available_ms) FROM events').fetchone()[0] or 0
                available = max(self.now(), received, prior)
                raw_id = db.execute('INSERT INTO raw_observations(source,received_ms,raw,sha256,accepted) VALUES(?,?,?,?,1)',
                                    (source, received, raw_bytes, digest)).lastrowid
                added = duplicates = 0
                pending = []
                for e in items:
                    e = json.loads(canonical(e))
                    if e['kind'] not in KINDS or type(e['final']) is not bool:
                        raise ValidationError('Invalid market event contract')
                    if ((e['final'] and e['event_ms'] > received + 5000)
                            or e['data'].get('open_ms', 0) > received + 5000
                            or e.get('exchange_event_ms', 0) > received + 5000):
                        raise ValidationError('Future event exceeds clock-skew allowance')
                    e.update(bindings[e['symbol']])
                    semantic = fingerprint({k: v for k, v in e.items() if k != 'exchange_event_ms'})
                    previous = db.execute('''SELECT semantic_hash FROM events WHERE instrument_id=? AND kind=?
                        AND event_key=? AND final=? ORDER BY id DESC LIMIT 1''',
                        (e['instrument_id'], e['kind'], e['key'], e['final'])).fetchone()
                    if previous and previous[0] == semantic:
                        duplicates += 1
                        continue
                    e.update(received_ms=received, available_ms=available, source=source,
                             availability_basis='recorded', raw_sha256=digest)
                    eid = db.execute('''INSERT INTO events(raw_id,symbol,instrument_id,metadata_version,kind,event_key,
                        event_ms,received_ms,available_ms,final,semantic_hash,document) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (raw_id, e['symbol'], e['instrument_id'], e['metadata_version'], e['kind'], e['key'],
                         e['event_ms'], received, available, e['final'], semantic, canonical(e))).lastrowid
                    pending.append((eid, e))
                    added += 1
                # Availability includes normalization and batch-write processing, not just receipt.
                available = max(available, self.now(), max(
                    (e['event_ms'] + (1 if e['kind'] == 'candle' else 0)
                     for _, e in pending if e['final']), default=0))
                for eid, e in pending:
                    e['available_ms'] = available
                    db.execute('UPDATE events SET available_ms=?,document=? WHERE id=?',
                               (available, canonical(e), eid))
                if checkpoint:
                    db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?)', (checkpoint[0], canonical(checkpoint[1])))
            return dict(raw_id=raw_id, added=added, duplicates=duplicates, received_ms=received)
        except (ValueError, TypeError, KeyError, BadZipFile, sqlite3.Error) as exc:
            with self.connection() as db:
                db.execute('INSERT INTO raw_observations(source,received_ms,raw,sha256,accepted,error) VALUES(?,?,?,?,0,?)',
                           (source, received, raw_bytes, digest, str(exc)))
            raise ValidationError(str(exc)) from exc

    def ingest_ws(self, raw, source='binance:websocket', received_ms=None):
        return self.ingest(raw, source, lambda text: [parse_ws(text)], received_ms)

    def ingest_rest(self, raw, symbol, kind='candle', source='binance:rest', received_ms=None, checkpoint=None):
        received = self.now() if received_ms is None else received_ms
        return self.ingest(raw, source, lambda text: rest_rows(kind, symbol, json.loads(text), received), received, checkpoint)

    def checkpoint(self, name):
        with self.connection() as db:
            row = db.execute('SELECT document FROM checkpoints WHERE name=?', (name,)).fetchone()
            return json.loads(row[0]) if row else None

    def save_checkpoint(self, name, document):
        with self.connection() as db:
            db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?)', (name, canonical(document)))

    def candle_gaps(self, symbol, start_ms, end_ms):
        """Current finalized coverage for repair scheduling, independent of research snapshots."""
        binding = self.binding(symbol)
        with self.connection() as db:
            rows = db.execute("""SELECT DISTINCT event_key FROM events WHERE instrument_id=?
                AND kind='candle' AND final=1 AND event_ms>=? AND event_ms<?""",
                (binding['instrument_id'], start_ms, end_ms)).fetchall()
        present = {int(r[0]) for r in rows}
        return [t for t in range(start_ms, end_ms, MINUTE) if t not in present]

    def log(self, **fields):
        with self.connection() as db:
            db.execute('INSERT INTO collector_log(observed_ms,document) VALUES(?,?)', (self.now(), canonical(fields)))

    def snapshot(self, symbols, start_ms, end_ms, kinds=('candle',), mode='recorded', delay_ms=None, as_of_ms=None):
        symbols = sorted({symbol_name(s) for s in symbols})
        kinds = sorted(set(kinds))
        integer(start_ms, 'start_ms'); integer(end_ms, 'end_ms')
        cutoff = self.now() if as_of_ms is None else integer(as_of_ms, 'as_of_ms')
        if not symbols or not kinds or set(kinds) - set(KINDS) or start_ms >= end_ms or cutoff > self.now():
            raise ValidationError('Invalid dataset range, symbols, kinds or cutoff')
        if 'candle' in kinds and (start_ms % MINUTE or end_ms % MINUTE):
            raise ValidationError('Candle dataset bounds must align to whole minutes')
        if mode not in ('recorded', 'modeled'):
            raise ValidationError('Availability mode must be recorded or modeled')
        if mode == 'modeled':
            if kinds != ['candle'] or delay_ms is None:
                raise ValidationError('Modeled availability requires candle-only data and an explicit delay_ms')
            integer(delay_ms, 'delay_ms')
        elif delay_ms is not None:
            raise ValidationError('Recorded replay cannot use modeled latency')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute(f'''SELECT * FROM events WHERE available_ms<=?
                AND symbol IN ({','.join('?' for _ in symbols)})
                AND kind IN ({','.join('?' for _ in kinds)})
                AND event_ms>=? AND event_ms<? ORDER BY id''', (cutoff, *symbols, *kinds, start_ms, end_ms)).fetchall()
            selected = []
            for r in rows:
                if r['symbol'] not in symbols or r['kind'] not in kinds:
                    continue
                d = json.loads(r['document'])
                stamp = d['data'].get('open_ms', d['event_ms'])
                if start_ms <= stamp < end_ms:
                    selected.append((r, d))
            if mode == 'modeled':
                # An explicit research dataset vintage; never change previously pinned experiments.
                latest = {}
                for r, d in selected:
                    if r['final']:
                        latest[(r['instrument_id'], r['event_key'])] = (r, d)
                selected = list(latest.values())
            refs = [(r['id'], r['available_ms'] if mode == 'recorded' else d['event_ms'] + 1 + delay_ms)
                    for r, d in selected]
            refs.sort(key=lambda x: (x[1], x[0]))
            document = dict(schema_version=1, symbols=symbols, kinds=kinds, start_ms=start_ms, end_ms=end_ms,
                            as_of_ms=cutoff, mode=mode, delay_ms=delay_ms, event_count=len(refs),
                            event_manifest_sha256=fingerprint(refs),
                            metadata_evidence='C01 binding observed at collection; historical rule validity unknown',
                            revision_policy='all recorded revisions' if mode == 'recorded' else 'latest finalized version at dataset cutoff')
            digest = fingerprint(document)
            db.execute('INSERT OR IGNORE INTO datasets VALUES(?,?)', (digest, canonical(document)))
            db.executemany('INSERT OR IGNORE INTO dataset_events VALUES(?,?,?)', [(digest, i, a) for i, a in refs])
        return dict(dataset_hash=digest, **document)

    def dataset(self, digest):
        with self.connection() as db:
            row = db.execute('SELECT document FROM datasets WHERE hash=?', (digest,)).fetchone()
        if not row:
            raise ValidationError('Unknown dataset snapshot')
        return dict(dataset_hash=digest, **json.loads(row[0]))

    def replay(self, digest, until_ms=None, after_id=None):
        """Immutable ordered input stream, including revisions and partial updates.

        after_id resumes *after that event in replay order*, not by numerical ID.
        """
        dataset = self.dataset(digest)
        if until_ms is not None:
            integer(until_ms, 'until_ms')
        with self.connection() as db:
            rows = db.execute('''SELECT e.id,e.document,d.available_ms FROM dataset_events d
                JOIN events e ON e.id=d.event_id WHERE d.dataset_hash=? ORDER BY d.available_ms,e.id''', (digest,)).fetchall()
        found = after_id is None
        if after_id is not None and after_id not in {r['id'] for r in rows}:
            raise ValidationError('Resume event does not belong to this dataset')
        for row in rows:
            if not found:
                found = row['id'] == after_id
                continue
            if until_ms is not None and row['available_ms'] > until_ms:
                break
            d = json.loads(row['document'])
            d.update(id=row['id'], available_ms=row['available_ms'], availability_basis=dataset['mode'])
            yield d

    def view(self, digest, as_of_ms):
        """Latest finalized values available by the decision time; partials cannot supersede finals."""
        latest = {}
        for e in self.replay(digest, until_ms=as_of_ms):
            if e['final']:
                latest[(e['instrument_id'], e['kind'], e['key'])] = e
        return sorted(latest.values(), key=lambda e: (e['event_ms'], e['id']))

    def asof(self, digest, symbol, kind, decision_ms, max_age_ms):
        integer(max_age_ms, 'max_age_ms')
        if max_age_ms == 0:
            raise ValidationError('max_age_ms must be positive')
        candidates = [e for e in self.view(digest, decision_ms) if e['symbol'] == symbol and e['kind'] == kind
                      and e['event_ms'] <= decision_ms]
        if not candidates:
            return None
        result = max(candidates, key=lambda e: (e['event_ms'], e['id']))
        return result if decision_ms - result['event_ms'] < max_age_ms else None

    def quality(self, digest, as_of_ms=None, stale_after_ms=180000):
        ds = self.dataset(digest)
        when = self.now() if as_of_ms is None else integer(as_of_ms, 'as_of_ms')
        integer(stale_after_ms, 'stale_after_ms')
        if stale_after_ms == 0:
            raise ValidationError('stale_after_ms must be positive')
        events = list(self.replay(digest, until_ms=when))
        final = self.view(digest, when)
        reports = []
        for symbol in ds['symbols']:
            bars = [e for e in final if e['symbol'] == symbol and e['kind'] == 'candle']
            opens = {e['data']['open_ms'] for e in bars}
            start = (ds['start_ms'] + MINUTE - 1) // MINUTE * MINUTE
            end = ds['end_ms'] // MINUTE * MINUTE
            gaps = []
            for t in range(start, end, MINUTE):
                if t not in opens:
                    if gaps and gaps[-1]['end_ms'] == t:
                        gaps[-1]['end_ms'] += MINUTE
                    else:
                        gaps.append(dict(start_ms=t, end_ms=t + MINUTE))
            last = max((e['event_ms'] for e in bars), default=None)
            reports.append(dict(symbol=symbol, expected_candles=(end-start)//MINUTE,
                                finalized_candles=len(bars), gaps=gaps,
                                stale=last is None or when-last >= stale_after_ms))
        keys = {(e['instrument_id'], e['kind'], e['key'], e['final']) for e in events}
        with self.connection() as db:
            quarantine = db.execute('SELECT COUNT(*) FROM raw_observations WHERE accepted=0').fetchone()[0]
        return dict(dataset_hash=digest, as_of_ms=when, availability_basis=ds['mode'], symbols=reports,
                    partial_updates=sum(not e['final'] for e in events), revisions=len(events)-len(keys),
                    quarantined_payloads_store_total=quarantine,
                    ready=bool(reports) and 'candle' in ds['kinds'] and all(not r['gaps'] and not r['stale'] for r in reports),
                    non_candle_coverage='Recorded observations only; no claim of gap-free trades, quotes or derivatives')
