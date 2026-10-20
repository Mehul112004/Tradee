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


def main():
    with tempfile.TemporaryDirectory(prefix="tradee-web-e2e-") as folder:
        settings = fixture(folder)
        settings.operator_token = "e2e-test-only"
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
                        )
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
            uvicorn.run(
                create_app(settings), host="127.0.0.1", port=8790, log_level="warning"
            )
        finally:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait()


if __name__ == "__main__":
    main()
