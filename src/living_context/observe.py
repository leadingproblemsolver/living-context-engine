from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from living_context.models import (
    ENTITY_KINDS,
    EVIDENCE_WEIGHTS,
    normalize,
    now_iso,
)

SOURCE_KINDS = set(EVIDENCE_WEIGHTS) | {"note"}
MAX_PACKET_BYTES = 20 * 1024 * 1024
MAX_CLAIMS_PER_PACKET = 2_000
MAX_REPEAT_EVIDENCE = 200

# ---------------------------------------------------------------------------
# The observation packet is the interop contract. Anything that can produce this
# shape — the line parser below, a model, a script, another tool — can drive the
# engine. It is deliberately small enough to write by hand.
# ---------------------------------------------------------------------------

OBSERVATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["source", "entities", "claims", "unknowns", "relationships"],
    "properties": {
        "source": {
            "type": "object",
            "additionalProperties": False,
            "required": ["ref", "kind", "actor", "observed_at"],
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "Where this came from: file path, URL, meeting id, ticket id.",
                },
                "kind": {
                    "type": "string",
                    "enum": sorted(SOURCE_KINDS),
                    "description": (
                        "How the information was obtained. 'assertion' is someone stating a "
                        "belief; 'interview' is a first-hand account; 'transaction' or "
                        "'experiment' is observed behaviour. Choose the weakest kind that "
                        "honestly describes the source."
                    ),
                },
                "actor": {
                    "type": "string",
                    "description": "Who asserted it. Empty string if genuinely unknown.",
                },
                "observed_at": {
                    "type": "string",
                    "description": "ISO-8601 date or datetime of the observation.",
                },
            },
        },
        "entities": {
            "type": "array",
            "description": "Things the claims are about. Reuse exact names across packets.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "kind", "aliases"],
                "properties": {
                    "name": {"type": "string"},
                    "kind": {"type": "string", "enum": sorted(ENTITY_KINDS)},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "claims": {
            "type": "array",
            "description": (
                "One belief about one attribute of one entity. Never restate the document; "
                "state what is now believed to be true and what supports it."
            ),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["entity", "attribute", "value", "importance", "evidence"],
                "properties": {
                    "entity": {"type": "string", "description": "Entity name, matching `entities`."},
                    "attribute": {
                        "type": "string",
                        "description": "Stable snake_case slot, e.g. primary_pain, buyer, blocker, price_point.",
                    },
                    "value": {"type": "string", "description": "The believed value, stated plainly."},
                    "importance": {
                        "type": "number",
                        "description": "0 to 1. How much this claim matters to the current decision.",
                    },
                    "evidence": {
                        "type": "array",
                        "description": "Verbatim support. A claim with no evidence is not a claim.",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["excerpt", "kind", "actor", "locator"],
                            "properties": {
                                "excerpt": {
                                    "type": "string",
                                    "description": "Quoted or closely paraphrased source text.",
                                },
                                "kind": {"type": "string", "enum": sorted(SOURCE_KINDS)},
                                "actor": {"type": "string"},
                                "locator": {
                                    "type": "string",
                                    "description": "Line number, timestamp, section, or page.",
                                },
                            },
                        },
                    },
                },
            },
        },
        "relationships": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["from", "to", "relation"],
                "properties": {
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "relation": {
                        "type": "string",
                        "description": "snake_case, e.g. blocks, buys_from, competes_with, causes.",
                    },
                },
            },
        },
        "unknowns": {
            "type": "array",
            "description": "Questions this source raised or failed to answer.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["question", "impact", "blocks_decision"],
                "properties": {
                    "question": {"type": "string"},
                    "impact": {
                        "type": "number",
                        "description": "0 to 1. How much a wrong answer would cost.",
                    },
                    "blocks_decision": {
                        "type": "string",
                        "description": "The decision that cannot be made until this is answered.",
                    },
                },
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Line syntax
# ---------------------------------------------------------------------------

DIRECTIVE = re.compile(r"^\s*@(?P<key>[a-zA-Z_]+)\s+(?P<value>.+?)\s*$")
MODIFIERS = re.compile(r"\[(?P<body>[^\[\]]*)\]\s*$")
CLAIM_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?claim\s*:\s*(?P<body>.+)$", re.IGNORECASE
)
UNKNOWN_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:unknown|open question|question)\s*:\s*(?P<body>.+)$",
    re.IGNORECASE,
)
DECISION_LINE = re.compile(r"^\s*(?:[-*]\s*)?decision\s*:\s*(?P<body>.+)$", re.IGNORECASE)
RISK_LINE = re.compile(r"^\s*(?:[-*]\s*)?risk\s*:\s*(?P<body>.+)$", re.IGNORECASE)
BLOCKER_LINE = re.compile(r"^\s*(?:[-*]\s*)?blocker\s*:\s*(?P<body>.+)$", re.IGNORECASE)
RELATION_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?relation\s*:\s*(?P<from>.+?)\s*-\[(?P<relation>[^\]]+)\]->\s*(?P<to>.+)$",
    re.IGNORECASE,
)
# `claim: Segment "Ops Managers" / primary_pain = compliance risk`
CLAIM_BODY = re.compile(
    r"^(?:(?P<entity>[^/=]+?)\s*/\s*)?(?P<attribute>[^/=]+?)\s*=\s*(?P<value>.+)$"
)
ENTITY_PREFIX = re.compile(r"^(?P<kind>[a-zA-Z_]+)\s+(?P<name>.+)$")


def _parse_modifiers(text: str) -> tuple[str, dict[str, str]]:
    """Strip and parse a trailing `[key=value, key=value]` group."""
    match = MODIFIERS.search(text)
    if not match:
        return text.strip(), {}
    modifiers: dict[str, str] = {}
    for chunk in match.group("body").split(","):
        if "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        key = normalize(key).replace(" ", "_")
        if key:
            modifiers[key] = value.strip()
    return text[: match.start()].strip(), modifiers


def _as_float(value: str | None, default: float) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def _split_entity(raw: str, default_kind: str = "other") -> tuple[str, str]:
    """`segment Manufacturing Ops` -> (segment, Manufacturing Ops)."""
    raw = raw.strip().strip('"')
    match = ENTITY_PREFIX.match(raw)
    if match and normalize(match.group("kind")) in ENTITY_KINDS:
        return normalize(match.group("kind")), match.group("name").strip().strip('"')
    return default_kind, raw


def _evidence_rows(
    excerpt: str,
    kind: str,
    actor: str,
    locator: str,
    repeats: int,
    independent: bool,
) -> list[dict]:
    """Expand `[n=14]` into the evidence rows it claims to stand for."""
    repeats = max(1, min(MAX_REPEAT_EVIDENCE, repeats))
    if repeats == 1:
        return [{"excerpt": excerpt, "kind": kind, "actor": actor, "locator": locator}]
    base = actor.strip()
    rows = []
    for index in range(repeats):
        if not independent:
            # One source repeated is not corroboration; keep the actor identical
            # so the correlation damping applies.
            label = base
        elif base:
            label = f"{base}#{index + 1}"
        else:
            label = f"respondent {index + 1}"
        rows.append(
            {
                "excerpt": excerpt,
                "kind": kind,
                "actor": label,
                "locator": f"{locator}#{index + 1}",
            }
        )
    return rows


def packet_from_text(
    text: str,
    source_ref: str,
    source_kind: str = "document",
    actor: str = "",
    observed_at: str | None = None,
) -> dict:
    """Parse the line syntax into an observation packet.

    Lines that do not match the syntax are ignored here — they are still stored
    by the observation extractor as searchable records. Only explicit statements
    become state.
    """
    source = {
        "ref": source_ref,
        "kind": source_kind if source_kind in SOURCE_KINDS else "document",
        "actor": actor,
        "observed_at": observed_at or now_iso(),
    }
    entities: dict[str, dict] = {}
    claims: list[dict] = []
    unknowns: list[dict] = []
    relationships: list[dict] = []
    default_entity: tuple[str, str] | None = None
    default_importance = 0.5
    in_fence = False

    def register(kind: str, name: str, aliases: list[str] | None = None) -> str:
        key = normalize(name)
        if not key:
            return ""
        existing = entities.get(key)
        if existing is None:
            entities[key] = {"name": name.strip(), "kind": kind, "aliases": aliases or []}
        elif aliases:
            existing["aliases"] = sorted(set(existing["aliases"]) | set(aliases))
        return name.strip()

    for number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.rstrip()
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        # A fenced block is documentation showing the syntax, not an assertion
        # made in it. Never let a README teach the graph something.
        if in_fence or not line.strip():
            continue

        directive = DIRECTIVE.match(line)
        if directive:
            key = normalize(directive.group("key"))
            value = directive.group("value").strip()
            if key == "source":
                source["ref"] = value
            elif key == "actor":
                source["actor"] = value
            elif key in {"date", "observed_at"}:
                source["observed_at"] = value
            elif key == "kind" and normalize(value) in SOURCE_KINDS:
                source["kind"] = normalize(value)
            elif key == "entity":
                entity_kind, entity_name = _split_entity(value)
                register(entity_kind, entity_name)
                default_entity = (entity_kind, entity_name)
            elif key == "importance":
                default_importance = _as_float(value, default_importance)
            continue

        body, modifiers = _parse_modifiers(line)
        line_kind = normalize(modifiers.get("kind", "")) or source["kind"]
        if line_kind not in SOURCE_KINDS:
            line_kind = source["kind"]
        line_actor = modifiers.get("actor", source["actor"])
        repeats = 1
        if modifiers.get("n", "").strip().isdigit():
            repeats = int(modifiers["n"].strip())
        independent = normalize(modifiers.get("independent", "true")) not in {"false", "no", "0"}
        locator = f"line {number}"

        relation_match = RELATION_LINE.match(body)
        if relation_match:
            from_kind, from_name = _split_entity(relation_match.group("from"))
            to_kind, to_name = _split_entity(relation_match.group("to"))
            register(from_kind, from_name)
            register(to_kind, to_name)
            relationships.append(
                {
                    "from": from_name,
                    "to": to_name,
                    "relation": normalize(relation_match.group("relation")).replace(" ", "_"),
                }
            )
            continue

        claim_match = CLAIM_LINE.match(body)
        if claim_match:
            parsed = CLAIM_BODY.match(claim_match.group("body").strip())
            if not parsed:
                continue
            if parsed.group("entity"):
                entity_kind, entity_name = _split_entity(parsed.group("entity"))
            elif default_entity:
                entity_kind, entity_name = default_entity
            else:
                continue
            register(entity_kind, entity_name)
            claims.append(
                {
                    "entity": entity_name,
                    "attribute": parsed.group("attribute").strip(),
                    "value": parsed.group("value").strip(),
                    "importance": _as_float(modifiers.get("importance"), default_importance),
                    "evidence": _evidence_rows(
                        raw_line.strip(), line_kind, line_actor, locator, repeats, independent
                    ),
                }
            )
            continue

        unknown_match = UNKNOWN_LINE.match(body)
        if unknown_match:
            unknowns.append(
                {
                    "question": unknown_match.group("body").strip(),
                    "impact": _as_float(modifiers.get("impact"), 0.5),
                    "blocks_decision": modifiers.get("blocks", ""),
                }
            )
            continue

        for pattern, entity_kind, attribute, default_value in (
            (DECISION_LINE, "decision", "status", "decided"),
            (RISK_LINE, "risk", "status", "open"),
            (BLOCKER_LINE, "constraint", "status", "blocking"),
        ):
            match = pattern.match(body)
            if not match:
                continue
            name = match.group("body").strip()
            register(entity_kind, name)
            claims.append(
                {
                    "entity": name,
                    "attribute": attribute,
                    "value": modifiers.get("status", default_value),
                    "importance": _as_float(modifiers.get("importance"), default_importance),
                    "evidence": _evidence_rows(
                        raw_line.strip(), line_kind, line_actor, locator, repeats, independent
                    ),
                }
            )
            break

    return {
        "source": source,
        "entities": [
            {"name": item["name"], "kind": item["kind"], "aliases": item["aliases"]}
            for item in entities.values()
        ],
        "claims": claims,
        "relationships": relationships,
        "unknowns": unknowns,
    }


# ---------------------------------------------------------------------------
# Packet validation and normalisation
# ---------------------------------------------------------------------------


def validate_packet(packet: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(packet, dict):
        return ["packet must be a JSON object"]
    source = packet.get("source")
    if not isinstance(source, dict):
        errors.append("packet.source must be an object")
    elif not str(source.get("ref") or "").strip():
        errors.append("packet.source.ref is required")
    for key in ("entities", "claims", "relationships", "unknowns"):
        value = packet.get(key, [])
        if value is not None and not isinstance(value, list):
            errors.append(f"packet.{key} must be an array")
    claims = packet.get("claims") or []
    if isinstance(claims, list):
        if len(claims) > MAX_CLAIMS_PER_PACKET:
            errors.append(f"packet.claims exceeds {MAX_CLAIMS_PER_PACKET} entries")
        for index, claim in enumerate(claims):
            if not isinstance(claim, dict):
                errors.append(f"packet.claims[{index}] must be an object")
                continue
            for required in ("entity", "attribute", "value"):
                if not str(claim.get(required) or "").strip():
                    errors.append(f"packet.claims[{index}].{required} is required")
            evidence = claim.get("evidence") or []
            if not isinstance(evidence, list):
                errors.append(f"packet.claims[{index}].evidence must be an array")
            elif not evidence:
                # Invariant 2: no floating beliefs.
                errors.append(
                    f"packet.claims[{index}] has no evidence; every claim needs provenance"
                )
    return errors


def normalize_packet(packet: dict, source_ref: str = "", observed_at: str | None = None) -> dict:
    """Fill defaults so hand-written and model-written packets behave the same."""
    source = dict(packet.get("source") or {})
    source.setdefault("ref", source_ref)
    source["ref"] = str(source.get("ref") or source_ref or "unknown")
    kind = normalize(str(source.get("kind") or ""))
    source["kind"] = kind if kind in SOURCE_KINDS else "document"
    source["actor"] = str(source.get("actor") or "")
    source["observed_at"] = str(source.get("observed_at") or observed_at or now_iso())

    entities = []
    for item in packet.get("entities") or []:
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            continue
        entity_kind = normalize(str(item.get("kind") or "other"))
        aliases = item.get("aliases") or []
        entities.append(
            {
                "name": str(item["name"]).strip(),
                "kind": entity_kind if entity_kind in ENTITY_KINDS else "other",
                "aliases": [str(alias) for alias in aliases if str(alias).strip()],
            }
        )
    known = {normalize(item["name"]): item["kind"] for item in entities}

    claims = []
    for item in packet.get("claims") or []:
        if not isinstance(item, dict):
            continue
        entity_name = str(item.get("entity") or "").strip()
        if not entity_name or not str(item.get("attribute") or "").strip():
            continue
        if not str(item.get("value") or "").strip():
            continue
        if normalize(entity_name) not in known:
            entities.append({"name": entity_name, "kind": "other", "aliases": []})
            known[normalize(entity_name)] = "other"
        evidence = []
        for row in item.get("evidence") or []:
            if not isinstance(row, dict):
                continue
            row_kind = normalize(str(row.get("kind") or source["kind"]))
            evidence.append(
                {
                    "excerpt": str(row.get("excerpt") or "").strip(),
                    "kind": row_kind if row_kind in SOURCE_KINDS else source["kind"],
                    "actor": str(row.get("actor") or source["actor"]),
                    "locator": str(row.get("locator") or ""),
                }
            )
        claims.append(
            {
                "entity": entity_name,
                "attribute": str(item["attribute"]).strip(),
                "value": str(item["value"]).strip(),
                "importance": _as_float(item.get("importance"), 0.5),
                "evidence": evidence,
            }
        )

    relationships = []
    for item in packet.get("relationships") or []:
        if not isinstance(item, dict):
            continue
        from_name = str(item.get("from") or "").strip()
        to_name = str(item.get("to") or "").strip()
        relation = normalize(str(item.get("relation") or "")).replace(" ", "_")
        if not (from_name and to_name and relation):
            continue
        for name in (from_name, to_name):
            if normalize(name) not in known:
                entities.append({"name": name, "kind": "other", "aliases": []})
                known[normalize(name)] = "other"
        relationships.append({"from": from_name, "to": to_name, "relation": relation})

    unknowns = []
    for item in packet.get("unknowns") or []:
        if isinstance(item, str):
            item = {"question": item}
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        unknowns.append(
            {
                "question": question,
                "impact": _as_float(item.get("impact"), 0.5),
                "blocks_decision": str(item.get("blocks_decision") or ""),
            }
        )

    return {
        "source": source,
        "entities": entities,
        "claims": claims,
        "relationships": relationships,
        "unknowns": unknowns,
    }


def content_hash(packet: dict) -> str:
    return hashlib.sha256(
        json.dumps(packet, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def load_packets(path: Path) -> list[dict]:
    """Read `.json` (single packet or array) or `.jsonl` (one packet per line)."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("symlink sources are not accepted")
    if not path.is_file():
        raise ValueError(f"not a file: {path}")
    if path.stat().st_size > MAX_PACKET_BYTES:
        raise ValueError(f"observation file exceeds 20 MB: {path}")
    text = path.read_text(encoding="utf-8")
    packets: list[dict] = []
    if path.suffix.lower() == ".jsonl":
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                packets.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{number} is not valid JSON: {error}") from error
        return packets
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{path} is not valid JSON: {error}") from error
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        return [parsed]
    raise ValueError(f"{path} must contain an object or an array of objects")
