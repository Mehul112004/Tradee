"""One real raw-input baseline per test process; isolated SQLite backups per case."""
import atexit
from contextlib import closing
from functools import lru_cache
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from scripts.verify_c14 import run_e2e,SyntheticFeed,runtime,LIVE
from tradee.c14 import SignalStore


@lru_cache(maxsize=1)
def baseline():
    temporary=tempfile.TemporaryDirectory(prefix='tradee-c14-e2e-'); atexit.register(temporary.cleanup)
    root=Path(os.environ.get('TRADEE_C14_E2E_OUTPUT',temporary.name)).resolve()
    result=run_e2e(root); return root,result


def isolated(root):
    base,_=baseline(); root=Path(root); (root/'research').mkdir()
    for source in (base/'research').glob('*.sqlite3'):
        with closing(sqlite3.connect(source)) as src,closing(sqlite3.connect(root/'research'/source.name)) as dst: src.backup(dst)
    for name in ('session.json','calendar.json'): shutil.copyfile(base/name,root/name)
    source=SignalStore(base/'c14.sqlite3'); manifest=source.session('paper_demo')['manifest']
    feed=SyntheticFeed(root,clock=[LIVE+181000]); s,r=runtime(root,feed); s.create(manifest)
    return feed,s,r


def trim_future(feed,cutoff):
    # An isolated fixture already contains the completed three-cycle E2E.
    # Remove only its later synthetic observations before appending new ones;
    # C02 correctly clamps availability behind its latest recorded clock.
    with feed.market.connection() as db:
        db.execute('DELETE FROM dataset_events WHERE event_id IN (SELECT id FROM events WHERE available_ms>?)',(cutoff,))
        db.execute('DELETE FROM events WHERE available_ms>?',(cutoff,))
