"""Local dashboard API. Viewer requests open every domain store read-only."""

import asyncio
import csv
import hmac
import io
import json
import time
from pathlib import Path
from fastapi import FastAPI, Request, Query, Header
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from tradee.c01 import ValidationError
from tradee.c06.engine import code_hash
from .config import load_settings, build_hash, ROOT
from .projections import Repository, redact, page
from .readers import MissingSource, LockedEvidence, SourceError
from .state import WebState
from .operations import JOBS, CONTROLS

COMMAND_FIELDS = {
    "refresh_registry": (set(), set()),
    "backfill": ({"symbol", "start_ms", "end_ms", "kind"}, set()),
    "dataset_snapshot": (
        {"symbols", "start_ms", "end_ms", "kinds", "mode", "as_of_ms"},
        {"delay_ms"},
    ),
    "start_runner": (
        {
            "session",
            "monitor",
            "reason",
            "expected_revision",
            "expected_audit_head",
            "interval_seconds",
            "max_cycles",
        },
        set(),
    ),
    "stop_runner": (
        {"session", "reason", "expected_revision", "expected_audit_head"},
        set(),
    ),
    "recover_runner": (
        {"session", "reason", "expected_revision", "expected_audit_head"},
        set(),
    ),
    "pause": ({"session", "reason", "expected_revision", "expected_audit_head"}, set()),
    "resume": (
        {"session", "reason", "expected_revision", "expected_audit_head"},
        set(),
    ),
    "recover": (
        {"session", "reason", "expected_revision", "expected_audit_head"},
        set(),
    ),
    "apply_pause": (
        {
            "session",
            "monitor",
            "report_hash",
            "reason",
            "expected_revision",
            "expected_audit_head",
        },
        set(),
    ),
    "reconcile_delivery": (
        {
            "session",
            "signal_id",
            "decision",
            "proof",
            "reason",
            "expected_revision",
            "expected_audit_head",
        },
        {"message_id"},
    ),
    "features": ({"dataset_hash", "config"}, set()),
    "simulation": (
        {"dataset_hash", "scenarios", "fees", "execution"},
        {"candidates", "funding", "calendars", "config"},
    ),
    "portfolio": ({"sources", "models"}, {"policy", "config"}),
    "register_experiment": ({"experiment"}, set()),
    "research_run": ({"experiment_hash"}, set()),
    "open_holdout": ({"experiment_hash", "reason", "confirmation"}, set()),
    "create_session": (
        {"experiment_hash", "portfolio_run", "spec", "monitor_name", "monitor_policy"},
        {"calendars"},
    ),
    "tick": ({"session"}, set()),
    "forward_observe": ({"monitor"}, set()),
    "replay": ({"monitor"}, {"report_hash"}),
}


def validate_command(kind, d):
    if kind not in COMMAND_FIELDS:
        raise ValidationError("Unsupported operator command")
    required, optional = COMMAND_FIELDS[kind]
    if not isinstance(d, dict) or required - set(d) or set(d) - required - optional:
        raise ValidationError("Command fields do not match the documented schema")
    if "reason" in required and (
        not isinstance(d["reason"], str) or not 5 <= len(d["reason"].strip()) <= 500
    ):
        raise ValidationError("A reason of 5–500 characters is required")
    if kind in CONTROLS and (
        type(d["expected_revision"]) is not int
        or d["expected_revision"] < 0
        or not isinstance(d["expected_audit_head"], str)
    ):
        raise ValidationError("Current session revision and audit head required")
    if kind == "open_holdout" and d["confirmation"] != f"OPEN {d['experiment_hash']}":
        raise ValidationError(
            "Type OPEN followed by the exact experiment hash to acknowledge irreversible holdout exposure"
        )

    import math, re

    for key in ("session", "monitor", "monitor_name"):
        if key in d and (
            not isinstance(d[key], str)
            or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", d[key])
        ):
            raise ValidationError("Bounded simple session/monitor name required")
    for key in (
        "dataset_hash",
        "experiment_hash",
        "portfolio_run",
        "report_hash",
        "signal_id",
    ):
        if (
            key in d
            and d[key] is not None
            and (
                not isinstance(d[key], str) or not re.fullmatch("[a-f0-9]{64}", d[key])
            )
        ):
            raise ValidationError("A pinned SHA256 artifact hash is required")
    if kind == "start_runner" and (
        type(d["interval_seconds"]) not in (int, float)
        or not math.isfinite(d["interval_seconds"])
        or not 0.5 <= d["interval_seconds"] <= 60
        or type(d["max_cycles"]) is not int
        or not 1 <= d["max_cycles"] <= 10000
    ):
        raise ValidationError(
            "Runner requires interval .5–60 seconds and 1–10000 cycles; hard duration limit is two hours"
        )
    if kind in ("backfill", "dataset_snapshot"):
        if (
            any(type(d[k]) is not int or d[k] < 0 for k in ("start_ms", "end_ms"))
            or not 0 < d["end_ms"] - d["start_ms"] <= 31 * 86400000
        ):
            raise ValidationError(
                "Data jobs require an ordered range of at most 31 days"
            )
    if kind == "backfill" and (
        d["kind"] not in ("candle", "funding", "open_interest")
        or not isinstance(d["symbol"], str)
        or not re.fullmatch("[A-Z0-9]{3,30}", d["symbol"])
    ):
        raise ValidationError("Supported Binance symbol/stream required")
    if kind == "features":
        from tradee.c03 import FeatureConfig

        FeatureConfig.from_dict(d["config"])
    if kind == "simulation":
        from tradee.c11 import Scenario, SimulationConfig
        from tradee.c07 import FeeSchedule, ExecutionConfig
        from tradee.c06 import FundingConfig
        from tradee.c08 import CandidateConfig

        if not isinstance(d["scenarios"], list) or not 1 <= len(d["scenarios"]) <= 100:
            raise ValidationError("1–100 frozen scenarios required")
        for x in d["scenarios"]:
            Scenario.from_dict(x)
        FeeSchedule.from_dict(d["fees"])
        ExecutionConfig.from_dict(d["execution"])
        SimulationConfig.from_dict(d.get("config", {}))
        FundingConfig.from_dict(d.get("funding", {}))
        if d.get("candidates"):
            CandidateConfig.from_dict(d["candidates"])
    if kind == "portfolio":
        from tradee.c13 import RiskPolicy, ReplayConfig

        RiskPolicy.from_dict(d.get("policy", {}))
        ReplayConfig.from_dict(d.get("config", {}))
        for key in ("sources", "models"):
            if (
                not isinstance(d[key], list)
                or not 1 <= len(d[key]) <= 100
                or any(
                    not isinstance(h, str) or not re.fullmatch("[a-f0-9]{64}", h)
                    for h in d[key]
                )
            ):
                raise ValidationError("Bounded pinned source/model hashes required")
    if kind == "register_experiment":
        from tradee.c12.contracts import Experiment

        Experiment.from_dict(d["experiment"])
    if kind == "create_session":
        from tradee.c14 import SessionSpec
        from tradee.c15 import MonitorPolicy

        SessionSpec.from_dict(d["spec"])
        MonitorPolicy.from_dict(d["monitor_policy"])
    if kind == "reconcile_delivery" and (
        d["decision"] not in ("sent", "not_sent")
        or not isinstance(d["proof"], str)
        or not d["proof"].strip()
    ):
        raise ValidationError("Explicit reconciliation decision and evidence required")


def create_app(settings=None):
    settings = settings or load_settings()
    state = WebState(settings.state_path)
    app = FastAPI(
        title="Tradee local dashboard",
        version="1.0",
        docs_url=None,
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.web = state
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"]
    )

    @app.middleware("http")
    async def boundary(request, call_next):
        origin = request.headers.get("origin")
        if origin and origin not in settings.origins:
            return JSONResponse(
                {
                    "error": {
                        "code": "origin_denied",
                        "message": "This origin is not allowed",
                    }
                },
                403,
            )
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            raw = await request.body()
            if len(raw) > 100000:
                return JSONResponse(
                    {
                        "error": {
                            "code": "body_too_large",
                            "message": "Command exceeds 100 KB",
                        }
                    },
                    413,
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ValidationError)
    async def invalid(request, exc):
        status = (
            423
            if isinstance(exc, LockedEvidence)
            else (
                404
                if isinstance(exc, MissingSource)
                else 409 if isinstance(exc, SourceError) else 422
            )
        )
        return JSONResponse(
            {"error": {"code": type(exc).__name__, "message": str(exc)[:300]}}, status
        )

    @app.exception_handler(Exception)
    async def unavailable(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": "source_unavailable",
                    "message": "Source could not be verified; inspect the local server log",
                }
            },
            503,
        )

    @app.get("/api/{workspace}/runners")
    def runners(workspace: str):
        from .runners import catalog

        settings.profile(workspace)
        return result(catalog(state, workspace), workspace)

    def repo(workspace):
        return Repository(settings, settings.profile(workspace))

    def result(data, workspace=None):
        if len(json.dumps(data).encode()) > settings.max_document_bytes:
            raise SourceError("Response exceeds the bounded document budget")
        return dict(
            data=redact(data),
            meta=dict(
                recorded_at_ms=int(time.time() * 1000),
                workspace=workspace,
                synthetic=settings.profile(workspace).synthetic if workspace else False,
                core_build=code_hash(),
                api_build=build_hash(),
            ),
        )

    def operator(request):
        if not settings.operator_token or not hmac.compare_digest(
            request.headers.get("authorization", ""),
            "Bearer " + settings.operator_token,
        ):
            from fastapi import HTTPException

            raise HTTPException(401, "Operator authorization required")

    def catalog(r, method):
        try:
            return getattr(r, method)()
        except MissingSource:
            return []

    @app.get("/api/health")
    def health():
        return result(dict(status="ok", operator_enabled=bool(settings.operator_token)))

    @app.get("/api/bootstrap")
    def bootstrap():
        return result(
            dict(
                workspaces=[
                    dict(id=p.id, label=p.label, synthetic=p.synthetic)
                    for p in settings.profiles
                ],
                default_workspace=settings.default_profile,
                operator_enabled=bool(settings.operator_token),
                commands=list(COMMAND_FIELDS),
            )
        )

    @app.get("/api/{workspace}/overview")
    def overview(workspace: str):
        r = repo(workspace)
        return result(
            dict(
                sources=r.sources(),
                sessions=catalog(r, "sessions"),
                datasets=catalog(r, "datasets"),
                monitors=catalog(r, "monitors"),
            ),
            workspace,
        )

    @app.get("/api/{workspace}/sessions")
    def sessions(workspace: str):
        return result(catalog(repo(workspace), "sessions"), workspace)

    @app.get("/api/{workspace}/sessions/{name}")
    def session(workspace: str, name: str, at_ms: int | None = Query(None, ge=0)):
        return result(repo(workspace).session(name, at_ms), workspace)

    @app.get("/api/{workspace}/sessions/{name}/signals")
    def signals(
        workspace: str,
        name: str,
        at_ms: int | None = Query(None, ge=0),
        limit: int = Query(50, ge=1, le=200),
        cursor: str | None = None,
    ):
        return result(
            page(
                repo(workspace).session(name, at_ms)["signals"],
                limit,
                cursor,
                f"{workspace}/{name}/{at_ms}",
            ),
            workspace,
        )

    @app.get("/api/{workspace}/sessions/{name}/signals/{sid}")
    def signal(
        workspace: str, name: str, sid: str, at_ms: int | None = Query(None, ge=0)
    ):
        return result(repo(workspace).signal(name, sid, at_ms), workspace)

    @app.get("/api/{workspace}/sessions/{name}/portfolio")
    def portfolio(workspace: str, name: str, at_ms: int | None = Query(None, ge=0)):
        return result(repo(workspace).portfolio(name, at_ms), workspace)

    @app.get("/api/{workspace}/sessions/{name}/analytics")
    def analytics(workspace: str, name: str, at_ms: int | None = Query(None, ge=0)):
        from .analytics import funded, lineage

        r = repo(workspace)
        return result(
            dict(funded=funded(r, name, at_ms), lineage=lineage(r, name, at_ms)),
            workspace,
        )

    @app.get("/api/{workspace}/datasets")
    def datasets(workspace: str):
        return result(catalog(repo(workspace), "datasets"), workspace)

    @app.get("/api/{workspace}/market")
    def market(
        workspace: str,
        dataset_hash: str,
        symbol: str,
        timeframe: str = "1m",
        start_ms: int | None = Query(None, ge=0),
        end_ms: int | None = Query(None, ge=0),
        at_ms: int | None = Query(None, ge=0),
        limit: int = Query(500, ge=1, le=2000),
        feature_run: str | None = None,
    ):
        return result(
            repo(workspace).market(
                dataset_hash,
                symbol,
                timeframe,
                start_ms,
                end_ms,
                at_ms,
                limit,
                feature_run,
            ),
            workspace,
        )

    @app.get("/api/{workspace}/research")
    def research(workspace: str):
        return result(catalog(repo(workspace), "research"), workspace)

    @app.get("/api/{workspace}/research/{key}")
    def experiment(workspace: str, key: str):
        return result(repo(workspace).experiment(key), workspace)

    @app.get("/api/{workspace}/runs")
    def runs(
        workspace: str,
        kind: str = Query("simulation", pattern="^(simulation|portfolio)$"),
    ):
        try:
            data = repo(workspace).runs(kind)
        except MissingSource:
            data = []
        return result(data, workspace)

    @app.get("/api/{workspace}/runs/{key}")
    def run(
        workspace: str,
        key: str,
        kind: str = Query("simulation", pattern="^(simulation|portfolio)$"),
    ):
        return result(repo(workspace).run(key, kind), workspace)

    @app.get("/api/{workspace}/models")
    def models(workspace: str):
        return result(catalog(repo(workspace), "models"), workspace)

    @app.get("/api/{workspace}/models/{key}")
    def model(workspace: str, key: str):
        return result(repo(workspace).model(key), workspace)

    @app.get("/api/{workspace}/monitors")
    def monitors(workspace: str):
        return result(catalog(repo(workspace), "monitors"), workspace)

    @app.get("/api/{workspace}/monitors/{name}")
    def monitor(
        workspace: str,
        name: str,
        report_hash: str | None = None,
        at_ms: int | None = Query(None, ge=0),
    ):
        return result(repo(workspace).forward(name, report_hash, at_ms), workspace)

    @app.get("/api/{workspace}/instruments")
    def instruments(workspace: str):
        return result(catalog(repo(workspace), "instruments"), workspace)

    @app.get("/api/{workspace}/quality/{key}")
    def quality(workspace: str, key: str):
        return result(repo(workspace).quality(key), workspace)

    @app.get("/api/{workspace}/artifacts/{kind}/{key}")
    def artifact(workspace: str, kind: str, key: str, download: bool = False):
        data = result(repo(workspace).artifact(kind, key), workspace)
        if download:
            return Response(
                json.dumps(data, indent=2),
                media_type="application/json",
                headers={
                    "Content-Disposition": f'attachment; filename="{kind}-evidence.json"'
                },
            )
        return data

    @app.get("/api/{workspace}/sessions/{name}/export")
    def export(
        workspace: str, name: str, format: str = Query("json", pattern="^(json|csv)$")
    ):
        data = redact(repo(workspace).session(name))
        if format == "json":
            return Response(
                json.dumps(result(data, workspace), indent=2),
                media_type="application/json",
                headers={
                    "Content-Disposition": 'attachment; filename="session-evidence.json"'
                },
            )
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(
            [
                "signal_id",
                "symbol",
                "side",
                "phase",
                "detected_ms",
                "entry_ms",
                "delivery",
                "scope",
            ]
        )
        for s in data["signals"]:
            values = [
                s["signal_id"],
                s["candidate"]["symbol"],
                s["candidate"]["side"],
                s["phase"],
                s["detected_ms"],
                s["entry_ms"],
                (s.get("delivery") or {}).get("state"),
                "hypothetical paper",
            ]
            writer.writerow(
                [
                    "'" + str(v) if str(v).startswith(("=", "+", "-", "@")) else v
                    for v in values
                ]
            )
        return Response(
            out.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="signals.csv"'},
        )

    @app.get("/api/{workspace}/worker")
    def worker_status(workspace: str):
        settings.profile(workspace)
        return result(state.worker_status(), workspace)

    @app.get("/api/{workspace}/jobs")
    def jobs(workspace: str):
        settings.profile(workspace)
        return result(state.jobs(workspace), workspace)

    @app.post("/api/{workspace}/commands/{kind}", status_code=202)
    async def command(workspace: str, kind: str, request: Request):
        operator(request)
        settings.profile(workspace)
        try:
            d = await request.json()
        except ValueError:
            raise ValidationError("JSON command required")
        validate_command(kind, d)
        key = request.headers.get("idempotency-key")
        existing = state.lookup(workspace, key, kind, d)
        if existing:
            return result(existing, workspace)
        if kind in CONTROLS:
            h = repo(workspace).session(d["session"])
            if (
                d["expected_revision"] != h["revision"]
                or d["expected_audit_head"] != h["audit_head"]
            ):
                existing = state.lookup(workspace, key, kind, d)
                if existing:
                    return result(existing, workspace)
                raise SourceError(
                    "Session changed; refresh before submitting the control"
                )
        r = state.request(workspace, request.headers.get("idempotency-key"), kind, d)
        return result(r, workspace)

    @app.post("/api/{workspace}/jobs/{uid}/cancel")
    def cancel(workspace: str, uid: str, request: Request):
        operator(request)
        if state.get(uid)["workspace"] != workspace:
            raise ValidationError("Operation belongs to another workspace")
        return result(state.cancel(uid), workspace)

    @app.get("/api/{workspace}/events")
    async def events(workspace: str, request: Request, after: int = Query(0, ge=0)):
        profile = settings.profile(workspace)
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            raise ValidationError("Invalid event cursor")

        async def stream():
            nonlocal cursor
            yield "retry: 3000\n\n"
            low, high = state.bounds(workspace)
            if cursor and (high is None or cursor > high or cursor < (low or 0) - 1):
                cursor = 0
                yield 'event: resync\ndata: {"reason":"cursor_outside_retention"}\n\n'

            while not await request.is_disconnected():
                for kind, path in profile.paths.items():
                    p = Path(path)
                    stat = p.stat() if p.exists() else None
                    state.sync(
                        workspace,
                        kind,
                        (
                            None
                            if stat is None
                            else [
                                stat.st_mtime_ns,
                                stat.st_size,
                                [
                                    (q.stat().st_mtime_ns, q.stat().st_size)
                                    for q in [Path(str(p) + "-wal")]
                                    if q.exists()
                                ],
                            ]
                        ),
                    )
                for e in state.events(workspace, cursor):
                    cursor = e["id"]
                    yield f"id: {cursor}\nevent: {e['kind']}\ndata: {json.dumps(e['document'])}\n\n"
                state.prune_events()
                yield ": heartbeat\n\n"
                await asyncio.sleep(3)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )

    dist = ROOT / "frontend/dist"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"error": {"message": "Unknown API route"}}, 404)
        target = (dist / path).resolve()
        if target.is_relative_to(dist.resolve()) and target.is_file():
            return FileResponse(target)
        if (dist / "index.html").is_file():
            return FileResponse(dist / "index.html")
        return JSONResponse(
            {"message": "Build frontend with npm run build in frontend/"}, 503
        )

    return app
