from __future__ import annotations

import json
from pathlib import Path

from living_context.connectors.base import ConnectorError, ConnectorResult, require, source_kind
from living_context.observe import load_packets, packet_from_text
from living_context.extract import observed_at

SUPPORTED = {".json", ".jsonl", ".md", ".txt"}
MAX_FILES = 500


class FileDropConnector:
    """A landing directory anything can write into.

    This is the escape hatch that makes the engine reachable from tools it has
    never heard of: Zapier, n8n, Make, a cron job, a Shortcut, an email rule.
    Drop a packet or a note in the folder and it gets staged for review.
    """

    name = "filedrop"
    description = "Ingest packets or notes dropped into a directory by any external tool"
    required_config = ("path",)
    example = {"path": ".lce/inbox", "kind": "document", "archive": True}

    def fetch(self, config: dict, cursor: str, root: Path | None = None) -> ConnectorResult:
        require(config, *self.required_config)
        kind = source_kind(config, "document")
        directory = Path(config["path"])
        if root and not directory.is_absolute():
            directory = root / directory
        if not directory.is_dir():
            raise ConnectorError(f"not a directory: {directory}")

        packets: list[dict] = []
        notes: list[str] = []
        newest = cursor
        processed: list[Path] = []

        candidates = sorted(
            item
            for item in directory.rglob("*")
            if item.is_file() and not item.is_symlink() and item.suffix.lower() in SUPPORTED
        )
        if len(candidates) > MAX_FILES:
            notes.append(f"only the first {MAX_FILES} files were read")
            candidates = candidates[:MAX_FILES]

        for item in candidates:
            stamp = observed_at(item)
            if cursor and stamp <= cursor:
                continue
            reference = item.relative_to(directory).as_posix()
            try:
                if item.suffix.lower() in {".json", ".jsonl"}:
                    for entry in load_packets(item):
                        if isinstance(entry, dict) and ("claims" in entry or "source" in entry):
                            entry.setdefault("source", {}).setdefault("ref", reference)
                            packets.append(entry)
                else:
                    parsed = packet_from_text(
                        item.read_text(encoding="utf-8", errors="replace"),
                        source_ref=reference,
                        source_kind=kind,
                        observed_at=stamp,
                    )
                    if parsed["claims"] or parsed["unknowns"]:
                        packets.append(parsed)
            except (ValueError, OSError) as error:
                notes.append(f"{reference}: {error}")
                continue
            processed.append(item)
            if stamp > newest:
                newest = stamp

        if config.get("archive") and processed:
            archive = directory / "_processed"
            archive.mkdir(exist_ok=True)
            for item in processed:
                try:
                    item.rename(archive / item.name)
                except OSError as error:
                    notes.append(f"could not archive {item.name}: {error}")

        return ConnectorResult(packets=packets, cursor=newest, notes=notes)
