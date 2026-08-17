from __future__ import annotations

from living_context.context import question_terms, term_overlap
from living_context.models import Decision, staleness_factor
from living_context.store import Store

# A decision is "decidable" when the beliefs it rests on are strong enough and
# nothing unresolved is pointed at it.
DECIDABLE = 0.7
THIN = 0.4


def add(
    store: Store,
    project: str,
    question: str,
    owner: str = "",
    weight: float = 0.7,
    due_at: str = "",
) -> dict:
    decision = Decision.build(project, question, owner, weight, due_at)
    created = store.upsert_decision(decision)
    return {**decision.to_dict(), "created": created}


def link(
    store: Store, project: str, decision_id: str, target_kind: str, target_id: str
) -> dict:
    decision = store.get_decision(decision_id)
    if decision is None:
        raise ValueError(f"unknown decision: {decision_id}")
    linked = store.link_decision(project, decision_id, target_kind, target_id)
    if target_kind == "claim":
        # Serving a decision is what makes a claim important. Raise the floor
        # rather than overwrite, so a hand-set higher value survives.
        claim = store.get_claim(target_id)
        if claim and float(claim["importance"]) < float(decision["weight"]):
            store.update_claim(target_id, importance=float(decision["weight"]))
    elif target_kind == "unknown":
        unknown = next(
            (row for row in store.unknowns(project, None) if row["unknown_id"] == target_id), None
        )
        if unknown and float(unknown["impact"]) < float(decision["weight"]):
            with store.conn:
                store.conn.execute(
                    "UPDATE unknowns SET impact=?, blocks_decision=? WHERE unknown_id=?",
                    (
                        float(decision["weight"]),
                        unknown["blocks_decision"] or decision["question"],
                        target_id,
                    ),
                )
    return {"decision_id": decision_id, "target_kind": target_kind, "target_id": target_id, "linked": linked}


def auto_link(
    store: Store, project: str, decision_id: str, limit: int = 8, threshold: float = 0.2
) -> dict:
    """Attach the claims and unknowns whose text answers the decision's question."""
    decision = store.get_decision(decision_id)
    if decision is None:
        raise ValueError(f"unknown decision: {decision_id}")
    terms = question_terms(decision["question"])
    linked: list[dict] = []

    scored, fallback = [], []
    for group in store.state(project):
        for claim in group["claims"]:
            # The entity's kind is part of the question's vocabulary: "which
            # segment" is asking about entities of kind `segment`.
            score = term_overlap(
                terms, group["entity"], group["kind"], claim["attribute"], claim["value"]
            )
            label = f"{group['entity']}.{claim['attribute']}"
            if score >= threshold:
                scored.append((score, "claim", claim["claim_id"], label))
            else:
                fallback.append(
                    (
                        round(float(claim["importance"]) * float(claim["effective_confidence"]), 4),
                        "claim",
                        claim["claim_id"],
                        label,
                    )
                )
    for unknown in store.unknowns(project, "open"):
        score = term_overlap(terms, unknown["question"], unknown["blocks_decision"])
        if score >= threshold:
            scored.append((score, "unknown", unknown["unknown_id"], unknown["question"][:80]))
        else:
            fallback.append(
                (float(unknown["impact"]), "unknown", unknown["unknown_id"], unknown["question"][:80])
            )

    # Wording rarely overlaps between a decision and the beliefs it rests on.
    # Rather than leave the decision empty — which reads as "no evidence exists"
    # — fall back to what the graph says matters most, and say that is what
    # happened so a human can prune it.
    used_fallback = not scored
    chosen = sorted(scored if scored else fallback, key=lambda item: -item[0])[:limit]
    for score, kind, target_id, label in chosen:
        result = link(store, project, decision_id, kind, target_id)
        if result["linked"]:
            linked.append({"kind": kind, "target_id": target_id, "label": label, "relevance": score})
    return {
        "decision_id": decision_id,
        "linked": linked,
        "candidates": len(scored),
        "matched_by": "relevance" if not used_fallback else "importance (no wording overlap)",
    }


def readiness(store: Store, project: str, decision_id: str, half_life_days: float = 180.0) -> dict:
    """Can this be decided yet, and if not, what is in the way?"""
    decision = store.get_decision(decision_id)
    if decision is None:
        raise ValueError(f"unknown decision: {decision_id}")

    links = store.decision_links(decision_id)
    claims, unknowns = [], []
    for row in links:
        if row["target_kind"] == "claim":
            claim = store.get_claim(row["target_id"])
            if claim is None or claim["status"] != "active":
                continue
            decay = staleness_factor(claim["last_seen_at"], half_life_days)
            entity = store.conn.execute(
                "SELECT name FROM entities WHERE entity_id=?", (claim["entity_id"],)
            ).fetchone()
            claims.append(
                {
                    "claim_id": claim["claim_id"],
                    "entity": entity["name"] if entity else claim["entity_id"],
                    "attribute": claim["attribute"],
                    "value": claim["value"],
                    "effective_confidence": round(claim["confidence"] * decay, 4),
                    "importance": claim["importance"],
                    "evidence_count": store.conn.execute(
                        "SELECT COUNT(*) FROM evidence WHERE claim_id=?", (claim["claim_id"],)
                    ).fetchone()[0],
                }
            )
        elif row["target_kind"] == "unknown":
            unknown = next(
                (item for item in store.unknowns(project, None) if item["unknown_id"] == row["target_id"]),
                None,
            )
            if unknown and unknown["status"] == "open":
                unknowns.append(unknown)

    claim_ids = {item["claim_id"] for item in claims}
    conflicts = [
        row
        for row in store.contradictions(project, "open", half_life_days)
        if row["claim_a"] in claim_ids or row["claim_b"] in claim_ids
    ]

    if not claims:
        support = 0.0
    else:
        # The weakest load-bearing belief governs, not the average: a decision is
        # only as sound as the claim most likely to be wrong.
        weights = sum(item["importance"] for item in claims) or 1.0
        mean = sum(item["effective_confidence"] * item["importance"] for item in claims) / weights
        weakest = min(item["effective_confidence"] for item in claims)
        support = round(0.5 * mean + 0.5 * weakest, 4)

    blockers = len(unknowns) + len(conflicts)
    score = round(support / (1.0 + 0.5 * blockers), 4)
    if not claims:
        verdict = "no evidence linked — run `lce decision link --auto` or ingest more"
    elif score >= DECIDABLE:
        verdict = "decidable now"
    elif score >= THIN:
        verdict = "thin — one more round of evidence would change the answer"
    else:
        verdict = "not yet — deciding now is a guess wearing a number"

    return {
        "decision_id": decision_id,
        "question": decision["question"],
        "status": decision["status"],
        "owner": decision["owner"],
        "due_at": decision["due_at"],
        "readiness": score,
        "support": support,
        "verdict": verdict,
        "claims": sorted(claims, key=lambda item: item["effective_confidence"]),
        "blocking_unknowns": unknowns,
        "blocking_contradictions": conflicts,
        "weakest_link": min(claims, key=lambda item: item["effective_confidence"])
        if claims
        else None,
    }


def board(store: Store, project: str, half_life_days: float = 180.0) -> list[dict]:
    return [
        readiness(store, project, row["decision_id"], half_life_days)
        for row in store.decisions(project)
    ]


def uncertainty_for_decision(
    store: Store, project: str, decision_id: str, half_life_days: float = 180.0
) -> dict:
    """The north-star metric, scoped to one decision instead of the whole graph."""
    report = readiness(store, project, decision_id, half_life_days)
    claim_load = sum(
        item["importance"] * (1.0 - item["effective_confidence"]) for item in report["claims"]
    )
    unknown_load = sum(float(row["impact"]) for row in report["blocking_unknowns"])
    conflict_load = sum(float(row["severity"]) for row in report["blocking_contradictions"])
    return {
        "decision_id": decision_id,
        "question": report["question"],
        "uncertainty": round(claim_load + unknown_load + conflict_load, 4),
        "claim_load": round(claim_load, 4),
        "unknown_load": round(unknown_load, 4),
        "contradiction_load": round(conflict_load, 4),
        "readiness": report["readiness"],
        "verdict": report["verdict"],
    }
