from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from living_context.models import (
    Action,
    Claim,
    Contradiction,
    ContextRecord,
    Entity,
    Evidence,
    ObservationSource,
    Relationship,
    Transition,
    Unknown,
    now_iso,
    staleness_factor,
)

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS records(
    record_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_line INTEGER NOT NULL,
    source_hash TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    tags_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    ingested_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_records_project ON records(project);
CREATE INDEX IF NOT EXISTS idx_records_kind ON records(kind);
CREATE INDEX IF NOT EXISTS idx_records_observed ON records(observed_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_records_project_source_line
    ON records(project, source_path, source_line, kind, text);
CREATE TABLE IF NOT EXISTS sources(
    project TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    last_ingested_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(project, source_path)
);

CREATE TABLE IF NOT EXISTS observations(
    observation_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    actor TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_observations_project ON observations(project);

CREATE TABLE IF NOT EXISTS entities(
    entity_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    canonical_key TEXT NOT NULL,
    aliases_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_key
    ON entities(project, kind, canonical_key);
CREATE INDEX IF NOT EXISTS idx_entities_project ON entities(project);

CREATE TABLE IF NOT EXISTS claims(
    claim_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    attribute TEXT NOT NULL,
    value TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL,
    importance REAL NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    superseded_by TEXT,
    metadata_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_claims_slot ON claims(project, entity_id, attribute);
CREATE INDEX IF NOT EXISTS idx_claims_status ON claims(project, status);

CREATE TABLE IF NOT EXISTS evidence(
    evidence_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    actor TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    locator TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    weight REAL
);
CREATE INDEX IF NOT EXISTS idx_evidence_claim ON evidence(claim_id);

CREATE TABLE IF NOT EXISTS transitions(
    transition_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    attribute TEXT NOT NULL,
    transition_type TEXT NOT NULL,
    from_value TEXT,
    to_value TEXT NOT NULL,
    from_confidence REAL NOT NULL,
    to_confidence REAL NOT NULL,
    rationale TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    superseded_claim_id TEXT,
    evidence_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transitions_project ON transitions(project, occurred_at);

CREATE TABLE IF NOT EXISTS contradictions(
    contradiction_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    attribute TEXT NOT NULL,
    claim_a TEXT NOT NULL,
    claim_b TEXT NOT NULL,
    status TEXT NOT NULL,
    severity REAL NOT NULL,
    note TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    resolved_at TEXT,
    resolution TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_contradictions_project ON contradictions(project, status);

CREATE TABLE IF NOT EXISTS unknowns(
    unknown_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    question TEXT NOT NULL,
    entity_id TEXT,
    impact REAL NOT NULL,
    status TEXT NOT NULL,
    blocks_decision TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    answer TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_unknowns_project ON unknowns(project, status);

CREATE TABLE IF NOT EXISTS relationships(
    relationship_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    from_entity TEXT NOT NULL,
    to_entity TEXT NOT NULL,
    relation TEXT NOT NULL,
    confidence REAL NOT NULL,
    source_ref TEXT NOT NULL,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_relationships_project ON relationships(project);

CREATE TABLE IF NOT EXISTS actions(
    action_id TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    rationale TEXT NOT NULL,
    target_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    expected_confidence_gain REAL NOT NULL,
    effort_days REAL NOT NULL,
    priority REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    result TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_actions_project ON actions(project, status, priority);

CREATE TABLE IF NOT EXISTS metrics(
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    uncertainty REAL NOT NULL,
    claims_active INTEGER NOT NULL,
    unknowns_open INTEGER NOT NULL,
    contradictions_open INTEGER NOT NULL,
    mean_confidence REAL NOT NULL,
    note TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_metrics_project ON metrics(project, captured_at);
"""

STATE_TABLES = (
    "observations",
    "entities",
    "claims",
    "evidence",
    "transitions",
    "contradictions",
    "unknowns",
    "relationships",
    "actions",
    "metrics",
)


def _row(raw: sqlite3.Row | None) -> dict | None:
    return dict(raw) if raw is not None else None


class Store:
    def __init__(self, root: Path, database: str = "data/living-context.sqlite"):
        self.root = root
        self.path = root / database
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self._migrate_legacy_sources()
        self.conn.executescript(SCHEMA)

    def _migrate_legacy_sources(self) -> None:
        exists = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sources'"
        ).fetchone()
        if not exists:
            return
        columns = [row[1] for row in self.conn.execute("PRAGMA table_info(sources)")]
        if "project" in columns:
            return
        with self.conn:
            self.conn.execute("ALTER TABLE sources RENAME TO sources_legacy")
            self.conn.execute(
                """
                CREATE TABLE sources(
                    project TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    record_count INTEGER NOT NULL,
                    last_ingested_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(project, source_path)
                )
                """
            )
            self.conn.execute(
                """
                INSERT OR IGNORE INTO sources(project, source_path, source_hash, record_count, last_ingested_at)
                SELECT COALESCE(r.project, 'legacy'), l.source_path, l.source_hash,
                       COUNT(r.record_id), l.last_ingested_at
                FROM sources_legacy l
                LEFT JOIN records r ON r.source_path = l.source_path
                GROUP BY COALESCE(r.project, 'legacy'), l.source_path, l.source_hash, l.last_ingested_at
                """
            )
            self.conn.execute("DROP TABLE sources_legacy")

    def close(self) -> None:
        self.conn.close()

    # -- observation layer --------------------------------------------------

    def replace_source(
        self, project: str, source_path: str, source_hash: str, records: list[ContextRecord]
    ) -> int:
        with self.conn:
            self.conn.execute(
                "DELETE FROM records WHERE project=? AND source_path=?",
                (project, source_path),
            )
            for record in records:
                self.conn.execute(
                    """
                    INSERT INTO records(
                        record_id, project, kind, text, source_path, source_line,
                        source_hash, observed_at, status, tags_json, metadata_json
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        record.record_id,
                        record.project,
                        record.kind,
                        record.text,
                        record.source_path,
                        record.source_line,
                        record.source_hash,
                        record.observed_at,
                        record.status,
                        json.dumps(record.tags),
                        json.dumps(record.metadata, sort_keys=True),
                    ),
                )
            self.conn.execute(
                """
                INSERT INTO sources(project, source_path, source_hash, record_count, last_ingested_at)
                VALUES(?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT(project, source_path) DO UPDATE SET
                    source_hash=excluded.source_hash,
                    record_count=excluded.record_count,
                    last_ingested_at=CURRENT_TIMESTAMP
                """,
                (project, source_path, source_hash, len(records)),
            )
        return len(records)

    def ingest(self, records: list[ContextRecord]) -> dict[str, int]:
        grouped: dict[tuple[str, str, str], list[ContextRecord]] = {}
        for record in records:
            grouped.setdefault(
                (record.project, record.source_path, record.source_hash), []
            ).append(record)
        count = 0
        for (project, path, source_hash), items in grouped.items():
            count += self.replace_source(project, path, source_hash, items)
        return {"sources": len(grouped), "records": count}

    def query(self, text: str, project=None, kinds=None, limit=20):
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        terms = [term.lower() for term in text.split() if len(term) >= 2]
        hits = []
        for raw in self.conn.execute("SELECT * FROM records"):
            row = dict(raw)
            if project and row["project"] != project:
                continue
            if kinds and row["kind"] not in kinds:
                continue
            blob = (
                f"{row['text']} {row['kind']} {row['project']} "
                f"{row['source_path']} {row['tags_json']}"
            ).lower()
            score = sum(1 for term in terms if term in blob) / (len(terms) or 1)
            if score or not terms:
                hits.append((score, row))
        hits.sort(
            key=lambda pair: (
                -pair[0],
                pair[1]["observed_at"],
                pair[1]["record_id"],
            )
        )
        result = []
        for score, row in hits[:limit]:
            row["tags"] = json.loads(row.pop("tags_json"))
            row["metadata"] = json.loads(row.pop("metadata_json"))
            row["score"] = round(score, 4)
            result.append(row)
        return result

    def timeline(self, project=None, limit=100):
        if limit < 1 or limit > 100_000:
            raise ValueError("limit must be between 1 and 100000")
        sql = "SELECT * FROM records"
        params: list[object] = []
        if project:
            sql += " WHERE project=?"
            params.append(project)
        sql += " ORDER BY observed_at, source_path, source_line LIMIT ?"
        params.append(limit)
        result = []
        for raw in self.conn.execute(sql, params):
            row = dict(raw)
            row["tags"] = json.loads(row.pop("tags_json"))
            row["metadata"] = json.loads(row.pop("metadata_json"))
            result.append(row)
        return result

    # -- state layer: writes ------------------------------------------------

    def record_observation(self, observation: ObservationSource) -> bool:
        """Returns True when this exact source content is new to the project."""
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT OR IGNORE INTO observations(
                    observation_id, project, source_ref, source_kind, actor,
                    observed_at, content_hash, ingested_at
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    observation.observation_id,
                    observation.project,
                    observation.source_ref,
                    observation.source_kind,
                    observation.actor,
                    observation.observed_at,
                    observation.content_hash,
                    observation.ingested_at,
                ),
            )
        return cursor.rowcount > 0

    def upsert_entity(self, entity: Entity) -> dict:
        existing = _row(
            self.conn.execute(
                "SELECT * FROM entities WHERE entity_id=?", (entity.entity_id,)
            ).fetchone()
        )
        if existing:
            aliases = sorted(set(json.loads(existing["aliases_json"])) | set(entity.aliases))
            with self.conn:
                self.conn.execute(
                    "UPDATE entities SET aliases_json=?, updated_at=? WHERE entity_id=?",
                    (json.dumps(aliases), now_iso(), entity.entity_id),
                )
            existing["aliases_json"] = json.dumps(aliases)
            return self._entity_row(existing)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO entities(
                    entity_id, project, kind, name, canonical_key, aliases_json,
                    created_at, updated_at, metadata_json
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    entity.entity_id,
                    entity.project,
                    entity.kind,
                    entity.name,
                    entity.canonical_key,
                    json.dumps(entity.aliases),
                    entity.created_at,
                    entity.updated_at,
                    json.dumps(entity.metadata, sort_keys=True),
                ),
            )
        return entity.to_dict()

    @staticmethod
    def _entity_row(row: dict) -> dict:
        row = dict(row)
        row["aliases"] = json.loads(row.pop("aliases_json", "[]"))
        row["metadata"] = json.loads(row.pop("metadata_json", "{}"))
        return row

    def find_entity(self, project: str, name_or_id: str) -> dict | None:
        from living_context.models import normalize

        direct = _row(
            self.conn.execute(
                "SELECT * FROM entities WHERE project=? AND entity_id=?",
                (project, name_or_id),
            ).fetchone()
        )
        if direct:
            return self._entity_row(direct)
        key = normalize(name_or_id)
        by_key = _row(
            self.conn.execute(
                "SELECT * FROM entities WHERE project=? AND canonical_key=? ORDER BY kind LIMIT 1",
                (project, key),
            ).fetchone()
        )
        if by_key:
            return self._entity_row(by_key)
        for raw in self.conn.execute("SELECT * FROM entities WHERE project=?", (project,)):
            row = self._entity_row(dict(raw))
            if key in row["aliases"]:
                return row
        return None

    def entities(self, project: str, kind: str | None = None) -> list[dict]:
        sql = "SELECT * FROM entities WHERE project=?"
        params: list[object] = [project]
        if kind:
            sql += " AND kind=?"
            params.append(kind)
        sql += " ORDER BY kind, name"
        return [self._entity_row(dict(raw)) for raw in self.conn.execute(sql, params)]

    def upsert_claim(self, claim: Claim) -> dict:
        existing = self.get_claim(claim.claim_id)
        if existing:
            return existing
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO claims(
                    claim_id, project, entity_id, attribute, value, normalized_value,
                    confidence, status, importance, first_seen_at, last_seen_at,
                    superseded_by, metadata_json
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    claim.claim_id,
                    claim.project,
                    claim.entity_id,
                    claim.attribute,
                    claim.value,
                    claim.normalized_value,
                    claim.confidence,
                    claim.status,
                    claim.importance,
                    claim.first_seen_at,
                    claim.last_seen_at,
                    claim.superseded_by,
                    json.dumps(claim.metadata, sort_keys=True),
                ),
            )
        return claim.to_dict()

    def get_claim(self, claim_id: str) -> dict | None:
        row = _row(
            self.conn.execute("SELECT * FROM claims WHERE claim_id=?", (claim_id,)).fetchone()
        )
        if row is None:
            return None
        row["metadata"] = json.loads(row.pop("metadata_json", "{}"))
        return row

    def claims_in_slot(
        self, project: str, entity_id: str, attribute: str, statuses: tuple[str, ...] = ("active",)
    ) -> list[dict]:
        placeholders = ",".join("?" for _ in statuses)
        rows = self.conn.execute(
            f"""
            SELECT * FROM claims
            WHERE project=? AND entity_id=? AND attribute=? AND status IN ({placeholders})
            ORDER BY confidence DESC, claim_id
            """,
            (project, entity_id, attribute, *statuses),
        )
        result = []
        for raw in rows:
            row = dict(raw)
            row["metadata"] = json.loads(row.pop("metadata_json", "{}"))
            result.append(row)
        return result

    def update_claim(self, claim_id: str, **fields) -> None:
        allowed = {
            "confidence",
            "status",
            "importance",
            "last_seen_at",
            "superseded_by",
            "value",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        assignments = ", ".join(f"{key}=?" for key in updates)
        with self.conn:
            self.conn.execute(
                f"UPDATE claims SET {assignments} WHERE claim_id=?",
                (*updates.values(), claim_id),
            )

    def add_evidence(self, evidence: Evidence) -> bool:
        """Idempotent by content: re-ingesting a file never inflates confidence."""
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT OR IGNORE INTO evidence(
                    evidence_id, project, claim_id, observation_id, kind, excerpt,
                    actor, source_ref, locator, observed_at, weight
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    evidence.evidence_id,
                    evidence.project,
                    evidence.claim_id,
                    evidence.observation_id,
                    evidence.kind,
                    evidence.excerpt,
                    evidence.actor,
                    evidence.source_ref,
                    evidence.locator,
                    evidence.observed_at,
                    evidence.weight,
                ),
            )
        return cursor.rowcount > 0

    def evidence_for(self, claim_id: str) -> list[dict]:
        return [
            dict(raw)
            for raw in self.conn.execute(
                "SELECT * FROM evidence WHERE claim_id=? ORDER BY observed_at, evidence_id",
                (claim_id,),
            )
        ]

    def record_transition(self, transition: Transition) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO transitions(
                    transition_id, project, entity_id, attribute, transition_type,
                    from_value, to_value, from_confidence, to_confidence, rationale,
                    claim_id, superseded_claim_id, evidence_json, occurred_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    transition.transition_id,
                    transition.project,
                    transition.entity_id,
                    transition.attribute,
                    transition.transition_type,
                    transition.from_value,
                    transition.to_value,
                    transition.from_confidence,
                    transition.to_confidence,
                    transition.rationale,
                    transition.claim_id,
                    transition.superseded_claim_id,
                    json.dumps(transition.evidence_ids),
                    transition.occurred_at,
                ),
            )

    def upsert_contradiction(self, contradiction: Contradiction) -> bool:
        existing = _row(
            self.conn.execute(
                "SELECT * FROM contradictions WHERE contradiction_id=?",
                (contradiction.contradiction_id,),
            ).fetchone()
        )
        if existing:
            with self.conn:
                self.conn.execute(
                    "UPDATE contradictions SET severity=?, note=? WHERE contradiction_id=?",
                    (contradiction.severity, contradiction.note, contradiction.contradiction_id),
                )
            return False
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO contradictions(
                    contradiction_id, project, entity_id, attribute, claim_a, claim_b,
                    status, severity, note, detected_at, resolved_at, resolution
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    contradiction.contradiction_id,
                    contradiction.project,
                    contradiction.entity_id,
                    contradiction.attribute,
                    contradiction.claim_a,
                    contradiction.claim_b,
                    contradiction.status,
                    contradiction.severity,
                    contradiction.note,
                    contradiction.detected_at,
                    contradiction.resolved_at,
                    contradiction.resolution,
                ),
            )
        return True

    def resolve_contradiction(
        self, contradiction_id: str, resolution: str, status: str = "resolved"
    ) -> dict:
        row = _row(
            self.conn.execute(
                "SELECT * FROM contradictions WHERE contradiction_id=?", (contradiction_id,)
            ).fetchone()
        )
        if row is None:
            raise ValueError(f"unknown contradiction: {contradiction_id}")
        with self.conn:
            self.conn.execute(
                "UPDATE contradictions SET status=?, resolution=?, resolved_at=? WHERE contradiction_id=?",
                (status, resolution, now_iso(), contradiction_id),
            )
        return {"contradiction_id": contradiction_id, "status": status, "resolution": resolution}

    def upsert_unknown(self, unknown: Unknown) -> bool:
        existing = _row(
            self.conn.execute(
                "SELECT * FROM unknowns WHERE unknown_id=?", (unknown.unknown_id,)
            ).fetchone()
        )
        if existing:
            with self.conn:
                self.conn.execute(
                    "UPDATE unknowns SET impact=MAX(impact, ?), blocks_decision=? WHERE unknown_id=?",
                    (
                        unknown.impact,
                        unknown.blocks_decision or existing["blocks_decision"],
                        unknown.unknown_id,
                    ),
                )
            return False
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO unknowns(
                    unknown_id, project, question, entity_id, impact, status,
                    blocks_decision, source_ref, created_at, resolved_at, answer
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    unknown.unknown_id,
                    unknown.project,
                    unknown.question,
                    unknown.entity_id,
                    unknown.impact,
                    unknown.status,
                    unknown.blocks_decision,
                    unknown.source_ref,
                    unknown.created_at,
                    unknown.resolved_at,
                    unknown.answer,
                ),
            )
        return True

    def resolve_unknown(self, unknown_id: str, answer: str, status: str = "resolved") -> dict:
        row = _row(
            self.conn.execute(
                "SELECT * FROM unknowns WHERE unknown_id=?", (unknown_id,)
            ).fetchone()
        )
        if row is None:
            raise ValueError(f"unknown question id: {unknown_id}")
        with self.conn:
            self.conn.execute(
                "UPDATE unknowns SET status=?, answer=?, resolved_at=? WHERE unknown_id=?",
                (status, answer, now_iso(), unknown_id),
            )
        return {"unknown_id": unknown_id, "status": status, "answer": answer}

    def upsert_relationship(self, relationship: Relationship) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO relationships(
                    relationship_id, project, from_entity, to_entity, relation,
                    confidence, source_ref, observed_at
                ) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(relationship_id) DO UPDATE SET
                    confidence=MAX(relationships.confidence, excluded.confidence),
                    observed_at=excluded.observed_at
                """,
                (
                    relationship.relationship_id,
                    relationship.project,
                    relationship.from_entity,
                    relationship.to_entity,
                    relationship.relation,
                    relationship.confidence,
                    relationship.source_ref,
                    relationship.observed_at,
                ),
            )

    def replace_proposed_actions(self, project: str, actions: list[Action]) -> int:
        """Regenerate proposals. Actions a human has picked up are never touched."""
        with self.conn:
            self.conn.execute(
                "DELETE FROM actions WHERE project=? AND status='proposed'", (project,)
            )
            written = 0
            for action in actions:
                cursor = self.conn.execute(
                    """
                    INSERT OR IGNORE INTO actions(
                        action_id, project, title, kind, rationale, target_kind, target_id,
                        expected_confidence_gain, effort_days, priority, status,
                        created_at, completed_at, result
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        action.action_id,
                        action.project,
                        action.title,
                        action.kind,
                        action.rationale,
                        action.target_kind,
                        action.target_id,
                        action.expected_confidence_gain,
                        action.effort_days,
                        action.priority,
                        action.status,
                        action.created_at,
                        action.completed_at,
                        action.result,
                    ),
                )
                written += cursor.rowcount
        return written

    def update_action(self, action_id: str, status: str, result: str = "") -> dict:
        row = _row(
            self.conn.execute("SELECT * FROM actions WHERE action_id=?", (action_id,)).fetchone()
        )
        if row is None:
            raise ValueError(f"unknown action: {action_id}")
        completed = now_iso() if status in {"done", "dropped"} else None
        with self.conn:
            self.conn.execute(
                "UPDATE actions SET status=?, result=?, completed_at=? WHERE action_id=?",
                (status, result, completed, action_id),
            )
        return {"action_id": action_id, "status": status, "result": result}

    # -- state layer: reads -------------------------------------------------

    def state(
        self,
        project: str,
        entity: str | None = None,
        half_life_days: float = 180.0,
        include_superseded: bool = False,
        as_of: str | None = None,
    ) -> list[dict]:
        statuses = ("active", "superseded") if include_superseded else ("active",)
        placeholders = ",".join("?" for _ in statuses)
        sql = f"""
            SELECT c.*, e.name AS entity_name, e.kind AS entity_kind
            FROM claims c JOIN entities e ON e.entity_id = c.entity_id
            WHERE c.project=? AND c.status IN ({placeholders})
        """
        params: list[object] = [project, *statuses]
        if entity:
            found = self.find_entity(project, entity)
            if found is None:
                return []
            sql += " AND c.entity_id=?"
            params.append(found["entity_id"])
        sql += " ORDER BY e.kind, e.name, c.attribute, c.confidence DESC"

        grouped: dict[str, dict] = {}
        for raw in self.conn.execute(sql, params):
            row = dict(raw)
            row.pop("metadata_json", None)
            decay = staleness_factor(row["last_seen_at"], half_life_days, as_of)
            row["staleness_factor"] = decay
            row["effective_confidence"] = round(row["confidence"] * decay, 4)
            row["evidence_count"] = self.conn.execute(
                "SELECT COUNT(*) FROM evidence WHERE claim_id=?", (row["claim_id"],)
            ).fetchone()[0]
            bucket = grouped.setdefault(
                row["entity_id"],
                {
                    "entity_id": row["entity_id"],
                    "entity": row.pop("entity_name"),
                    "kind": row.pop("entity_kind"),
                    "claims": [],
                },
            )
            row.pop("entity_name", None)
            row.pop("entity_kind", None)
            bucket["claims"].append(row)
        return list(grouped.values())

    def transitions(self, project: str, since: str | None = None, limit: int = 100) -> list[dict]:
        limit = max(1, min(1000, limit))
        sql = """
            SELECT t.*, t.rowid AS insertion_order,
                   e.name AS entity_name, e.kind AS entity_kind
            FROM transitions t LEFT JOIN entities e ON e.entity_id = t.entity_id
            WHERE t.project=?
        """
        params: list[object] = [project]
        if since:
            sql += " AND t.occurred_at >= ?"
            params.append(since)
        sql += " ORDER BY t.occurred_at DESC, t.rowid DESC LIMIT ?"
        params.append(limit)
        result = []
        for raw in self.conn.execute(sql, params):
            row = dict(raw)
            row["evidence_ids"] = json.loads(row.pop("evidence_json", "[]"))
            result.append(row)
        return result

    def contradictions(
        self, project: str, status: str | None = "open", half_life_days: float = 180.0
    ) -> list[dict]:
        sql = """
            SELECT c.*, e.name AS entity_name
            FROM contradictions c LEFT JOIN entities e ON e.entity_id = c.entity_id
            WHERE c.project=?
        """
        params: list[object] = [project]
        if status:
            sql += " AND c.status=?"
            params.append(status)
        sql += " ORDER BY c.severity DESC, c.detected_at DESC"
        result = []
        for raw in self.conn.execute(sql, params):
            row = dict(raw)
            for side in ("claim_a", "claim_b"):
                claim = self.get_claim(row[side])
                row[f"{side}_value"] = claim["value"] if claim else None
                # Report the same decayed number the state view shows, so one
                # belief never appears to hold two different confidences.
                row[f"{side}_confidence"] = (
                    round(
                        claim["confidence"]
                        * staleness_factor(claim["last_seen_at"], half_life_days),
                        4,
                    )
                    if claim
                    else None
                )
            result.append(row)
        return result

    def unknowns(self, project: str, status: str | None = "open") -> list[dict]:
        sql = "SELECT * FROM unknowns WHERE project=?"
        params: list[object] = [project]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY impact DESC, created_at"
        return [dict(raw) for raw in self.conn.execute(sql, params)]

    def relationships(self, project: str) -> list[dict]:
        return [
            dict(raw)
            for raw in self.conn.execute(
                "SELECT * FROM relationships WHERE project=? ORDER BY relation", (project,)
            )
        ]

    def actions(self, project: str, status: str | None = None, limit: int = 20) -> list[dict]:
        limit = max(1, min(500, limit))
        sql = "SELECT * FROM actions WHERE project=?"
        params: list[object] = [project]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY priority DESC, created_at LIMIT ?"
        params.append(limit)
        return [dict(raw) for raw in self.conn.execute(sql, params)]

    # -- the north-star metric ---------------------------------------------

    def uncertainty(self, project: str, half_life_days: float = 180.0) -> dict:
        """Total open uncertainty weighted by what it would cost to be wrong.

        Falling uncertainty per unit time is the only number the engine is
        trying to move.
        """
        unknowns = self.unknowns(project, "open")
        unknown_load = sum(float(row["impact"]) for row in unknowns)

        claim_load = 0.0
        confidences: list[float] = []
        claim_count = 0
        for raw in self.conn.execute(
            "SELECT confidence, importance, last_seen_at FROM claims WHERE project=? AND status='active'",
            (project,),
        ):
            decay = staleness_factor(raw["last_seen_at"], half_life_days)
            effective = raw["confidence"] * decay
            confidences.append(effective)
            claim_load += raw["importance"] * (1.0 - effective)
            claim_count += 1

        open_contradictions = self.contradictions(project, "open")
        contradiction_load = sum(float(row["severity"]) for row in open_contradictions)

        total = unknown_load + claim_load + contradiction_load
        return {
            "project": project,
            "uncertainty": round(total, 4),
            "unknown_load": round(unknown_load, 4),
            "claim_load": round(claim_load, 4),
            "contradiction_load": round(contradiction_load, 4),
            "claims_active": claim_count,
            "unknowns_open": len(unknowns),
            "contradictions_open": len(open_contradictions),
            "mean_confidence": round(sum(confidences) / len(confidences), 4)
            if confidences
            else 0.0,
        }

    def snapshot_metric(self, project: str, half_life_days: float = 180.0, note: str = "") -> dict:
        summary = self.uncertainty(project, half_life_days)
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO metrics(
                    project, captured_at, uncertainty, claims_active, unknowns_open,
                    contradictions_open, mean_confidence, note
                ) VALUES(?,?,?,?,?,?,?,?)
                """,
                (
                    project,
                    now_iso(),
                    summary["uncertainty"],
                    summary["claims_active"],
                    summary["unknowns_open"],
                    summary["contradictions_open"],
                    summary["mean_confidence"],
                    note,
                ),
            )
        return summary

    def metrics(self, project: str, limit: int = 50) -> list[dict]:
        limit = max(1, min(1000, limit))
        return [
            dict(raw)
            for raw in self.conn.execute(
                "SELECT * FROM metrics WHERE project=? ORDER BY captured_at DESC, snapshot_id DESC LIMIT ?",
                (project, limit),
            )
        ]

    # -- lifecycle ----------------------------------------------------------

    def projects(self) -> list[dict]:
        rows = {
            row["project"]: dict(row)
            for row in self.conn.execute(
                """
                SELECT project, COUNT(*) records, COUNT(DISTINCT source_path) sources,
                       MIN(observed_at) first_observed_at, MAX(observed_at) last_observed_at
                FROM records GROUP BY project ORDER BY project
                """
            )
        }
        for raw in self.conn.execute(
            "SELECT project, COUNT(*) n FROM claims WHERE status='active' GROUP BY project"
        ):
            bucket = rows.setdefault(
                raw["project"],
                {
                    "project": raw["project"],
                    "records": 0,
                    "sources": 0,
                    "first_observed_at": None,
                    "last_observed_at": None,
                },
            )
            bucket["claims"] = raw["n"]
        for row in rows.values():
            row.setdefault("claims", 0)
        return [rows[key] for key in sorted(rows)]

    def delete_project(self, project: str) -> dict[str, int]:
        if not project.strip():
            raise ValueError("project is required")
        record_count = self.conn.execute(
            "SELECT COUNT(*) FROM records WHERE project=?", (project,)
        ).fetchone()[0]
        source_count = self.conn.execute(
            "SELECT COUNT(*) FROM sources WHERE project=?", (project,)
        ).fetchone()[0]
        claim_count = self.conn.execute(
            "SELECT COUNT(*) FROM claims WHERE project=?", (project,)
        ).fetchone()[0]
        with self.conn:
            self.conn.execute("DELETE FROM records WHERE project=?", (project,))
            self.conn.execute("DELETE FROM sources WHERE project=?", (project,))
            for table in STATE_TABLES:
                self.conn.execute(f"DELETE FROM {table} WHERE project=?", (project,))
        return {
            "records_deleted": record_count,
            "sources_deleted": source_count,
            "claims_deleted": claim_count,
        }

    def status(self):
        row = self.conn.execute(
            """
            SELECT COUNT(*) records,
                   COUNT(DISTINCT project || char(31) || source_path) sources,
                   COUNT(DISTINCT project) projects
            FROM records
            """
        ).fetchone()
        kinds = {
            value["kind"]: value["n"]
            for value in self.conn.execute(
                "SELECT kind, COUNT(*) n FROM records GROUP BY kind ORDER BY kind"
            )
        }
        counts = {}
        for table in ("entities", "claims", "evidence", "transitions", "contradictions", "unknowns"):
            counts[table] = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        projects = self.conn.execute(
            "SELECT COUNT(DISTINCT project) FROM entities"
        ).fetchone()[0]
        return {
            "records": row["records"],
            "sources": row["sources"],
            "projects": max(row["projects"], projects),
            "by_kind": kinds,
            "state": counts,
            "database": str(self.path),
        }
