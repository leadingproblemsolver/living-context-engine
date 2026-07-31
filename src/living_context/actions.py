from __future__ import annotations

import re

from living_context.models import (
    ACTION_EFFORT_DAYS,
    Action,
    confidence_from_evidence,
    digest,
)
from living_context.store import Store

# Claims about what people *do* cannot be settled by asking. When an attribute
# looks behavioural, the router escalates from interview to experiment.
BEHAVIOURAL = re.compile(
    r"\b(pay|paid|paying|price|pricing|willing|buy|buys|purchase|churn|renew|"
    r"retention|adopt|adoption|usage|convert|conversion|switch)\b",
    re.IGNORECASE,
)
MARKET_SHAPED = re.compile(
    r"\b(how many|market size|competitor|competitors|landscape|pricing page|"
    r"regulat|compliance requirement|who else)\b",
    re.IGNORECASE,
)
PERSON_SHAPED = re.compile(r"\b(who owns|who decides|who approves|which team)\b", re.IGNORECASE)

# What each method would add if it were run, expressed as evidence rows so the
# projected confidence uses exactly the same maths as the real thing.
PROPOSED_EVIDENCE = {
    "interview": [
        {"kind": "interview", "actor": f"prospective-respondent-{index}"} for index in range(8)
    ],
    "experiment": [{"kind": "experiment", "actor": "designed-test"}],
    "desk_research": [
        {"kind": "public_source", "actor": f"source-{index}"} for index in range(3)
    ],
    "instrument": [{"kind": "usage_data", "actor": "product-telemetry"}],
    "ask_expert": [{"kind": "third_party", "actor": "domain-expert"}],
    "reconcile": [{"kind": "interview", "actor": f"tiebreak-respondent-{index}"} for index in range(4)],
    "decide": [{"kind": "assertion", "actor": "decision-owner"}],
}

METHOD_LABEL = {
    "interview": "Interview",
    "experiment": "Run an experiment",
    "desk_research": "Desk research",
    "instrument": "Instrument and measure",
    "ask_expert": "Ask a domain expert",
    "reconcile": "Reconcile conflicting evidence",
    "decide": "Make the call",
}


def _method_for_question(question: str) -> str:
    if BEHAVIOURAL.search(question):
        return "experiment"
    if MARKET_SHAPED.search(question):
        return "desk_research"
    if PERSON_SHAPED.search(question):
        return "ask_expert"
    return "interview"


def _method_for_claim(attribute: str, value: str, evidence: list[dict]) -> str:
    kinds = {row.get("kind") for row in evidence}
    behavioural = bool(BEHAVIOURAL.search(f"{attribute} {value}"))
    if behavioural and kinds <= {"assertion", "inference", "document", "interview"}:
        return "experiment" if "interview" in kinds else "interview"
    if kinds <= {"assertion", "inference"}:
        return "interview"
    if MARKET_SHAPED.search(f"{attribute} {value}"):
        return "desk_research"
    return "interview"


def _projected_gain(current_evidence: list[dict], method: str) -> float:
    current = confidence_from_evidence(current_evidence)
    projected = confidence_from_evidence(current_evidence + PROPOSED_EVIDENCE.get(method, []))
    return round(max(0.0, projected - current), 4)


def _priority(impact: float, uncertainty: float, gain: float, effort_days: float, linkage: float) -> float:
    """Uncertainty removed per unit of effort, weighted by what it is worth."""
    effort = max(0.25, effort_days) ** 0.5
    return round((impact * uncertainty * max(gain, 0.01) * linkage) / effort, 6)


def propose_actions(
    store: Store,
    project: str,
    half_life_days: float = 180.0,
    confidence_floor: float = 0.6,
    importance_floor: float = 0.4,
) -> list[Action]:
    """Turn every open uncertainty into something a person can actually do."""
    proposals: list[Action] = []

    for unknown in store.unknowns(project, "open"):
        method = _method_for_question(unknown["question"])
        effort = ACTION_EFFORT_DAYS.get(method, 2.0)
        gain = _projected_gain([], method)
        impact = float(unknown["impact"])
        linkage = 1.5 if unknown["blocks_decision"] else 1.0
        if method == "experiment":
            # Behavioural questions have exactly one method that can settle
            # them, so the cheaper-looking alternatives are not alternatives.
            linkage *= 1.6
        proposals.append(
            Action(
                action_id=digest(project, "unknown", unknown["unknown_id"], method),
                project=project,
                title=f"{METHOD_LABEL[method]} to answer: {unknown['question']}",
                kind=method,
                rationale=(
                    f"Open question with impact {impact:.2f}"
                    + (f"; blocks: {unknown['blocks_decision']}" if unknown["blocks_decision"] else "")
                    + f". Expected confidence after this: {gain:.2f} from zero."
                ),
                target_kind="unknown",
                target_id=unknown["unknown_id"],
                expected_confidence_gain=gain,
                effort_days=effort,
                priority=_priority(impact, 1.0, gain, effort, linkage),
                status="proposed",
            )
        )

    for contradiction in store.contradictions(project, "open"):
        method = "reconcile"
        effort = ACTION_EFFORT_DAYS[method]
        severity = float(contradiction["severity"])
        claim_a = store.get_claim(contradiction["claim_a"])
        claim_b = store.get_claim(contradiction["claim_b"])
        evidence = store.evidence_for(contradiction["claim_a"]) + store.evidence_for(
            contradiction["claim_b"]
        )
        gain = _projected_gain(evidence, method)
        entity_name = contradiction.get("entity_name") or contradiction["entity_id"]
        proposals.append(
            Action(
                action_id=digest(project, "contradiction", contradiction["contradiction_id"], method),
                project=project,
                title=(
                    f"Resolve conflict on {entity_name}.{contradiction['attribute']}: "
                    f"{contradiction['note']}"
                ),
                kind=method,
                rationale=(
                    "Two active beliefs disagree and neither is strong enough to retire the "
                    f"other ({(claim_a or {}).get('confidence', 0):.2f} vs "
                    f"{(claim_b or {}).get('confidence', 0):.2f}). Design a check that only one "
                    "of them can survive."
                ),
                target_kind="contradiction",
                target_id=contradiction["contradiction_id"],
                expected_confidence_gain=gain,
                effort_days=effort,
                # A live contradiction is worth more than its severity suggests:
                # it is the cheapest place to learn something.
                priority=_priority(max(severity, 0.3), 1.0, gain, effort, 1.4),
                status="proposed",
            )
        )

    for group in store.state(project, half_life_days=half_life_days):
        # A decision is an act, not a belief awaiting verification. Its
        # consequences get tested through the claims it rests on.
        if group["kind"] == "decision":
            continue
        for claim in group["claims"]:
            effective = float(claim["effective_confidence"])
            importance = float(claim["importance"])
            if effective >= confidence_floor or importance < importance_floor:
                continue
            evidence = store.evidence_for(claim["claim_id"])
            method = _method_for_claim(claim["attribute"], claim["value"], evidence)
            effort = ACTION_EFFORT_DAYS.get(method, 2.0)
            gain = _projected_gain(evidence, method)
            if gain < 0.02:
                continue
            stale = float(claim["staleness_factor"]) < 0.8
            reason = (
                f"Held at {effective:.2f} on {len(evidence)} piece(s) of evidence"
                + (" and the evidence is ageing" if stale else "")
                + f". Importance {importance:.2f}."
            )
            proposals.append(
                Action(
                    action_id=digest(project, "claim", claim["claim_id"], method),
                    project=project,
                    title=(
                        f"{METHOD_LABEL[method]} to test: {group['entity']}."
                        f"{claim['attribute']} = {claim['value']}"
                    ),
                    kind=method,
                    rationale=reason,
                    target_kind="claim",
                    target_id=claim["claim_id"],
                    expected_confidence_gain=gain,
                    effort_days=effort,
                    priority=_priority(importance, 1.0 - effective, gain, effort, 1.0),
                    status="proposed",
                )
            )

    proposals.sort(key=lambda action: (-action.priority, action.title))
    return proposals


def refresh_actions(store: Store, project: str, half_life_days: float = 180.0) -> list[dict]:
    proposals = propose_actions(store, project, half_life_days)
    store.replace_proposed_actions(project, proposals)
    return [action.to_dict() for action in proposals]
