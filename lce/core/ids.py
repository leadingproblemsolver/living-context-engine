"""Deterministic identifier and hashing helpers.

All functions here are pure: given the same inputs they always produce the
same outputs, with no timestamps or randomness. This is required for
synchronization idempotency -- resyncing an unchanged file must produce
identical doc_id/ru_id/signal_id values, not new rows.
"""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_path(root: str | Path, path: str | Path) -> str:
    """Return a root-relative, forward-slash-normalized path string.

    If `path` is not under `root`, falls back to the absolute posix form of
    `path` so callers always get a stable string rather than an exception.
    """
    root_p = Path(root).resolve()
    path_p = Path(path).resolve()
    try:
        rel = path_p.relative_to(root_p)
        return PurePosixPath(rel.as_posix()).as_posix()
    except ValueError:
        return PurePosixPath(path_p.as_posix()).as_posix()


def doc_id_for_path(canonical_path_str: str) -> str:
    return "doc_" + sha256_text(canonical_path_str)[:16]


def ru_id_for(doc_id: str, sequence_number: int, content: str) -> str:
    return "ru_" + sha256_text(f"{doc_id}:{sequence_number}:{content}")[:16]


def signal_id_for(ru_id: str, signal_type: str, content: str) -> str:
    return "sig_" + sha256_text(f"{ru_id}:{signal_type}:{content}")[:16]


def cluster_id_for(topic: str) -> str:
    return "cl_" + sha256_text(topic)[:16]
