"""Runtime configuration for the LCE CLI.

Precedence: explicit overrides > environment variables > defaults.
No third-party dependency (no pydantic) -- this module must remain
importable with the standard library only.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    project_root: Path
    state_dir: Path
    db_path: Path
    continuity_dir: Path
    parser_backend: str = "stdlib"
    llm_backend: str = "none"

    @classmethod
    def load(cls, cwd: str | Path = ".", overrides: dict | None = None) -> "Settings":
        overrides = overrides or {}
        project_root = Path(cwd).resolve()
        state_dir = Path(
            overrides.get("state_dir")
            or os.environ.get("LCE_STATE_DIR")
            or (project_root / ".lce")
        )
        db_path = Path(
            overrides.get("db_path")
            or os.environ.get("LCE_DB_PATH")
            or (state_dir / "living_context.db")
        )
        continuity_dir = Path(
            overrides.get("continuity_dir")
            or os.environ.get("LCE_CONTINUITY_DIR")
            or (state_dir / "continuity")
        )
        parser_backend = overrides.get("parser_backend") or os.environ.get(
            "LCE_PARSER_BACKEND", "stdlib"
        )
        llm_backend = overrides.get("llm_backend") or os.environ.get(
            "LCE_LLM_BACKEND", "none"
        )
        return cls(
            project_root=project_root,
            state_dir=state_dir,
            db_path=db_path,
            continuity_dir=continuity_dir,
            parser_backend=parser_backend,
            llm_backend=llm_backend,
        )

    def ensure_dirs(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.continuity_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / "runs").mkdir(parents=True, exist_ok=True)
        (self.state_dir / "exports").mkdir(parents=True, exist_ok=True)
