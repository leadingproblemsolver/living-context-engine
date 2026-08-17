from __future__ import annotations

import json
from pathlib import Path

from living_context.connectors.base import ConnectorError, ConnectorResult, require, source_kind
from living_context.observe import packet_from_text

MAX_FILES = 2_000


class SlackExportConnector:
    """A Slack workspace export directory — no OAuth app required.

    Deliberately reads the export rather than the API: a team can try the engine
    on the last quarter of their own conversations without asking anyone for an
    app install. Messages default to `assertion` strength, because that is what
    they are.
    """

    name = "slack_export"
    description = "Read a Slack export directory (channel/YYYY-MM-DD.json) as observations"
    required_config = ("path",)
    example = {
        "path": "~/Downloads/slack-export",
        "channels": ["product", "research"],
        "kind": "assertion",
    }

    def fetch(self, config: dict, cursor: str, root: Path | None = None) -> ConnectorResult:
        require(config, *self.required_config)
        kind = source_kind(config, "assertion")
        directory = Path(str(config["path"])).expanduser()
        if root and not directory.is_absolute():
            directory = root / directory
        if not directory.is_dir():
            raise ConnectorError(f"not a Slack export directory: {directory}")

        wanted = {str(item).lstrip("#") for item in (config.get("channels") or [])}
        users = self._users(directory)

        packets: list[dict] = []
        notes: list[str] = []
        newest = cursor
        files = sorted(
            item
            for item in directory.glob("*/*.json")
            if item.is_file() and not item.is_symlink()
        )
        if len(files) > MAX_FILES:
            notes.append(f"only the first {MAX_FILES} day files were read")
            files = files[:MAX_FILES]

        for item in files:
            channel = item.parent.name
            if wanted and channel not in wanted:
                continue
            day = item.stem
            if cursor and day <= cursor:
                continue
            try:
                messages = json.loads(item.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as error:
                notes.append(f"{channel}/{item.name}: {error}")
                continue
            if not isinstance(messages, list):
                continue

            lines = []
            for message in messages:
                if not isinstance(message, dict) or message.get("subtype"):
                    continue
                text = str(message.get("text") or "").strip()
                if not text:
                    continue
                author = users.get(str(message.get("user") or ""), str(message.get("user") or ""))
                lines.append(f"@actor {author}" if author else "")
                lines.append(text)
            if not lines:
                continue

            parsed = packet_from_text(
                "\n".join(line for line in lines if line),
                source_ref=f"slack/{channel}/{day}",
                source_kind=kind,
                observed_at=day,
            )
            if parsed["claims"] or parsed["unknowns"]:
                packets.append(parsed)
            if day > newest:
                newest = day

        if not packets and not notes:
            notes.append(
                "no explicit statements found. Slack only becomes state where "
                "someone wrote a `claim:` or `unknown:` line, or where you run the "
                "text through `lce prompt extract`."
            )
        return ConnectorResult(packets=packets, cursor=newest, notes=notes)

    @staticmethod
    def _users(directory: Path) -> dict[str, str]:
        path = directory / "users.json"
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        if not isinstance(payload, list):
            return {}
        return {
            str(item.get("id")): str(item.get("name") or item.get("real_name") or item.get("id"))
            for item in payload
            if isinstance(item, dict) and item.get("id")
        }
