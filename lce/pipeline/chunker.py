"""Deterministic chunking into retrieval units (RUs)."""
from __future__ import annotations

from lce.core.ids import ru_id_for, sha256_text


def chunk_text(doc_id: str, text: str, max_chars: int = 900, overlap: int = 120) -> list[dict]:
    chunks = []
    n = len(text)
    start = 0
    seq = 0
    if n == 0:
        return []
    while start < n:
        end = min(n, start + max_chars)
        if end < n:
            cut = text.rfind("\n\n", start, end)
            if cut > start + 250:
                end = cut
        content = text[start:end].strip()
        if content:
            h = sha256_text(content)
            chunks.append(
                {
                    "ru_id": ru_id_for(doc_id, seq, h),
                    "doc_id": doc_id,
                    "sequence_number": seq,
                    "content": content,
                    "chunk_hash": h,
                    "start_char": start,
                    "end_char": end,
                    "json_path": None,
                    "metadata": {"chunker": "deterministic_char_window"},
                }
            )
            seq += 1
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def chunk_json_paths(doc_id: str, json_paths: list[tuple[str, object]]) -> list[dict]:
    rows = []
    for seq, (path, value) in enumerate(json_paths):
        content = f"{path}: {value}"
        h = sha256_text(content)
        rows.append(
            {
                "ru_id": ru_id_for(doc_id, seq, h),
                "doc_id": doc_id,
                "sequence_number": seq,
                "content": content,
                "chunk_hash": h,
                "start_char": 0,
                "end_char": len(content),
                "json_path": path,
                "metadata": {"chunker": "json_path"},
            }
        )
    return rows
