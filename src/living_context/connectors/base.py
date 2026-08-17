from __future__ import annotations

from dataclasses import dataclass, field

from living_context.observe import SOURCE_KINDS
from living_context.models import normalize, now_iso


@dataclass
class ConnectorResult:
    """Every connector returns the same thing: packets, a cursor, and notes.

    One shape means a user can write their own in an afternoon, and the engine
    never grows per-source special cases.
    """

    packets: list[dict] = field(default_factory=list)
    cursor: str = ""
    notes: list[str] = field(default_factory=list)


class ConnectorError(RuntimeError):
    """Configuration or transport problem the operator can fix."""


def require(config: dict, *keys: str) -> None:
    missing = [key for key in keys if not str(config.get(key) or "").strip()]
    if missing:
        raise ConnectorError(f"missing required config: {', '.join(missing)}")


def source_kind(config: dict, default: str) -> str:
    kind = normalize(str(config.get("kind") or default))
    if kind not in SOURCE_KINDS:
        raise ConnectorError(
            f"unsupported source kind '{kind}'. Use one of: {', '.join(sorted(SOURCE_KINDS))}"
        )
    return kind


def packet(
    ref: str,
    kind: str,
    actor: str = "",
    observed_at: str = "",
    entities: list[dict] | None = None,
    claims: list[dict] | None = None,
    unknowns: list[dict] | None = None,
    relationships: list[dict] | None = None,
) -> dict:
    return {
        "source": {
            "ref": ref,
            "kind": kind,
            "actor": actor,
            "observed_at": observed_at or now_iso(),
        },
        "entities": entities or [],
        "claims": claims or [],
        "relationships": relationships or [],
        "unknowns": unknowns or [],
    }


def claim(
    entity: str,
    attribute: str,
    value: str,
    excerpt: str,
    kind: str,
    actor: str,
    locator: str,
    importance: float = 0.6,
) -> dict:
    return {
        "entity": entity,
        "attribute": attribute,
        "value": value,
        "importance": importance,
        "evidence": [
            {"excerpt": excerpt[:2000], "kind": kind, "actor": actor, "locator": locator}
        ],
    }
