"""Source-qualified dashboard queries. Domain math and verification stay in core."""

from collections import Counter
from copy import deepcopy
import base64
import json
import time
from decimal import Decimal, localcontext
from tradee.c01 import ValidationError, Policy
from tradee.c01.domain import fingerprint
from tradee.c02.domain import aggregate
from tradee.c03.catalog import TIMEFRAMES
from tradee.c10.source import pages
from tradee.c06.engine import code_hash
from .config import KINDS
from .readers import (
    reader,
    indexed,
    document,
    AccessPolicy,
    MissingSource,
    SourceError,
    LockedEvidence,
)


def redact(value):
    if isinstance(value, list):
        return [redact(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for k, v in value.items():
        if k.lower() in ("token", "api_key", "secret", "authorization", "proof"):
            result[k] = "[redacted]"
        elif k == "chat_id" and v is not None:
            result[k] = "…" + str(v)[-4:]
        else:
            result[k] = redact(v)
    return result


def page(items, limit=50, cursor=None, scope=""):
    version = fingerprint(items)
    start = 0
    if cursor:
        try:
            p = json.loads(base64.urlsafe_b64decode(cursor.encode()))
            start = p["offset"]
            if p["version"] != version or p["scope"] != scope:
                raise SourceError("Collection changed; refresh before paging")
            if type(start) is not int or not 0 <= start <= len(items):
                raise ValueError()
        except SourceError:
            raise
        except Exception as e:
            raise ValidationError("Invalid pagination cursor") from e
    token = None
    if start + limit < len(items):
        token = base64.urlsafe_b64encode(
            json.dumps(
                dict(version=version, scope=scope, offset=start + limit)
            ).encode()
        ).decode()
    return dict(
        items=items[start : start + limit],
        total=len(items),
        next_cursor=token,
        version=version,
    )


class Repository:
    def __init__(self, settings, profile):
        self.settings = settings
        self.profile = profile
        self.policy = AccessPolicy(profile)
        self._readers = {}

    def store(self, kind):
        if kind not in self._readers:
            self._readers[kind] = reader(self.profile, kind)
        return self._readers[kind]

    def sources(self):
        items = []
        for kind in KINDS:
            try:
                s = self.store(kind)
                with s.connection() as db:
                    tables = [
                        r[0]
                        for r in db.execute(
                            "SELECT name FROM sqlite_master WHERE type='table'"
                        )
                    ]
                items.append(
                    dict(
                        component=kind,
                        state="available",
                        schema_version=1,
                        tables=len(tables),
                    )
                )
            except MissingSource:
                items.append(dict(component=kind, state="not_configured"))
            except Exception:
                # Only a fixed error class goes to the browser, never a path/provider payload.
                items.append(dict(component=kind, state="integrity_error"))
        return items

    def sessions(self):
        s = self.store("c14")
        rows = indexed(s, "SELECT name FROM sessions ORDER BY name")
        result = []
        for r in rows:
            h = s.session(r["name"])
            self.policy.experiment(h["manifest"]["research"]["experiment_hash"])
            c = h["cycle"]
            spec = h["manifest"]["spec"]
            now = int(time.time() * 1000)
            result.append(
                dict(
                    name=r["name"],
                    deployment_hash=h["deployment_hash"],
                    revision=h["revision"],
                    cycle_hash=h["cycle_hash"],
                    mode=spec["runtime"]["mode"],
                    paused=bool(h["paused"]),
                    fault=h["fault"],
                    start_ms=spec["start_ms"],
                    end_ms=spec["end_ms"],
                    as_of_ms=None if c is None else c["as_of_ms"],
                    health=None if c is None else c["health"],
                    age_ms=None if c is None else max(0, now - c["as_of_ms"]),
                    producer_compatible=h["manifest"]["code_hash"] == code_hash(),
                    symbols=h["manifest"]["execution"]["enabled_symbols"],
                )
            )
        return result

    def session(self, name, at_ms=None):
        s = self.store("c14")
        evidence = s.evidence(name)
        h = evidence["head"]
        self.policy.experiment(h["manifest"]["research"]["experiment_hash"])
        events = evidence["events"]
        cycles = evidence["cycles"]
        cycle = h["cycle"]
        replay_clocks = [max(x["cycle"]["as_of_ms"], x["recorded_ms"]) for x in cycles]
        if at_ms is not None:
            cycles = [
                i
                for i in cycles
                if max(i["cycle"]["as_of_ms"], i["recorded_ms"]) <= at_ms
            ]
            cycle = None if not cycles else cycles[-1]["cycle"]
            events = [e for e in events if max(e["at_ms"], e["recorded_ms"]) <= at_ms]
        delivery = {}
        for e in events:
            d = e["payload"].get("delivery")
            if d:
                delivery[d["signal_id"]] = d
        recording = {}
        for item in cycles:
            for signal in item["cycle"]["signals"]:
                stamps = recording.setdefault(signal["signal_id"], {})
                stamps.setdefault("first_detection_ms", item["recorded_ms"])
                if signal.get("entry_ms") is not None:
                    stamps.setdefault("first_admission_ms", item["recorded_ms"])
                if signal.get("paper_outcome") is not None:
                    stamps.setdefault("first_outcome_ms", item["recorded_ms"])
        signals = (
            []
            if cycle is None
            else [
                dict(
                    x,
                    delivery=delivery.get(x["signal_id"]),
                    recording=recording.get(x["signal_id"], {}),
                )
                for x in cycle["signals"]
            ]
        )
        paused = next(
            (
                e["kind"] == "paused"
                for e in reversed(events)
                if e["kind"] in ("paused", "resumed")
            ),
            False,
        )
        return dict(
            name=name,
            manifest=h["manifest"],
            deployment_hash=h["deployment_hash"],
            revision=h["revision"] if at_ms is None else None,
            audit_head=events[-1]["event_hash"] if events else None,
            cycle_hash=fingerprint(cycle) if cycle else None,
            cycle=cycle,
            signals=signals,
            events=events,
            replay_clocks=replay_clocks,
            cycles=[
                dict(
                    cycle_hash=x["cycle_hash"],
                    as_of_ms=x["cycle"]["as_of_ms"],
                    recorded_ms=x["recorded_ms"],
                    processing_ms=x["processing_ms"],
                )
                for x in cycles
            ],
            paused=paused,
            mode=h["manifest"]["spec"]["runtime"]["mode"],
            view="decision_as_of" if at_ms is not None else "latest_recorded",
            producer_compatible=h["manifest"]["code_hash"] == code_hash(),
        )

    def signal(self, name, sid, at_ms=None):
        h = self.session(name, at_ms)
        s = next((x for x in h["signals"] if x["signal_id"] == sid), None)
        if s is None:
            raise ValidationError("Signal not present in this evidence vintage")
        return dict(
            signal=s,
            cycle_hash=h["cycle_hash"],
            dataset=h["cycle"]["dataset"],
            events=[
                e
                for e in h["events"]
                if e["payload"].get("delivery", {}).get("signal_id") == sid
            ],
            model_hash=h["manifest"]["research"]["model_hash"],
            scenario=h["manifest"]["scenario"],
        )

    def portfolio(self, name, at_ms=None):
        h = self.session(name, at_ms)
        c = h["cycle"]
        if c is None:
            return dict(
                available=False,
                reason="No paper cycle at this cursor",
                samples=[],
                trades=[],
            )
        p = self.store("c13")
        summary = p.summary(c["portfolio"]["run_hash"])
        if summary != c["portfolio"]:
            raise SourceError("Portfolio receipt mismatch")
        report = p.report(summary["report_hash"])
        samples = [
            x["payload"]
            for x in p.records(summary["run_hash"])
            if x["kind"] == "sample"
        ]
        if report["terminal_account"] != c["paper_account"]:
            raise SourceError("Paper wallet differs from funded report")
        return dict(
            available=True,
            run_hash=summary["run_hash"],
            report_hash=summary["report_hash"],
            report=report,
            samples=samples,
            account=c["paper_account"],
            risk=c["paper_risk"],
            policy=h["manifest"]["risk"],
            trades=report["trades"],
            scope="Shared hypothetical paper wallet",
        )

    def datasets(self):
        s = self.store("c02")
        result = []
        for r in indexed(s, "SELECT hash,document FROM datasets ORDER BY rowid DESC"):
            d = document(r["document"], r["hash"])
            result.append(dict(dataset_hash=r["hash"], **d))
        return sorted(
            result, key=lambda x: (x["as_of_ms"], x["event_count"]), reverse=True
        )

    def market(
        self,
        dataset_hash,
        symbol,
        timeframe="1m",
        start_ms=None,
        end_ms=None,
        at_ms=None,
        limit=500,
        feature_run=None,
    ):
        if timeframe not in TIMEFRAMES:
            raise ValidationError("Unsupported timeframe; use the C03 catalog")
        s = self.store("c02")
        ds = s.dataset(dataset_hash)
        copy = dict(ds)
        copy.pop("dataset_hash")
        if fingerprint(copy) != dataset_hash:
            raise SourceError("Dataset hash verification failed")
        if symbol not in ds["symbols"]:
            raise ValidationError("Instrument not in this dataset")
        cutoff = ds["as_of_ms"] if at_ms is None else min(at_ms, ds["as_of_ms"])
        interval = TIMEFRAMES[timeframe]
        end = (
            min(ds["end_ms"], cutoff + 1)
            if end_ms is None
            else min(end_ms, ds["end_ms"], cutoff + 1)
        )
        start = (
            max(ds["start_ms"], end - limit * interval)
            if start_ms is None
            else max(start_ms, ds["start_ms"])
        )
        if start >= end:
            raise ValidationError("Ordered intersecting market range required")
        self.policy.range(start, end)
        cutoff = min(cutoff, end)
        events = []
        latest = {}
        partials = {}
        quotes = {}
        seen = set()
        quote_series = []
        funding_series = []
        for e in s.replay(dataset_hash, until_ms=cutoff):
            events.append(e)
            if len(events) > self.settings.max_events:
                raise SourceError("Market read event budget exceeded")
            if e["symbol"] != symbol:
                continue
            if e["kind"] == "quote" and start <= e["event_ms"] < end:
                with localcontext() as ctx:
                    ctx.prec = 120
                    bid = Decimal(e["data"]["bid"])
                    ask = Decimal(e["data"]["ask"])
                    spread = (
                        str((ask - bid) / ((ask + bid) / 2) * 10000)
                        if ask + bid
                        else None
                    )
                quote_series.append(
                    dict(
                        e,
                        spread_bps=spread,
                        available_delay_ms=e["available_ms"] - e["event_ms"],
                    )
                )
            if (
                e["kind"] in ("funding", "mark")
                and e["data"].get("funding_rate") is not None
                and start <= e["event_ms"] < end
            ):
                funding_series.append(e)
            if e["kind"] == "candle":
                key = (e["instrument_id"], e["key"])
                seen.add(key)
                if e["final"]:
                    latest[key] = e
                else:
                    partials[key] = e
            elif e["kind"] in ("quote", "mark", "trade", "funding"):
                old = quotes.get(e["kind"])
                if old is None or (e["event_ms"], e["available_ms"], e["id"]) > (
                    old["event_ms"],
                    old["available_ms"],
                    old["id"],
                ):
                    quotes[e["kind"]] = e
        bars = aggregate(list(latest.values()), interval)
        metadata = None
        if latest:
            observation = list(latest.values())[-1]
            metadata = self.store("c01").version(observation["metadata_version"])
        bars = [
            b
            for b in bars
            if start <= b["data"]["open_ms"] < end
            and b["data"]["close_ms"] + 1 <= cutoff
        ][-limit:]
        gaps = []
        for a, b in zip(bars, bars[1:]):
            if b["data"]["open_ms"] > a["data"]["open_ms"] + interval:
                gaps.append(
                    dict(
                        start_ms=a["data"]["open_ms"] + interval,
                        end_ms=b["data"]["open_ms"],
                    )
                )
        features = []
        feature_manifest = None
        feature_source = None
        fs = self.store("c03") if self.profile.path("c03").exists() else None
        materialized = None
        if fs:
            with fs.connection() as db:
                if feature_run:
                    row = db.execute(
                        "SELECT hash FROM runs WHERE hash=?", (feature_run,)
                    ).fetchone()
                    if row:
                        materialized = row["hash"]
                else:
                    row = db.execute(
                        "SELECT run_hash FROM snapshots WHERE json_extract(document,'$.dataset_hash')=? AND json_extract(document,'$.timeframe')=? AND json_extract(document,'$.evaluation_as_of_ms')<=? ORDER BY computed_at_ms DESC,rowid DESC LIMIT 1",
                        (dataset_hash, timeframe, cutoff),
                    ).fetchone()
                    if row:
                        materialized = row["run_hash"]
        if materialized:
            feature_manifest = fs.manifest(materialized)
            if feature_manifest["dataset"]["dataset_hash"] != dataset_hash:
                raise ValidationError("Feature run must share the exact chart dataset")
            feature_source = (
                "C03 materialized causal reconstruction; not a decision publication"
            )
            for row in indexed(
                fs,
                "SELECT hash,document FROM snapshots WHERE run_hash=? AND json_extract(document,'$.timeframe')=? AND json_extract(document,'$.target_open_ms')>=? AND json_extract(document,'$.target_open_ms')<? AND json_extract(document,'$.evaluation_as_of_ms')<=? ORDER BY json_extract(document,'$.evaluation_as_of_ms')",
                (materialized, timeframe, start, end, cutoff),
                limit=self.settings.max_rows,
            ):
                f = document(row["document"], row["hash"])
                if f["instrument_id"].split(":")[2] == symbol:
                    features.append(f)
        elif feature_run:
            self.policy.run(feature_run)
            sim = self.store("c11")
            feature_manifest = sim.manifest(feature_run)
            if feature_manifest["dataset"]["dataset_hash"] != dataset_hash:
                raise ValidationError("Feature run must share the exact chart dataset")
            sim.summary(feature_run)
            feature_source = "C11 frozen simulation feature artifacts"
            for a in pages(sim, feature_run, "feature"):
                f = a["payload"]
                if (
                    f["timeframe"] == timeframe
                    and f["target_open_ms"] is not None
                    and start <= f["target_open_ms"] < end
                    and f["evaluation_as_of_ms"] <= cutoff
                    and f["instrument_id"].split(":")[2] == symbol
                ):
                    features.append(f)
        return dict(
            dataset_hash=dataset_hash,
            dataset=ds,
            symbol=symbol,
            timeframe=timeframe,
            start_ms=start,
            end_ms=end,
            as_of_ms=cutoff,
            candles=bars,
            metadata=metadata,
            quotes=quotes,
            quote_series=quote_series,
            funding_series=funding_series,
            feature_manifest=feature_manifest,
            feature_source=feature_source,
            features=sorted(
                features, key=lambda f: (f["target_open_ms"], f["evaluation_as_of_ms"])
            ),
            gaps=gaps,
            provisional=[
                e
                for k, e in partials.items()
                if k not in latest and start <= e["data"]["open_ms"] < end
            ],
            coverage=dict(
                final_minutes=len(latest),
                distinct_candle_keys=len(seen),
                returned_bars=len(bars),
                gap_intervals=len(gaps),
            ),
            feature_status="available" if features else "not_materialized",
            sampling="none",
            availability_basis=ds["mode"],
        )

    def research(self):
        s = self.store("c12")
        result = []
        for r in indexed(s, "SELECT hash FROM experiments ORDER BY rowid DESC"):
            h = r["hash"]
            m = s.manifest(h)
            events = s.events(h)
            locked = h in self.policy.locked_experiments
            jobs = s.jobs(h)
            # Job artifacts are not returned from discovery; selected detail is gated.
            result.append(
                dict(
                    experiment_hash=h,
                    name=m["experiment"]["name"],
                    family=m["experiment"]["family"],
                    locked=locked,
                    manifest=m,
                    jobs=[
                        {k: v for k, v in x.items() if k not in ("artifact", "error")}
                        for x in jobs
                    ],
                    events=(
                        events
                        if not locked
                        else [
                            dict(kind=e["kind"], recorded_ms=e["recorded_ms"])
                            for e in events
                        ]
                    ),
                    decision=None if locked else s.decision(h),
                )
            )
        return result

    def experiment(self, h):
        s = self.store("c12")
        m = s.manifest(h)
        events = s.events(h)
        locked = h in self.policy.locked_experiments
        jobs = s.jobs(h)
        artifacts = []
        for j in jobs:
            if j["artifact"] and (
                not locked or "holdout" not in j["key"] and "portfolio" not in j["key"]
            ):
                artifacts.append(
                    dict(
                        key=j["key"],
                        artifact_hash=j["artifact"],
                        document=s.artifact(j["artifact"]),
                    )
                )
        return dict(
            manifest=m,
            locked=locked,
            events=(
                events
                if not locked
                else [
                    dict(kind=e["kind"], recorded_ms=e["recorded_ms"]) for e in events
                ]
            ),
            artifacts=artifacts,
            decision=None if locked else s.decision(h),
        )

    def runs(self, kind="simulation"):
        if kind == "simulation":
            s = self.store("c11")
            result = []
            for r in indexed(s, "SELECT hash FROM runs ORDER BY rowid DESC"):
                try:
                    self.policy.run(r["hash"])
                except LockedEvidence:
                    result.append(dict(run_hash=r["hash"], locked=True))
                    continue
                m = s.manifest(r["hash"])
                summary = s.summary(r["hash"])
                result.append(
                    dict(
                        **summary,
                        locked=False,
                        dataset=m["dataset"],
                        scenarios=m["scenarios"],
                        decision_window_ms=m["decision_window_ms"],
                        code_hash=m["code_hash"],
                    )
                )
            return result
        s = self.store("c13")
        result = []
        for r in indexed(s, "SELECT hash FROM replays ORDER BY rowid DESC"):
            m = s.manifest(r["hash"])
            for source in m["sources"]:
                self.policy.run(source["run_hash"])
            result.append(dict(**s.summary(r["hash"]), manifest=m))
        return result

    def run(self, h, kind="simulation"):
        from .analytics import distribution

        if kind == "simulation":
            self.policy.run(h)
            s = self.store("c11")
            summary = s.summary(h)
            m = s.manifest(h)
            report = s.report(summary["report_hash"])
            records = list(pages(s, h, "sample"))
            return dict(
                manifest=m,
                summary=summary,
                report=report,
                distribution=distribution(report["trades"]),
                samples=[x["payload"] for x in records],
            )
        s = self.store("c13")
        m = s.manifest(h)
        for source in m["sources"]:
            self.policy.run(source["run_hash"])
        summary = s.summary(h)
        return dict(
            manifest=m,
            summary=summary,
            report=s.report(summary["report_hash"]),
            samples=[x["payload"] for x in s.records(h) if x["kind"] == "sample"],
        )

    def models(self):
        from tradee.c10.engine import verified_model

        result = []
        if self.profile.path("c10").exists():
            s = self.store("c10")
            for row in indexed(s, "SELECT hash FROM models ORDER BY rowid DESC"):
                model = s.model(row["hash"])
                for source in model["fit"]["sources"]:
                    self.policy.run(source["run_hash"])
                evaluations = []
                for r in indexed(
                    s, "SELECT hash FROM evaluations WHERE model_hash=?", (row["hash"],)
                ):
                    evaluation = s.evaluation(r["hash"])
                    for source in evaluation["sources"]:
                        self.policy.run(source["run_hash"])
                    evaluations.append(evaluation)
                result.append(
                    dict(
                        **s.summary(row["hash"]),
                        model=model,
                        evaluations=evaluations,
                        source="C10 registry",
                    )
                )
        # C12 freezes its final C10 model inside a verified training artifact;
        # it need not be separately copied/published into a C10 database.
        if self.profile.path("c12").exists():
            for experiment in self.research():
                for artifact in self.experiment(experiment["experiment_hash"])[
                    "artifacts"
                ]:
                    if artifact["key"] != "training/final":
                        continue
                    d = artifact["document"]
                    h = d["model_hash"]
                    if any(m["model_hash"] == h for m in result):
                        continue
                    model = dict(model_hash=h, **d["model"])
                    verified_model(model)
                    for source in model["fit"]["sources"]:
                        self.policy.run(source["run_hash"])
                    f = model["fit"]
                    result.append(
                        dict(
                            model_hash=h,
                            fit_hash=model["fit_hash"],
                            snapshot_hash=f["snapshot_hash"],
                            ready=f["ready"],
                            available_ms=model["available_ms"],
                            availability_basis=model["availability_basis"],
                            window=f["window"],
                            coverage=f["coverage"],
                            cohorts=f["cohorts"],
                            release_status=f["release_status"],
                            model=model,
                            evaluations=[],
                            source="C12 frozen final training",
                        )
                    )
        return result

    def model(self, h):
        found = next((m["model"] for m in self.models() if m["model_hash"] == h), None)
        if found is None:
            raise ValidationError("Unknown permitted frozen model")
        return found

    def monitors(self):
        s = self.store("c15")
        result = []
        for r in indexed(s, "SELECT name FROM monitors ORDER BY name"):
            h = s.head(r["name"])
            self.session(h["manifest"]["session"])
            result.append(h)
        return result

    def forward(self, name, report_hash=None, at_ms=None):
        s = self.store("c15")
        h = s.head(name)
        self.session(h["manifest"]["session"])
        history = [
            dict(event_hash=e["event_hash"], observed_ms=e["at_ms"], **e["payload"])
            for e in s.events(name)
            if e["kind"] == "observed" and (at_ms is None or e["at_ms"] <= at_ms)
        ]
        key = report_hash or (history[-1]["report_hash"] if history else None)
        report = None if key is None else s.artifact(key)
        if report is not None and (
            report.get("manifest_hash") != h["manifest_hash"]
            or at_ms is not None
            and report["observed_ms"] > at_ms
        ):
            raise ValidationError(
                "Report does not belong to this monitor/evidence cursor"
            )
        head = {k: v for k, v in h.items() if k != "report"}
        if at_ms is not None:
            head = dict(
                head,
                revision=None,
                report_hash=key,
                last_ms=None if report is None else report["observed_ms"],
            )
        return dict(
            head=head,
            report_hash=key,
            report=report,
            history=history,
            events=[e for e in s.events(name) if at_ms is None or e["at_ms"] <= at_ms],
        )

    def instruments(self):
        s = self.store("c01")
        rows = indexed(
            s,
            "SELECT hash,symbol,instrument_id,first_observed_ms FROM versions ORDER BY first_observed_ms DESC",
        )
        result = []
        for r in rows:
            if any(x["instrument_id"] == r["instrument_id"] for x in result):
                continue
            result.append(dict(**r, version=s.version(r["hash"])))
        return result

    def quality(self, dataset_hash):
        from .analytics import coverage_calendar

        s = self.store("c02")
        ds = s.dataset(dataset_hash)
        self.policy.range(ds["start_ms"], ds["end_ms"])
        if (ds["end_ms"] - ds["start_ms"]) // 60000 > 500000:
            raise SourceError("Quality range budget exceeded; pin a smaller dataset")
        q = s.quality(dataset_hash)
        return dict(
            dataset=ds,
            quality=q,
            calendar=coverage_calendar(ds, q),
            collector=indexed(
                s,
                "SELECT observed_ms,document FROM collector_log ORDER BY id DESC LIMIT 30",
            ),
        )

    def artifact(self, kind, h):
        if kind == "c11":
            s = self.store(kind)
            for table in ("runs", "reports", "artifacts"):
                with s.connection() as db:
                    row = (
                        db.execute(
                            f"SELECT run_hash FROM {table} WHERE hash=?", (h,)
                        ).fetchone()
                        if table != "runs"
                        else None
                    )
                if table == "runs":
                    try:
                        self.policy.run(h)
                        return s.manifest(h)
                    except LockedEvidence:
                        raise
                    except ValidationError:
                        continue
                if row:
                    self.policy.run(row[0])
                    s.summary(row[0])
                    return s.report(h) if table == "reports" else s.artifact(h)
            raise ValidationError("Unknown artifact")
        if kind == "c12":
            # Only artifacts reachable through an authorized experiment detail.
            for e in self.research():
                d = self.experiment(e["experiment_hash"])
                for a in d["artifacts"]:
                    if a["artifact_hash"] == h:
                        return a["document"]
            raise LockedEvidence(
                "Artifact is not exposed by permitted research evidence"
            )
        if kind == "c13":
            s = self.store(kind)
            for r in self.runs("portfolio"):
                if h in (r["run_hash"], r["report_hash"]):
                    return s.artifact(h)
            raise ValidationError("Use a permitted portfolio report")
        if kind == "c14":
            s = self.store(kind)
            for summary in self.sessions():
                e = s.evidence(summary["name"])
                allowed = (
                    {e["head"]["deployment_hash"]}
                    | {c["cycle_hash"] for c in e["cycles"]}
                    | {x["event_hash"] for x in e["events"]}
                )
                if h in allowed:
                    return s.artifact(h)
            raise ValidationError("Use a permitted session artifact")
        if kind == "c15":
            s = self.store(kind)
            for m in self.monitors():
                allowed = {m["manifest_hash"]} | {
                    e["payload"]["report_hash"]
                    for e in s.events(m["name"])
                    if e["kind"] == "observed"
                }
                if h in allowed:
                    return s.artifact(h)
            raise ValidationError("Use a permitted monitor artifact")
        if kind == "c01":
            return self.store(kind).version(h)
        if kind == "c02":
            d = self.store(kind).dataset(h)
            self.policy.range(d["start_ms"], d["end_ms"])
            return d
        raise ValidationError("Unsupported evidence kind")
