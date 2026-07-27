from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from living_context.models import ContextRecord

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
"""


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "data" / "living-context.sqlite"
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


    def projects(self) -> list[dict]:
        return [
            dict(row)
            for row in self.conn.execute(
                """
                SELECT project, COUNT(*) records, COUNT(DISTINCT source_path) sources,
                       MIN(observed_at) first_observed_at, MAX(observed_at) last_observed_at
                FROM records GROUP BY project ORDER BY project
                """
            )
        ]

    def delete_project(self, project: str) -> dict[str, int]:
        if not project.strip():
            raise ValueError("project is required")
        record_count = self.conn.execute(
            "SELECT COUNT(*) FROM records WHERE project=?", (project,)
        ).fetchone()[0]
        source_count = self.conn.execute(
            "SELECT COUNT(*) FROM sources WHERE project=?", (project,)
        ).fetchone()[0]
        with self.conn:
            self.conn.execute("DELETE FROM records WHERE project=?", (project,))
            self.conn.execute("DELETE FROM sources WHERE project=?", (project,))
        return {"records_deleted": record_count, "sources_deleted": source_count}

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
        return {
            "records": row["records"],
            "sources": row["sources"],
            "projects": row["projects"],
            "by_kind": kinds,
            "database": str(self.path),
        }
