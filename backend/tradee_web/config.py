from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import json
from tradee.c01 import ValidationError
from tradee.environment import load_environment

ROOT = Path(__file__).resolve().parents[2]
KINDS = (
    "c01",
    "c02",
    "c03",
    "c06",
    "c07",
    "c08",
    "c09",
    "c10",
    "c11",
    "c12",
    "c13",
    "c14",
    "c15",
)


@dataclass(frozen=True)
class Profile:
    id: str
    label: str
    paths: dict
    synthetic: bool = False

    def path(self, kind):
        if kind not in KINDS:
            raise ValidationError("Unknown component")
        return Path(self.paths[kind]).resolve()


@dataclass
class Settings:
    profiles: tuple
    default_profile: str = "local"
    state_path: Path = field(default_factory=lambda: ROOT / "data/web.sqlite3")
    operator_token: str = field(default="", repr=False)
    origins: tuple = (
        "http://127.0.0.1:8787",
        "http://localhost:8787",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    max_events: int = 250000
    max_rows: int = 5000
    max_document_bytes: int = 50000000

    def profile(self, key):
        found = next((p for p in self.profiles if p.id == key), None)
        if found is None:
            raise ValidationError("Unknown workspace")
        return found


def load_settings(config=None, operator_token=None):
    if config:
        doc = json.loads(Path(config).read_text())
        profiles = []
        for p in doc["profiles"]:
            base = Path(p["root"]).expanduser().resolve()
            paths = {
                k: str(base / p.get("files", {}).get(k, k + ".sqlite3")) for k in KINDS
            }
            profiles.append(
                Profile(p["id"], p["label"], paths, p.get("synthetic", False))
            )
        settings = Settings(
            tuple(profiles),
            doc.get("default_profile", profiles[0].id),
            Path(doc.get("state_path", ROOT / "data/web.sqlite3"))
            .expanduser()
            .resolve(),
        )
    else:
        local = Profile(
            "local",
            "Local recording",
            {k: str(ROOT / "data" / f"{k}.sqlite3") for k in KINDS},
        )
        base = ROOT / "data/c15_verification/e2e_v3"
        verification = Profile(
            "verification",
            "Verification · synthetic",
            {
                k: str(
                    base / ("" if k in ("c14", "c15") else "research") / f"{k}.sqlite3"
                )
                for k in KINDS
            },
            True,
        )
        settings = Settings((local, verification))
    if len({p.id for p in settings.profiles}) != len(settings.profiles):
        raise ValidationError("Distinct workspace identifiers required")
    for p in settings.profiles:
        if not p.id.isidentifier() or len({p.path(k) for k in KINDS}) != len(KINDS):
            raise ValidationError(
                "Distinct component stores and simple workspace IDs required"
            )
        if settings.state_path in {p.path(k) for k in KINDS}:
            raise ValidationError("Web state must be separate from domain stores")
    settings.profile(settings.default_profile)
    settings.operator_token = (
        operator_token
        if operator_token is not None
        else load_environment().operator_token
    )
    return settings


def build_hash():
    base = Path(__file__).parent
    return hashlib.sha256(
        b"".join(p.read_bytes() for p in sorted(base.glob("*.py")))
    ).hexdigest()
