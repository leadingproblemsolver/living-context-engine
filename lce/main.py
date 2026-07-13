"""LCE CLI entrypoint: argparse dispatch, one handler per verb, honest exit codes.

No exception is ever silently swallowed. Success exits 0; a recognized user
error (LCEUserError) prints a one-line message to stderr and exits its
declared code; any other exception is logged, its traceback printed, and
the process exits 1.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from lce.continuity import ledger
from lce.continuity.compile import compile_artifact, render_json, render_markdown
from lce.continuity.packet import build_context_packet
from lce.core.config import Settings
from lce.core.logging import RunLogger
from lce.pipeline.sync import SyncEngine
from lce.retrieval import query as run_query
from lce.storage.sqlite_store import SQLiteStore


class LCEUserError(Exception):
    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


def print_json(x) -> None:
    print(json.dumps(x, indent=2, ensure_ascii=False, default=str))


def _bootstrap(require_db: bool = True) -> tuple[Settings, SQLiteStore]:
    settings = Settings.load(".")
    if require_db and not settings.db_path.exists():
        raise LCEUserError(
            f"no database at {settings.db_path}; run `lce init` first", exit_code=2
        )
    settings.ensure_dirs()
    try:
        store = SQLiteStore(settings.db_path)
    except sqlite3.DatabaseError as e:
        raise LCEUserError(f"database unreadable/corrupt at {settings.db_path}: {e}", exit_code=3) from e
    return settings, store


# ---- commands ----


def cmd_init(args) -> None:
    settings = Settings.load(".")
    settings.ensure_dirs()
    SQLiteStore(settings.db_path)
    print_json(
        {
            "status": "initialized",
            "state_dir": str(settings.state_dir),
            "db_path": str(settings.db_path),
            "continuity_dir": str(settings.continuity_dir),
        }
    )


def cmd_doctor(args) -> None:
    settings, store = _bootstrap()
    counts = store.counts()
    validation = store.validation_report()
    sync_runs = store.recent_runs(limit=1, command="sync")
    last_sync = sync_runs[0] if sync_runs else None
    pending = store.list_continuity_records(state="pending")
    ready = bool(validation["ok"]) and last_sync is not None and last_sync.get("status") == "completed"
    reasons = []
    if not validation["ok"]:
        reasons.append("validation report has orphaned records or invalid signal types")
    if last_sync is None:
        reasons.append("corpus has never been synced")
    elif last_sync.get("status") != "completed":
        reasons.append(f"last sync run ended with status={last_sync.get('status')!r}")
    print_json(
        {
            "ready": ready,
            "reasons": reasons,
            "state_dir": str(settings.state_dir),
            "db_path": str(settings.db_path),
            "counts": counts,
            "validation": validation,
            "last_sync": last_sync,
            "pending_continuity_records": len(pending),
        }
    )


def cmd_sync(args) -> None:
    settings = Settings.load(".")
    settings.ensure_dirs()
    store = SQLiteStore(settings.db_path)
    logger = RunLogger(settings, "sync", args.path)
    try:
        engine = SyncEngine(settings, store, logger)
        corpus_proof = engine.sync(args.path, dry_run=args.dry_run)

        continuity_proof = None
        if not args.dry_run:
            cont_dir = settings.continuity_dir
            if cont_dir.exists() and any(cont_dir.iterdir()):
                cont_engine = SyncEngine(settings, store, logger)
                continuity_proof = cont_engine.sync(str(cont_dir), dry_run=False)

        proof = {"corpus": corpus_proof, "continuity": continuity_proof}
        payload = logger.finalize("dry_run" if args.dry_run else "completed", proof)
        if not args.dry_run:
            store.add_run(payload)
        print_json(
            {
                "run_id": payload["run_id"],
                "status": payload["status"],
                "trace_path": payload["trace_path"],
                "proof": proof,
            }
        )
    except Exception as e:
        logger.error("sync failed", e)
        payload = logger.finalize("failed", {"error": str(e)})
        try:
            store.add_run(payload)
        except Exception:
            pass
        raise


def cmd_query(args) -> None:
    settings, store = _bootstrap()
    hits = run_query(store, args.text, intent=args.intent, top_k=args.top_k)
    print_json({"query": args.text, "intent": args.intent, "hits": [h.to_dict() for h in hits]})


def cmd_brief(args) -> None:
    settings, store = _bootstrap()
    packet = build_context_packet(settings, store, query=args.text or args.intent or "current state", intent=args.intent)
    print_json(packet.to_dict())


def cmd_compile(args) -> None:
    settings, store = _bootstrap()
    packet = build_context_packet(settings, store, query=args.topic, intent=args.intent, top_k=args.top_k)
    artifact = compile_artifact(packet, artifact_type=args.type, mode="deterministic")
    if args.format == "markdown":
        out_text = render_markdown(artifact)
    else:
        out_text = json.dumps(render_json(artifact), indent=2, ensure_ascii=False, default=str)
    if args.out:
        Path(args.out).write_text(out_text, encoding="utf-8")
        print_json({"artifact_type": args.type, "topic": args.topic, "written_to": args.out})
    else:
        print(out_text)


def cmd_log(args) -> None:
    settings, store = _bootstrap()
    record = ledger.log_outcome(
        store,
        content=args.content,
        outcome_type=args.outcome_type,
        source_artifact=args.source_artifact,
        evidence_refs=[],
    )
    print_json(record)


def cmd_accept(args) -> None:
    settings, store = _bootstrap()
    try:
        record = ledger.accept(store, settings, args.record_id)
    except ledger.LedgerError as e:
        raise LCEUserError(str(e), exit_code=6) from e
    print_json(record)


def cmd_reject(args) -> None:
    settings, store = _bootstrap()
    try:
        record = ledger.reject(store, args.record_id)
    except ledger.LedgerError as e:
        raise LCEUserError(str(e), exit_code=6) from e
    print_json(record)


def cmd_status(args) -> None:
    settings, store = _bootstrap()
    print_json(
        {
            "state_dir": str(settings.state_dir),
            "db_path": str(settings.db_path),
            "counts": store.counts(),
            "recent_runs": store.recent_runs(limit=5),
            "pending_continuity_records": [r["record_id"] for r in store.list_continuity_records(state="pending")],
        }
    )


def cmd_export(args) -> None:
    settings, store = _bootstrap()
    payload = {
        "counts": store.counts(),
        "documents": store.scan_documents(),
        "signals": store.get_signals(),
        "continuity_records": store.list_continuity_records(),
        "validation": store.validation_report(),
    }
    if args.format == "markdown":
        out_text = "\n".join(f"- {d['source_path']} ({d['status']})" for d in payload["documents"])
    else:
        out_text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    if args.out:
        Path(args.out).write_text(out_text, encoding="utf-8")
        print_json({"written_to": args.out, "counts": payload["counts"]})
    else:
        print(out_text)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lce")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name, func, args=None):
        sp = sub.add_parser(name)
        for a_args, a_kwargs in args or []:
            sp.add_argument(*a_args, **a_kwargs)
        sp.set_defaults(func=func)
        return sp

    add("init", cmd_init)
    add("doctor", cmd_doctor)
    add(
        "sync",
        cmd_sync,
        [
            (["path"], {"nargs": "?", "default": "."}),
            (["--dry-run"], {"action": "store_true"}),
        ],
    )
    add(
        "query",
        cmd_query,
        [
            (["--text"], {"required": True}),
            (["--intent"], {"default": None}),
            (["--top-k"], {"type": int, "default": 20}),
        ],
    )
    add(
        "brief",
        cmd_brief,
        [
            (["--text"], {"default": None}),
            (["--intent"], {"default": None}),
        ],
    )
    add(
        "compile",
        cmd_compile,
        [
            (["--type"], {"dest": "type", "default": "dossier"}),
            (["--topic"], {"required": True}),
            (["--intent"], {"default": None}),
            (["--top-k"], {"type": int, "default": 20}),
            (["--format"], {"choices": ["json", "markdown"], "default": "json"}),
            (["--out"], {"default": None}),
        ],
    )
    add(
        "log",
        cmd_log,
        [
            (["--content"], {"required": True}),
            (["--outcome-type"], {"required": True}),
            (["--source-artifact"], {"default": None}),
        ],
    )
    add("accept", cmd_accept, [(["record_id"], {})])
    add("reject", cmd_reject, [(["record_id"], {})])
    add("status", cmd_status)
    add(
        "export",
        cmd_export,
        [
            (["--format"], {"choices": ["json", "markdown"], "default": "json"}),
            (["--out"], {"default": None}),
        ],
    )
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
        return 0
    except LCEUserError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.exit_code
    except Exception as e:
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
