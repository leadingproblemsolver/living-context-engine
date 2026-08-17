from __future__ import annotations

from living_context.models import (
    Claim,
    Contradiction,
    Entity,
    Evidence,
    ObservationSource,
    Relationship,
    Transition,
    Unknown,
    confidence_from_evidence,
    digest,
    normalize,
    now_iso,
    staleness_factor,
)
from living_context.observe import content_hash, normalize_packet, validate_packet
from living_context.store import Store

# A new value must beat the incumbent by this margin before it supersedes it.
# Below the margin the two beliefs are both kept and the conflict stays open,
# because a near-tie is information, not noise.
SUPERSEDE_MARGIN = 1.25

MULTIVALUE_SUFFIX = "[]"


def _is_multivalued(attribute: str) -> bool:
    return attribute.strip().endswith(MULTIVALUE_SUFFIX)


def _describe_evidence(rows: list[dict]) -> str:
    if not rows:
        return "no evidence"
    kinds: dict[str, int] = {}
    actors = set()
    for row in rows:
        kinds[row.get("kind") or "unknown"] = kinds.get(row.get("kind") or "unknown", 0) + 1
        if row.get("actor"):
            actors.add(str(row["actor"]).split("#")[0])
    parts = [f"{count} {kind}" for kind, count in sorted(kinds.items())]
    summary = ", ".join(parts)
    if actors:
        summary += f" from {len(actors)} source{'s' if len(actors) != 1 else ''}"
    return summary


def apply_packet(
    store: Store,
    project: str,
    packet: dict,
    half_life_days: float = 180.0,
    source_ref: str = "",
) -> dict:
    """Compare one observation against current state and record what changed.

    This is the whole loop: extraction has already happened by the time a packet
    arrives; here we diff it against the graph, write the transition, and keep
    the reason the belief moved.
    """
    packet = normalize_packet(packet, source_ref=source_ref)
    errors = validate_packet(packet)
    if errors:
        raise ValueError("; ".join(errors))

    source = packet["source"]
    observation = ObservationSource.build(
        project=project,
        source_ref=source["ref"],
        source_kind=source["kind"],
        actor=source["actor"],
        observed_at=source["observed_at"],
        content_hash=content_hash(packet),
    )
    is_new_observation = store.record_observation(observation)

    report = {
        "source": source["ref"],
        "observation_id": observation.observation_id,
        "new_observation": is_new_observation,
        "entities_seen": 0,
        "claims_seen": 0,
        "evidence_added": 0,
        "transitions": [],
        "contradictions_opened": [],
        "unknowns_added": [],
        "relationships_added": 0,
    }

    entity_ids: dict[str, str] = {}
    for item in packet["entities"]:
        entity = Entity.build(project, item["kind"], item["name"], item.get("aliases"))
        problems = entity.validate()
        if problems:
            continue
        store.upsert_entity(entity)
        entity_ids[normalize(item["name"])] = entity.entity_id
        report["entities_seen"] += 1

    for item in packet["claims"]:
        entity_id = entity_ids.get(normalize(item["entity"]))
        if entity_id is None:
            found = store.find_entity(project, item["entity"])
            if found is None:
                continue
            entity_id = found["entity_id"]

        transition = _apply_claim(
            store=store,
            project=project,
            entity_id=entity_id,
            item=item,
            observation=observation,
            half_life_days=half_life_days,
            report=report,
        )
        report["claims_seen"] += 1
        if transition:
            report["transitions"].append(transition)

    for item in packet["unknowns"]:
        unknown = Unknown.build(
            project=project,
            question=item["question"],
            impact=item.get("impact", 0.5),
            blocks_decision=item.get("blocks_decision", ""),
            source_ref=source["ref"],
        )
        if store.upsert_unknown(unknown):
            report["unknowns_added"].append(
                {"unknown_id": unknown.unknown_id, "question": unknown.question}
            )

    for item in packet["relationships"]:
        from_id = entity_ids.get(normalize(item["from"]))
        to_id = entity_ids.get(normalize(item["to"]))
        if not (from_id and to_id):
            continue
        store.upsert_relationship(
            Relationship.build(
                project=project,
                from_entity=from_id,
                to_entity=to_id,
                relation=item["relation"],
                confidence=0.6,
                source_ref=source["ref"],
            )
        )
        report["relationships_added"] += 1

    return report


def _apply_claim(
    store: Store,
    project: str,
    entity_id: str,
    item: dict,
    observation: ObservationSource,
    half_life_days: float,
    report: dict,
) -> dict | None:
    # Fold known attribute aliases before anything else. `main_pain` and
    # `primary_pain` must land in the same slot or the delta silently vanishes.
    aliases = store.attribute_aliases(project)
    attribute = item["attribute"]
    attribute_key = normalize(attribute).replace(" ", "_")
    attribute = aliases.get(attribute_key, attribute)
    observed_at = observation.observed_at
    claim = Claim.build(
        project=project,
        entity_id=entity_id,
        attribute=attribute,
        value=item["value"],
        importance=item.get("importance", 0.5),
        observed_at=observed_at,
    )
    if claim.validate():
        return None

    store.record_attribute(project, claim.attribute)
    prior = store.claims_in_slot(project, entity_id, claim.attribute)
    existing = store.get_claim(claim.claim_id)
    store.upsert_claim(claim)

    added_evidence: list[str] = []
    for row in item["evidence"]:
        evidence = Evidence.build(
            project=project,
            claim_id=claim.claim_id,
            observation_id=observation.observation_id,
            kind=row["kind"],
            excerpt=row["excerpt"],
            actor=row["actor"],
            source_ref=observation.source_ref,
            locator=row["locator"],
            observed_at=observed_at,
        )
        if store.add_evidence(evidence):
            added_evidence.append(evidence.evidence_id)
    report["evidence_added"] += len(added_evidence)

    # Nothing new was learned about an already-known claim: no transition.
    if existing and not added_evidence:
        return None

    all_evidence = store.evidence_for(claim.claim_id)
    new_confidence = confidence_from_evidence(all_evidence)
    old_confidence = float(existing["confidence"]) if existing else 0.0
    last_seen = max(
        [observed_at] + ([existing["last_seen_at"]] if existing else [])
    )
    store.update_claim(
        claim.claim_id,
        confidence=new_confidence,
        last_seen_at=last_seen,
        importance=max(claim.importance, float(existing["importance"]) if existing else 0.0),
    )

    competitors = [row for row in prior if row["claim_id"] != claim.claim_id]
    evidence_summary = _describe_evidence(all_evidence)

    if existing:
        transition_type = "reinforced" if new_confidence >= old_confidence else "weakened"
        rationale = (
            f"{len(added_evidence)} new observation(s) — now {evidence_summary}; "
            f"confidence {old_confidence:.2f} -> {new_confidence:.2f}"
        )
        from_value: str | None = claim.value
        superseded_claim_id = None
    elif not competitors or _is_multivalued(claim.attribute):
        transition_type = "established"
        rationale = f"first stated here; supported by {evidence_summary}"
        from_value = None
        superseded_claim_id = None
    else:
        transition_type, rationale, superseded_claim_id = _resolve_conflict(
            store=store,
            project=project,
            entity_id=entity_id,
            claim=claim,
            new_confidence=new_confidence,
            competitors=competitors,
            evidence_summary=evidence_summary,
            half_life_days=half_life_days,
            report=report,
        )
        from_value = competitors[0]["value"]

    transition = Transition(
        transition_id=digest(claim.claim_id, transition_type, observed_at, len(all_evidence)),
        project=project,
        entity_id=entity_id,
        attribute=claim.attribute,
        transition_type=transition_type,
        from_value=from_value,
        to_value=claim.value,
        from_confidence=round(old_confidence, 4),
        to_confidence=new_confidence,
        rationale=rationale,
        claim_id=claim.claim_id,
        superseded_claim_id=superseded_claim_id,
        evidence_ids=added_evidence,
        occurred_at=now_iso(),
    )
    store.record_transition(transition)
    return transition.to_dict()


def _resolve_conflict(
    store: Store,
    project: str,
    entity_id: str,
    claim: Claim,
    new_confidence: float,
    competitors: list[dict],
    evidence_summary: str,
    half_life_days: float,
    report: dict,
) -> tuple[str, str, str | None]:
    """A conflicting value always produces a contradiction record.

    Whether the new value also supersedes the old one depends on the evidence,
    not on which arrived last.
    """
    new_effective = new_confidence * staleness_factor(claim.last_seen_at, half_life_days)
    strongest = max(
        competitors,
        key=lambda row: row["confidence"] * staleness_factor(row["last_seen_at"], half_life_days),
    )
    rival_effective = strongest["confidence"] * staleness_factor(
        strongest["last_seen_at"], half_life_days
    )

    supersedes = new_effective >= rival_effective * SUPERSEDE_MARGIN
    superseded_claim_id = None

    for rival in competitors:
        pair = sorted([claim.claim_id, rival["claim_id"]])
        contradiction = Contradiction(
            contradiction_id=digest(project, entity_id, claim.attribute, *pair),
            project=project,
            entity_id=entity_id,
            attribute=claim.attribute,
            claim_a=pair[0],
            claim_b=pair[1],
            status="resolved" if supersedes else "open",
            severity=round(
                min(new_confidence, float(rival["confidence"]))
                * max(claim.importance, float(rival["importance"])),
                4,
            ),
            note=f'"{rival["value"]}" vs "{claim.value}"',
            resolution=(
                f"superseded by stronger evidence ({new_effective:.2f} vs {rival_effective:.2f})"
                if supersedes
                else ""
            ),
        )
        if store.upsert_contradiction(contradiction) and not supersedes:
            report["contradictions_opened"].append(
                {
                    "contradiction_id": contradiction.contradiction_id,
                    "attribute": claim.attribute,
                    "note": contradiction.note,
                    "severity": contradiction.severity,
                }
            )
        if supersedes:
            store.update_claim(
                rival["claim_id"], status="superseded", superseded_by=claim.claim_id
            )
            superseded_claim_id = rival["claim_id"]

    if supersedes:
        return (
            "revised",
            (
                f'"{strongest["value"]}" -> "{claim.value}": new evidence '
                f"({evidence_summary}) outweighs the prior belief "
                f"({new_effective:.2f} vs {rival_effective:.2f})"
            ),
            superseded_claim_id,
        )
    return (
        "contested",
        (
            f'"{strongest["value"]}" and "{claim.value}" both stand '
            f"({rival_effective:.2f} vs {new_effective:.2f}); neither side of the "
            f"conflict is strong enough to retire the other"
        ),
        None,
    )


def apply_packets(
    store: Store,
    project: str,
    packets: list[dict],
    half_life_days: float = 180.0,
    source_ref: str = "",
) -> dict:
    reports = []
    for packet in packets:
        reports.append(
            apply_packet(store, project, packet, half_life_days, source_ref=source_ref)
        )
    summary = {
        "packets": len(reports),
        "entities_seen": sum(item["entities_seen"] for item in reports),
        "claims_seen": sum(item["claims_seen"] for item in reports),
        "evidence_added": sum(item["evidence_added"] for item in reports),
        "transitions": [t for item in reports for t in item["transitions"]],
        "contradictions_opened": [
            c for item in reports for c in item["contradictions_opened"]
        ],
        "unknowns_added": [u for item in reports for u in item["unknowns_added"]],
        "sources": sorted({item["source"] for item in reports}),
    }
    summary["transition_counts"] = {}
    for transition in summary["transitions"]:
        key = transition["transition_type"]
        summary["transition_counts"][key] = summary["transition_counts"].get(key, 0) + 1
    return summary
