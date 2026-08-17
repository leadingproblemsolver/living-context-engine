from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Observation layer (v1 primitive, retained)
# ---------------------------------------------------------------------------

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
        errors = []
        for field_name in (
            "record_id",
            "project",
            "kind",
            "text",
            "source_path",
            "source_hash",
            "observed_at",
        ):
            if not getattr(self, field_name):
                errors.append(f"{field_name} is required")
        if self.kind not in KINDS:
            errors.append(f"unsupported kind: {self.kind}")
        if self.source_line < 1:
            errors.append("source_line must be >= 1")
        try:
            datetime.fromisoformat(self.observed_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("observed_at must be an ISO-8601 date or datetime")
        if len(self.text) > 10_000:
            errors.append("text exceeds 10000 characters")
        if len(self.project) > 200:
            errors.append("project exceeds 200 characters")
        if len(self.source_path) > 1000:
            errors.append("source_path exceeds 1000 characters")
        return errors

    def to_dict(self):
        result = asdict(self)
        result["tags"] = list(self.tags)
        return result


# ---------------------------------------------------------------------------
# State layer (Entity / Claim / Evidence / Transition / Contradiction)
# ---------------------------------------------------------------------------

ENTITY_KINDS = {
    "segment",
    "person",
    "company",
    "problem",
    "solution",
    "competitor",
    "channel",
    "metric",
    "constraint",
    "decision",
    "experiment",
    "assumption",
    "risk",
    "project",
    "other",
}

# Evidence weights express "how much does one observation of this type move
# belief", not "how true is it".
EVIDENCE_WEIGHTS = {
    "experiment": 0.35,
    "transaction": 0.34,
    "measurement": 0.32,
    "interview": 0.30,
    "usage_data": 0.30,
    "document": 0.15,
    "public_source": 0.12,
    "third_party": 0.12,
    "assertion": 0.08,
    "inference": 0.05,
}
DEFAULT_EVIDENCE_WEIGHT = 0.10
CONFIDENCE_CEILING = 0.97

# A method ceiling bounds what a kind of evidence can ever establish, no matter
# how much of it accumulates. Stated intent does not become proof of behaviour by
# repetition — only a transaction or an experiment can carry a claim that high.
KIND_CEILINGS = {
    "experiment": 0.95,
    "transaction": 0.95,
    "measurement": 0.93,
    "usage_data": 0.92,
    "interview": 0.85,
    "document": 0.75,
    "public_source": 0.70,
    "third_party": 0.70,
    "assertion": 0.60,
    "inference": 0.50,
}
DEFAULT_KIND_CEILING = 0.70

# Repeat observations from the same actor using the same method are correlated,
# not independent. Each additional one counts for less. Without this, one loud
# voice repeated often reads as certainty.
CORRELATION_DECAY = 0.7

TRANSITION_TYPES = {
    "established",
    "reinforced",
    "revised",
    "contested",
    "weakened",
    "retired",
}
CLAIM_STATUSES = {"active", "superseded", "retracted"}
CONTRADICTION_STATUSES = {"open", "resolved", "accepted"}
UNKNOWN_STATUSES = {"open", "resolved", "dropped"}
ACTION_STATUSES = {"proposed", "in_progress", "done", "dropped"}
ACTION_KINDS = {
    "interview",
    "experiment",
    "desk_research",
    "instrument",
    "ask_expert",
    "decide",
    "reconcile",
}

# Rough effort in person-days, used only to rank actions against each other.
ACTION_EFFORT_DAYS = {
    "interview": 3.0,
    "experiment": 8.0,
    "desk_research": 1.0,
    "instrument": 4.0,
    "ask_expert": 0.5,
    "decide": 0.5,
    "reconcile": 1.0,
}


def now_iso() -> str:
    # Microsecond resolution: several transitions can be recorded inside one
    # second, and their order is the story of how a belief moved.
    return datetime.now(timezone.utc).isoformat()


def digest(*parts: object, length: int = 24) -> str:
    joined = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:length]


def normalize(text: str) -> str:
    """Canonical form used for identity and equality of names and values."""
    lowered = re.sub(r"\s+", " ", (text or "").strip().lower())
    lowered = lowered.strip("\"'` ")
    return lowered.rstrip(".").strip()


def parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def confidence_from_evidence(evidence: list[dict]) -> float:
    """Noisy-OR over independent evidence, damped for correlated repeats.

    A claim's confidence is derived from its evidence rows and nothing else, so
    it can always be recomputed from provenance.
    """
    if not evidence:
        return 0.0
    seen: dict[tuple[str, str], int] = {}
    remaining = 1.0
    ceiling = 0.0
    for item in sorted(evidence, key=lambda row: row.get("observed_at") or ""):
        kind = (item.get("kind") or "").lower()
        base = EVIDENCE_WEIGHTS.get(kind, DEFAULT_EVIDENCE_WEIGHT)
        override = item.get("weight")
        if isinstance(override, (int, float)) and override > 0:
            base = min(0.6, float(override))
        ceiling = max(ceiling, KIND_CEILINGS.get(kind, DEFAULT_KIND_CEILING))
        key = (kind, normalize(str(item.get("actor") or "")))
        repeats = seen.get(key, 0)
        seen[key] = repeats + 1
        remaining *= 1.0 - base * (CORRELATION_DECAY**repeats)
    return round(min(CONFIDENCE_CEILING, ceiling, 1.0 - remaining), 4)


def staleness_factor(
    last_observed_at: str, half_life_days: float, as_of: str | None = None
) -> float:
    """Belief decays toward half its stated strength as its evidence ages."""
    if half_life_days <= 0:
        return 1.0
    reference = parse_timestamp(as_of) if as_of else datetime.now(timezone.utc)
    age_days = max(
        0.0, (reference - parse_timestamp(last_observed_at)).total_seconds() / 86400.0
    )
    return round(max(0.5, 1.0 - (age_days / (half_life_days * 2.0))), 4)


@dataclass
class Entity:
    entity_id: str
    project: str
    kind: str
    name: str
    canonical_key: str
    aliases: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def build(
        project: str, kind: str, name: str, aliases: list[str] | None = None
    ) -> "Entity":
        kind = kind if kind in ENTITY_KINDS else "other"
        canonical_key = normalize(name)
        return Entity(
            entity_id=digest(project, kind, canonical_key),
            project=project,
            kind=kind,
            name=name.strip(),
            canonical_key=canonical_key,
            aliases=sorted({normalize(alias) for alias in (aliases or []) if normalize(alias)}),
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.canonical_key:
            errors.append("entity name is required")
        if len(self.name) > 300:
            errors.append("entity name exceeds 300 characters")
        if self.kind not in ENTITY_KINDS:
            errors.append(f"unsupported entity kind: {self.kind}")
        return errors

    def to_dict(self):
        return asdict(self)


@dataclass
class Evidence:
    evidence_id: str
    project: str
    claim_id: str
    observation_id: str
    kind: str
    excerpt: str
    actor: str
    source_ref: str
    locator: str
    observed_at: str
    weight: float | None = None

    @staticmethod
    def build(
        project: str,
        claim_id: str,
        observation_id: str,
        kind: str,
        excerpt: str,
        actor: str,
        source_ref: str,
        locator: str,
        observed_at: str,
        weight: float | None = None,
    ) -> "Evidence":
        return Evidence(
            evidence_id=digest(
                project, claim_id, source_ref, locator, normalize(excerpt), actor
            ),
            project=project,
            claim_id=claim_id,
            observation_id=observation_id,
            kind=kind,
            excerpt=excerpt[:2000],
            actor=actor,
            source_ref=source_ref,
            locator=locator,
            observed_at=observed_at,
            weight=weight,
        )

    def to_dict(self):
        return asdict(self)


@dataclass
class Claim:
    claim_id: str
    project: str
    entity_id: str
    attribute: str
    value: str
    normalized_value: str
    confidence: float = 0.0
    status: str = "active"
    importance: float = 0.5
    first_seen_at: str = field(default_factory=now_iso)
    last_seen_at: str = field(default_factory=now_iso)
    superseded_by: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def build(
        project: str,
        entity_id: str,
        attribute: str,
        value: str,
        importance: float = 0.5,
        observed_at: str | None = None,
    ) -> "Claim":
        attribute_key = normalize(attribute).replace(" ", "_")
        normalized_value = normalize(value)
        stamp = observed_at or now_iso()
        return Claim(
            claim_id=digest(project, entity_id, attribute_key, normalized_value),
            project=project,
            entity_id=entity_id,
            attribute=attribute_key,
            value=value.strip(),
            normalized_value=normalized_value,
            importance=max(0.0, min(1.0, importance)),
            first_seen_at=stamp,
            last_seen_at=stamp,
        )

    def validate(self) -> list[str]:
        errors = []
        if not self.attribute:
            errors.append("claim attribute is required")
        if not self.normalized_value:
            errors.append("claim value is required")
        if self.status not in CLAIM_STATUSES:
            errors.append(f"unsupported claim status: {self.status}")
        if not 0.0 <= self.confidence <= 1.0:
            errors.append("confidence must be between 0 and 1")
        if len(self.value) > 2000:
            errors.append("claim value exceeds 2000 characters")
        return errors

    def to_dict(self):
        return asdict(self)


@dataclass
class Transition:
    transition_id: str
    project: str
    entity_id: str
    attribute: str
    transition_type: str
    from_value: str | None
    to_value: str
    from_confidence: float
    to_confidence: float
    rationale: str
    claim_id: str
    superseded_claim_id: str | None
    evidence_ids: list[str]
    occurred_at: str = field(default_factory=now_iso)

    def to_dict(self):
        return asdict(self)


@dataclass
class Contradiction:
    contradiction_id: str
    project: str
    entity_id: str
    attribute: str
    claim_a: str
    claim_b: str
    status: str = "open"
    severity: float = 0.5
    note: str = ""
    detected_at: str = field(default_factory=now_iso)
    resolved_at: str | None = None
    resolution: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class Unknown:
    unknown_id: str
    project: str
    question: str
    entity_id: str | None = None
    impact: float = 0.5
    status: str = "open"
    blocks_decision: str = ""
    source_ref: str = ""
    created_at: str = field(default_factory=now_iso)
    resolved_at: str | None = None
    answer: str = ""

    @staticmethod
    def build(
        project: str,
        question: str,
        entity_id: str | None = None,
        impact: float = 0.5,
        blocks_decision: str = "",
        source_ref: str = "",
    ) -> "Unknown":
        return Unknown(
            unknown_id=digest(project, normalize(question)),
            project=project,
            question=question.strip(),
            entity_id=entity_id,
            impact=max(0.0, min(1.0, impact)),
            blocks_decision=blocks_decision,
            source_ref=source_ref,
        )

    def to_dict(self):
        return asdict(self)


@dataclass
class Relationship:
    relationship_id: str
    project: str
    from_entity: str
    to_entity: str
    relation: str
    confidence: float = 0.5
    source_ref: str = ""
    observed_at: str = field(default_factory=now_iso)

    @staticmethod
    def build(
        project: str,
        from_entity: str,
        to_entity: str,
        relation: str,
        confidence: float = 0.5,
        source_ref: str = "",
    ) -> "Relationship":
        relation_key = normalize(relation).replace(" ", "_")
        return Relationship(
            relationship_id=digest(project, from_entity, to_entity, relation_key),
            project=project,
            from_entity=from_entity,
            to_entity=to_entity,
            relation=relation_key,
            confidence=max(0.0, min(1.0, confidence)),
            source_ref=source_ref,
        )

    def to_dict(self):
        return asdict(self)


@dataclass
class Action:
    action_id: str
    project: str
    title: str
    kind: str
    rationale: str
    target_kind: str
    target_id: str
    expected_confidence_gain: float
    effort_days: float
    priority: float
    status: str = "proposed"
    created_at: str = field(default_factory=now_iso)
    completed_at: str | None = None
    result: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class ObservationSource:
    observation_id: str
    project: str
    source_ref: str
    source_kind: str
    actor: str
    observed_at: str
    content_hash: str
    ingested_at: str = field(default_factory=now_iso)

    @staticmethod
    def build(
        project: str,
        source_ref: str,
        source_kind: str,
        actor: str,
        observed_at: str,
        content_hash: str,
    ) -> "ObservationSource":
        return ObservationSource(
            observation_id=digest(project, source_ref, content_hash),
            project=project,
            source_ref=source_ref,
            source_kind=source_kind,
            actor=actor,
            observed_at=observed_at,
            content_hash=content_hash,
        )

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# Adoption layer: proposals, decisions, connectors
# ---------------------------------------------------------------------------

PROPOSAL_KINDS = {"claim", "unknown", "relationship", "entity_merge", "attribute_alias"}
PROPOSAL_STATUSES = {"pending", "accepted", "rejected", "superseded"}
DECISION_STATUSES = {"open", "decided", "deferred", "reversed"}

# Where a proposal came from. Deterministic parsing is trusted by default;
# anything inferred or pulled from a third party is not.
ORIGINS = {"parser", "model", "connector", "api", "human"}
TRUSTED_ORIGINS = ("parser", "human")


@dataclass
class Proposal:
    """A change waiting for a human. Nothing inferred enters state unreviewed."""

    proposal_id: str
    project: str
    kind: str
    origin: str
    payload: dict[str, Any]
    source_ref: str
    summary: str
    status: str = "pending"
    created_at: str = field(default_factory=now_iso)
    decided_at: str | None = None
    decided_by: str = ""
    note: str = ""

    @staticmethod
    def build(
        project: str,
        kind: str,
        origin: str,
        payload: dict,
        source_ref: str,
        summary: str,
    ) -> "Proposal":
        import json as _json

        # Identity is the content, so re-pulling a source cannot pile up
        # duplicate pending proposals.
        key = _json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return Proposal(
            proposal_id=digest(project, kind, key),
            project=project,
            kind=kind if kind in PROPOSAL_KINDS else "claim",
            origin=origin,
            payload=payload,
            source_ref=source_ref,
            summary=summary[:400],
        )

    def to_dict(self):
        return asdict(self)


@dataclass
class Decision:
    """An open question the organisation owes an answer to.

    Claims exist to serve decisions. Linking them is what turns a confidence
    number into something worth spending a week on.
    """

    decision_id: str
    project: str
    question: str
    owner: str = ""
    status: str = "open"
    weight: float = 0.7
    due_at: str = ""
    choice: str = ""
    rationale: str = ""
    created_at: str = field(default_factory=now_iso)
    decided_at: str | None = None

    @staticmethod
    def build(
        project: str,
        question: str,
        owner: str = "",
        weight: float = 0.7,
        due_at: str = "",
    ) -> "Decision":
        return Decision(
            decision_id=digest(project, normalize(question), length=16),
            project=project,
            question=question.strip(),
            owner=owner,
            weight=max(0.0, min(1.0, weight)),
            due_at=due_at,
        )

    def to_dict(self):
        return asdict(self)
