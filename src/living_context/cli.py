from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from living_context.extract import extract_path
from living_context.packs import build_pack
from living_context.server import serve
from living_context.store import Store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lce",
        description="Turn project files into traceable, queryable operational context.",
    )
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest")
    ingest.add_argument("path")
    ingest.add_argument("--project", required=True)

    query = sub.add_parser("query")
    query.add_argument("text")
    query.add_argument("--project")
    query.add_argument("--kind", action="append")
    query.add_argument("--limit", type=int, default=20)
    query.add_argument("--json", action="store_true")

    timeline = sub.add_parser("timeline")
    timeline.add_argument("--project")
    timeline.add_argument("--limit", type=int, default=100)
    timeline.add_argument("--json", action="store_true")

    pack = sub.add_parser("pack")
    pack.add_argument("text")
    pack.add_argument("--project")
    pack.add_argument("--output", default="artifacts/context-pack.md")
    pack.add_argument("--limit", type=int, default=30)

    export = sub.add_parser("export")
    export.add_argument("--output", required=True)
    export.add_argument("--format", choices=["json", "csv"], default="json")
    export.add_argument("--project")

    server = sub.add_parser("serve")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8790)

    sub.add_parser("status")
    sub.add_parser("projects")
    delete_project = sub.add_parser("delete-project")
    delete_project.add_argument("project")
    delete_project.add_argument("--yes", action="store_true")
    sub.add_parser("validate")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).resolve()

    if args.command == "serve":
        serve(root, args.host, args.port)
        return 0

    store = Store(root)
    try:
        if args.command == "ingest":
            records = extract_path(Path(args.path), args.project, root)
            print(json.dumps(store.ingest(records), indent=2))
            return 0

        if args.command == "query":
            items = store.query(
                args.text,
                args.project,
                set(args.kind or []),
                args.limit,
            )
            if args.json:
                print(json.dumps(items, indent=2))
            elif items:
                print(
                    "\n".join(
                        f"[{item['score']:.2f}] {item['kind']} — {item['text']} "
                        f"({item['source_path']}:{item['source_line']})"
                        for item in items
                    )
                )
            else:
                print("No matching context.")
            return 0

        if args.command == "timeline":
            items = store.timeline(args.project, args.limit)
            if args.json:
                print(json.dumps(items, indent=2))
            elif items:
                print(
                    "\n".join(
                        f"{item['observed_at']} | {item['kind']} | {item['text']} | "
                        f"{item['source_path']}:{item['source_line']}"
                        for item in items
                    )
                )
            else:
                print("No context ingested.")
            return 0

        if args.command == "pack":
            result = build_pack(
                store,
                args.text,
                Path(args.output),
                args.project,
                args.limit,
            )
            print(json.dumps(result, indent=2))
            return 0

        if args.command == "export":
            rows = store.timeline(args.project, 100000)
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            if args.format == "json":
                output.write_text(json.dumps(rows, indent=2, sort_keys=True), encoding="utf-8")
            else:
                fields = [
                    "record_id",
                    "project",
                    "kind",
                    "text",
                    "source_path",
                    "source_line",
                    "source_hash",
                    "observed_at",
                    "status",
                ]
                with output.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows({key: row.get(key) for key in fields} for row in rows)
            print(output)
            return 0

        if args.command == "status":
            print(json.dumps(store.status(), indent=2, sort_keys=True))
            return 0

        if args.command == "projects":
            print(json.dumps({"projects": store.projects()}, indent=2, sort_keys=True))
            return 0

        if args.command == "delete-project":
            if not args.yes:
                print(json.dumps({"status": "blocked", "reason": "pass --yes to confirm destructive deletion"}, indent=2))
                return 2
            print(json.dumps(store.delete_project(args.project), indent=2))
            return 0

        if args.command == "validate":
            required = [
                "README.md",
                "pyproject.toml",
                "src/living_context/cli.py",
                "examples/project-notes.md",
            ]
            missing = [relative for relative in required if not (root / relative).exists()]
            result = {
                "status": "ok" if not missing else "fail",
                "missing": missing,
                **store.status(),
            }
            print(json.dumps(result, indent=2))
            return 0 if not missing else 1
    finally:
        store.close()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
