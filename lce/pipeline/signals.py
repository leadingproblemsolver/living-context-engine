"""Deterministic heuristic signal extraction.

This is the SOLE signal extractor (there must never be a second one). The
persisted taxonomy is closed: every row's signal_type must be one of
requirement|decision|blocker|next_action|assumption|question|context.
Nothing is ever persisted with signal_type=None -- text that doesn't match a
specific pattern either falls back to "context" (if it's substantial prose)
or is dropped before insertion (if it's trivial/non-prose).
"""
from __future__ import annotations

import re

from lce.core.ids import signal_id_for

VALID_SIGNAL_TYPES = {
    "requirement",
    "decision",
    "blocker",
    "next_action",
    "assumption",
    "question",
    "context",
}

# Order matters: first matching pattern wins.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "requirement",
        re.compile(
            r"^\s*requirement\s*:|\b(required|requirement|must\b|non-negotiable|success criteria|done when)\b",
            re.I,
        ),
    ),
    (
        "decision",
        re.compile(
            r"^\s*decision\s*:|\b(decision|decided|we will use|we chose|chosen|selected|going with)\b",
            re.I,
        ),
    ),
    (
        "blocker",
        re.compile(
            r"^\s*blocker\s*:|\b(blocker|blocked|\brisk\b|constraint|cannot\b|can't\b|missing\b|failing\b|broken\b|issue\b|problem\b)\b",
            re.I,
        ),
    ),
    (
        "next_action",
        re.compile(
            r"^\s*next[ _-]?action\s*:|\b(next action|todo|to-do|next step|will implement|implement\b|integrate\b)\b",
            re.I,
        ),
    ),
    (
        "assumption",
        re.compile(
            r"^\s*assumption\s*:|\b(assume|assumption|assuming that|we assume|assumed)\b",
            re.I,
        ),
    ),
    (
        "question",
        re.compile(r"^\s*question\s*:|\?\s*$", re.I),
    ),
]

MIN_SIGNAL_LEN = 12
MIN_CONTEXT_LEN = 80


def detect_signal_type(text: str) -> str | None:
    """Classify a sentence. Returns a valid taxonomy value or None.

    None means "not classifiable as a specific signal type" -- callers
    decide whether that becomes 'context' or gets dropped; None itself is
    never persisted.
    """
    for signal_type, pattern in _PATTERNS:
        if pattern.search(text):
            return signal_type
    return None


def extract_signals(rus: list[dict], backend: str = "heuristic") -> list[dict]:
    out = []
    seen: set[tuple[str, str, str]] = set()

    for ru in rus:
        sentences = re.split(r"(?<=[.!?])\s+|\n+", ru["content"])
        for raw in sentences:
            s = raw.strip(" -\t")
            if len(s) < MIN_SIGNAL_LEN:
                continue

            signal_type = detect_signal_type(s)
            if signal_type is None:
                if len(s) < MIN_CONTEXT_LEN:
                    # Too short and not a strong match for anything specific;
                    # not worth persisting as generic context noise.
                    continue
                signal_type = "context"

            assert signal_type in VALID_SIGNAL_TYPES

            content = s[:1000] if signal_type != "context" else s[:600]
            key = (ru["ru_id"], signal_type, content.strip())
            if key in seen:
                continue
            seen.add(key)

            out.append(
                {
                    "signal_id": signal_id_for(ru["ru_id"], signal_type, content),
                    "ru_id": ru["ru_id"],
                    "doc_id": ru["doc_id"],
                    "signal_type": signal_type,
                    "content": content,
                    "confidence": 0.72 if signal_type != "context" else 0.45,
                    "metadata": {"extractor": "heuristic_regex" if signal_type != "context" else "heuristic_context"},
                }
            )

    return out
