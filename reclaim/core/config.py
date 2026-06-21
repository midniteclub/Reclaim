"""Application configuration: load/save AppConfig as JSON."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass
class AppConfig:
    """Persisted user/app settings."""
    default_root: str = "C:\\"
    excluded_paths: list[str] = field(default_factory=list)
    stale_days: int = 180
    theme: str = "light"
    profiles: dict[str, dict] = field(default_factory=dict)


def _default_path() -> Path:
    return Path.home() / ".reclaim" / "config.json"


def load_config(path=None) -> AppConfig:
    """Load config from ``path`` (default ~/.reclaim/config.json).

    Returns ``AppConfig()`` defaults if the file does not exist. Tolerates
    missing keys (defaults fill in) and ignores unknown/extra keys.
    """
    p = Path(path) if path is not None else _default_path()
    if not p.exists():
        return AppConfig()
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    known = {f.name for f in fields(AppConfig)}
    filtered = {k: v for k, v in data.items() if k in known}
    return AppConfig(**filtered)


def save_config(cfg: AppConfig, path=None) -> None:
    """Write ``cfg`` to ``path`` (default ~/.reclaim/config.json), creating dirs."""
    p = Path(path) if path is not None else _default_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(cfg), indent=2))
