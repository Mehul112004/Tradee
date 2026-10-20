import copy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager, closing


@contextmanager
def mutation(path):
    with closing(sqlite3.connect(path)) as db:
        with db:
            yield db


from fastapi.testclient import TestClient
from tradee.c01 import ValidationError
from tradee.c01.domain import fingerprint
from tradee.c12 import ResearchStore
from backend.tradee_web.app import create_app, validate_command
from backend.tradee_web.projections import Repository, page, redact
from backend.tradee_web.analytics import distribution
from backend.tradee_web.readers import reader, SourceError
from backend.tradee_web.state import WebState
from backend.tradee_web.operations import execute
from .support import fixture


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = fixture(self.temp.name)
        self.profile = self.settings.profile("test")
        self.repo = Repository(self.settings, self.profile)
        self.client = TestClient(
            create_app(self.settings), raise_server_exceptions=False
        )
        self.addCleanup(self.client.close)

    def get(self, path):
        return self.client.get("/api/test/" + path)

    def hashes(self):
        return {
            p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
            for p in self.profile.paths.values()
            if Path(p).is_file()
        }

    def command(self, kind, doc, key="key1", token=True):
        return self.client.post(
            "/api/test/commands/" + kind,
            json=doc,
            headers={
                "Idempotency-Key": key,
                **({"Authorization": "Bearer test-operator-token"} if token else {}),
            },
        )

    def head(self):
        return self.repo.session("paper_demo")

    def control(self):
        h = self.head()
        return dict(
            session="paper_demo",
            reason="Operator verification",
            expected_revision=h["revision"],
            expected_audit_head=h["audit_head"],
        )

    def test_read_routes_preserve_all_domain_bytes(self):
        before = self.hashes()
        h = self.head()
        ds = h["cycle"]["dataset"]["dataset_hash"]
        run = h["cycle"]["simulation"]["run_hash"]
        paths = [
            "overview",
            "sessions",
            "sessions/paper_demo",
            "sessions/paper_demo/signals",
            "sessions/paper_demo/portfolio",
            "sessions/paper_demo/analytics",
            "datasets",
            f"market?dataset_hash={ds}&symbol=BTCUSDT",
            "research",
            "runs",
            f"runs/{run}",
            "models",
            "monitors",
            "monitors/forward",
            "instruments",
            f"quality/{ds}",
            "sessions/paper_demo/export?format=csv",
            f"artifacts/c02/{ds}",
        ]
        for path in paths:
            with self.subTest(path=path):
                r = self.get(path)
                self.assertEqual(r.status_code, 200, r.text[:400])
        self.assertEqual(before, self.hashes())

    def test_paper_wallet_and_independent_tracks_remain_distinct(self):
        p = self.get("sessions/paper_demo/portfolio").json()["data"]
        f = self.get("monitors/forward").json()["data"]["report"]
        self.assertEqual(p["account"]["cash_usdt"], "328.489")
        self.assertEqual(len(p["trades"]), 3)
        self.assertEqual(f["summary"]["independent"]["mature_net_usdt"], "16.978")
        self.assertEqual(f["summary"]["portfolio"]["mature_net_usdt"], "8.489")
        self.assertFalse(f["promotion_authorized"])

    def test_missing_sources_are_not_created(self):
        for path in self.profile.paths.values():
            Path(path).unlink(missing_ok=True)
        r = self.get("overview")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            all(x["state"] == "not_configured" for x in r.json()["data"]["sources"])
        )
        self.assertFalse(any(Path(p).exists() for p in self.profile.paths.values()))

    def test_readonly_connection_refuses_writes(self):
        s = reader(self.profile, "c14")
        with s.connection() as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("DELETE FROM sessions")

    def test_corrupt_domain_artifact_is_not_shown(self):
        h = self.head()["deployment_hash"]
        with mutation(self.profile.path("c14")) as db:
            db.execute("UPDATE artifacts SET document='{}' WHERE hash=?", (h,))
        self.assertGreaterEqual(self.get("sessions/paper_demo").status_code, 400)

    def test_corrupt_market_payload_is_not_charted(self):
        ds = self.repo.datasets()[0]["dataset_hash"]
        with mutation(self.profile.path("c02")) as db:
            row = db.execute(
                "SELECT id,document FROM events WHERE kind='candle' LIMIT 1"
            ).fetchone()
            d = json.loads(row[1])
            d["data"]["close"] = "98765"
            db.execute(
                "UPDATE events SET document=? WHERE id=?", (json.dumps(d), row[0])
            )
        # Use a dataset that actually contains the corrupted observation.
        with mutation(self.profile.path("c02")) as db:
            ds = db.execute(
                "SELECT dataset_hash FROM dataset_events WHERE event_id=? LIMIT 1",
                (row[0],),
            ).fetchone()[0]
        self.assertEqual(
            self.get(f"market?dataset_hash={ds}&symbol=BTCUSDT").status_code, 409
        )

    def test_dataset_membership_manifest_is_verified(self):
        ds = self.repo.datasets()[0]["dataset_hash"]
        with mutation(self.profile.path("c02")) as db:
            db.execute(
                "DELETE FROM dataset_events WHERE dataset_hash=? AND event_id=(SELECT MIN(event_id) FROM dataset_events WHERE dataset_hash=?)",
                (ds, ds),
            )
        self.assertEqual(
            self.get(f"market?dataset_hash={ds}&symbol=BTCUSDT").status_code, 409
        )

    def test_cutoff_hides_unrecorded_cycles_and_outcomes(self):
        h = self.head()
        first = min(max(c["as_of_ms"], c["recorded_ms"]) for c in h["cycles"])
        early = self.get(f"sessions/paper_demo?at_ms={first-1}").json()["data"]
        self.assertIsNone(early["cycle"])
        self.assertEqual(early["signals"], [])
        self.assertTrue(
            all(max(e["at_ms"], e["recorded_ms"]) < first for e in early["events"])
        )
        selected = self.get(f"sessions/paper_demo?at_ms={first}").json()["data"]
        self.assertIsNone(selected["revision"])
        self.assertTrue(
            all(max(e["at_ms"], e["recorded_ms"]) <= first for e in selected["events"])
        )

    def test_actual_candles_no_incomplete_higher_buckets(self):
        ds = self.repo.datasets()[0]
        h = ds["dataset_hash"]
        m = self.get(f"market?dataset_hash={h}&symbol=BTCUSDT").json()["data"]
        self.assertTrue(m["candles"])
        self.assertEqual(m["candles"][0]["data"]["open_ms"] % 60000, 0)
        higher = self.get(
            f"market?dataset_hash={h}&symbol=BTCUSDT&timeframe=1h"
        ).json()["data"]
        self.assertEqual(higher["candles"], [])
        self.assertEqual(higher["sampling"], "none")

    def test_market_range_caps_quote_knowledge(self):
        ds = self.repo.datasets()[0]
        end = ds["start_ms"] + 240000
        m = self.get(
            f"market?dataset_hash={ds['dataset_hash']}&symbol=BTCUSDT&end_ms={end}"
        ).json()["data"]
        self.assertLessEqual(m["as_of_ms"], end)
        self.assertTrue(all(e["available_ms"] <= end for e in m["quotes"].values()))

    def lock_holdout(self):
        e = copy.deepcopy(self.repo.research()[0]["manifest"]["experiment"])
        e["name"] = "new_locked_protocol"
        e["family"] = "new_locked_family"
        self.profile.path("c12").unlink()
        s = ResearchStore(self.profile.path("c12"))
        s.register(e)
        return e

    def test_locked_holdout_denied_across_surfaces(self):
        e = self.lock_holdout()
        run = e["variants"][0]["holdout_runs"][0]
        h = fingerprint(e)
        # C12 manifest contains extra metadata, so discover its actual registered hash.
        listing = self.get("research").json()["data"]
        entry = next(x for x in listing if x["name"] == e["name"])
        h = entry["experiment_hash"]
        self.assertTrue(entry["locked"])
        self.assertIsNone(entry["decision"])
        self.assertEqual(self.get(f"runs/{run}").status_code, 423)
        self.assertEqual(self.get(f"artifacts/c11/{run}").status_code, 423)
        manifest = reader(self.profile, "c11").manifest(run)
        ds = manifest["dataset"]["dataset_hash"]
        self.assertEqual(
            self.get(
                f'market?dataset_hash={ds}&symbol=BTCUSDT&start_ms={manifest["decision_window_ms"][0]}&end_ms={manifest["decision_window_ms"][1]}'
            ).status_code,
            423,
        )
        detail = self.get(f"research/{h}").json()["data"]
        self.assertFalse(any("holdout" in a["key"] for a in detail["artifacts"]))
        report = reader(self.profile, "c11").summary(run)["report_hash"]
        self.assertEqual(self.get(f"artifacts/c11/{report}").status_code, 423)

    def test_raw_artifact_requires_owning_session(self):
        r = self.get("artifacts/c14/" + "f" * 64)
        self.assertEqual(r.status_code, 422)
        r = self.get("artifacts/c14/" + self.head()["deployment_hash"])
        self.assertEqual(r.status_code, 200)

    def test_invalid_parameters_bounded(self):
        self.assertEqual(
            self.get("sessions/paper_demo/signals?limit=0").status_code, 422
        )
        self.assertEqual(
            self.get("market?dataset_hash=no&symbol=BTCUSDT&limit=2001").status_code,
            422,
        )
        self.assertEqual(self.get("sessions/paper_demo?at_ms=-1").status_code, 422)
        self.assertEqual(self.get("runs?kind=bogus").status_code, 422)

    def test_pagination_has_snapshot_and_scope_binding(self):
        rows = self.head()["signals"]
        p = page(rows, 2, scope="a")
        self.assertEqual(len(p["items"]), 2)
        second = page(rows, 2, p["next_cursor"], "a")
        self.assertEqual(second["items"], rows[2:4])
        with self.assertRaises(SourceError):
            page(rows, 2, p["next_cursor"], "b")
        with self.assertRaises(SourceError):
            page(rows[:-1], 2, p["next_cursor"], "a")

    def test_bearer_auth_and_origin_protection(self):
        before = self.hashes()
        self.assertEqual(
            self.command("pause", self.control(), token=False).status_code, 401
        )
        self.assertEqual(
            self.client.post(
                "/api/test/commands/pause",
                json=self.control(),
                headers={
                    "Origin": "https://evil.example",
                    "Authorization": "Bearer test-operator-token",
                },
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                "/api/bootstrap", headers={"Host": "evil.example"}
            ).status_code,
            400,
        )
        self.assertEqual(before, self.hashes())

    def test_queued_command_is_durable_and_idempotent(self):
        before = self.hashes()
        d = self.control()
        a = self.command("resume", d)
        self.assertEqual(a.status_code, 202, a.text)
        b = self.command("resume", d)
        self.assertEqual(a.json()["data"]["id"], b.json()["data"]["id"])
        self.assertEqual(before, self.hashes())
        conflict = self.command("pause", d)
        self.assertEqual(conflict.status_code, 422)
        self.assertNotIn("test-operator-token", self.get("jobs").text)

    def test_stale_control_rejected_on_admission_and_execution(self):
        d = self.control()
        d["expected_revision"] -= 1
        self.assertEqual(self.command("resume", d).status_code, 409)
        with self.assertRaises(ValidationError):
            execute(self.settings, "test", "resume", d)

    def test_control_worker_delegates_to_core_once(self):
        d = self.control()
        a = self.command("resume", d).json()["data"]
        state = WebState(self.settings.state_path)
        claim = state.claim()
        self.assertEqual(claim["id"], a["id"])
        result = execute(self.settings, "test", "resume", d)
        state.finish(a["id"], result)
        head = reader(self.profile, "c14").session("paper_demo")
        self.assertFalse(head["paused"])
        self.assertEqual(head["revision"], d["expected_revision"] + 1)
        self.assertEqual(state.jobs("test")[0]["state"], "succeeded")
        self.assertIsNone(state.claim())

    def test_queued_cancel_does_not_mutate_core(self):
        before = self.hashes()
        a = self.command("resume", self.control()).json()["data"]
        r = self.client.post(
            f"/api/test/jobs/{a['id']}/cancel",
            headers={"Authorization": "Bearer test-operator-token"},
        )
        self.assertEqual(r.json()["data"]["state"], "cancelled")
        self.assertEqual(before, self.hashes())
        self.assertIsNone(WebState(self.settings.state_path).claim())

    def test_running_job_cannot_be_cancelled(self):
        a = self.command("resume", self.control()).json()["data"]
        state = WebState(self.settings.state_path)
        state.claim()
        with self.assertRaises(ValidationError):
            state.cancel(a["id"])

    def test_no_arbitrary_execution_send_or_unknown_fields(self):
        self.assertEqual(self.command("send", {}).status_code, 422)
        self.assertEqual(
            self.command("pause", dict(self.control(), command="rm")).status_code, 422
        )
        with self.assertRaises(ValidationError):
            validate_command(
                "open_holdout",
                dict(experiment_hash="abc", reason="test reason", confirmation="yes"),
            )

    def test_no_secret_or_chat_identity_in_viewer_response(self):
        self.assertEqual(
            redact(
                {"token": "abc", "nested": {"proof": "private", "chat_id": "123456789"}}
            ),
            {
                "token": "[redacted]",
                "nested": {"proof": "[redacted]", "chat_id": "…6789"},
            },
        )
        self.assertNotIn("test-operator-token", self.client.get("/api/bootstrap").text)

    def test_ui_state_cannot_overwrite_domain(self):
        before = self.hashes()
        with self.assertRaises(ValidationError):
            WebState(self.profile.path("c14"))
        self.assertEqual(before, self.hashes())

    def test_distribution_exact_edges_and_unknown_denominators(self):
        d = distribution(
            [
                dict(label_status="mature", net_r=x)
                for x in ["-3", "-2", "-1", "0", "1", "2"]
            ]
            + [dict(label_status="unresolved", net_r=None)]
        )
        self.assertEqual([b["count"] for b in d["bins"]], [1] * 6)
        self.assertEqual(d["omitted"], 1)

    def test_drawdown_starts_at_initial_capital_and_uses_funded_samples(self):
        d = self.get("sessions/paper_demo/analytics").json()["data"]
        self.assertEqual(d["funded"]["drawdown"][0]["drawdown_usdt"], "0")
        self.assertEqual(d["funded"]["distribution"]["mature"], 3)
        self.assertEqual(len(d["lineage"]["nodes"]), 7)

    def test_durable_events_replay_without_loss_or_duplicate_cursor(self):
        state = WebState(self.settings.state_path)
        state.sync("test", "c14", {"revision": 1})
        state.sync("test", "c14", {"revision": 1})
        a = state.events("test")
        self.assertEqual(len(a), 1)
        state.event("test", "job_completed", {"id": "x"})
        b = state.events("test", a[0]["id"])
        self.assertEqual(len(b), 1)
        self.assertGreater(b[0]["id"], a[0]["id"])

    def test_frontend_spa_and_no_api_fallback(self):
        self.assertEqual(self.client.get("/markets").status_code, 200)
        self.assertEqual(self.get("does-not-exist").status_code, 404)
        self.assertIn("no-store", self.get("overview").headers["cache-control"])
        self.assertIn(
            "frame-ancestors 'none'",
            self.get("overview").headers["content-security-policy"],
        )

    def test_runner_reservation_is_single_and_stop_is_explicit(self):
        from unittest.mock import patch
        from backend.tradee_web import runners

        d = dict(self.control(), monitor="forward", interval_seconds=1, max_cycles=2)
        with patch("backend.tradee_web.runners.subprocess.Popen") as spawn:
            a = runners.start(self.settings, "test", d)
            with self.assertRaises(ValidationError):
                runners.start(self.settings, "test", d)
            self.assertEqual(spawn.call_count, 1)
            self.assertNotIn("shell", spawn.call_args.kwargs)
        self.assertEqual(
            runners.catalog(WebState(self.settings.state_path), "test")[0]["state"],
            "starting",
        )
        stopped = runners.stop(self.settings, "test", "paper_demo")
        self.assertEqual(stopped["state"], "stop_requested")
        self.assertEqual(stopped["runner_id"], a["runner_id"])
        self.assertTrue(reader(self.profile, "c14").session("paper_demo")["paused"])

    def test_runner_recovery_checks_process_lock_and_start_handshake(self):
        from unittest.mock import patch
        from backend.tradee_web import runners
        import fcntl

        d = dict(self.control(), monitor="forward", interval_seconds=1, max_cycles=2)
        with patch("backend.tradee_web.runners.subprocess.Popen"):
            a = runners.start(self.settings, "test", d)
        with self.assertRaises(ValidationError):
            runners.recover(self.settings, "test", "paper_demo")
        state = WebState(self.settings.state_path)
        with state.connection() as db:
            db.execute("UPDATE runners SET state='running',heartbeat_ms=0")
        lockpath = (
            str(self.settings.state_path)
            + ".runner-test-"
            + hashlib.sha256(b"paper_demo").hexdigest()
            + ".lock"
        )
        with open(lockpath, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(ValidationError):
                runners.recover(self.settings, "test", "paper_demo")
        recovered = runners.recover(self.settings, "test", "paper_demo")
        self.assertEqual(recovered["recovered"], [a["runner_id"]])
        self.assertFalse(recovered["runner_started"])

    def test_expired_session_cannot_start_owned_runner(self):
        d = dict(self.control(), monitor="forward", interval_seconds=1, max_cycles=2)
        with self.assertRaisesRegex(ValidationError, "Session has ended"):
            execute(self.settings, "test", "start_runner", d)

    def test_command_contracts_validate_before_queuing(self):
        self.assertEqual(
            self.command(
                "features",
                dict(dataset_hash="a" * 64, config={"features": ["made_up"]}),
            ).status_code,
            422,
        )
        self.assertEqual(
            self.command(
                "backfill",
                dict(symbol="BTCUSDT", start_ms=0, end_ms=32 * 86400000, kind="candle"),
            ).status_code,
            422,
        )
        self.assertEqual(
            self.command(
                "start_runner",
                dict(
                    self.control(), monitor="forward", interval_seconds=0, max_cycles=1
                ),
            ).status_code,
            422,
        )
        self.assertEqual(self.get("jobs").json()["data"], [])

    def test_worker_status_and_bounded_event_retention(self):
        state = WebState(self.settings.state_path)
        self.assertEqual(state.worker_status()["state"], "not_running")
        state.worker_heartbeat()
        self.assertEqual(state.worker_status()["state"], "connected")
        with state.connection() as db:
            db.executemany(
                "INSERT INTO events(workspace,kind,at_ms,document) VALUES(?,?,?,?)",
                [("test", "resource_changed", 0, "{}")] * 10020,
            )
        state.prune_events()
        lo, hi = state.bounds("test")
        self.assertEqual(hi - lo, 10000)
        self.assertEqual(self.get("worker").json()["data"]["state"], "connected")

    def test_explicit_feature_job_materializes_core_snapshots(self):
        h = self.head()["cycle"]["dataset"]["dataset_hash"]
        self.assertFalse(self.profile.path("c03").exists())
        execute(
            self.settings,
            "test",
            "features",
            dict(
                dataset_hash=h,
                config=dict(features=["ema20", "atr14", "rsi14"], timeframes=["1m"]),
            ),
        )
        self.assertTrue(self.profile.path("c03").is_file())
        data = self.get(f"market?dataset_hash={h}&symbol=BTCUSDT").json()["data"]
        self.assertEqual(data["feature_status"], "available")
        self.assertTrue(
            any(
                v["status"] == "insufficient_history"
                for f in data["features"]
                for v in f["values"].values()
            )
        )

    def test_explicit_dataset_job_preserves_original_vintage(self):
        h = self.head()["cycle"]["dataset"]["dataset_hash"]
        old = self.repo.store("c02").dataset(h)
        d = {
            k: old[k]
            for k in ("symbols", "start_ms", "end_ms", "kinds", "mode", "as_of_ms")
        }
        result = execute(self.settings, "test", "dataset_snapshot", d)
        self.assertEqual(result["dataset_hash"], h)
        self.assertEqual(self.repo.store("c02").dataset(h), old)

    def test_alternate_simulation_hash_cannot_bypass_reserved_interval(self):
        from tradee.c11 import SimulationStore, Scenario, SimulationConfig
        from tradee.c07 import FeeSchedule, ExecutionConfig
        from tradee.c08 import CandidateConfig
        from tradee.c06 import FundingConfig

        e = self.lock_holdout()
        h = e["variants"][0]["holdout_runs"][0]
        m = reader(self.profile, "c11").manifest(h)
        # A pre-existing alternative over the same raw interval is conservatively
        # locked too; protection is not just a list of registered run hashes.
        self.assertTrue(any(x["locked"] for x in self.get("runs").json()["data"]))
        policy = Repository(self.settings, self.profile).policy
        policy.locked_runs.clear()
        with self.assertRaisesRegex(ValidationError, "reserved final evidence"):
            policy.run(h)

    def test_completed_command_retry_returns_original_receipt_after_revision_changes(
        self,
    ):
        d = self.control()
        a = self.command("resume", d).json()["data"]
        state = WebState(self.settings.state_path)
        state.claim()
        state.finish(a["id"], execute(self.settings, "test", "resume", d))
        retry = self.command("resume", d)
        self.assertEqual(retry.status_code, 202)
        self.assertEqual(retry.json()["data"]["id"], a["id"])
        self.assertEqual(retry.json()["data"]["state"], "succeeded")

    def test_forward_cursor_hides_future_report_and_rejects_later_pinned_report(self):
        latest = self.repo.forward("forward")
        early = self.get("monitors/forward?at_ms=1").json()["data"]
        self.assertIsNone(early["report"])
        self.assertEqual(early["events"], [])
        self.assertEqual(
            self.get(
                "monitors/forward?at_ms=1&report_hash=" + latest["report_hash"]
            ).status_code,
            422,
        )

    def test_runner_continues_outcome_tail_after_detection_window(self):
        from unittest.mock import patch
        from backend.tradee_web import runners
        from tradee.c14 import SessionSpec

        d = dict(self.control(), monitor="forward", interval_seconds=0.5, max_cycles=1)
        with patch("backend.tradee_web.runners.subprocess.Popen"):
            uid = runners.start(self.settings, "test", d)["runner_id"]
        spec = SessionSpec.from_dict(self.head()["manifest"]["spec"])
        when = spec.end_ms + min(1000, spec.tail_ms // 2)
        with (
            patch("time.time", return_value=when / 1000),
            patch("time.sleep"),
            patch(
                "backend.tradee_web.operations.execute", return_value={}
            ) as execute_core,
        ):
            runners.run(self.settings, uid)
        self.assertEqual(
            [c.args[2] for c in execute_core.call_args_list],
            ["tick", "forward_observe"],
        )
        row = runners.catalog(WebState(self.settings.state_path), "test")[0]
        self.assertEqual(row["cycles"], 1)
        self.assertEqual(row["state"], "stopped")

    def test_runner_waits_for_future_start_without_observing_or_pausing(self):
        from unittest.mock import patch
        from backend.tradee_web import runners

        d = dict(self.control(), monitor="forward", interval_seconds=0.5, max_cycles=1)
        with patch("backend.tradee_web.runners.subprocess.Popen"):
            uid = runners.start(self.settings, "test", d)["runner_id"]
        state = WebState(self.settings.state_path)
        when = self.head()["manifest"]["spec"]["start_ms"] - 1000

        def request_stop(*args):
            with state.connection() as db:
                db.execute("UPDATE runners SET stop_requested=1 WHERE id=?", (uid,))

        with (
            patch("time.time", return_value=when / 1000),
            patch("time.sleep", side_effect=request_stop),
            patch("backend.tradee_web.operations.execute") as execute_core,
        ):
            runners.run(self.settings, uid)
        execute_core.assert_not_called()
        self.assertTrue(reader(self.profile, "c14").session("paper_demo")["paused"])

    def test_live_mark_funding_rate_is_separate_from_historical_settlement(self):
        h = self.head()["cycle"]["dataset"]["dataset_hash"]
        data = self.get(f"market?dataset_hash={h}&symbol=BTCUSDT").json()["data"]
        self.assertTrue(data["funding_series"])
        self.assertTrue(all(e["kind"] == "mark" for e in data["funding_series"]))
        self.assertEqual(data["funding_series"][-1]["data"]["funding_rate"], "0.001")

    def test_explicit_first_backfill_can_initialize_c02_after_registry(self):
        from unittest.mock import patch

        self.profile.path("c02").unlink()
        with patch(
            "tradee.c02.RestClient.backfill", return_value={"accepted": 0}
        ) as acquire:
            execute(
                self.settings,
                "test",
                "backfill",
                dict(symbol="BTCUSDT", start_ms=0, end_ms=60000, kind="candle"),
            )
        self.assertTrue(self.profile.path("c02").is_file())
        acquire.assert_called_once()

    def test_c12_frozen_model_is_available_without_copying_to_c10(self):
        h = self.head()["manifest"]["research"]["model_hash"]
        self.profile.path("c10").unlink()
        models = self.get("models").json()["data"]
        self.assertTrue(any(m["model_hash"] == h for m in models))
        model = self.get("models/" + h)
        self.assertEqual(model.status_code, 200)
        self.assertEqual(model.json()["data"]["model_hash"], h)
        self.assertFalse(self.profile.path("c10").exists())

    def test_research_detail_verifies_job_artifact_against_audit(self):
        e = self.repo.research()[0]["experiment_hash"]
        with mutation(self.profile.path("c12")) as db:
            other = db.execute(
                "SELECT artifact FROM jobs WHERE experiment=? AND key='report/holdout'",
                (e,),
            ).fetchone()[0]
            db.execute(
                "UPDATE jobs SET artifact=? WHERE experiment=? AND key='training/final'",
                (other, e),
            )
        self.assertEqual(self.get("research/" + e).status_code, 422)

    def test_generic_report_read_verifies_owning_inventory(self):
        h = self.head()["cycle"]["simulation"]["run_hash"]
        summary = reader(self.profile, "c11").summary(h)
        self.assertEqual(
            self.get("artifacts/c11/" + summary["report_hash"]).status_code, 200
        )
        with mutation(self.profile.path("c11")) as db:
            db.execute(
                "DELETE FROM artifacts WHERE run_hash=? AND hash=(SELECT MIN(hash) FROM artifacts WHERE run_hash=?)",
                (h, h),
            )
        self.assertGreaterEqual(
            self.get("artifacts/c11/" + summary["report_hash"]).status_code, 400
        )


if __name__ == "__main__":
    unittest.main()
