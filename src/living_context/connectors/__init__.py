from __future__ import annotations

import json
from pathlib import Path

from living_context.connectors.base import ConnectorError, ConnectorResult
from living_context.connectors.csv_rows import CsvConnector
from living_context.connectors.filedrop import FileDropConnector
from living_context.connectors.github_issues import GitHubIssuesConnector
from living_context.connectors.slack_export import SlackExportConnector
from living_context.review import stage_packet
from living_context.store import Store

CONNECTORS = {
    connector.name: connector
    for connector in (
        CsvConnector(),
        GitHubIssuesConnector(),
        SlackExportConnector(),
        FileDropConnector(),
    )
}

CONFIG_RELATIVE = ".lce/connectors.json"


def catalogue() -> list[dict]:
    return [
        {
            "name": connector.name,
            "description": connector.description,
            "required_config": list(connector.required_config),
            "example": connector.example,
        }
        for connector in sorted(CONNECTORS.values(), key=lambda item: item.name)
    ]


def load_definitions(root: Path) -> list[dict]:
    path = Path(root) / CONFIG_RELATIVE
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ConnectorError(f"{CONFIG_RELATIVE} is not valid JSON: {error}") from error
    entries = payload.get("connectors") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise ConnectorError(f"{CONFIG_RELATIVE} must contain a list of connectors")
    definitions = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        if entry.get("enabled") is False:
            continue
        name = str(entry["name"])
        if name not in CONNECTORS:
            raise ConnectorError(
                f"unknown connector '{name}'. Available: {', '.join(sorted(CONNECTORS))}"
            )
        definitions.append(
            {
                "name": name,
                "id": str(entry.get("id") or name),
                "config": entry.get("config") or {},
            }
        )
    return definitions


def pull(
    store: Store,
    project: str,
    root: Path,
    definitions: list[dict],
    origin_prefix: str = "connector",
    dry_run: bool = False,
    reset: bool = False,
) -> dict:
    """Fetch from each configured source and stage what comes back.

    Connector output is never applied directly. A third-party system does not get
    to write your beliefs — it gets to propose them.
    """
    report = {"connectors": [], "packets": 0, "staged": 0, "errors": []}
    for definition in definitions:
        connector = CONNECTORS[definition["name"]]
        cursor = "" if reset else store.connector_cursor(project, definition["id"])
        entry = {
            "connector": definition["name"],
            "id": definition["id"],
            "cursor_before": cursor,
            "packets": 0,
            "staged": 0,
            "notes": [],
        }
        try:
            result: ConnectorResult = connector.fetch(definition["config"], cursor, root=root)
        except ConnectorError as error:
            entry["error"] = str(error)
            report["errors"].append(f"{definition['id']}: {error}")
            report["connectors"].append(entry)
            continue

        entry["notes"] = result.notes
        entry["packets"] = len(result.packets)
        report["packets"] += len(result.packets)
        origin = f"{origin_prefix}:{definition['name']}"
        for item in result.packets:
            if dry_run:
                continue
            try:
                staged = stage_packet(store, project, item, origin, source_ref=definition["id"])
            except ValueError as error:
                entry["notes"].append(str(error))
                continue
            entry["staged"] += sum(
                value for key, value in staged["staged"].items() if key != "duplicates"
            )
        report["staged"] += entry["staged"]
        if not dry_run:
            store.set_connector_cursor(
                project,
                definition["id"],
                result.cursor or cursor,
                f"{entry['packets']} packets, {entry['staged']} staged",
            )
        entry["cursor_after"] = result.cursor or cursor
        report["connectors"].append(entry)
    return report
