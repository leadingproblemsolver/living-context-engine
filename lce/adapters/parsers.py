"""Corpus discovery and file parsing.

Base backend is stdlib-only (txt/md/json/jsonl/log/csv). PDF/DOCX/PPTX/HTML
parsing is an optional extra (`unstructured`) -- if it's not installed, the
failure is reported as a structured ParseFailure, never as placeholder
content that pollutes retrieval.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from lce.core.ids import sha256_text

SUPPORTED = {".txt", ".md", ".json", ".jsonl", ".log", ".csv"}
OPTIONAL = {".pdf", ".docx", ".html", ".pptx"}
IGNORED_DIR_PREFIXES = (".lce", ".git", ".venv", "node_modules")


class ParseFailure(Exception):
    def __init__(self, path: str, reason: str):
        super().__init__(reason)
        self.path = path
        self.reason = reason


def discover(path: str | Path) -> list[Path]:
    """Discover supported files under `path`.

    Ignored-directory filtering (.lce/.git/.venv/node_modules) only applies
    to path components *below* the given root, not the root's own ancestor
    chain -- otherwise a direct sync of a folder that happens to live inside
    an ignored ancestor (e.g. the continuity reingest folder under `.lce/`)
    would discover zero files.
    """
    p = Path(path).resolve()
    if p.is_file():
        return [p]
    if not p.exists():
        raise FileNotFoundError(path)
    files = []
    for f in p.rglob("*"):
        if not f.is_file():
            continue
        rel_parts = f.relative_to(p).parts
        if any(part.startswith(IGNORED_DIR_PREFIXES) for part in rel_parts):
            continue
        if f.suffix.lower() in SUPPORTED | OPTIONAL:
            files.append(f)
    return sorted(files)


def flatten_json(obj, prefix="$"):
    rows = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            rows += flatten_json(v, f"{prefix}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            rows += flatten_json(v, f"{prefix}[{i}]")
    else:
        rows.append((prefix, obj))
    return rows


def parse_file(path: str | Path, backend: str = "stdlib") -> dict:
    """Parse a single file.

    Returns a dict with source_type/content/metadata/json_paths/content_hash.
    Raises ParseFailure for anything that cannot be safely turned into text
    -- callers must catch this and isolate it, never insert its message as
    document content.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    try:
        raw_bytes = path.read_bytes()
    except OSError as e:
        raise ParseFailure(str(path), f"{type(e).__name__}: {e}") from e

    meta = {"parser_backend": "stdlib", "file_name": path.name}
    json_paths: list[tuple[str, object]] = []

    if suffix == ".json":
        try:
            obj = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ParseFailure(str(path), f"invalid JSON: {e}") from e
        json_paths = flatten_json(obj)
        content = json.dumps(obj, indent=2, ensure_ascii=False)
        source_type = "json"
    elif suffix == ".jsonl":
        rows = []
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ParseFailure(str(path), f"invalid UTF-8: {e}") from e
        for i, line in enumerate(text.splitlines()):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"line": i, "raw": line})
        for i, row in enumerate(rows):
            json_paths += flatten_json(row, f"$[{i}]")
        content = "\n\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
        source_type = "jsonl"
    elif suffix in OPTIONAL:
        try:
            from unstructured.partition.auto import partition
        except ImportError as e:
            raise ParseFailure(
                str(path),
                f"optional parser dependency not installed for {suffix}: {e}",
            ) from e
        try:
            elements = partition(filename=str(path))
            content = "\n\n".join(getattr(e, "text", "") for e in elements if getattr(e, "text", ""))
            meta["parser_backend"] = "unstructured"
            source_type = suffix.strip(".")
        except Exception as e:
            raise ParseFailure(str(path), f"{type(e).__name__}: {e}") from e
    else:
        try:
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ParseFailure(str(path), f"invalid UTF-8: {e}") from e
        source_type = suffix.strip(".") or "text"

    return {
        "source_type": source_type,
        "content": content,
        "metadata": meta,
        "json_paths": json_paths,
        "content_hash": sha256_text(content),
    }
