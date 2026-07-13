"""Bounded context-packet construction.

Every compiled artifact is built from one of these packets -- never
directly from raw retrieval hits. Freshness is always computed and never
hidden: a packet built from a stale corpus says so explicitly.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from lce.core.ids import canonical_path
from lce.retrieval import RetrievalHit, query as run_query


@dataclass
class FreshnessInfo:
    last_sync_at: str | None
    stale: bool
    reason: str | None

    def to_dict(self) -> dict:
        return {"last_sync_at": self.last_sync_at, "stale": self.stale, "reason": self.reason}


@dataclass
class ContextPacket:
    query: str
    intent: str | None
    freshness: FreshnessInfo
    decisions: list[RetrievalHit]
    blockers: list[RetrievalHit]
    next_actions: list[RetrievalHit]
    assumptions: list[RetrievalHit]
    questions: list[RetrievalHit]
    evidence: list[RetrievalHit]
    uncertainties: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "intent": self.intent,
            "freshness": self.freshness.to_dict(),
            "decisions": [h.to_dict() for h in self.decisions],
            "blockers": [h.to_dict() for h in self.blockers],
            "next_actions": [h.to_dict() for h in self.next_actions],
            "assumptions": [h.to_dict() for h in self.assumptions],
            "questions": [h.to_dict() for h in self.questions],
            "evidence": [h.to_dict() for h in self.evidence],
            "uncertainties": self.uncertainties,
        }


def compute_freshness(settings, store) -> FreshnessInfo:
    runs = store.recent_runs(limit=1, command="sync")
    last_sync_at = runs[0]["ended_at"] if runs else None
    if last_sync_at is None:
        return FreshnessInfo(last_sync_at=None, stale=True, reason="corpus has never been synced")

    docs = store.scan_documents()
    stale_paths = []
    for d in docs:
        if d.get("origin") != "corpus" or d.get("status") != "active":
            continue
        full_path = settings.project_root / d["source_path"]
        try:
            current_mtime = os.stat(full_path).st_mtime
        except OSError:
            stale_paths.append(d["source_path"])
            continue
        if d.get("mtime") is not None and current_mtime > d["mtime"] + 1e-6:
            stale_paths.append(d["source_path"])

    if stale_paths:
        preview = ", ".join(stale_paths[:5])
        return FreshnessInfo(
            last_sync_at=last_sync_at,
            stale=True,
            reason=f"{len(stale_paths)} source file(s) changed since last sync (e.g. {preview}); run `lce sync` again",
        )
    return FreshnessInfo(last_sync_at=last_sync_at, stale=False, reason=None)


def _detect_uncertainties(hits: list[RetrievalHit]) -> list[str]:
    """Surface low-confidence or contradictory-looking evidence rather than
    silently presenting it with the same authority as strong evidence."""
    uncertainties = []
    decisions_by_content = {}
    for h in hits:
        if h.signal_type == "decision":
            decisions_by_content.setdefault(h.content.strip().lower()[:40], []).append(h)
    # crude contradiction signal: multiple distinct decision statements
    # touching very similar leading text -- flag for human review rather
    # than silently picking one.
    if len(decisions_by_content) > 1:
        keys = list(decisions_by_content.keys())
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                if keys[i][:15] == keys[j][:15] and keys[i] != keys[j]:
                    uncertainties.append(
                        f"possibly conflicting decisions found: {decisions_by_content[keys[i]][0].content!r} vs {decisions_by_content[keys[j]][0].content!r}"
                    )
    return uncertainties


def build_context_packet(settings, store, *, query: str, intent: str | None = None, top_k: int = 20) -> ContextPacket:
    hits = run_query(store, query, intent=intent, top_k=top_k)

    decisions = [h for h in hits if h.signal_type == "decision"]
    blockers = [h for h in hits if h.signal_type == "blocker"]
    next_actions = [h for h in hits if h.signal_type == "next_action"]
    assumptions = [h for h in hits if h.signal_type == "assumption"]
    questions = [h for h in hits if h.signal_type == "question"]
    evidence = [h for h in hits if h.signal_type in (None, "context", "requirement")]

    freshness = compute_freshness(settings, store)
    uncertainties = _detect_uncertainties(hits)
    if not hits:
        uncertainties.append(f"no evidence found for query {query!r}")

    return ContextPacket(
        query=query,
        intent=intent,
        freshness=freshness,
        decisions=decisions,
        blockers=blockers,
        next_actions=next_actions,
        assumptions=assumptions,
        questions=questions,
        evidence=evidence,
        uncertainties=uncertainties,
    )
