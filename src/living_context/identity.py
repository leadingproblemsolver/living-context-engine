from __future__ import annotations

import difflib

from living_context.models import Proposal, normalize
from living_context.store import Store

# Two names this similar are almost always the same thing wearing two spellings.
NAME_THRESHOLD = 0.82
# Attribute drift is judged mostly by structure, not spelling: two attributes
# that share a word and are used on the same entity are probably one slot.
ATTRIBUTE_THRESHOLD = 0.70

# Words that carry no identity. "Acme Inc" and "Acme" are one company.
NOISE_TOKENS = {
    "inc", "inc.", "llc", "ltd", "ltd.", "corp", "corp.", "corporation", "co",
    "company", "gmbh", "sa", "plc", "the", "team", "group", "holdings",
}


def _tokens(name: str) -> set[str]:
    return {token for token in normalize(name).split() if token not in NOISE_TOKENS}


def similarity(left: str, right: str) -> float:
    """Blend of token overlap and character similarity, both stdlib-only."""
    left_tokens, right_tokens = _tokens(left), _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    jaccard = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    ratio = difflib.SequenceMatcher(
        None, " ".join(sorted(left_tokens)), " ".join(sorted(right_tokens))
    ).ratio()
    # One containing the other ("Acme" vs "Acme Fabrication") is a strong signal
    # that token overlap alone understates.
    containment = 1.0 if left_tokens <= right_tokens or right_tokens <= left_tokens else 0.0
    return round(max(0.6 * jaccard + 0.4 * ratio, containment * 0.9), 4)


def duplicate_entities(store: Store, project: str, threshold: float = NAME_THRESHOLD) -> list[dict]:
    """Candidate merges, strongest first. Never applied without a human."""
    entities = store.entities(project)
    candidates = []
    for index, left in enumerate(entities):
        for right in entities[index + 1 :]:
            if left["kind"] != right["kind"]:
                continue
            score = similarity(left["name"], right["name"])
            if score < threshold:
                continue
            # Keep whichever carries more evidence; that is the name the graph
            # already agrees on.
            left_claims = store.conn.execute(
                "SELECT COUNT(*) FROM claims WHERE entity_id=?", (left["entity_id"],)
            ).fetchone()[0]
            right_claims = store.conn.execute(
                "SELECT COUNT(*) FROM claims WHERE entity_id=?", (right["entity_id"],)
            ).fetchone()[0]
            keep, merge = (left, right) if left_claims >= right_claims else (right, left)
            candidates.append(
                {
                    "keep": keep["entity_id"],
                    "keep_name": keep["name"],
                    "merge": merge["entity_id"],
                    "merge_name": merge["name"],
                    "kind": keep["kind"],
                    "similarity": score,
                    "claims": {keep["name"]: max(left_claims, right_claims), merge["name"]: min(left_claims, right_claims)},
                }
            )
    return sorted(candidates, key=lambda item: -item["similarity"])


def attribute_similarity(left: str, right: str) -> float:
    """Sharing a word is the signal; spelling distance is only a tie-breaker."""
    left_tokens = {token for token in left.replace("_", " ").split() if token}
    right_tokens = {token for token in right.replace("_", " ").split() if token}
    shared = left_tokens & right_tokens
    ratio = difflib.SequenceMatcher(None, left, right).ratio()
    if not shared:
        return round(ratio, 4)
    overlap = len(shared) / min(len(left_tokens), len(right_tokens))
    return round(max(ratio, 0.5 + 0.5 * overlap), 4)


def duplicate_attributes(
    store: Store, project: str, threshold: float = ATTRIBUTE_THRESHOLD
) -> list[dict]:
    """Attribute drift is worse than entity drift: it hides changes.

    `primary_pain` and `main_pain` are the same slot, so a new value in one never
    contests the old value in the other — the delta silently disappears and the
    graph looks calmer than reality.
    """
    rows = [row for row in store.vocabulary(project) if not row["canonical"]]
    entities_by_attribute: dict[str, set[str]] = {}
    for raw in store.conn.execute(
        "SELECT DISTINCT attribute, entity_id FROM claims WHERE project=?", (project,)
    ):
        entities_by_attribute.setdefault(raw["attribute"], set()).add(raw["entity_id"])
    # The better-evidenced name survives, same rule as merging entities.
    evidence_by_attribute = {
        raw["attribute"]: raw["n"]
        for raw in store.conn.execute(
            """
            SELECT c.attribute, COUNT(e.evidence_id) n
            FROM claims c LEFT JOIN evidence e ON e.claim_id = c.claim_id
            WHERE c.project=? GROUP BY c.attribute
            """,
            (project,),
        )
    }

    def standing(row: dict) -> tuple[int, int]:
        return (evidence_by_attribute.get(row["attribute"], 0), row["uses"])

    candidates = []
    for index, left in enumerate(rows):
        for right in rows[index + 1 :]:
            # Two attributes only collide if something actually carries both.
            shared_entities = entities_by_attribute.get(
                left["attribute"], set()
            ) & entities_by_attribute.get(right["attribute"], set())
            if not shared_entities:
                continue
            score = attribute_similarity(left["attribute"], right["attribute"])
            if score < threshold:
                continue
            canonical, alias = (
                (left, right) if standing(left) >= standing(right) else (right, left)
            )
            candidates.append(
                {
                    "attribute": alias["attribute"],
                    "canonical": canonical["attribute"],
                    "similarity": score,
                    "shared_entities": len(shared_entities),
                    "evidence": {
                        canonical["attribute"]: evidence_by_attribute.get(canonical["attribute"], 0),
                        alias["attribute"]: evidence_by_attribute.get(alias["attribute"], 0),
                    },
                    "uses": {canonical["attribute"]: canonical["uses"], alias["attribute"]: alias["uses"]},
                }
            )
    return sorted(candidates, key=lambda item: (-item["similarity"], -item["shared_entities"]))


def propose_identity_fixes(store: Store, project: str, origin: str = "parser") -> dict:
    """Stage merge and alias proposals. Identity is never changed silently."""
    staged = {"entity_merge": 0, "attribute_alias": 0, "duplicates": 0}

    for candidate in duplicate_entities(store, project):
        proposal = Proposal.build(
            project,
            "entity_merge",
            origin,
            {
                "keep": candidate["keep"],
                "merge": candidate["merge"],
                "reason": f"name similarity {candidate['similarity']:.2f}",
            },
            "identity-resolution",
            f"merge \"{candidate['merge_name']}\" into \"{candidate['keep_name']}\" "
            f"({candidate['kind']}, similarity {candidate['similarity']:.2f})",
        )
        if store.add_proposal(proposal):
            staged["entity_merge"] += 1
        else:
            staged["duplicates"] += 1

    for candidate in duplicate_attributes(store, project):
        proposal = Proposal.build(
            project,
            "attribute_alias",
            origin,
            {"attribute": candidate["attribute"], "canonical": candidate["canonical"]},
            "identity-resolution",
            f"fold attribute `{candidate['attribute']}` into `{candidate['canonical']}` "
            f"— both used on {candidate['shared_entities']} shared entity/entities, "
            f"similarity {candidate['similarity']:.2f}. Reject if they are genuinely "
            f"different slots.",
        )
        if store.add_proposal(proposal):
            staged["attribute_alias"] += 1
        else:
            staged["duplicates"] += 1

    return staged
