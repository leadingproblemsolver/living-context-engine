from __future__ import annotations

import json
import sys
from pathlib import Path

from living_context import decisions as decision_board
from living_context import prompts as prompt_library
from living_context import review
from living_context.config import load_config, resolve_project
from living_context.context import build_context, explain_claim, render_markdown
from living_context.digest import build as build_digest
from living_context.digest import render_markdown as render_digest
from living_context.store import Store

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "living-context-engine"

# The engine as a tool the user's own assistant can reach. This is the surface
# that matters most for adoption: the graph becomes available inside whatever
# the user is already doing, and proposals flow back without anyone leaving it.

_PROJECT = {"type": "string", "description": "Project id. Defaults to the configured project."}


def _schema(**properties) -> dict:
    return {"type": "object", "properties": {"project": _PROJECT, **properties}}


TOOLS = [
    {
        "name": "lce_context",
        "description": (
            "Assemble the decision-scoped context pack for a question: the relevant "
            "beliefs with confidence and provenance, what recently changed, conflicts "
            "in scope, open unknowns, and the ranked next actions. Use this before "
            "answering any question about what the team knows."
        ),
        "inputSchema": _schema(
            task={"type": "string", "description": "The decision or question to scope to."},
            limit={"type": "integer", "description": "Max entities (default 25)."},
        ),
    },
    {
        "name": "lce_state",
        "description": "Current beliefs with confidence and evidence counts, optionally for one entity.",
        "inputSchema": _schema(entity={"type": "string", "description": "Entity name or id."}),
    },
    {
        "name": "lce_why",
        "description": (
            "Explain one belief: its evidence, independent sources, method ceiling, how "
            "it got here, what disputes it, and what would move it."
        ),
        "inputSchema": _schema(claim_id={"type": "string", "description": "Claim id or prefix."}),
    },
    {
        "name": "lce_delta",
        "description": "State changes with the reason each belief moved.",
        "inputSchema": _schema(
            since={"type": "string", "description": "ISO-8601 lower bound."},
            limit={"type": "integer"},
        ),
    },
    {
        "name": "lce_contradictions",
        "description": "Open conflicts between active beliefs, with both sides and severity.",
        "inputSchema": _schema(),
    },
    {
        "name": "lce_unknowns",
        "description": "Open questions ranked by impact, with the decision each one blocks.",
        "inputSchema": _schema(),
    },
    {
        "name": "lce_actions",
        "description": "Ranked verification actions: what to do next to remove the most uncertainty.",
        "inputSchema": _schema(limit={"type": "integer"}),
    },
    {
        "name": "lce_decisions",
        "description": (
            "The decision board with readiness for each: can it be decided yet, what is "
            "the weakest belief it rests on, what is blocking it."
        ),
        "inputSchema": _schema(),
    },
    {
        "name": "lce_digest",
        "description": "The recurring summary: what moved, new conflicts, decidable decisions, next moves.",
        "inputSchema": _schema(since={"type": "string"}),
    },
    {
        "name": "lce_propose_observation",
        "description": (
            "Propose a state update from something you just learned. Takes an observation "
            "packet (source, entities, claims with evidence, unknowns). Every claim needs "
            "evidence. Nothing is applied directly — it is staged for human review."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": _PROJECT,
                "packet": {
                    "type": "object",
                    "description": "An observation packet. Call lce_packet_schema for the shape.",
                },
            },
            "required": ["packet"],
        },
    },
    {
        "name": "lce_packet_schema",
        "description": "The JSON schema for observation packets, plus the extraction rules.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "lce_review_queue",
        "description": "Proposals waiting for a human, with acceptance rates per source.",
        "inputSchema": _schema(limit={"type": "integer"}),
    },
]


class Server:
    def __init__(self, root: Path, project: str | None = None):
        self.root = Path(root)
        self.config = load_config(self.root)
        self.project_override = project

    # -- plumbing ----------------------------------------------------------

    def project_for(self, arguments: dict) -> str:
        return resolve_project(self.config, arguments.get("project") or self.project_override)

    def _store(self) -> Store:
        return Store(self.root, self.config.database)

    def handle(self, message: dict) -> dict | None:
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        if method == "initialize":
            return self._ok(
                request_id,
                {
                    "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
                    "capabilities": {"tools": {}, "prompts": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": self._version()},
                    "instructions": (
                        "This project keeps a traceable model of what the team believes, "
                        "with confidence derived from evidence. Call lce_context before "
                        "answering questions about the project's knowledge, cite the "
                        "confidence you find, and use lce_propose_observation to record "
                        "anything new you learn."
                    ),
                },
            )
        if method in {"notifications/initialized", "notifications/cancelled"}:
            return None
        if method == "ping":
            return self._ok(request_id, {})
        if method == "tools/list":
            return self._ok(request_id, {"tools": TOOLS})
        if method == "prompts/list":
            return self._ok(
                request_id,
                {
                    "prompts": [
                        {
                            "name": item["name"],
                            "description": item["description"],
                            "arguments": [
                                {"name": "task", "description": "Decision question", "required": False},
                                {"name": "id", "description": "Contradiction id", "required": False},
                            ],
                        }
                        for item in prompt_library.list_prompts()
                    ]
                },
            )
        if method == "prompts/get":
            return self._prompt(request_id, params)
        if method == "tools/call":
            return self._call(request_id, params)
        if request_id is None:
            return None
        return self._error(request_id, -32601, f"unknown method: {method}")

    @staticmethod
    def _version() -> str:
        from living_context import __version__

        return __version__

    @staticmethod
    def _ok(request_id, result) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    @staticmethod
    def _content(payload: object, is_error: bool = False) -> dict:
        text = payload if isinstance(payload, str) else json.dumps(payload, indent=2, default=str)
        return {"content": [{"type": "text", "text": text}], "isError": is_error}

    # -- dispatch ----------------------------------------------------------

    def _prompt(self, request_id, params: dict) -> dict:
        name = params.get("name") or ""
        arguments = params.get("arguments") or {}
        store = self._store()
        try:
            project = self.project_for(arguments)
            rendered = prompt_library.render_prompt(name, store, project, arguments)
        except ValueError as error:
            return self._error(request_id, -32602, str(error))
        finally:
            store.close()
        return self._ok(
            request_id,
            {
                "description": f"living-context: {name}",
                "messages": [{"role": "user", "content": {"type": "text", "text": rendered}}],
            },
        )

    def _call(self, request_id, params: dict) -> dict:
        name = params.get("name") or ""
        arguments = params.get("arguments") or {}

        if name == "lce_packet_schema":
            from living_context.observe import OBSERVATION_SCHEMA

            return self._ok(
                request_id,
                self._content(
                    {"schema": OBSERVATION_SCHEMA, "rules": prompt_library.EXTRACTION_RULES}
                ),
            )

        store = self._store()
        try:
            project = self.project_for(arguments)
            half_life = self.config.half_life_days
            limit = int(arguments.get("limit") or 20)

            if name == "lce_context":
                task = str(arguments.get("task") or "").strip()
                if not task:
                    return self._ok(request_id, self._content("task is required", True))
                pack = build_context(
                    store, project, task, limit=int(arguments.get("limit") or 25),
                    half_life_days=half_life,
                )
                return self._ok(request_id, self._content(render_markdown(pack)))
            if name == "lce_state":
                return self._ok(
                    request_id,
                    self._content(
                        store.state(
                            project,
                            entity=arguments.get("entity"),
                            half_life_days=half_life,
                        )
                    ),
                )
            if name == "lce_why":
                from living_context.context import render_explanation

                report = explain_claim(
                    store, project, str(arguments.get("claim_id") or ""), half_life
                )
                return self._ok(request_id, self._content(render_explanation(report)))
            if name == "lce_delta":
                return self._ok(
                    request_id,
                    self._content(
                        store.transitions(project, since=arguments.get("since"), limit=limit)
                    ),
                )
            if name == "lce_contradictions":
                return self._ok(
                    request_id, self._content(store.contradictions(project, "open", half_life))
                )
            if name == "lce_unknowns":
                return self._ok(request_id, self._content(store.unknowns(project, "open")))
            if name == "lce_actions":
                return self._ok(
                    request_id, self._content(store.actions(project, "proposed", limit))
                )
            if name == "lce_decisions":
                return self._ok(
                    request_id, self._content(decision_board.board(store, project, half_life))
                )
            if name == "lce_digest":
                report = build_digest(store, project, arguments.get("since"), half_life)
                return self._ok(request_id, self._content(render_digest(report)))
            if name == "lce_review_queue":
                return self._ok(
                    request_id,
                    self._content(
                        {
                            "pending": store.proposals(project, "pending", limit=limit),
                            "acceptance": store.proposal_stats(project),
                        }
                    ),
                )
            if name == "lce_propose_observation":
                packet = arguments.get("packet")
                if not isinstance(packet, dict):
                    return self._ok(request_id, self._content("packet must be an object", True))
                staged = review.stage_packet(store, project, packet, "model", "mcp")
                return self._ok(
                    request_id,
                    self._content(
                        {
                            **staged,
                            "note": (
                                "Staged for review. Run `lce review` to accept or reject. "
                                "Nothing has entered the graph yet."
                            ),
                        }
                    ),
                )
            return self._ok(request_id, self._content(f"unknown tool: {name}", True))
        except ValueError as error:
            return self._ok(request_id, self._content(str(error), True))
        finally:
            store.close()


def serve(root: Path, project: str | None = None, stream=None, output=None) -> None:
    """Read newline-delimited JSON-RPC from stdin, write responses to stdout."""
    server = Server(root, project)
    stream = stream or sys.stdin
    output = output or sys.stdout
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            output.write(
                json.dumps(
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
                )
                + "\n"
            )
            output.flush()
            continue
        response = server.handle(message)
        if response is not None:
            output.write(json.dumps(response, default=str) + "\n")
            output.flush()
