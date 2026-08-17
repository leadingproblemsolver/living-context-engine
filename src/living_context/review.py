from __future__ import annotations

from living_context.delta import apply_packet
from living_context.models import Proposal
from living_context.observe import normalize_packet, validate_packet
from living_context.store import Store

# Deterministic parsing of a file a human wrote is trusted. Anything inferred by
# a model, or pulled from a third-party system, waits for a person.
DEFAULT_AUTO_APPLY = ("parser", "human")


def auto_applies(origin: str, auto_apply: tuple[str, ...] | list[str]) -> bool:
    root = origin.split(":", 1)[0]
    return root in tuple(auto_apply)


def _single_claim_packet(source: dict, entities: list[dict], claim: dict) -> dict:
    names = {claim["entity"]}
    return {
        "source": source,
        "entities": [item for item in entities if item["name"] in names] or [
            {"name": claim["entity"], "kind": "other", "aliases": []}
        ],
        "claims": [claim],
        "relationships": [],
        "unknowns": [],
    }


def stage_packet(
    store: Store,
    project: str,
    packet: dict,
    origin: str,
    source_ref: str = "",
) -> dict:
    """Split a packet into individually reviewable proposals.

    One proposal per claim, so a reviewer can accept the three that are right
    and reject the one that is a hallucination, rather than judging a blob.
    """
    packet = normalize_packet(packet, source_ref=source_ref)
    errors = validate_packet(packet)
    if errors:
        raise ValueError("; ".join(errors))

    source = packet["source"]
    staged = {"claims": 0, "unknowns": 0, "relationships": 0, "duplicates": 0}
    proposals: list[dict] = []

    def record(kind: str, payload: dict, summary: str) -> None:
        proposal = Proposal.build(project, kind, origin, payload, source["ref"], summary)
        if store.add_proposal(proposal):
            staged[kind + "s" if kind in {"claim", "unknown", "relationship"} else kind] += 1
            proposals.append({"proposal_id": proposal.proposal_id, "summary": summary})
        else:
            staged["duplicates"] += 1

    for claim in packet["claims"]:
        record(
            "claim",
            _single_claim_packet(source, packet["entities"], claim),
            f"{claim['entity']}.{claim['attribute']} = {claim['value']} "
            f"({len(claim['evidence'])} evidence, {source['kind']})",
        )
    for unknown in packet["unknowns"]:
        record(
            "unknown",
            {"source": source, "entities": [], "claims": [], "relationships": [], "unknowns": [unknown]},
            f"unknown: {unknown['question']} (impact {unknown['impact']:.2f})",
        )
    for relationship in packet["relationships"]:
        record(
            "relationship",
            {
                "source": source,
                "entities": [
                    item
                    for item in packet["entities"]
                    if item["name"] in {relationship["from"], relationship["to"]}
                ],
                "claims": [],
                "relationships": [relationship],
                "unknowns": [],
            },
            f"{relationship['from']} -[{relationship['relation']}]-> {relationship['to']}",
        )

    return {"source": source["ref"], "origin": origin, "staged": staged, "proposals": proposals}


def accept(
    store: Store,
    project: str,
    proposal_id: str,
    half_life_days: float = 180.0,
    decided_by: str = "",
) -> dict:
    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise ValueError(f"unknown proposal: {proposal_id}")
    if proposal["project"] != project:
        raise ValueError(f"proposal {proposal_id} belongs to project {proposal['project']}")
    if proposal["status"] != "pending":
        return {"proposal_id": proposal_id, "status": proposal["status"], "applied": False}

    payload = proposal["payload"]
    result: dict
    if proposal["kind"] in {"claim", "unknown", "relationship"}:
        result = apply_packet(
            store, project, payload, half_life_days, source_ref=proposal["source_ref"]
        )
    elif proposal["kind"] == "entity_merge":
        result = store.merge_entities(
            project, payload["keep"], payload["merge"], payload.get("reason", "")
        )
    elif proposal["kind"] == "attribute_alias":
        moved = store.rename_attribute(project, payload["attribute"], payload["canonical"])
        result = {"attribute": payload["attribute"], "canonical": payload["canonical"], "claims_moved": moved}
    else:
        raise ValueError(f"cannot apply proposal kind: {proposal['kind']}")

    store.settle_proposal(proposal_id, "accepted", decided_by)
    return {
        "proposal_id": proposal_id,
        "status": "accepted",
        "applied": True,
        "kind": proposal["kind"],
        "result": result,
    }


def reject(
    store: Store, project: str, proposal_id: str, note: str = "", decided_by: str = ""
) -> dict:
    proposal = store.get_proposal(proposal_id)
    if proposal is None:
        raise ValueError(f"unknown proposal: {proposal_id}")
    store.settle_proposal(proposal_id, "rejected", decided_by, note)
    return {"proposal_id": proposal_id, "status": "rejected", "note": note}


def accept_many(
    store: Store,
    project: str,
    proposal_ids: list[str],
    half_life_days: float = 180.0,
    decided_by: str = "",
) -> dict:
    applied, failed = [], []
    for proposal_id in proposal_ids:
        try:
            applied.append(accept(store, project, proposal_id, half_life_days, decided_by))
        except ValueError as error:
            failed.append({"proposal_id": proposal_id, "error": str(error)})
    return {"accepted": len(applied), "failed": failed, "results": applied}
