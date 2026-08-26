#!/usr/bin/env python3
"""Discover and score GitHub issues for human-reviewed constraint intelligence.

Uses only the Python standard library. Public searches work without a token at a
lower rate limit; set GITHUB_TOKEN for authenticated requests.

This script never posts comments. It preserves the issue evidence needed by the
constraint-intelligence compiler and produces a review queue for a human operator.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

API_URL = "https://api.github.com/search/issues"
USER_AGENT = "living-context-engine-review-pipeline/2.2"
# GitHub Search rejects queries with more than five explicit AND/OR/NOT operators.
# Five phrases require at most four OR operators and leave the safety qualifiers intact.
MAX_TERMS_PER_SEARCH = 5
# Authenticated issue search allows a bounded request rate but can still trigger
# secondary abuse protection on bursts. Pace searches and recover conservatively.
SEARCH_PACE_SECONDS = 2.2
SECONDARY_RETRY_LIMIT = 3
SECONDARY_BACKOFF_SECONDS = 5.0


@dataclass(frozen=True)
class Candidate:
    repository: str
    number: int
    title: str
    body: str
    url: str
    created_at: str
    updated_at: str
    comments: int
    author: str
    labels: list[str]
    query_id: str
    matched_terms: list[str]
    relevance: int
    intent: int
    recency: int
    validation: int
    spam_penalty: int
    score: int
    reason: str
    draft_angle: str
    source_platform: str = "github"
    unresolved: bool = True
    contribution_gap: bool = True


def load_config(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not load config {path}: {exc}") from exc
    if not isinstance(data.get("queries"), list):
        raise SystemExit("Config must contain a 'queries' list")
    return data


def github_get(params: dict[str, str], token: str | None) -> dict[str, Any]:
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)

    for attempt in range(SECONDARY_RETRY_LIMIT + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            secondary_limited = exc.code == 403 and "secondary rate limit" in body.lower()
            if secondary_limited and attempt < SECONDARY_RETRY_LIMIT:
                retry_after = exc.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else SECONDARY_BACKOFF_SECONDS * (2 ** attempt)
                except ValueError:
                    delay = SECONDARY_BACKOFF_SECONDS * (2 ** attempt)
                time.sleep(max(delay, SEARCH_PACE_SECONDS))
                continue
            raise RuntimeError(f"GitHub API returned {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"GitHub API request failed: {exc.reason}") from exc

    raise RuntimeError("GitHub API search retry budget exhausted")


def age_score(created_at: str) -> int:
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    days = max(0, (datetime.now(timezone.utc) - created).days)
    if days <= 14:
        return 15
    if days <= 45:
        return 12
    if days <= 90:
        return 8
    return 3


def score_item(item: dict[str, Any], query: dict[str, Any]) -> Candidate:
    title = str(item.get("title", ""))
    body = str(item.get("body") or "")
    text = f"{title}\n{body}".lower()
    terms = [str(term).lower() for term in query.get("terms", [])]
    matched = sorted({term for term in terms if term in text})

    relevance = min(40, 12 + 7 * len(matched))
    intent_markers = (
        "how do i", "how can i", "need a way", "looking for", "workaround",
        "blocked", "production", "manual restart", "rollback", "downgrade",
        "duplicate", "silent", "stuck", "resume", "retry", "data loss",
        "customer", "enterprise", "hours", "days", "wrong user", "unauthorized",
    )
    intent = min(25, 7 + 4 * sum(marker in text for marker in intent_markers))
    recency = age_score(str(item.get("created_at")))
    comments = int(item.get("comments", 0))
    validation = 10 if comments >= 3 else 7 if comments >= 1 else 2

    login = str((item.get("user") or {}).get("login", ""))
    label_names = [str(label.get("name", "")) for label in item.get("labels", [])]
    labels_text = " ".join(label_names)
    spam_markers = ("dependabot", "renovate", "stale", "duplicate", "invalid", "good first issue")
    spam_penalty = 20 if any(marker in f"{login} {labels_text}".lower() for marker in spam_markers) else 0

    score = max(0, min(100, relevance + intent + recency + validation - spam_penalty))
    repository_url = str(item.get("repository_url", ""))
    repository = repository_url.removeprefix("https://api.github.com/repos/")
    angle = str(query.get("help_angle", "Preserve as market evidence by default; interact only when there is a concrete unresolved contribution gap."))
    reason = (
        f"Matched {len(matched)} signal terms; {comments} comments; "
        f"intent={intent}, recency={recency}, penalty={spam_penalty}."
    )
    return Candidate(
        repository=repository,
        number=int(item["number"]),
        title=title,
        body=body,
        url=str(item["html_url"]),
        created_at=str(item["created_at"]),
        updated_at=str(item["updated_at"]),
        comments=comments,
        author=login,
        labels=label_names,
        query_id=str(query["id"]),
        matched_terms=matched,
        relevance=relevance,
        intent=intent,
        recency=recency,
        validation=validation,
        spam_penalty=spam_penalty,
        score=score,
        reason=reason,
        draft_angle=angle,
    )


def build_query(query: dict[str, Any], created_after: str, terms: list[str] | None = None) -> str:
    selected_terms = [str(term) for term in (terms if terms is not None else query.get("terms", []))]
    phrases = " OR ".join(f'"{term}"' for term in selected_terms)
    exclusions = " ".join(f'-label:"{label}"' for label in query.get("exclude_labels", []))
    repositories = " ".join(f"repo:{repo}" for repo in query.get("repositories", []))
    phrase_clause = f"({phrases}) " if phrases else ""
    return (
        f"is:issue is:open created:>{created_after} {phrase_clause}"
        f"{repositories} {exclusions} archived:false"
    ).strip()


def build_queries(query: dict[str, Any], created_after: str) -> list[str]:
    """Split broad signal families into GitHub-legal boolean query batches."""
    terms = [str(term) for term in query.get("terms", [])]
    if not terms:
        return [build_query(query, created_after, [])]
    return [
        build_query(query, created_after, terms[index:index + MAX_TERMS_PER_SEARCH])
        for index in range(0, len(terms), MAX_TERMS_PER_SEARCH)
    ]


def render_markdown(candidates: list[Candidate]) -> str:
    lines = [
        "# GitHub signal review queue",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "> Human review required. Default public action is no comment. Preserve strong evidence even when intervention value is low.",
        "",
    ]
    for index, candidate in enumerate(candidates, start=1):
        lines.extend([
            f"## {index}. [{candidate.repository} #{candidate.number}]({candidate.url}) — discovery {candidate.score}/100",
            "",
            f"**{candidate.title}**",
            "",
            f"- Query: `{candidate.query_id}`",
            f"- Author: `{candidate.author}`; comments: {candidate.comments}",
            f"- Labels: {', '.join(candidate.labels) or 'none'}",
            f"- Matched terms: {', '.join(candidate.matched_terms) or 'none'}",
            f"- Qualification: {candidate.reason}",
            f"- Review angle: {candidate.draft_angle}",
            "- Next gate: compile constraint value independently from intervention value; inspect the full thread before any public action.",
            "",
        ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config/constraint_signal_queries.json"))
    parser.add_argument("--created-after", default="2026-05-01")
    parser.add_argument("--per-query", type=int, default=30)
    parser.add_argument("--min-score", type=int, default=45)
    parser.add_argument("--output", type=Path, default=Path("artifacts/github-review-queue.json"))
    parser.add_argument("--markdown", type=Path, default=Path("artifacts/github-review-queue.md"))
    args = parser.parse_args()

    config = load_config(args.config)
    token = os.getenv("GITHUB_TOKEN")
    candidates: dict[str, Candidate] = {}
    first_search = True

    for query in config["queries"]:
        for search in build_queries(query, args.created_after):
            if not first_search:
                time.sleep(SEARCH_PACE_SECONDS)
            first_search = False
            payload = github_get(
                {"q": search, "sort": "updated", "order": "desc", "per_page": str(args.per_query)},
                token,
            )
            for item in payload.get("items", []):
                if "pull_request" in item:
                    continue
                candidate = score_item(item, query)
                if candidate.score < args.min_score:
                    continue
                current = candidates.get(candidate.url)
                if current is None or candidate.score > current.score:
                    candidates[candidate.url] = candidate

    ranked = sorted(candidates.values(), key=lambda item: (-item.score, -item.comments, item.updated_at))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps([asdict(item) for item in ranked], indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(render_markdown(ranked), encoding="utf-8")
    print(f"Wrote {len(ranked)} qualified signals to {args.output} and {args.markdown}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
