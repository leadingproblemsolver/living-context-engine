from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any
from datetime import datetime

KINDS = {"decision", "blocker", "action", "fact", "question", "risk", "note"}

@dataclass(frozen=True, slots=True)
class ContextRecord:
    record_id: str
    project: str
    kind: str
    text: str
    source_path: str
    source_line: int
    source_hash: str
    observed_at: str
    status: str = "active"
    tags: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    def validate(self) -> list[str]:
        errors=[]
        for field_name in ("record_id","project","kind","text","source_path","source_hash","observed_at"):
            if not getattr(self, field_name): errors.append(f"{field_name} is required")
        if self.kind not in KINDS: errors.append(f"unsupported kind: {self.kind}")
        if self.source_line < 1: errors.append("source_line must be >= 1")
        try:
            datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("observed_at must be an ISO-8601 date or datetime")
        if len(self.text) > 10_000: errors.append("text exceeds 10000 characters")
        if len(self.project) > 200: errors.append("project exceeds 200 characters")
        if len(self.source_path) > 1000: errors.append("source_path exceeds 1000 characters")
        return errors
    def to_dict(self):
        result=asdict(self); result["tags"]=list(self.tags); return result
