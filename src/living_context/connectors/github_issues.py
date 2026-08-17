from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from living_context.connectors.base import ConnectorError, ConnectorResult, require, source_kind
from living_context.observe import packet_from_text

API = "https://api.github.com"
PAGE_SIZE = 50
MAX_PAGES = 10


def fetch_json(url: str, token: str = "", timeout: float = 20.0) -> object:
    """Isolated so the connector can be tested without a network."""
    request = urllib.request.Request(url)
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("User-Agent", "living-context-engine")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise ConnectorError(f"GitHub returned {error.code} for {url}: {detail}") from error
    except urllib.error.URLError as error:
        raise ConnectorError(f"could not reach GitHub: {error.reason}") from error


class GitHubIssuesConnector:
    """Issues and their comments as observations.

    Teams already write decisions, blockers, and open questions in issues. The
    claim syntax works inside an issue body, so a team can adopt the engine
    without leaving the tracker.
    """

    name = "github_issues"
    description = "Read issues and comments from a repository as observations"
    required_config = ("repo",)
    example = {
        "repo": "owner/name",
        "labels": ["research"],
        "state": "all",
        "kind": "document",
        "token_env": "GITHUB_TOKEN",
        "include_comments": True,
    }

    def fetch(self, config: dict, cursor: str, root=None) -> ConnectorResult:
        require(config, *self.required_config)
        repo = str(config["repo"]).strip("/")
        if repo.count("/") != 1:
            raise ConnectorError("config.repo must be 'owner/name'")
        kind = source_kind(config, "document")
        token = os.environ.get(str(config.get("token_env") or "GITHUB_TOKEN"), "")
        transport = config.get("_transport") or fetch_json

        query = {
            "state": str(config.get("state") or "all"),
            "per_page": str(PAGE_SIZE),
            "sort": "updated",
            "direction": "asc",
        }
        if cursor:
            query["since"] = cursor
        labels = config.get("labels") or []
        if labels:
            query["labels"] = ",".join(str(item) for item in labels)

        packets: list[dict] = []
        notes: list[str] = []
        newest = cursor
        for page in range(1, MAX_PAGES + 1):
            url = f"{API}/repos/{repo}/issues?{urllib.parse.urlencode({**query, 'page': page})}"
            batch = transport(url, token)
            if not isinstance(batch, list):
                raise ConnectorError(f"unexpected response from {url}")
            if not batch:
                break
            for issue in batch:
                if not isinstance(issue, dict):
                    continue
                number = issue.get("number")
                updated = str(issue.get("updated_at") or "")
                ref = f"{repo}#{number}"
                body = str(issue.get("body") or "")
                title = str(issue.get("title") or "")
                actor = str((issue.get("user") or {}).get("login") or "")
                text = f"{title}\n\n{body}"

                if config.get("include_comments", True) and issue.get("comments"):
                    comments = transport(
                        f"{API}/repos/{repo}/issues/{number}/comments?per_page={PAGE_SIZE}", token
                    )
                    if isinstance(comments, list):
                        for comment in comments:
                            if isinstance(comment, dict):
                                text += "\n\n" + str(comment.get("body") or "")

                parsed = packet_from_text(
                    text, source_ref=ref, source_kind=kind, actor=actor, observed_at=updated
                )
                issue_labels = {
                    str((label or {}).get("name") if isinstance(label, dict) else label).lower()
                    for label in (issue.get("labels") or [])
                }
                # A labelled issue with no explicit statement is still a signal:
                # its title is the open question.
                if not parsed["claims"] and not parsed["unknowns"]:
                    if issue_labels & {"question", "unknown", "research"} or title.rstrip().endswith("?"):
                        parsed["unknowns"] = [
                            {
                                "question": title,
                                "impact": 0.6,
                                "blocks_decision": "",
                            }
                        ]
                    else:
                        continue
                packets.append(parsed)
                if updated > newest:
                    newest = updated
            if len(batch) < PAGE_SIZE:
                break
        else:
            notes.append(f"stopped after {MAX_PAGES} pages; run again to continue")

        return ConnectorResult(packets=packets, cursor=newest, notes=notes)
