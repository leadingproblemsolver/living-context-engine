"""Synchronization: discover -> parse -> chunk -> extract signals -> persist.

Parser failures are isolated (caught, logged, reported) and never turned
into document content. Missing-file detection is scoped to the synced
root so a partial sync never marks unrelated documents as missing.
"""
from __future__ import annotations

import os

from lce.adapters.parsers import ParseFailure, discover, parse_file
from lce.core.ids import canonical_path, doc_id_for_path
from lce.pipeline.chunker import chunk_json_paths, chunk_text
from lce.pipeline.signals import extract_signals


class SyncEngine:
    def __init__(self, settings, store, logger):
        self.settings = settings
        self.store = store
        self.logger = logger

    def _scope_root(self, input_path: str) -> str | None:
        """Canonical scope root for missing-detection.

        Returns None when the synced path IS the project root (a full sync,
        where "not seen" legitimately means "gone"). Otherwise returns the
        canonical path of the synced subpath so missing-detection stays
        scoped to it.
        """
        root_canon = canonical_path(self.settings.project_root, self.settings.project_root)
        input_canon = canonical_path(self.settings.project_root, input_path)
        if input_canon in (root_canon, ".", ""):
            return None
        return input_canon

    def sync(self, input_path: str, dry_run: bool = False) -> dict:
        self.logger.stage_start("discover")
        try:
            files = discover(input_path)
        except FileNotFoundError as e:
            self.logger.error("discover failed", e, path=str(input_path))
            raise
        self.logger.stage_end("discover", files=len(files))

        scope_root = self._scope_root(input_path)
        seen_paths: set[str] = set()
        changed: list[dict] = []
        skipped: list[dict] = []
        errors: list[dict] = []
        parsed_items = []

        self.logger.stage_start("fingerprint_diff")
        for f in files:
            p = canonical_path(self.settings.project_root, f)
            try:
                parsed = parse_file(f, self.settings.parser_backend)
            except ParseFailure as e:
                errors.append({"path": p, "error": e.reason})
                self.logger.error("file parse failed", path=p, reason=e.reason)
                continue
            except Exception as e:
                errors.append({"path": p, "error": f"{type(e).__name__}: {e}"})
                self.logger.error("file parse failed (unexpected)", e, path=p)
                continue

            seen_paths.add(p)
            doc_id = doc_id_for_path(p)
            old = self.store.get_document_by_path(p)
            state = "new" if not old else ("modified" if old["content_hash"] != parsed["content_hash"] else "unchanged")
            parsed_items.append((f, p, doc_id, parsed, old, state))
            (skipped if state == "unchanged" else changed).append({"path": p, "state": state, "doc_id": doc_id})
        self.logger.stage_end(
            "fingerprint_diff", changed_or_new=len(changed), unchanged=len(skipped), errors=len(errors)
        )

        if dry_run:
            return {"dry_run": True, "changed_or_new": changed, "unchanged": skipped, "errors": errors}

        origin = "continuity" if scope_root == canonical_path(self.settings.project_root, self.settings.continuity_dir) else "corpus"

        all_new_rus: list[dict] = []
        all_new_signals: list[dict] = []
        all_json_index: list[dict] = []

        self.logger.stage_start("recompute_changed")
        for f, p, doc_id, parsed, old, state in parsed_items:
            if state == "unchanged":
                continue
            st = os.stat(f)
            doc = {
                "doc_id": doc_id,
                "source_path": p,
                "source_type": parsed["source_type"],
                "content_hash": parsed["content_hash"],
                "status": "active",
                "mtime": st.st_mtime,
                "size_bytes": st.st_size,
                "content": parsed["content"],
                "metadata": parsed["metadata"],
                "origin": origin,
                "last_seen_run_id": self.logger.run_id,
            }
            self.store.invalidate_document_artifacts(doc_id)
            self.store.upsert_document(doc)

            if parsed["source_type"] in ("json", "jsonl") and parsed["json_paths"]:
                rus = chunk_json_paths(doc_id, parsed["json_paths"])
            else:
                rus = chunk_text(doc_id, parsed["content"])
            self.store.insert_rus(rus)

            sigs = extract_signals(rus, self.settings.llm_backend)
            self.store.insert_signals(sigs)

            jp = []
            if parsed["json_paths"]:
                ru_by_path = {r.get("json_path"): r for r in rus if r.get("json_path")}
                for path, value in parsed["json_paths"]:
                    ru = ru_by_path.get(path)
                    if ru:
                        from lce.core.ids import sha256_text

                        preview = str(value)[:500]
                        jp.append(
                            {
                                "path_id": sha256_text(f"jsonpath:{doc_id}:{path}"),
                                "doc_id": doc_id,
                                "ru_id": ru["ru_id"],
                                "json_path": path,
                                "value_preview": preview,
                                "value_hash": sha256_text(str(value)),
                            }
                        )
                self.store.insert_json_paths(jp)

            all_new_rus += rus
            all_new_signals += sigs
            all_json_index += jp
        self.logger.stage_end(
            "recompute_changed",
            documents_changed_or_new=len(changed),
            retrieval_units=len(all_new_rus),
            signals=len(all_new_signals),
            json_paths=len(all_json_index),
        )

        self.logger.stage_start("missing_detection")
        missing = self.store.mark_missing_not_seen(seen_paths, self.logger.run_id, scope_root=scope_root, origin=origin)
        self.logger.stage_end("missing_detection", missing=len(missing))

        self.logger.stage_start("cluster_rebuild")
        self.store.rebuild_clusters()
        self.logger.stage_end("cluster_rebuild")

        return {
            "documents_discovered": len(files),
            "documents_changed_or_new": len(changed),
            "documents_unchanged": len(skipped),
            "missing_marked": len(missing),
            "retrieval_units_generated": len(all_new_rus),
            "signals_extracted": len(all_new_signals),
            "json_paths_indexed": len(all_json_index),
            "errors": errors,
            "db_counts": self.store.counts(),
        }
