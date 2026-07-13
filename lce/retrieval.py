"""The sole retrieval implementation. Every consumer (query, brief, compile)
gets hits through this module in the canonical schema -- there must never
be a second, competing retrieval implementation with its own hit shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

VALID_TYPES = {"signal", "retrieval_unit", "document"}


@dataclass
class RetrievalHit:
    type: str  # signal|retrieval_unit|document
    score: float
    signal_type: str | None
    content: str
    source_path: str | None
    doc_id: str | None
    ru_id: str | None
    signal_id: str | None
    domain: str | None
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "score": self.score,
            "signal_type": self.signal_type,
            "content": self.content,
            "source_path": self.source_path,
            "doc_id": self.doc_id,
            "ru_id": self.ru_id,
            "signal_id": self.signal_id,
            "domain": self.domain,
            "reasons": self.reasons,
        }


def _norm_term(t: str) -> str:
    t = t.lower().strip()
    return t[:-1] if len(t) > 4 and t.endswith("s") else t


def _score_text(text: str, terms: list[str]) -> tuple[float, list[str]]:
    text_l = (text or "").lower()
    score = 0.0
    reasons = []
    for t in terms:
        c = text_l.count(t)
        if c:
            score += c
            reasons.append(f"matched '{t}' x{c}")
    return score, reasons


# Signal types get a base boost so a matching decision/blocker/next_action
# outranks a matching generic context fragment, all else equal.
_SIGNAL_TYPE_BOOST = {
    "decision": 3.0,
    "blocker": 3.0,
    "next_action": 2.5,
    "requirement": 2.0,
    "assumption": 1.5,
    "question": 1.0,
    "context": 0.0,
}


def _dedupe(hits: list[RetrievalHit]) -> list[RetrievalHit]:
    """Collapse near-duplicate hits (same type/signal_type/content/source)."""
    seen = set()
    out = []
    for h in hits:
        key = (h.type, h.signal_type, h.content.strip(), h.source_path, h.doc_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def query(
    store,
    text: str,
    *,
    intent: str | None = None,
    top_k: int = 20,
    domain: str | None = None,
) -> list[RetrievalHit]:
    """Keyword-score signals and retrieval units against `text`.

    `intent` (decisions|blockers|mistakes|next_actions|current_state|
    deployability|handoff) narrows which signal types are eligible and
    boosts their ranking, without excluding everything else outright.
    """
    terms = [_norm_term(t) for t in text.split() if len(t) > 2]

    intent_signal_types = {
        "decisions": {"decision"},
        "blockers": {"blocker"},
        "mistakes": {"blocker", "context"},
        "next_actions": {"next_action"},
        "current_state": {"decision", "blocker", "next_action", "context"},
        "deployability": {"blocker", "requirement", "context"},
        "handoff": {"decision", "blocker", "next_action", "assumption", "question"},
    }.get(intent)

    hits: list[RetrievalHit] = []

    for s in store.get_signals():
        base_score, reasons = _score_text(s.get("content", ""), terms)
        if base_score == 0 and not terms:
            base_score = 0.0
        if base_score == 0:
            continue
        boost = _SIGNAL_TYPE_BOOST.get(s.get("signal_type"), 0.0)
        intent_bonus = 2.0 if intent_signal_types and s.get("signal_type") in intent_signal_types else 0.0
        if intent_signal_types and intent_bonus == 0.0:
            # still eligible, just not boosted -- never hide potentially relevant evidence
            pass
        score = base_score + boost + intent_bonus
        if intent_bonus:
            reasons.append(f"intent match for '{intent}'")
        if s.get("origin") == "continuity":
            reasons.append("origin=continuity (previously accepted)")
        hits.append(
            RetrievalHit(
                type="signal",
                score=score,
                signal_type=s.get("signal_type"),
                content=s.get("content", ""),
                source_path=s.get("source_path"),
                doc_id=s.get("doc_id"),
                ru_id=s.get("ru_id"),
                signal_id=s.get("signal_id"),
                domain=domain,
                reasons=reasons,
            )
        )

    for r in store.get_rus():
        base_score, reasons = _score_text(r.get("content", ""), terms)
        if base_score == 0:
            continue
        hits.append(
            RetrievalHit(
                type="retrieval_unit",
                score=base_score,
                signal_type=None,
                content=r.get("content", ""),
                source_path=r.get("source_path"),
                doc_id=r.get("doc_id"),
                ru_id=r.get("ru_id"),
                signal_id=None,
                domain=domain,
                reasons=reasons,
            )
        )

    hits = _dedupe(hits)
    hits.sort(key=lambda h: (-h.score, h.source_path or ""))
    return hits[:top_k]
