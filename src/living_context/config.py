from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_RELATIVE = ".lce/config.json"

DEFAULTS = {
    "project": "",
    "sources": ["docs", ".lce/observations"],
    "half_life_days": 180,
    "model": "claude-opus-5",
    "effort": "high",
    "database": "data/living-context.sqlite",
    "profile": "",
    # Deterministic parsing of a file a human wrote is applied directly. Model
    # extraction and connector pulls are staged for review.
    "auto_apply": ["parser", "human"],
}


@dataclass
class Config:
    root: Path
    project: str = ""
    sources: list[str] = field(default_factory=lambda: list(DEFAULTS["sources"]))
    half_life_days: float = float(DEFAULTS["half_life_days"])
    model: str = DEFAULTS["model"]
    effort: str = DEFAULTS["effort"]
    database: str = DEFAULTS["database"]
    profile: str = ""
    auto_apply: list[str] = field(default_factory=lambda: list(DEFAULTS["auto_apply"]))
    path: Path | None = None

    @property
    def exists(self) -> bool:
        return self.path is not None and self.path.exists()

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "sources": self.sources,
            "half_life_days": self.half_life_days,
            "model": self.model,
            "effort": self.effort,
            "database": self.database,
            "profile": self.profile,
            "auto_apply": self.auto_apply,
        }


def load_config(root: Path) -> Config:
    """Read `.lce/config.json` if present. Absent config is a valid state."""
    path = root / CONFIG_RELATIVE
    config = Config(root=root, path=path)
    if not path.exists():
        return config
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError(f"{CONFIG_RELATIVE} is not valid JSON: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError(f"{CONFIG_RELATIVE} must contain a JSON object")

    config.project = str(raw.get("project") or "").strip()
    sources = raw.get("sources")
    if isinstance(sources, list):
        config.sources = [str(item) for item in sources if str(item).strip()]
    half_life = raw.get("half_life_days")
    if isinstance(half_life, (int, float)) and half_life >= 0:
        config.half_life_days = float(half_life)
    config.model = str(raw.get("model") or DEFAULTS["model"])
    config.effort = str(raw.get("effort") or DEFAULTS["effort"])
    config.database = str(raw.get("database") or DEFAULTS["database"])
    config.profile = str(raw.get("profile") or "")
    auto_apply = raw.get("auto_apply")
    if isinstance(auto_apply, list):
        config.auto_apply = [str(item) for item in auto_apply if str(item).strip()]
    return config


def resolve_project(config: Config, explicit: str | None) -> str:
    """Explicit flag wins, then config, then the repository directory name."""
    for candidate in (explicit, config.project, config.root.name):
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    raise ValueError("a project identifier is required (pass --project or run `lce init`)")
