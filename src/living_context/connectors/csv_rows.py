from __future__ import annotations

import csv
from pathlib import Path

from living_context.connectors.base import (
    ConnectorError,
    ConnectorResult,
    claim,
    packet,
    require,
    source_kind,
)

MAX_ROWS = 20_000


class CsvConnector:
    """Spreadsheet exports — the format real research actually arrives in.

    Survey tools, CRMs, and interview trackers all export a table. One row
    becomes one observation, one mapped column becomes one claim.
    """

    name = "csv"
    description = "Map a CSV/TSV export (survey, CRM, interview tracker) into claims"
    required_config = ("path", "entity_column")
    example = {
        "path": "research/q3-survey.csv",
        "entity_column": "company",
        "entity_kind": "company",
        "actor_column": "respondent",
        "date_column": "responded_at",
        "kind": "interview",
        "claims": {"primary_pain": "biggest_problem", "buyer": "who_signs"},
        "unknown_columns": ["what_we_still_dont_know"],
        "excerpt_column": "verbatim",
        "importance": 0.7,
        "roll_up": {
            "entity": "Manufacturing Ops Managers",
            "kind": "segment",
            "attributes": ["primary_pain", "buyer"],
        },
    }

    def fetch(self, config: dict, cursor: str, root: Path | None = None) -> ConnectorResult:
        require(config, *self.required_config)
        kind = source_kind(config, "interview")
        path = Path(config["path"])
        if root and not path.is_absolute():
            path = root / path
        if path.is_symlink():
            raise ConnectorError("symlink sources are not accepted")
        if not path.is_file():
            raise ConnectorError(f"no such file: {path}")

        roll_up = config.get("roll_up") or {}
        if roll_up and not str(roll_up.get("entity") or "").strip():
            raise ConnectorError("config.roll_up needs an `entity` name")
        mapping = config.get("claims") or {}
        if not isinstance(mapping, dict) or not mapping:
            raise ConnectorError(
                "config.claims must map attribute -> column, e.g. "
                '{"primary_pain": "biggest_problem"}'
            )
        unknown_columns = [str(item) for item in (config.get("unknown_columns") or [])]
        importance = float(config.get("importance", 0.6))
        entity_kind = str(config.get("entity_kind") or "company")
        delimiter = "\t" if path.suffix.lower() in {".tsv", ".tab"} else ","

        packets: list[dict] = []
        notes: list[str] = []
        newest = cursor
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if not reader.fieldnames:
                raise ConnectorError(f"{path} has no header row")
            unmapped = [
                column
                for column in list(mapping.values()) + unknown_columns
                if column not in reader.fieldnames
            ]
            if unmapped:
                raise ConnectorError(
                    f"columns not in {path.name}: {', '.join(unmapped)}. "
                    f"Available: {', '.join(reader.fieldnames)}"
                )
            if config["entity_column"] not in reader.fieldnames:
                raise ConnectorError(
                    f"entity_column '{config['entity_column']}' not in {path.name}"
                )

            for number, row in enumerate(reader, start=2):
                if number - 1 > MAX_ROWS:
                    notes.append(f"stopped at {MAX_ROWS} rows")
                    break
                entity = (row.get(config["entity_column"]) or "").strip()
                if not entity:
                    continue
                observed_at = (row.get(str(config.get("date_column") or "")) or "").strip()
                # Rows already seen on a previous run are skipped by date, when the
                # export carries one. Without a date column every run restages,
                # which is harmless because evidence is idempotent.
                if cursor and observed_at and observed_at <= cursor:
                    continue
                actor = (row.get(str(config.get("actor_column") or "")) or "").strip()
                excerpt_base = (
                    row.get(str(config.get("excerpt_column") or "")) or ""
                ).strip()
                locator = f"row {number}"

                claims = []
                entities = [{"name": entity, "kind": entity_kind, "aliases": []}]
                rolled = [
                    str(item)
                    for item in (roll_up.get("attributes") or list(mapping))
                ]
                for attribute, column in mapping.items():
                    value = (row.get(column) or "").strip()
                    if not value:
                        continue
                    respondent = actor or f"{path.name}:{locator}"
                    claims.append(
                        claim(
                            entity=entity,
                            attribute=str(attribute),
                            value=value,
                            excerpt=excerpt_base or f"{column}: {value}",
                            kind=kind,
                            actor=respondent,
                            locator=locator,
                            importance=importance,
                        )
                    )
                    # One row is one respondent. Rolling the same answer up to the
                    # population is what turns a table of facts into a belief: each
                    # row becomes independent evidence for the segment-level claim,
                    # while the per-row claim stays attributable to its company.
                    if roll_up and str(attribute) in rolled:
                        claims.append(
                            claim(
                                entity=str(roll_up["entity"]),
                                attribute=str(attribute),
                                value=value,
                                excerpt=excerpt_base or f"{entity} — {column}: {value}",
                                kind=kind,
                                actor=respondent,
                                locator=f"{locator} ({entity})",
                                importance=max(importance, float(roll_up.get("importance", importance))),
                            )
                        )
                if roll_up:
                    entities.append(
                        {
                            "name": str(roll_up["entity"]),
                            "kind": str(roll_up.get("kind") or "segment"),
                            "aliases": [],
                        }
                    )
                unknowns = [
                    {"question": (row.get(column) or "").strip(), "impact": 0.6, "blocks_decision": ""}
                    for column in unknown_columns
                    if (row.get(column) or "").strip()
                ]
                if not (claims or unknowns):
                    continue
                packets.append(
                    packet(
                        ref=f"{path.name}#{locator}",
                        kind=kind,
                        actor=actor,
                        observed_at=observed_at,
                        entities=entities,
                        claims=claims,
                        unknowns=unknowns,
                    )
                )
                if observed_at > newest:
                    newest = observed_at

        return ConnectorResult(packets=packets, cursor=newest, notes=notes)
