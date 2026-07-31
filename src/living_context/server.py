from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from living_context.config import load_config
from living_context.context import build_context
from living_context.store import Store


class Handler(BaseHTTPRequestHandler):
    root = Path.cwd()
    database = "data/living-context.sqlite"
    half_life_days = 180.0
    default_project: str | None = None
    token: str | None = None
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
        if not self.token:
            return True
        supplied = self.headers.get("Authorization", "")
        expected = f"Bearer {self.token}"
        return hmac.compare_digest(supplied, expected)

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

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("/health", "/health/live"):
            return self.send_json(200, {"status": "ok"})
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
    if host not in {"127.0.0.1", "localhost", "::1"} and not token:
        raise RuntimeError("LCE_API_TOKEN is required when binding beyond loopback")
    try:
        config = load_config(Path(root))
    except ValueError:
        config = None
    Handler.root = root
    Handler.database = database
    Handler.half_life_days = config.half_life_days if config else 180.0
    Handler.default_project = (config.project or None) if config else None
    Handler.token = token
    Handler.cors_origin = os.environ.get("LCE_CORS_ORIGIN")
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Living Context API listening on http://{host}:{port}")
    server.serve_forever()
