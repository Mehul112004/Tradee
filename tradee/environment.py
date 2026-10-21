"""Server-side project configuration; never mutate the caller's environment."""

from dataclasses import dataclass, field
import os
from pathlib import Path

from dotenv import dotenv_values
from tradee.c01 import ValidationError

ROOT_ENV = Path(__file__).resolve().parents[1] / ".env"


@dataclass(frozen=True)
class Environment:
    telegram_token: str = field(default="", repr=False)
    telegram_chat_id: str = ""
    operator_token: str = field(default="", repr=False)


def load_environment(path=None, environ=None):
    """Read only Tradee settings. Exported values (even empty) beat file aliases.

    Resolve the root file independently of cwd, with no parent-directory search,
    interpolation, shell evaluation, or automatic import from another project.
    PYTHON_DOTENV_DISABLED=1 isolates offline tests/deployments from local secrets.
    """
    process = os.environ if environ is None else environ
    values = {}
    if process.get("PYTHON_DOTENV_DISABLED", "").lower() not in (
        "1", "true", "t", "yes", "y",
    ):
        target = ROOT_ENV if path is None else Path(path)
        try:
            if target.exists():
                with target.open(encoding="utf-8") as stream:
                    values = dotenv_values(stream=stream, interpolate=False)
        except (OSError, UnicodeError):
            raise ValidationError("Cannot read Tradee .env configuration") from None

    def setting(*names):
        for source in (process, values):
            for name in names:
                if name in source:
                    return source[name] or ""
        return ""

    return Environment(
        telegram_token=setting("TRADEE_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=setting("TELEGRAM_CHAT_ID"),
        operator_token=setting("TRADEE_WEB_OPERATOR_TOKEN"),
    )
