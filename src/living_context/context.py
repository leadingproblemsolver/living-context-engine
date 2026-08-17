from __future__ import annotations

import json
import re
from pathlib import Path

from living_context.models import KIND_CEILINGS, normalize, staleness_factor
from living_context.store import Store

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "we", "us", "our", "should", "could",
    "would", "do", "does", "did", "is", "are", "was", "were", "be", "to", "of", "in",
    "on", "for", "with", "this", "that", "it", "its", "as", "at", "by", "from", "will",
    "can", "how", "what", "why", "who", "when", "which", "about", "any", "all",
}

# Kinds that constrain every decision, whether or not the task text mentions them.
ALWAYS_RELEVANT_KINDS = {"decision", "constraint", "risk"}


def question_terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{1,}", normalize(text))
        if token not in STOPWORDS
    }


def term_overlap(terms: set[str], *fields: str) -> float:
    if not terms:
        return 0.0
    blob = normalize(" ".join(field for field in fields if field))
    hits = sum(1 for term in terms if term in blob)
    return round(hits / len(terms), 4)


def citations(evidence: list[dict], limit: int = 4) -> list[dict]:
    """One line per distinct observation, with a count for repeats.

    Fifteen identical excerpts from one interview round are one citation with
    n=15, not fifteen citations — the pack has to stay readable.
    """
    grouped: dict[tuple[str, str, str], dict] = {}
    for row in evidence:
        locator = row["locator"].split("#")[0]
        # A connector often bakes the row into the source ref already; repeating
        # it reads as two different citations of the same thing.
        source = (
            row["source_ref"]
            if not locator or locator in row["source_ref"]
            else f"{row['source_ref']}:{locator}"
        ).rstrip(":")
        key = (source, row["kind"], normalize(row["excerpt"]))
        bucket = grouped.setdefault(
            key,
            {
                "source": source,
                "kind": row["kind"],
                "actor": str(row["actor"]).split("#")[0],
                "excerpt": row["excerpt"][:240],
                "count": 0,
            },
        )
        bucket["count"] += 1
    for bucket in grouped.values():
        if bucket["count"] > 1:
            # Naming one actor for a group of observations would misattribute it.
            bucket["actor"] = ""
    return sorted(grouped.values(), key=lambda item: -item["count"])[:limit]


def build_context(
    store: Store,
    project: str,
    task: str,
    limit: int = 25,
    half_life_days: float = 180.0,
    action_limit: int = 10,
) -> dict:
    """Assemble the context a specific decision needs — not the whole graph.

    Context is a generated artifact. Two different questions against the same
    graph should produce two different packs.
    """
    limit = max(1, min(200, limit))
    terms = question_terms(task)

    scored_entities = []
    for group in store.state(project, half_life_days=half_life_days):
        claim_scores = []
        for claim in group["claims"]:
            claim_score = term_overlap(terms, claim["attribute"], claim["value"])
            claim_scores.append((claim_score, claim))
        entity_score = term_overlap(terms, group["entity"], group["kind"])
        best_claim = max((score for score, _ in claim_scores), default=0.0)
        relevance = max(entity_score, best_claim)
        if group["kind"] in ALWAYS_RELEVANT_KINDS:
            relevance = max(relevance, 0.34)
        if relevance <= 0.0:
            continue
        claims = []
        for claim_score, claim in sorted(claim_scores, key=lambda pair: -pair[0]):
            evidence = store.evidence_for(claim["claim_id"])
            claims.append(
                {
                    **claim,
                    "relevance": claim_score,
                    "evidence": citations(evidence),
                    "evidence_total": len(evidence),
                }
            )
        scored_entities.append(
            {
                "entity_id": group["entity_id"],
                "entity": group["entity"],
                "kind": group["kind"],
                "relevance": relevance,
                "claims": claims,
            }
        )

    scored_entities.sort(key=lambda item: (-item["relevance"], item["entity"]))
    selected = scored_entities[:limit]
    in_scope = {item["entity_id"] for item in selected}

    contradictions = [
        row
        for row in store.contradictions(project, "open", half_life_days)
        if not in_scope or row["entity_id"] in in_scope or term_overlap(terms, row["note"]) > 0
    ]
    unknowns = [
        row
        for row in store.unknowns(project, "open")
        if term_overlap(terms, row["question"], row["blocks_decision"]) > 0 or row["impact"] >= 0.6
    ] or store.unknowns(project, "open")[:5]

    transitions = [
        row
        for row in store.transitions(project, limit=200)
        if not in_scope or row["entity_id"] in in_scope
    ][:limit]

    actions = store.actions(project, status="proposed", limit=action_limit)
    metric = store.uncertainty(project, half_life_days)

    return {
        "task": task,
        "project": project,
        "entities": selected,
        "contradictions": contradictions,
        "unknowns": unknowns,
        "recent_transitions": transitions,
        "next_actions": actions,
        "uncertainty": metric,
        "coverage": {
            "entities_matched": len(selected),
            "entities_total": len(scored_entities),
            "claims_included": sum(len(item["claims"]) for item in selected),
        },
    }


def render_markdown(pack: dict) -> str:
    lines: list[str] = [
        "# Decision Context",
        "",
        f"**Task:** {pack['task']}",
        f"**Project:** {pack['project']}",
        "",
        "## Current reality model",
    ]
    if not pack["entities"]:
        lines.append("")
        lines.append("_No state matches this task yet. Ingest observations first._")
    for item in pack["entities"]:
        lines.extend(["", f"### {item['entity']} ({item['kind']})"])
        for claim in item["claims"]:
            stale = " · ageing" if claim["staleness_factor"] < 0.8 else ""
            lines.append(
                f"- **{claim['attribute']}** = {claim['value']} "
                f"— confidence {claim['effective_confidence']:.2f} "
                f"({claim['evidence_total']} evidence{stale})"
            )
            for evidence in claim["evidence"]:
                repeats = f" ×{evidence['count']}" if evidence["count"] > 1 else ""
                actor = f" {evidence['actor']}" if evidence["actor"] else ""
                lines.append(
                    f"    - `{evidence['source']}` [{evidence['kind']}{repeats}]"
                    f"{actor} {evidence['excerpt']}"
                )

    lines.extend(["", "## What changed"])
    if pack["recent_transitions"]:
        for transition in pack["recent_transitions"]:
            arrow = (
                f"{transition['from_value']} → {transition['to_value']}"
                if transition["from_value"]
                else transition["to_value"]
            )
            lines.append(
                f"- `{transition['occurred_at']}` **{transition['transition_type']}** "
                f"{transition.get('entity_name') or transition['entity_id']}."
                f"{transition['attribute']}: {arrow}"
            )
            lines.append(f"    - why: {transition['rationale']}")
    else:
        lines.append("")
        lines.append("_No recorded state changes in scope._")

    lines.extend(["", "## Contradictions in scope"])
    if pack["contradictions"]:
        for row in pack["contradictions"]:
            lines.append(
                f"- `{row['contradiction_id']}` {row.get('entity_name') or row['entity_id']}"
                f".{row['attribute']}: {row['note']} (severity {row['severity']:.2f})"
            )
    else:
        lines.append("")
        lines.append("_None open._")

    lines.extend(["", "## Open unknowns"])
    if pack["unknowns"]:
        for row in pack["unknowns"]:
            blocks = f" — blocks: {row['blocks_decision']}" if row["blocks_decision"] else ""
            lines.append(f"- `{row['unknown_id']}` {row['question']} (impact {row['impact']:.2f}){blocks}")
    else:
        lines.append("")
        lines.append("_None open._")

    lines.extend(["", "## Next highest-value actions"])
    if pack["next_actions"]:
        for index, action in enumerate(pack["next_actions"], 1):
            lines.append(
                f"{index}. **{action['title']}** — priority {action['priority']:.3f}, "
                f"+{action['expected_confidence_gain']:.2f} confidence, "
                f"~{action['effort_days']:g}d (`{action['action_id']}`)"
            )
            lines.append(f"    - {action['rationale']}")
    else:
        lines.append("")
        lines.append("_Run `lce actions --refresh` to generate them._")

    metric = pack["uncertainty"]
    lines.extend(
        [
            "",
            "## Uncertainty",
            "",
            f"- total: **{metric['uncertainty']:.2f}** "
            f"(unknowns {metric['unknown_load']:.2f}, claims {metric['claim_load']:.2f}, "
            f"contradictions {metric['contradiction_load']:.2f})",
            f"- active claims: {metric['claims_active']}, mean confidence {metric['mean_confidence']:.2f}",
            f"- open unknowns: {metric['unknowns_open']}, open contradictions: {metric['contradictions_open']}",
            "",
            "## Boundary",
            "",
            "- Every claim above is derived from ingested evidence and can be traced to its source.",
            "- Confidence is computed from evidence weight, source independence, and age. "
            "It is not a probability of truth.",
            "- Absence from this pack is not evidence of absence in the world.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_context(pack: dict, output: Path) -> dict:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(pack), encoding="utf-8")
    json_path = output.with_suffix(".json")
    json_path.write_text(json.dumps(pack, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "markdown": str(output),
        "json": str(json_path),
        "entities": len(pack["entities"]),
        "claims": pack["coverage"]["claims_included"],
        "actions": len(pack["next_actions"]),
    }


def explain_claim(
    store: Store, project: str, claim_ref: str, half_life_days: float = 180.0
) -> dict:
    """Walk one belief back to its sources and forward to what would change it.

    The question a user actually asks of a knowledge system is not "what do we
    know" but "why do you say that".
    """
    claim = store.get_claim(claim_ref)
    if claim is None:
        for group in store.state(project, half_life_days=half_life_days):
            for candidate in group["claims"]:
                if candidate["claim_id"].startswith(claim_ref):
                    claim = store.get_claim(candidate["claim_id"])
                    break
            if claim:
                break
    if claim is None:
        raise ValueError(f"unknown claim: {claim_ref}")

    entity = store.conn.execute(
        "SELECT name, kind FROM entities WHERE entity_id=?", (claim["entity_id"],)
    ).fetchone()
    evidence = store.evidence_for(claim["claim_id"])
    decay = staleness_factor(claim["last_seen_at"], half_life_days)
    kinds: dict[str, int] = {}
    actors: set[str] = set()
    for row in evidence:
        kinds[row["kind"]] = kinds.get(row["kind"], 0) + 1
        actors.add(str(row["actor"]).split("#")[0])

    strongest = max(kinds, key=lambda key: KIND_CEILINGS.get(key, 0.0)) if kinds else ""
    ceiling = KIND_CEILINGS.get(strongest, 0.0)
    at_ceiling = bool(ceiling) and claim["confidence"] >= ceiling - 0.01

    history = [
        row
        for row in store.transitions(project, limit=500)
        if row["claim_id"] == claim["claim_id"]
        or row["superseded_claim_id"] == claim["claim_id"]
    ]
    conflicts = [
        row
        for row in store.contradictions(project, None, half_life_days)
        if claim["claim_id"] in (row["claim_a"], row["claim_b"])
    ]

    if at_ceiling:
        to_move = (
            f"nothing of the same kind will help — {strongest} evidence caps at "
            f"{ceiling:.2f}. Only stronger evidence (a measurement, transaction, or "
            f"experiment) can raise this."
        )
    elif len(actors) <= 1:
        to_move = "a second independent source; repeats from the same one add little"
    else:
        to_move = "more independent sources, or one stronger method"

    return {
        "claim_id": claim["claim_id"],
        "entity": entity["name"] if entity else claim["entity_id"],
        "entity_kind": entity["kind"] if entity else "",
        "attribute": claim["attribute"],
        "value": claim["value"],
        "status": claim["status"],
        "confidence": claim["confidence"],
        "effective_confidence": round(claim["confidence"] * decay, 4),
        "staleness_factor": decay,
        "importance": claim["importance"],
        "first_seen_at": claim["first_seen_at"],
        "last_seen_at": claim["last_seen_at"],
        "evidence_kinds": kinds,
        "independent_sources": len(actors),
        "method_ceiling": {"kind": strongest, "ceiling": ceiling, "at_ceiling": at_ceiling},
        "citations": citations(evidence, limit=12),
        "history": history,
        "contradictions": conflicts,
        "serves_decisions": store.decisions_for_target(project, claim["claim_id"]),
        "what_would_move_it": to_move,
    }


def render_explanation(report: dict) -> str:
    lines = [
        f"{report['entity']}.{report['attribute']} = {report['value']}",
        "",
        f"  confidence      {report['effective_confidence']:.2f} "
        f"(stored {report['confidence']:.2f} × age {report['staleness_factor']:.2f})",
        f"  importance      {report['importance']:.2f}",
        f"  evidence        {sum(report['evidence_kinds'].values())} rows, "
        f"{report['independent_sources']} independent source(s): "
        + ", ".join(f"{count}×{kind}" for kind, count in sorted(report["evidence_kinds"].items())),
    ]
    ceiling = report["method_ceiling"]
    if ceiling["kind"]:
        marker = " — AT CEILING" if ceiling["at_ceiling"] else ""
        lines.append(
            f"  method ceiling  {ceiling['ceiling']:.2f} ({ceiling['kind']}){marker}"
        )
    lines.extend(["", "  cited:"])
    for item in report["citations"]:
        repeats = f" ×{item['count']}" if item["count"] > 1 else ""
        lines.append(f"    - [{item['kind']}{repeats}] {item['source']} — {item['excerpt'][:140]}")
    if report["history"]:
        lines.extend(["", "  how it got here:"])
        for row in report["history"]:
            lines.append(f"    - [{row['transition_type']}] {row['rationale']}")
    if report["contradictions"]:
        lines.extend(["", "  disputed by:"])
        for row in report["contradictions"]:
            lines.append(f"    - [{row['status']}] {row['note']}")
    if report["serves_decisions"]:
        lines.extend(["", "  serves decisions:"])
        for row in report["serves_decisions"]:
            lines.append(f"    - {row['question']} ({row['status']})")
    lines.extend(["", f"  to move it: {report['what_would_move_it']}"])
    return "\n".join(lines) + "\n"
