"""Human-authorized continuity ledger: log / accept / reject.

Derived output never becomes durable memory on its own -- these functions
are only ever invoked directly by a human-issued CLI command (`lce log`,
`lce accept`, `lce reject`), never by `sync` or `compile`. Only an
`accepted` record ever produces a reingest file; `rejected`/`pending`
records never re-enter the corpus, so a rejected suggestion can never be
promoted to current direction by a later sync.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from lce.core.ids import sha256_text


class LedgerError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_id(content: str, outcome_type: str, created_at: str, actor: str) -> str:
    return "cr_" + sha256_text(f"{content}:{outcome_type}:{created_at}:{actor}")[:16]


def log_outcome(store, *, content: str, outcome_type: str, actor: str = "human", source_artifact: str | None = None, evidence_refs: list[dict] | None = None) -> dict:
    created_at = _now()
    record = {
        "record_id": _record_id(content, outcome_type, created_at, actor),
        "state": "pending",
        "content": content,
        "outcome_type": outcome_type,
        "created_at": created_at,
        "actor": actor,
        "source_artifact": source_artifact,
        "evidence_refs": evidence_refs or [],
        "reingest_path": None,
    }
    store.insert_continuity_record(record)
    return record


def write_reingest_file(record: dict, continuity_dir: Path) -> Path:
    continuity_dir.mkdir(parents=True, exist_ok=True)
    path = continuity_dir / f"{record['record_id']}.md"
    frontmatter = (
        "---\n"
        "lce_generated: true\n"
        "lineage: continuity_record\n"
        f"record_id: {record['record_id']}\n"
        f"outcome_type: {record['outcome_type']}\n"
        f"state: accepted\n"
        f"source_artifact: {record.get('source_artifact') or ''}\n"
        f"created_at: {record['created_at']}\n"
        "---\n\n"
    )
    body = f"{record['outcome_type'].capitalize()} (accepted): {record['content']}\n"
    path.write_text(frontmatter + body, encoding="utf-8")
    return path


def _require_pending(store, record_id: str) -> dict:
    record = store.get_continuity_record(record_id)
    if record is None:
        raise LedgerError(f"no continuity record with id {record_id!r}")
    if record["state"] != "pending":
        raise LedgerError(f"record {record_id!r} is {record['state']!r}, only 'pending' records can transition")
    return record


def accept(store, settings, record_id: str) -> dict:
    record = _require_pending(store, record_id)
    reingest_path = write_reingest_file(record, settings.continuity_dir)
    store.update_continuity_state(record_id, "accepted", reingest_path=str(reingest_path))
    return store.get_continuity_record(record_id)


def reject(store, record_id: str) -> dict:
    _require_pending(store, record_id)
    store.update_continuity_state(record_id, "rejected")
    return store.get_continuity_record(record_id)
