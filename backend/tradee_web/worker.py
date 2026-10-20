"""One owned local worker. No notification-send kind or arbitrary subprocess input."""

import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path
from .config import load_settings
from .state import WebState
from .operations import execute


def run(settings):
    state = WebState(settings.state_path)
    with open(str(settings.state_path) + ".worker.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("A worker already owns this web state")
        with state.connection() as db:
            db.execute(
                "UPDATE requests SET state='interrupted',error='Worker exited before acknowledgment; inspect domain audit before resubmitting' WHERE state='running'"
            )
        import threading

        heartbeat_stop = threading.Event()

        def heartbeat():
            while not heartbeat_stop.is_set():
                state.worker_heartbeat()
                heartbeat_stop.wait(2)

        threading.Thread(target=heartbeat, daemon=True).start()
        while True:
            task = state.claim()
            if task is None:
                time.sleep(0.5)
                continue
            # A separate process protects the API and avoids unsafe in-process
            # thread cancellation while a core transaction is publishing.
            command = [
                sys.executable,
                "-m",
                "backend.tradee_web.worker",
                "--task",
                task["id"],
                "--state",
                str(settings.state_path),
            ]
            if os.environ.get("TRADEE_WEB_CONFIG"):
                command += ["--config", os.environ["TRADEE_WEB_CONFIG"]]
            env = dict(os.environ)
            env["TRADEE_WEB_WORKER_PARENT"] = str(os.getpid())
            try:
                subprocess.run(
                    command,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=7200,
                )
            except subprocess.TimeoutExpired:
                state.finish(
                    task["id"],
                    error="Worker time budget exceeded; inspect domain audit before resubmitting",
                )
            current = state.get(task["id"])
            if current["state"] == "running":
                state.finish(task["id"], error="worker_interrupted_or_budget_exceeded")


def child(settings, uid):
    import threading

    parent = os.getppid()
    state = WebState(settings.state_path)

    def watchdog():
        while True:
            time.sleep(1)
            if os.getppid() != parent:
                os._exit(71)

    threading.Thread(target=watchdog, daemon=True).start()
    task = state.get(uid)
    try:
        result = execute(settings, task["workspace"], task["kind"], task["document"])
        state.finish(uid, result)
    except Exception as e:
        from tradee.c01 import ValidationError

        state.finish(
            uid,
            error=(
                str(e)[:300]
                if isinstance(e, ValidationError)
                else "Core operation failed; inspect source integrity and domain audit"
            ),
        )


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--config")
    p.add_argument("--state")
    p.add_argument("--task")
    a = p.parse_args()
    settings = load_settings(a.config)
    if a.config:
        os.environ["TRADEE_WEB_CONFIG"] = str(Path(a.config).resolve())
    if a.state:
        settings.state_path = Path(a.state).resolve()
    child(settings, a.task) if a.task else run(settings)
