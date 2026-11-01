"""Disposable current-source dashboard fixture + API + owned worker for E2E."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uvicorn
from backend.tests.support import fixture
from backend.tradee_web.app import create_app
from backend.tradee_web.config import Profile, KINDS
from backend.tests.analysis_support import (
    FixtureCandleSource,
    seed_metadata,
    fixture_c02_feed,
)


def main():
    os.environ["PYTHON_DOTENV_DISABLED"] = "1"
    with tempfile.TemporaryDirectory(prefix="tradee-web-e2e-") as folder:
        settings = fixture(folder)
        settings.operator_token = "e2e-test-only"
        local = Path(folder) / "local"
        local.mkdir()
        settings.profiles += (
            Profile(
                "local",
                "Local recording",
                {k: str(local / f"{k}.sqlite3") for k in KINDS},
            ),
        )
        settings.origins += ("http://127.0.0.1:8790",)
        config = Path(folder) / "profiles.json"
        config.write_text(
            json.dumps(
                dict(
                    default_profile="test",
                    state_path=str(settings.state_path),
                    profiles=[
                        dict(
                            id="test",
                            label="Synthetic E2E",
                            root=folder,
                            synthetic=True,
                        ),
                        dict(
                            id="local",
                            label="Local recording",
                            root=str(local),
                            synthetic=False,
                        ),
                    ],
                )
            )
        )
        env = dict(os.environ)
        env["TRADEE_WEB_CONFIG"] = str(config)
        worker = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "backend.tradee_web.worker",
                "--config",
                str(config),
            ],
            env=env,
        )
        try:
            app = create_app(settings)
            # Test-only source injection: real HTTP/UI/storage, no public network.
            app.state.analysis.source = FixtureCandleSource()
            app.state.analysis.feed_factory = fixture_c02_feed
            app.state.analysis.metadata = lambda workspace, session, now: seed_metadata(
                settings, workspace, session, now
            )
            uvicorn.run(app, host="127.0.0.1", port=8790, log_level="warning")
        finally:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait()


if __name__ == "__main__":
    main()
