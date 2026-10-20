"""Current-source raw-input fixture; every test gets isolated SQLite backups."""

from pathlib import Path
from contextlib import closing
import sqlite3
from tests.c15_integration_support import baseline
from backend.tradee_web.config import Settings, Profile, KINDS


def fixture(root):
    base, _ = baseline()
    root = Path(root)
    paths = {}
    for k in KINDS:
        source = base / ("" if k in ("c14", "c15") else "research") / f"{k}.sqlite3"
        dest = root / f"{k}.sqlite3"
        paths[k] = str(dest)
        if source.is_file():
            with (
                closing(sqlite3.connect(source)) as src,
                closing(sqlite3.connect(dest)) as dst,
            ):
                src.backup(dst)
    return Settings(
        (Profile("test", "Synthetic test", paths, True),),
        default_profile="test",
        state_path=root / "web.sqlite3",
        operator_token="test-operator-token",
    )
