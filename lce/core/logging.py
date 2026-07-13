"""Structured, append-only run logging.

Every command execution gets a RunLogger. Stage transitions and messages are
written as JSONL trace events so `doctor`/`status` can report on the actual
last run instead of a hand-maintained claim file.
"""
from __future__ import annotations

import json
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunLogger:
    def __init__(self, settings, command: str, input_path: str | None = None):
        self.settings = settings
        self.command = command
        self.input_path = input_path
        self.run_id = "run_" + uuid.uuid4().hex[:16]
        self.started_at = _now()
        self._start_perf = time.perf_counter()
        self.events: list[dict] = []
        self._stage_starts: dict[str, float] = {}
        self.trace_path = self.settings.state_dir / "runs" / f"{self.run_id}.jsonl"

    def _emit(self, level: str, message: str, **context) -> None:
        event = {"ts": _now(), "run_id": self.run_id, "level": level, "message": message, "context": context}
        self.events.append(event)
        try:
            self.trace_path.parent.mkdir(parents=True, exist_ok=True)
            with self.trace_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def stage_start(self, stage: str, **context) -> None:
        self._stage_starts[stage] = time.perf_counter()
        self._emit("info", f"stage_start:{stage}", stage=stage, **context)

    def stage_end(self, stage: str, **metrics) -> None:
        start = self._stage_starts.pop(stage, None)
        duration_ms = int((time.perf_counter() - start) * 1000) if start is not None else None
        self._emit("info", f"stage_end:{stage}", stage=stage, duration_ms=duration_ms, **metrics)

    def info(self, message: str, **context) -> None:
        self._emit("info", message, **context)

    def error(self, message: str, exc: Exception | None = None, **context) -> None:
        if exc is not None:
            context["error_type"] = type(exc).__name__
            context["error"] = str(exc)
            context["traceback"] = traceback.format_exc()
        self._emit("error", message, **context)

    def finalize(self, status: str, proof: dict | None = None) -> dict:
        ended_at = _now()
        total_duration_ms = int((time.perf_counter() - self._start_perf) * 1000)
        return {
            "run_id": self.run_id,
            "command": self.command,
            "input_path": self.input_path,
            "status": status,
            "started_at": self.started_at,
            "ended_at": ended_at,
            "total_duration_ms": total_duration_ms,
            "trace_path": str(self.trace_path),
            "proof": proof or {},
            "events": self.events,
        }
