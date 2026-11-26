"""Configuration: library location, contact email and optional API keys.

Order of precedence: environment variables, then ~/.config/suluh/config.json,
then defaults. Nothing personal is hardcoded.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "suluh" / "config.json"


def _file_config() -> dict:
    p = config_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


@dataclass
class Config:
    library: Path
    email: str | None = None
    core_key: str | None = None
    openalex_key: str | None = None
    s2_key: str | None = None

    @classmethod
    def load(cls, library: str | os.PathLike | None = None) -> "Config":
        fc = _file_config()
        lib = (
            library
            or os.environ.get("SULUH_LIBRARY")
            or fc.get("library")
            or Path.home() / "Suluh-Library"
        )
        return cls(
            library=Path(lib).expanduser(),
            email=os.environ.get("SULUH_EMAIL") or fc.get("email"),
            core_key=os.environ.get("SULUH_CORE_KEY") or fc.get("core_key"),
            openalex_key=os.environ.get("SULUH_OPENALEX_KEY") or fc.get("openalex_key"),
            s2_key=os.environ.get("SULUH_S2_KEY") or fc.get("s2_key"),
        )


def save_setting(key: str, value: str) -> Path:
    """Persist one setting to the config file and return its path."""
    allowed = {"library", "email", "core_key", "openalex_key", "s2_key"}
    if key not in allowed:
        raise ValueError(f"Unknown setting '{key}'. Allowed: {', '.join(sorted(allowed))}")
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = _file_config()
    data[key] = value
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return p
