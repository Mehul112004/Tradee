"""Allowlisted commands delegated to the production core; no Telegram sends."""

import time
from pathlib import Path
from tradee.c01 import Registry, ValidationError
from tradee.c02 import MarketStore
from tradee.c03 import FeatureStore, FeatureConfig
from tradee.c07 import ExecutionConfig, FeeSchedule
from tradee.c06 import FundingConfig
from tradee.c08 import CandidateConfig
from tradee.c10 import EstimatorStore
from tradee.c11 import SimulationStore, Scenario, SimulationConfig
from tradee.c12 import ResearchStore
from tradee.c13 import PortfolioStore, RiskPolicy, ReplayConfig
from tradee.c14 import SignalStore, SessionSpec, SignalRuntime, load_release, Dispatcher
from tradee.c15 import MonitorStore, MonitorPolicy, ForwardMonitor, reconcile
from .projections import Repository

JOBS = (
    "features",
    "simulation",
    "portfolio",
    "research_run",
    "open_holdout",
    "register_experiment",
    "create_session",
    "tick",
    "forward_observe",
    "replay",
)
CONTROLS = (
    "start_runner",
    "stop_runner",
    "recover_runner",
    "pause",
    "resume",
    "apply_pause",
    "recover",
    "reconcile_delivery",
)


def stores(profile):
    """Only called after explicit operator command admission, never by a GET."""
    return {
        k: profile.path(k)
        for k in ("c01", "c02", "c03", "c10", "c11", "c12", "c13", "c14", "c15")
    }


def execute(settings, workspace, kind, d):
    profile = settings.profile(workspace)
    paths = stores(profile)
    repo = Repository(settings, profile)

    def require(*kinds):
        for k in kinds:
            if not paths[k].is_file():
                raise ValidationError(f"{k}: existing source required")

    def market():
        require("c01", "c02")
        return MarketStore(Registry(paths["c01"]), paths["c02"])

    def sim():
        require("c11")
        return SimulationStore(paths["c11"])

    def portfolio():
        require("c13")
        return PortfolioStore(paths["c13"])

    def signals():
        require("c14")
        return SignalStore(paths["c14"])

    def research():
        require("c12")
        return ResearchStore(paths["c12"])

    def forward():
        require("c15")
        return ForwardMonitor(MonitorStore(paths["c15"]), signals(), sim(), portfolio())

    now = int(time.time() * 1000)
    if kind == "refresh_registry":
        from tradee.c01 import BinanceProvider

        return Registry(paths["c01"]).refresh(BinanceProvider())
    if kind == "backfill":
        from tradee.c02 import RestClient

        repo.policy.range(d["start_ms"], d["end_ms"])
        require("c01")
        target = MarketStore(Registry(paths["c01"]), paths["c02"])
        return RestClient().backfill(
            target, d["symbol"], d["start_ms"], d["end_ms"], d["kind"]
        )
    if kind == "dataset_snapshot":
        repo.policy.range(d["start_ms"], d["end_ms"])
        return market().snapshot(
            d["symbols"],
            d["start_ms"],
            d["end_ms"],
            d["kinds"],
            d["mode"],
            d.get("delay_ms"),
            d["as_of_ms"],
        )
    if kind in CONTROLS:
        name = d["session"]
        head = repo.session(name)
        if (
            d.get("expected_revision") != head["revision"]
            or d.get("expected_audit_head") != head["audit_head"]
        ):
            raise ValidationError(
                "Control compare-and-swap conflict; refresh the session"
            )
        if kind == "start_runner":
            from .runners import start

            if not head["producer_compatible"]:
                raise ValidationError(
                    "Runner requires the current frozen core producer"
                )
            if now >= SessionSpec.from_dict(head["manifest"]["spec"]).tail_end_ms:
                raise ValidationError(
                    "Session has ended; create a new prospective session"
                )
            if repo.forward(d["monitor"])["head"]["manifest"]["session"] != name:
                raise ValidationError("Monitor/session mismatch")
            return start(settings, workspace, d)
        if kind == "recover_runner":
            from .runners import recover

            return recover(settings, workspace, name)
        if kind == "stop_runner":
            from .runners import stop

            return stop(settings, workspace, name)
        if kind in ("pause", "resume"):
            return signals().pause(
                name,
                kind == "pause",
                d["reason"],
                now,
                head["revision"],
                head["audit_head"],
            )
        # The single durable worker serializes web controls. Core delivery
        # operations retain their own durable claim/reconciliation transactions.
        if kind == "recover":
            return Dispatcher(signals()).recover(name, now)
        if kind == "apply_pause":
            if repo.forward(d["monitor"])["head"]["manifest"]["session"] != name:
                raise ValidationError("Monitor does not belong to the selected session")
            return forward().apply_pause(d["monitor"], d["report_hash"], now)
        if kind == "reconcile_delivery":
            if not any(x["signal_id"] == d["signal_id"] for x in head["signals"]):
                raise ValidationError("Signal not owned by this session")
            return Dispatcher(signals()).reconcile(
                d["signal_id"], d["decision"], d["proof"], d.get("message_id")
            )
    if kind == "features":
        require("c01", "c02")
        ds = repo.store("c02").dataset(d["dataset_hash"])
        repo.policy.range(ds["start_ms"], ds["end_ms"])
        return FeatureStore(paths["c03"]).run(
            market(), d["dataset_hash"], FeatureConfig.from_dict(d["config"])
        )
    if kind == "simulation":
        require("c01", "c02")
        ds = repo.store("c02").dataset(d["dataset_hash"])
        repo.policy.range(ds["start_ms"], ds["end_ms"])
        return SimulationStore(paths["c11"]).run(
            market(),
            d["dataset_hash"],
            [Scenario.from_dict(x) for x in d["scenarios"]],
            FeeSchedule.from_dict(d["fees"]),
            ExecutionConfig.from_dict(d["execution"]),
            CandidateConfig.from_dict(d["candidates"]) if d.get("candidates") else None,
            FundingConfig.from_dict(d.get("funding", {})),
            d.get("calendars", []),
            SimulationConfig.from_dict(d.get("config", {})),
        )
    if kind == "portfolio":
        for h in d["sources"]:
            repo.policy.run(h)
        models = [repo.model(h) for h in d["models"]]
        return PortfolioStore(paths["c13"]).replay(
            sim(),
            market(),
            d["sources"],
            models,
            RiskPolicy.from_dict(d.get("policy", {})),
            ReplayConfig.from_dict(d.get("config", {})),
        )
    if kind == "register_experiment":
        return ResearchStore(paths["c12"]).register(d["experiment"])
    if kind == "research_run":
        return research().run(d["experiment_hash"], sim())
    if kind == "open_holdout":
        return research().open_holdout(d["experiment_hash"], sim(), d["reason"])
    if kind == "create_session":
        spec = SessionSpec.from_dict(d["spec"])
        monitor_policy = MonitorPolicy.from_dict(d["monitor_policy"])
        require("c01", "c02", "c11", "c12", "c13")
        signal_store = SignalStore(paths["c14"])
        manifest = load_release(
            research(),
            portfolio(),
            sim(),
            d["experiment_hash"],
            d["portfolio_run"],
            spec,
            d.get("calendars", []),
        )
        result = signal_store.create(manifest)
        monitor = ForwardMonitor(
            MonitorStore(paths["c15"]), signal_store, sim(), portfolio()
        )
        try:
            registered = monitor.store.head(d["monitor_name"])
        except ValidationError:
            registered = monitor.register(
                d["monitor_name"], spec.name, monitor_policy, now
            )
        if (
            registered["manifest"]["deployment_hash"] != result["deployment_hash"]
            or registered["manifest"]["policy"] != monitor_policy.document()
        ):
            raise ValidationError(
                "Existing monitor does not match this frozen deployment/policy"
            )
        return dict(session=result, monitor=registered, runner_started=False)
    if kind == "tick":
        # Data collection remains a separately owned core CLI process. A UI tick
        # must not run an unmonitored session or advance beyond its bounded tail.
        require("c15")
        names = [m for m in repo.monitors() if m["manifest"]["session"] == d["session"]]
        if not names:
            raise ValidationError(
                "Register a prospective C15 monitor before ticking this session"
            )
        spec = SessionSpec.from_dict(repo.session(d["session"])["manifest"]["spec"])
        stamp = min(now - spec.runtime.source_settle_ms, spec.tail_end_ms)
        return SignalRuntime(signals(), market(), sim(), portfolio()).tick(
            d["session"], stamp
        )
    if kind == "forward_observe":
        return forward().observe(d["monitor"], now)
    if kind == "replay":
        return reconcile(forward(), d["monitor"], market(), now, d.get("report_hash"))
    raise ValidationError("Unknown command kind")
