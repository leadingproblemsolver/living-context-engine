from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from living_context import decisions as decision_board
from living_context import review
from living_context.config import load_config
from living_context.context import build_context
from living_context.digest import build as build_digest
from living_context.digest import render_html
from living_context.store import Store

MAX_BODY_BYTES = 5 * 1024 * 1024


class Handler(BaseHTTPRequestHandler):
    root = Path.cwd()
    database = "data/living-context.sqlite"
    half_life_days = 180.0
    default_project: str | None = None
    token: str | None = None
    write_token: str | None = None
    cors_origin: str | None = None

    def send_json(self, status: int, payload: object) -> None:
        data = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        request_origin = self.headers.get("Origin")
        if self.cors_origin and request_origin == self.cors_origin:
            self.send_header("Access-Control-Allow-Origin", self.cors_origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
        self.wfile.write(data)

    def authorized(self) -> bool:
        supplied = self.headers.get("Authorization", "")
        if self.write_token and hmac.compare_digest(supplied, f"Bearer {self.write_token}"):
            return True
        if not self.token:
            return True
        return hmac.compare_digest(supplied, f"Bearer {self.token}")

    def write_authorized(self) -> bool:
        """Writing needs its own token. A read token can never propose state."""
        if not self.write_token:
            return False
        supplied = self.headers.get("Authorization", "")
        return hmac.compare_digest(supplied, f"Bearer {self.write_token}")

    def do_OPTIONS(self) -> None:
        origin = self.headers.get("Origin")
        if not self.cors_origin or origin != self.cors_origin:
            return self.send_json(403, {"error": "cors_origin_not_allowed"})
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self.cors_origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    @staticmethod
    def bounded_integer(raw: str, default: int, maximum: int) -> int:
        try:
            return min(maximum, max(1, int(raw)))
        except (TypeError, ValueError):
            return default

    def _project(self, params: dict) -> str | None:
        value = params.get("project", [None])[0]
        return value or self.default_project

    def send_html(self, status: int, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        """The only write surface: propose observations. Never applies them."""
        parsed = urlparse(self.path)
        if parsed.path != "/api/observations":
            return self.send_json(404, {"error": "not_found"})
        if not self.write_authorized():
            return self.send_json(
                401,
                {
                    "error": "write_token_required",
                    "detail": "set LCE_API_WRITE_TOKEN and send it as a bearer token",
                },
            )
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.send_json(400, {"error": "bad_content_length"})
        if length <= 0:
            return self.send_json(400, {"error": "empty_body"})
        if length > MAX_BODY_BYTES:
            return self.send_json(413, {"error": "body_too_large"})
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            return self.send_json(400, {"error": "invalid_json", "detail": str(error)})

        params = parse_qs(parsed.query)
        project = self._project(params) or (
            payload.get("project") if isinstance(payload, dict) else None
        )
        if not project:
            return self.send_json(400, {"error": "project_required"})

        packets = []
        if isinstance(payload, dict):
            packets = payload.get("packets") if isinstance(payload.get("packets"), list) else [payload]
        elif isinstance(payload, list):
            packets = payload
        packets = [item for item in packets if isinstance(item, dict)]
        if not packets:
            return self.send_json(400, {"error": "no_packets"})

        key = self.headers.get("Idempotency-Key", "").strip()
        store = Store(self.root, self.database)
        try:
            if key:
                remembered = store.remembered_response(key)
                if remembered is not None:
                    return self.send_json(200, {**remembered, "replayed": True})
            staged, errors = [], []
            for packet in packets:
                try:
                    staged.append(
                        review.stage_packet(
                            store, project, packet, "api", packet.get("source", {}).get("ref", "api")
                        )
                    )
                except ValueError as error:
                    errors.append(str(error))
            response = {
                "project": project,
                "accepted_for_review": len(staged),
                "rejected": errors,
                "pending_total": len(store.proposals(project, "pending", limit=1000)),
                "note": "staged for review; run `lce review` to apply",
            }
            if key:
                store.remember_response(key, project, response)
            return self.send_json(200 if staged else 400, response)
        finally:
            store.close()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/health", "/health/live"):
            return self.send_json(200, {"status": "ok"})
        if parsed.path in ("/", "/index.html"):
            if not self.authorized():
                return self.send_json(401, {"error": "unauthorized"})
            params = parse_qs(parsed.query)
            project = self._project(params)
            if not project:
                return self.send_html(
                    200,
                    "<!doctype html><meta charset=utf-8><title>Living Context</title>"
                    "<p>Pass <code>?project=&lt;id&gt;</code>, or configure a project "
                    "in <code>.lce/config.json</code>.</p>",
                )
            store = Store(self.root, self.database)
            try:
                report = build_digest(
                    store, project, params.get("since", [None])[0], self.half_life_days
                )
                return self.send_html(200, render_html(report))
            finally:
                store.close()
        if not self.authorized():
            return self.send_json(401, {"error": "unauthorized"})

        store = Store(self.root, self.database)
        try:
            params = parse_qs(parsed.query)
            project = self._project(params)

            if parsed.path == "/health/ready":
                return self.send_json(200, {"status": "ok", **store.status()})
            if parsed.path == "/api/status":
                return self.send_json(200, store.status())
            if parsed.path == "/api/projects":
                return self.send_json(200, {"projects": store.projects()})

            if parsed.path == "/api/query":
                limit = self.bounded_integer(params.get("limit", ["20"])[0], 20, 100)
                return self.send_json(
                    200,
                    {
                        "items": store.query(
                            params.get("q", [""])[0][:500], project, limit=limit
                        )
                    },
                )
            if parsed.path == "/api/timeline":
                limit = self.bounded_integer(params.get("limit", ["100"])[0], 100, 500)
                return self.send_json(200, {"items": store.timeline(project, limit)})

            # State-layer endpoints all require a project.
            state_paths = {
                "/api/state",
                "/api/entities",
                "/api/delta",
                "/api/contradictions",
                "/api/unknowns",
                "/api/actions",
                "/api/metric",
                "/api/context",
                "/api/proposals",
                "/api/decisions",
                "/api/digest",
            }
            if parsed.path in state_paths and not project:
                return self.send_json(400, {"error": "project_required"})

            if parsed.path == "/api/state":
                return self.send_json(
                    200,
                    {
                        "items": store.state(
                            project,
                            entity=params.get("entity", [None])[0],
                            half_life_days=self.half_life_days,
                        )
                    },
                )
            if parsed.path == "/api/entities":
                return self.send_json(
                    200,
                    {"items": store.entities(project, kind=params.get("kind", [None])[0])},
                )
            if parsed.path == "/api/delta":
                limit = self.bounded_integer(params.get("limit", ["50"])[0], 50, 500)
                return self.send_json(
                    200,
                    {
                        "items": store.transitions(
                            project, since=params.get("since", [None])[0], limit=limit
                        )
                    },
                )
            if parsed.path == "/api/contradictions":
                status = params.get("status", ["open"])[0]
                return self.send_json(
                    200, {"items": store.contradictions(project, status or None)}
                )
            if parsed.path == "/api/unknowns":
                status = params.get("status", ["open"])[0]
                return self.send_json(200, {"items": store.unknowns(project, status or None)})
            if parsed.path == "/api/actions":
                limit = self.bounded_integer(params.get("limit", ["20"])[0], 20, 200)
                status = params.get("status", ["proposed"])[0]
                return self.send_json(
                    200, {"items": store.actions(project, status or None, limit)}
                )
            if parsed.path == "/api/metric":
                limit = self.bounded_integer(params.get("limit", ["20"])[0], 20, 200)
                return self.send_json(
                    200,
                    {
                        "current": store.uncertainty(project, self.half_life_days),
                        "history": store.metrics(project, limit),
                    },
                )
            if parsed.path == "/api/proposals":
                status = params.get("status", ["pending"])[0]
                limit = self.bounded_integer(params.get("limit", ["50"])[0], 50, 500)
                return self.send_json(
                    200,
                    {
                        "items": store.proposals(project, status or None, limit=limit),
                        "acceptance": store.proposal_stats(project),
                    },
                )
            if parsed.path == "/api/decisions":
                return self.send_json(
                    200, {"items": decision_board.board(store, project, self.half_life_days)}
                )
            if parsed.path == "/api/digest":
                return self.send_json(
                    200,
                    build_digest(
                        store, project, params.get("since", [None])[0], self.half_life_days
                    ),
                )
            if parsed.path == "/api/context":
                task = params.get("task", params.get("q", [""]))[0][:500]
                if not task:
                    return self.send_json(400, {"error": "task_required"})
                limit = self.bounded_integer(params.get("limit", ["25"])[0], 25, 100)
                return self.send_json(
                    200,
                    build_context(
                        store, project, task, limit=limit, half_life_days=self.half_life_days
                    ),
                )
            return self.send_json(404, {"error": "not_found"})
        finally:
            store.close()

    def log_message(self, fmt: str, *args: object) -> None:
        return


def serve(
    root: Path,
    host: str = "127.0.0.1",
    port: int = 8790,
    database: str = "data/living-context.sqlite",
) -> None:
    token = os.environ.get("LCE_API_TOKEN")
    write_token = os.environ.get("LCE_API_WRITE_TOKEN")
    if host not in {"127.0.0.1", "localhost", "::1"} and not token:
        raise RuntimeError("LCE_API_TOKEN is required when binding beyond loopback")
    if write_token and write_token == token:
        raise RuntimeError(
            "LCE_API_WRITE_TOKEN must differ from LCE_API_TOKEN; otherwise every "
            "reader can propose state"
        )
    try:
        config = load_config(Path(root))
    except ValueError:
        config = None
    Handler.root = root
    Handler.database = database
    Handler.half_life_days = config.half_life_days if config else 180.0
    Handler.default_project = (config.project or None) if config else None
    Handler.token = token
    Handler.write_token = write_token
    Handler.cors_origin = os.environ.get("LCE_CORS_ORIGIN")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Living Context API listening on http://{host}:{port}")
    server.serve_forever()
