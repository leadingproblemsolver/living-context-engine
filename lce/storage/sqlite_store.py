"""The sole storage implementation for LCE. Raw sqlite3, stdlib-only.

There must never be a second storage implementation (e.g. an ORM layer) --
that duplication is exactly the kind of drift this system is designed to
prevent. Everything reads/writes through this class.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from lce.core.ids import cluster_id_for

VALID_CONTINUITY_STATES = {"pending", "accepted", "rejected", "superseded"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def dumps(x) -> str:
    return json.dumps(x if x is not None else {}, ensure_ascii=False, sort_keys=True)


def loads(x, default=None):
    try:
        return json.loads(x) if x else ({} if default is None else default)
    except (TypeError, ValueError):
        return {} if default is None else default


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS documents(
  doc_id TEXT PRIMARY KEY, source_path TEXT UNIQUE, source_type TEXT, content_hash TEXT,
  status TEXT DEFAULT 'active', mtime REAL, size_bytes INTEGER, content TEXT,
  metadata_json TEXT DEFAULT '{}', origin TEXT DEFAULT 'corpus',
  created_at TEXT, updated_at TEXT, last_seen_run_id TEXT
);

CREATE TABLE IF NOT EXISTS retrieval_units(
  ru_id TEXT PRIMARY KEY, doc_id TEXT, sequence_number INTEGER, content TEXT, chunk_hash TEXT,
  start_char INTEGER, end_char INTEGER, json_path TEXT, metadata_json TEXT DEFAULT '{}', created_at TEXT,
  FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
);
CREATE INDEX IF NOT EXISTS idx_ru_doc ON retrieval_units(doc_id);

CREATE TABLE IF NOT EXISTS signals(
  signal_id TEXT PRIMARY KEY, ru_id TEXT, doc_id TEXT, signal_type TEXT NOT NULL, content TEXT,
  confidence REAL, metadata_json TEXT DEFAULT '{}', created_at TEXT,
  FOREIGN KEY(ru_id) REFERENCES retrieval_units(ru_id), FOREIGN KEY(doc_id) REFERENCES documents(doc_id)
);
CREATE INDEX IF NOT EXISTS idx_sig_doc ON signals(doc_id);
CREATE INDEX IF NOT EXISTS idx_sig_type ON signals(signal_type);

CREATE TABLE IF NOT EXISTS clusters(
  cluster_id TEXT PRIMARY KEY, topic TEXT UNIQUE, ru_ids_json TEXT DEFAULT '[]', signal_ids_json TEXT DEFAULT '[]',
  metadata_json TEXT DEFAULT '{}', updated_at TEXT
);

CREATE TABLE IF NOT EXISTS json_path_index(
  path_id TEXT PRIMARY KEY, doc_id TEXT, ru_id TEXT, json_path TEXT, value_preview TEXT, value_hash TEXT,
  FOREIGN KEY(doc_id) REFERENCES documents(doc_id), FOREIGN KEY(ru_id) REFERENCES retrieval_units(ru_id)
);

CREATE TABLE IF NOT EXISTS pipeline_runs(
  run_id TEXT PRIMARY KEY, command TEXT, input_path TEXT, status TEXT,
  started_at TEXT, ended_at TEXT, total_duration_ms INTEGER, proof_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS stage_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, ts TEXT, level TEXT, message TEXT, context_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS continuity_records(
  record_id TEXT PRIMARY KEY,
  state TEXT NOT NULL CHECK (state IN ('pending','accepted','rejected','superseded')),
  content TEXT NOT NULL,
  outcome_type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  actor TEXT NOT NULL,
  source_artifact TEXT,
  evidence_refs_json TEXT DEFAULT '[]',
  reingest_path TEXT
);
"""


class SQLiteStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init()

    def conn(self):
        c = sqlite3.connect(self.db_path)
        c.row_factory = sqlite3.Row
        return c

    def init(self):
        with self.conn() as db:
            db.executescript(SCHEMA)

    # ---- pipeline runs ----

    def add_run(self, payload: dict):
        with self.conn() as db:
            db.execute(
                "INSERT OR REPLACE INTO pipeline_runs VALUES (?,?,?,?,?,?,?,?)",
                (
                    payload["run_id"],
                    payload.get("command"),
                    payload.get("input_path"),
                    payload.get("status"),
                    payload.get("started_at"),
                    payload.get("ended_at"),
                    payload.get("total_duration_ms"),
                    dumps(payload.get("proof", {})),
                ),
            )
            for e in payload.get("events", []):
                db.execute(
                    "INSERT INTO stage_events(run_id,ts,level,message,context_json) VALUES (?,?,?,?,?)",
                    (payload["run_id"], e.get("ts"), e.get("level"), e.get("message"), dumps(e.get("context", {}))),
                )

    def counts(self):
        names = ["documents", "retrieval_units", "signals", "clusters", "json_path_index", "pipeline_runs", "continuity_records"]
        with self.conn() as db:
            return {n: db.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0] for n in names}

    def recent_runs(self, limit=8, command: str | None = None):
        q = "SELECT run_id,command,input_path,status,started_at,ended_at,total_duration_ms FROM pipeline_runs"
        params: tuple = ()
        if command:
            q += " WHERE command=?"
            params = (command,)
        q += " ORDER BY started_at DESC LIMIT ?"
        params = params + (limit,)
        with self.conn() as db:
            return [dict(r) for r in db.execute(q, params)]

    # ---- documents ----

    def get_document_by_path(self, path: str):
        with self.conn() as db:
            r = db.execute("SELECT * FROM documents WHERE source_path=?", (path,)).fetchone()
            return dict(r) if r else None

    def get_document(self, doc_id: str):
        with self.conn() as db:
            r = db.execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,)).fetchone()
            return dict(r) if r else None

    def upsert_document(self, d: dict):
        t = now()
        with self.conn() as db:
            old = db.execute("SELECT created_at FROM documents WHERE doc_id=?", (d["doc_id"],)).fetchone()
            created = old["created_at"] if old else t
            db.execute(
                """INSERT OR REPLACE INTO documents(doc_id,source_path,source_type,content_hash,status,mtime,size_bytes,content,metadata_json,origin,created_at,updated_at,last_seen_run_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    d["doc_id"],
                    d["source_path"],
                    d["source_type"],
                    d["content_hash"],
                    d.get("status", "active"),
                    d.get("mtime"),
                    d.get("size_bytes"),
                    d.get("content", ""),
                    dumps(d.get("metadata", {})),
                    d.get("origin", "corpus"),
                    created,
                    t,
                    d.get("last_seen_run_id"),
                ),
            )

    def invalidate_document_artifacts(self, doc_id: str):
        with self.conn() as db:
            db.execute("DELETE FROM json_path_index WHERE doc_id=?", (doc_id,))
            db.execute("DELETE FROM signals WHERE doc_id=?", (doc_id,))
            db.execute("DELETE FROM retrieval_units WHERE doc_id=?", (doc_id,))

    def insert_rus(self, rows: list[dict]):
        with self.conn() as db:
            db.executemany(
                """INSERT OR REPLACE INTO retrieval_units(ru_id,doc_id,sequence_number,content,chunk_hash,start_char,end_char,json_path,metadata_json,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        r["ru_id"], r["doc_id"], r["sequence_number"], r["content"], r["chunk_hash"],
                        r["start_char"], r["end_char"], r.get("json_path"), dumps(r.get("metadata", {})), now(),
                    )
                    for r in rows
                ],
            )

    def insert_signals(self, rows: list[dict]):
        with self.conn() as db:
            db.executemany(
                """INSERT OR REPLACE INTO signals(signal_id,ru_id,doc_id,signal_type,content,confidence,metadata_json,created_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                [
                    (
                        r["signal_id"], r["ru_id"], r["doc_id"], r["signal_type"], r["content"],
                        r.get("confidence", 0.7), dumps(r.get("metadata", {})), now(),
                    )
                    for r in rows
                ],
            )

    def insert_json_paths(self, rows: list[dict]):
        with self.conn() as db:
            db.executemany(
                "INSERT OR REPLACE INTO json_path_index(path_id,doc_id,ru_id,json_path,value_preview,value_hash) VALUES(?,?,?,?,?,?)",
                [
                    (r["path_id"], r["doc_id"], r["ru_id"], r["json_path"], r.get("value_preview", ""), r.get("value_hash", ""))
                    for r in rows
                ],
            )

    def rebuild_clusters(self):
        with self.conn() as db:
            signals = [dict(r) for r in db.execute("SELECT * FROM signals")]
            groups: dict[str, dict] = {}
            for s in signals:
                topic = s.get("signal_type") or "context"
                groups.setdefault(topic, {"ru_ids": set(), "signal_ids": set()})
                groups[topic]["ru_ids"].add(s.get("ru_id"))
                groups[topic]["signal_ids"].add(s.get("signal_id"))
            for topic, g in groups.items():
                db.execute(
                    "INSERT OR REPLACE INTO clusters VALUES(?,?,?,?,?,?)",
                    (
                        cluster_id_for(topic),
                        topic,
                        dumps(sorted(g["ru_ids"])),
                        dumps(sorted(g["signal_ids"])),
                        dumps({"method": "heuristic"}),
                        now(),
                    ),
                )

    def mark_missing_not_seen(self, seen_paths: set[str], run_id: str, scope_root: str | None = None, origin: str = "corpus"):
        """Mark active documents as missing, scoped to `scope_root` and `origin`.

        Only documents with the given origin whose source_path is under
        scope_root (or all active documents of that origin, if scope_root is
        None meaning a full sync of that origin) are eligible. This prevents
        a partial/subdirectory sync from silently marking unrelated
        documents outside its scope -- or documents belonging to a different
        origin entirely -- as missing.
        """
        with self.conn() as db:
            current = [dict(r) for r in db.execute("SELECT doc_id,source_path FROM documents WHERE status='active' AND origin=?", (origin,))]
            missing = []
            for d in current:
                path = d["source_path"]
                if scope_root is not None and not (path == scope_root or path.startswith(scope_root.rstrip("/") + "/")):
                    continue
                if path not in seen_paths:
                    db.execute(
                        "UPDATE documents SET status='missing', updated_at=?, last_seen_run_id=? WHERE doc_id=?",
                        (now(), run_id, d["doc_id"]),
                    )
                    missing.append(d)
            return missing

    def scan_documents(self):
        with self.conn() as db:
            return [dict(r) for r in db.execute("SELECT doc_id, source_path, content_hash, status, origin, updated_at, mtime FROM documents ORDER BY source_path")]

    def get_rus(self, doc_id=None):
        q = "SELECT ru.*, d.source_path, d.origin FROM retrieval_units ru JOIN documents d ON d.doc_id=ru.doc_id"
        params: tuple = ()
        if doc_id:
            q += " WHERE ru.doc_id=? ORDER BY ru.sequence_number"
            params = (doc_id,)
        with self.conn() as db:
            return [dict(r) for r in db.execute(q, params)]

    def get_signals(self, doc_id=None):
        q = "SELECT s.*, d.source_path, d.origin FROM signals s JOIN documents d ON d.doc_id=s.doc_id"
        params: tuple = ()
        if doc_id:
            q += " WHERE s.doc_id=? "
            params = (doc_id,)
        with self.conn() as db:
            return [dict(r) for r in db.execute(q, params)]

    def validation_report(self):
        with self.conn() as db:
            orphan_rus = db.execute(
                "SELECT COUNT(*) FROM retrieval_units ru LEFT JOIN documents d ON d.doc_id=ru.doc_id WHERE d.doc_id IS NULL"
            ).fetchone()[0]
            orphan_sigs = db.execute(
                "SELECT COUNT(*) FROM signals s LEFT JOIN retrieval_units ru ON ru.ru_id=s.ru_id WHERE ru.ru_id IS NULL"
            ).fetchone()[0]
            null_signal_types = db.execute("SELECT COUNT(*) FROM signals WHERE signal_type IS NULL").fetchone()[0]
            duplicate_paths = db.execute("SELECT source_path, COUNT(*) c FROM documents GROUP BY source_path HAVING c>1").fetchall()
            missing_sources = [dict(r) for r in db.execute("SELECT doc_id,source_path FROM documents WHERE status='missing'")]
        return {
            "ok": orphan_rus == 0 and orphan_sigs == 0 and null_signal_types == 0 and len(duplicate_paths) == 0,
            "orphan_retrieval_units": orphan_rus,
            "orphan_signals": orphan_sigs,
            "null_signal_types": null_signal_types,
            "duplicate_document_paths": [dict(r) for r in duplicate_paths],
            "missing_sources": missing_sources,
        }

    # ---- continuity ledger ----

    def insert_continuity_record(self, record: dict):
        with self.conn() as db:
            db.execute(
                """INSERT INTO continuity_records(record_id,state,content,outcome_type,created_at,actor,source_artifact,evidence_refs_json,reingest_path)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    record["record_id"], record["state"], record["content"], record["outcome_type"],
                    record["created_at"], record["actor"], record.get("source_artifact"),
                    dumps(record.get("evidence_refs", [])), record.get("reingest_path"),
                ),
            )

    def get_continuity_record(self, record_id: str):
        with self.conn() as db:
            r = db.execute("SELECT * FROM continuity_records WHERE record_id=?", (record_id,)).fetchone()
            if not r:
                return None
            d = dict(r)
            d["evidence_refs"] = loads(d.pop("evidence_refs_json"), [])
            return d

    def list_continuity_records(self, state: str | None = None):
        q = "SELECT * FROM continuity_records"
        params: tuple = ()
        if state:
            q += " WHERE state=?"
            params = (state,)
        q += " ORDER BY created_at DESC"
        with self.conn() as db:
            rows = [dict(r) for r in db.execute(q, params)]
        for d in rows:
            d["evidence_refs"] = loads(d.pop("evidence_refs_json"), [])
        return rows

    def update_continuity_state(self, record_id: str, new_state: str, reingest_path: str | None = None):
        if new_state not in VALID_CONTINUITY_STATES:
            raise ValueError(f"invalid continuity state: {new_state}")
        with self.conn() as db:
            db.execute(
                "UPDATE continuity_records SET state=?, reingest_path=COALESCE(?, reingest_path) WHERE record_id=?",
                (new_state, reingest_path, record_id),
            )
