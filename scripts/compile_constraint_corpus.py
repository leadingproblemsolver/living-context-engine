#!/usr/bin/env python3
"""Merge multiple signal lists, deduplicate them, then run constraint intelligence."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def load_list(path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not load {path}: {exc}") from exc
    if not isinstance(data, list):
        raise SystemExit(f"{path} must contain a JSON list")
    return [item for item in data if isinstance(item, dict)]


def identity(record: dict[str, Any], index: int) -> str:
    if record.get("signal_id"):
        return str(record["signal_id"])
    repository = str(record.get("repository", ""))
    number = record.get("number")
    if repository and number is not None:
        return f"github:{repository}#{number}"
    if record.get("url"):
        return str(record["url"])
    return f"anonymous:{index}:{record.get('title', '')}"


def merge(inputs: list[Path]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    counter = 0
    for path in inputs:
        for record in load_list(path):
            counter += 1
            key = identity(record, counter)
            if key not in merged:
                merged[key] = record
                continue
            # Later inputs enrich earlier seed evidence without erasing populated fields.
            combined = dict(merged[key])
            for field, value in record.items():
                if value not in (None, "", [], {}):
                    combined[field] = value
            merged[key] = combined
    return list(merged.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--taxonomy", type=Path, default=Path("config/constraint_taxonomy.json"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/constraint-intelligence.json"))
    parser.add_argument("--constraints", type=Path, default=Path("artifacts/constraint-leaderboard.json"))
    parser.add_argument("--markdown", type=Path, default=Path("artifacts/constraint-intelligence.md"))
    args = parser.parse_args()

    corpus = merge(args.input)
    with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
        json.dump(corpus, handle, indent=2)
        handle.write("\n")
        temp_path = Path(handle.name)

    try:
        command = [
            sys.executable,
            "scripts/build_constraint_intelligence.py",
            "--input", str(temp_path),
            "--taxonomy", str(args.taxonomy),
            "--output", str(args.output),
            "--constraints", str(args.constraints),
            "--markdown", str(args.markdown),
        ]
        completed = subprocess.run(command, check=False)
        return completed.returncode
    finally:
        temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
