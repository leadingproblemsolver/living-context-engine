from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from living_context.models import ContextRecord

PREFIXES = {
    "decision": ("decision:", "decided:", "we chose", "we will"),
    "blocker": ("blocker:", "blocked:", "cannot proceed", "can't proceed"),
    "action": ("action:", "next:", "todo:", "next action:"),
    "risk": ("risk:", "failure mode:", "concern:"),
    "question": ("question:", "unknown:", "open question:"),
    "fact": ("fact:", "evidence:", "verified:"),
}
TAG = re.compile(r"(?<!\w)#([a-zA-Z][a-zA-Z0-9_-]{1,40})")
DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2}(?:[T ][0-9:.+\-Z]+)?)\b")
SUPPORTED = {".md", ".txt", ".json", ".yaml", ".yml"}
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 1_000
MAX_RECORD_TEXT = 10_000


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _kind(line: str) -> str:
    lowered = line.strip().lower().lstrip("-*[] ")
    for kind, prefixes in PREFIXES.items():
        if any(lowered.startswith(prefix) for prefix in prefixes):
            return kind
    if line.strip().endswith("?"):
        return "question"
    if re.match(r"^\s*[-*]\s*\[[ xX]\]", line):
        return "action"
    return "note"


def _clean(line: str) -> str:
    text = re.sub(r"^\s*(?:[-*]\s*)?(?:\[[ xX]\]\s*)?", "", line).strip()
    for prefixes in PREFIXES.values():
        for prefix in prefixes:
            if text.lower().startswith(prefix):
                return text[len(prefix) :].strip(" :-")
    return text


def records_from_text(
    text: str,
    source_path: str,
    project: str,
    source_hash: str,
    fallback_date: str,
) -> list[ContextRecord]:
    output = []
    for line_number, line in enumerate(text.splitlines(), 1):
        cleaned = _clean(line)
        if (
            not cleaned
            or len(cleaned) < 2
            or len(cleaned) > MAX_RECORD_TEXT
            or cleaned.startswith("```")
            or cleaned.startswith("# ")
        ):
            continue
        kind = _kind(line)
        match = DATE.search(line)
        observed = match.group(1) if match else fallback_date
        tags = tuple(sorted(set(TAG.findall(line))))
        identity = f"{project}:{source_path}:{source_hash}:{line_number}:{kind}:{cleaned}"
        record_id = hashlib.sha256(identity.encode()).hexdigest()[:24]
        record = ContextRecord(
            record_id,
            project,
            kind,
            cleaned,
            source_path,
            line_number,
            source_hash,
            observed,
            tags=tags,
        )
        if not record.validate():
            output.append(record)
    return output


def read_source(path: Path) -> tuple[str, bytes]:
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"source exceeds 10 MB: {path}")
    data = path.read_bytes()
    if path.suffix.lower() == ".json":
        parsed = json.loads(data.decode("utf-8"))
        return json.dumps(parsed, indent=2, sort_keys=True), data
    return data.decode("utf-8", errors="replace"), data


def extract_path(path: Path, project: str, root: Path) -> list[ContextRecord]:
    del root  # retained for backwards-compatible function signature
    path = Path(path)
    if path.is_symlink():
        raise ValueError("symlink sources are not accepted")
    path = path.resolve()
    if not path.exists():
        raise ValueError(f"source path does not exist: {path}")
    if not project.strip() or len(project) > 200:
        raise ValueError("project is required and must be <= 200 characters")
    if path.is_file():
        if path.suffix.lower() not in SUPPORTED:
            raise ValueError(f"unsupported source type: {path.suffix or 'none'}")
        paths = [path]
        source_root = path.parent.parent
    else:
        paths = sorted(
            candidate
            for candidate in path.rglob("*")
            if candidate.is_file()
            and not candidate.is_symlink()
            and candidate.suffix.lower() in SUPPORTED
            and ".git" not in candidate.parts
        )
        source_root = path
    if len(paths) > MAX_FILES:
        raise ValueError("source set exceeds 1000 files")
    records = []
    for item in paths:
        text, data = read_source(item)
        source_hash = sha256(data)
        stamp = datetime.fromtimestamp(item.stat().st_mtime, timezone.utc).isoformat()
        relative = item.relative_to(source_root).as_posix()
        records.extend(
            records_from_text(text, relative, project.strip(), source_hash, stamp)
        )
    return records
