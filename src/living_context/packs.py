from __future__ import annotations

import json
from pathlib import Path

from living_context.store import Store


def build_pack(
    store: Store,
    query: str,
    output: Path,
    project: str | None = None,
    limit: int = 30,
) -> dict:
    hits = store.query(query, project=project, limit=limit)
    grouped: dict[str, list[dict]] = {}
    for hit in hits:
        grouped.setdefault(hit["kind"], []).append(hit)

    lines = [
        "# Context Recovery Pack",
        "",
        f"**Query:** {query}",
        f"**Project:** {project or 'all'}",
        "",
        "## Source boundary",
        "Only records ingested into this local database are included. "
        "Every item preserves its source path and line.",
    ]
    for kind in ("decision", "blocker", "action", "risk", "question", "fact", "note"):
        if kind not in grouped:
            continue
        lines.extend(["", f"## {kind.title()}s"])
        for item in grouped[kind]:
            lines.append(
                f"- {item['text']} — `{item['source_path']}:{item['source_line']}`"
            )

    lines.extend(
        [
            "",
            "## Explicit limitations",
            "- Extraction is deterministic line classification, not semantic proof.",
            "- Absence from this pack does not prove absence from the source corpus.",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path = output.with_suffix(".json")
    json_path.write_text(
        json.dumps({"query": query, "project": project, "items": hits}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {"markdown": str(output), "json": str(json_path), "items": len(hits)}
