"""One current-source raw-input C15 baseline; each mutation uses SQLite backups."""
import atexit
from contextlib import closing
from functools import lru_cache
import os
from pathlib import Path
import sqlite3
import tempfile
from scripts.verify_c15 import run_e2e
from scripts.verify_c14 import SyntheticFeed
from tradee.c11 import SimulationStore
from tradee.c13 import PortfolioStore
from tradee.c14 import SignalStore
from tradee.c15 import MonitorStore,ForwardMonitor


@lru_cache(maxsize=1)
def baseline():
    temp=tempfile.TemporaryDirectory(prefix='tradee-c15-e2e-'); atexit.register(temp.cleanup)
    root=Path(os.environ.get('TRADEE_C15_E2E_OUTPUT',temp.name)).resolve()
    return root,run_e2e(root)


def isolated(root):
    base,result=baseline(); root=Path(root); (root/'research').mkdir()
    for source in [*base.glob('*.sqlite3'),*(base/'research').glob('*.sqlite3')]:
        dest=root/source.relative_to(base)
        with closing(sqlite3.connect(source)) as src,closing(sqlite3.connect(dest)) as dst: src.backup(dst)
    feed=SyntheticFeed(root); signals=SignalStore(root/'c14.sqlite3')
    monitor=ForwardMonitor(MonitorStore(root/'c15.sqlite3'),signals,SimulationStore(root/'research/c11.sqlite3'),PortfolioStore(root/'research/c13.sqlite3'))
    return monitor,feed,result
