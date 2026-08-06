from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "discover_github_issues.py"
SPEC = spec_from_file_location("discover_github_issues", SCRIPT)
assert SPEC and SPEC.loader
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_build_query_preserves_issue_and_safety_filters():
    query = {
        "id": "test",
        "terms": ["losing context", "decision log"],
        "exclude_labels": ["duplicate", "invalid"],
    }

    rendered = MODULE.build_query(query, "2026-05-01")

    assert "is:issue is:open" in rendered
    assert '"losing context" OR "decision log"' in rendered
    assert 'created:>2026-05-01' in rendered
    assert '-label:"duplicate"' in rendered
    assert "archived:false" in rendered


def test_score_prefers_specific_active_human_pain():
    item = {
        "number": 42,
        "title": "How can I stop losing context during project handoffs?",
        "body": "We need a way to resume work with a source line audit trail and decision log.",
        "html_url": "https://github.com/example/repo/issues/42",
        "repository_url": "https://api.github.com/repos/example/repo",
        "created_at": "2026-08-01T00:00:00Z",
        "updated_at": "2026-08-02T00:00:00Z",
        "comments": 4,
        "user": {"login": "human-author"},
        "labels": [],
    }
    query = {
        "id": "context-loss",
        "terms": ["losing context", "resume work", "source line", "decision log"],
        "help_angle": "Offer a source-linked context pack.",
    }

    candidate = MODULE.score_item(item, query)

    assert candidate.repository == "example/repo"
    assert candidate.score >= 75
    assert candidate.spam_penalty == 0
    assert "decision log" in candidate.matched_terms


def test_score_penalizes_bot_or_stale_noise():
    item = {
        "number": 7,
        "title": "Decision log dependency update",
        "body": "Automated update.",
        "html_url": "https://github.com/example/repo/issues/7",
        "repository_url": "https://api.github.com/repos/example/repo",
        "created_at": "2026-08-01T00:00:00Z",
        "updated_at": "2026-08-01T00:00:00Z",
        "comments": 0,
        "user": {"login": "dependabot[bot]"},
        "labels": [{"name": "stale"}],
    }
    query = {"id": "decision", "terms": ["decision log"]}

    candidate = MODULE.score_item(item, query)

    assert candidate.spam_penalty == 20
    assert candidate.score < 55
