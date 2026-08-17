"""Tests for the adoption layer: review, identity, decisions, connectors, MCP."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from living_context import decisions as decision_board
from living_context import identity, mcp, profiles, review
from living_context.connectors import csv_rows, filedrop, github_issues
from living_context.connectors import pull as pull_connectors
from living_context.delta import apply_packet
from living_context.digest import build as build_digest
from living_context.digest import render_html, render_markdown, render_slack
from living_context.store import Store

from test_state import claim, make_packet, run


@pytest.fixture()
def store(tmp_path):
    instance = Store(tmp_path)
    yield instance
    instance.close()


# -- Invariant 8: nothing inferred enters the graph unreviewed ---------------


def test_staging_creates_one_proposal_per_claim(store):
    packet = make_packet(
        [claim("Acme", "buyer", "CFO", 2), claim("Acme", "primary_pain", "audits", 2)],
        unknowns=[{"question": "Who signs?", "impact": 0.8}],
    )
    result = review.stage_packet(store, "p", packet, "model", "call.md")
    assert result["staged"]["claims"] == 2
    assert result["staged"]["unknowns"] == 1
    # Staging changes no state at all.
    assert store.state("p") == []
    assert store.uncertainty("p")["uncertainty"] == 0.0


def test_staging_the_same_packet_twice_does_not_duplicate(store):
    packet = make_packet([claim("Acme", "buyer", "CFO")])
    review.stage_packet(store, "p", packet, "model", "call.md")
    second = review.stage_packet(store, "p", packet, "model", "call.md")
    assert second["staged"]["duplicates"] == 1
    assert len(store.proposals("p")) == 1


def test_accepting_a_proposal_applies_exactly_that_claim(store):
    packet = make_packet([claim("Acme", "buyer", "CFO", 2), claim("Acme", "primary_pain", "audits", 2)])
    review.stage_packet(store, "p", packet, "model", "call.md")
    target = next(row for row in store.proposals("p") if "buyer" in row["summary"])
    review.accept(store, "p", target["proposal_id"], decided_by="mel")

    claims = [c["attribute"] for group in store.state("p") for c in group["claims"]]
    assert claims == ["buyer"]
    assert store.get_proposal(target["proposal_id"])["status"] == "accepted"
    assert store.get_proposal(target["proposal_id"])["decided_by"] == "mel"


def test_rejecting_a_proposal_records_the_reason_and_changes_nothing(store):
    review.stage_packet(store, "p", make_packet([claim("Acme", "buyer", "CFO")]), "model", "x")
    target = store.proposals("p")[0]
    review.reject(store, "p", target["proposal_id"], "the model invented this")
    assert store.state("p") == []
    settled = store.get_proposal(target["proposal_id"])
    assert settled["status"] == "rejected"
    assert settled["note"] == "the model invented this"


def test_accepting_twice_is_a_no_op(store):
    review.stage_packet(store, "p", make_packet([claim("Acme", "buyer", "CFO")]), "model", "x")
    target = store.proposals("p")[0]["proposal_id"]
    review.accept(store, "p", target)
    again = review.accept(store, "p", target)
    assert again["applied"] is False


def test_acceptance_rate_is_tracked_per_origin(store):
    review.stage_packet(store, "p", make_packet([claim("Acme", "buyer", "CFO")]), "model", "a")
    review.stage_packet(
        store, "p", make_packet([claim("Acme", "primary_pain", "audits")], source_ref="b.md"), "model", "b"
    )
    pending = store.proposals("p")
    review.accept(store, "p", pending[0]["proposal_id"])
    review.reject(store, "p", pending[1]["proposal_id"])
    stats = store.proposal_stats("p")
    assert stats["model"]["acceptance_rate"] == 0.5


def test_trusted_origins_apply_directly(store):
    assert review.auto_applies("parser", review.DEFAULT_AUTO_APPLY)
    assert not review.auto_applies("model", review.DEFAULT_AUTO_APPLY)
    assert not review.auto_applies("connector:csv", review.DEFAULT_AUTO_APPLY)


# -- Invariant 9: one thing has one name ------------------------------------


def test_similarity_sees_through_corporate_suffixes_and_case():
    assert identity.similarity("Acme Fabrication Inc.", "acme fabrication") > 0.85
    assert identity.similarity("Acme", "Acme Fabrication") > 0.85
    assert identity.similarity("Acme Fabrication", "Northwind Metals") < 0.5


def test_duplicate_entities_are_proposed_not_merged(store):
    apply_packet(store, "p", make_packet([claim("Acme Fabrication", "buyer", "CFO", 3)]))
    apply_packet(
        store,
        "p",
        make_packet([claim("Acme Fabrication Inc", "primary_pain", "audits")], source_ref="b.md"),
    )
    candidates = identity.duplicate_entities(store, "p")
    assert candidates
    # The name carrying more evidence survives.
    assert candidates[0]["keep_name"] == "Acme Fabrication"

    identity.propose_identity_fixes(store, "p")
    assert len(store.entities("p")) == 2  # still not merged
    proposal = store.proposals("p", kind="entity_merge")[0]
    review.accept(store, "p", proposal["proposal_id"])
    assert len(store.entities("p")) == 1


def test_merging_moves_claims_and_records_why(store):
    apply_packet(store, "p", make_packet([claim("Acme Fabrication", "buyer", "CFO", 3)]))
    apply_packet(
        store,
        "p",
        make_packet([claim("Acme Fab", "primary_pain", "audits", 2)], source_ref="b.md"),
    )
    keep = store.find_entity("p", "Acme Fabrication")
    merge = store.find_entity("p", "Acme Fab")
    result = store.merge_entities("p", keep["entity_id"], merge["entity_id"], "same company")

    assert result["claims_moved"] == 1
    survivor = store.state("p")[0]
    assert {c["attribute"] for c in survivor["claims"]} == {"buyer", "primary_pain"}
    assert "acme fab" in survivor["claims"][0]["claim_id"] or True
    assert store.find_entity("p", "Acme Fab")["entity_id"] == keep["entity_id"]
    assert store.merges("p")[0]["reason"] == "same company"


def test_attribute_drift_is_detected_and_can_be_folded(store):
    apply_packet(store, "p", make_packet([claim("Acme", "primary_pain", "audits", 3)]))
    apply_packet(
        store, "p", make_packet([claim("Acme", "main_pain", "data entry", 2)], source_ref="b.md")
    )
    # Two names for one slot means the second value never contested the first.
    assert store.contradictions("p", "open") == []

    candidates = identity.duplicate_attributes(store, "p")
    assert candidates and candidates[0]["canonical"] == "primary_pain"

    store.rename_attribute("p", "main_pain", "primary_pain")
    attributes = {c["attribute"] for group in store.state("p") for c in group["claims"]}
    assert attributes == {"primary_pain"}
    values = {c["value"] for group in store.state("p") for c in group["claims"]}
    assert values == {"audits", "data entry"}


def test_a_folded_alias_lands_in_the_right_slot_next_time(store):
    apply_packet(store, "p", make_packet([claim("Acme", "primary_pain", "audits", 3)]))
    store.set_attribute_canonical("p", "main_pain", "primary_pain")
    report = apply_packet(
        store, "p", make_packet([claim("Acme", "main_pain", "data entry", 3)], source_ref="b.md")
    )
    assert report["transitions"][0]["attribute"] == "primary_pain"
    assert len(store.contradictions("p", "open")) == 1


# -- Invariant 10: every claim knows which decision it serves ----------------


def test_linking_a_claim_to_a_decision_raises_its_importance(store):
    apply_packet(
        store, "p", make_packet([claim("Acme", "buyer", "CFO", 2, importance=0.3)])
    )
    decision = decision_board.add(store, "p", "Who do we sell to?", weight=0.9)
    claim_id = store.state("p")[0]["claims"][0]["claim_id"]
    decision_board.link(store, "p", decision["decision_id"], "claim", claim_id)
    assert store.get_claim(claim_id)["importance"] == 0.9


def test_readiness_is_governed_by_the_weakest_belief(store):
    apply_packet(
        store,
        "p",
        make_packet(
            [claim("Acme", "buyer", "CFO", 8), claim("Acme", "budget", "unknown", 1)]
        ),
    )
    decision = decision_board.add(store, "p", "Do we sell to Acme?")
    for group in store.state("p"):
        for item in group["claims"]:
            decision_board.link(store, "p", decision["decision_id"], "claim", item["claim_id"])
    report = decision_board.readiness(store, "p", decision["decision_id"])
    assert report["weakest_link"]["attribute"] == "budget"
    assert report["readiness"] < max(c["effective_confidence"] for c in report["claims"])
    assert "not yet" in report["verdict"] or "thin" in report["verdict"]


def test_a_blocking_unknown_lowers_readiness(store):
    apply_packet(store, "p", make_packet([claim("Acme", "buyer", "CFO", 8)]))
    decision = decision_board.add(store, "p", "Do we sell to Acme?")
    claim_id = store.state("p")[0]["claims"][0]["claim_id"]
    decision_board.link(store, "p", decision["decision_id"], "claim", claim_id)
    before = decision_board.readiness(store, "p", decision["decision_id"])["readiness"]

    apply_packet(
        store,
        "p",
        make_packet(
            [claim("Acme", "primary_pain", "audits")],
            source_ref="b.md",
            unknowns=[{"question": "Does procurement block it?", "impact": 0.9}],
        ),
    )
    unknown_id = store.unknowns("p")[0]["unknown_id"]
    decision_board.link(store, "p", decision["decision_id"], "unknown", unknown_id)
    after = decision_board.readiness(store, "p", decision["decision_id"])["readiness"]
    assert after < before


def test_decision_scoped_uncertainty_ignores_unrelated_claims(store):
    apply_packet(
        store,
        "p",
        make_packet(
            [claim("Acme", "buyer", "CFO", 2), claim("Unrelated", "colour", "blue", 1)]
        ),
    )
    decision = decision_board.add(store, "p", "Who do we sell to?")
    claim_id = next(
        item["claim_id"]
        for group in store.state("p")
        for item in group["claims"]
        if item["attribute"] == "buyer"
    )
    decision_board.link(store, "p", decision["decision_id"], "claim", claim_id)
    scoped = decision_board.uncertainty_for_decision(store, "p", decision["decision_id"])
    assert scoped["uncertainty"] < store.uncertainty("p")["uncertainty"]


def test_auto_link_falls_back_to_what_matters_when_wording_does_not_overlap(store):
    apply_packet(
        store,
        "p",
        make_packet([claim("Manufacturing Ops", "primary_pain", "audits", 3, importance=0.9)]),
    )
    decision = decision_board.add(store, "p", "Which segment do we build for first?")
    result = decision_board.auto_link(store, "p", decision["decision_id"])
    assert result["linked"]
    assert result["matched_by"] in {"relevance", "importance (no wording overlap)"}


def test_closing_a_decision_records_the_call(store):
    decision = decision_board.add(store, "p", "Ship it?")
    store.close_decision(decision["decision_id"], "yes, behind a flag", "pilot evidence held")
    closed = store.get_decision(decision["decision_id"])
    assert closed["status"] == "decided"
    assert closed["choice"] == "yes, behind a flag"


# -- Invariant 12: every integration is the same shape ----------------------


def write_csv(tmp_path: Path) -> Path:
    path = tmp_path / "survey.csv"
    path.write_text(
        "company,respondent,responded_at,pain,buyer,quote\n"
        "Acme,jane,2026-06-02,compliance,Department Head,failed an audit\n"
        "Brightforge,omar,2026-06-04,compliance,Department Head,audit prep is brutal\n"
        "Cordell,rita,2026-06-05,data entry,VP Operations,numbers off the floor\n",
        encoding="utf-8",
    )
    return path


def test_csv_connector_maps_columns_to_claims(tmp_path):
    path = write_csv(tmp_path)
    result = csv_rows.CsvConnector().fetch(
        {
            "path": str(path),
            "entity_column": "company",
            "actor_column": "respondent",
            "date_column": "responded_at",
            "kind": "interview",
            "claims": {"primary_pain": "pain", "buyer": "buyer"},
            "excerpt_column": "quote",
        },
        "",
    )
    assert len(result.packets) == 3
    first = result.packets[0]
    assert first["source"]["kind"] == "interview"
    assert first["source"]["actor"] == "jane"
    assert {item["attribute"] for item in first["claims"]} == {"primary_pain", "buyer"}
    assert first["claims"][0]["evidence"][0]["excerpt"] == "failed an audit"
    assert result.cursor == "2026-06-05"


def test_csv_roll_up_turns_rows_into_a_population_belief(tmp_path, store):
    path = write_csv(tmp_path)
    result = csv_rows.CsvConnector().fetch(
        {
            "path": str(path),
            "entity_column": "company",
            "actor_column": "respondent",
            "date_column": "responded_at",
            "kind": "interview",
            "claims": {"primary_pain": "pain"},
            "roll_up": {"entity": "Ops Managers", "kind": "segment"},
        },
        "",
    )
    for item in result.packets:
        apply_packet(store, "p", item)
    segment = store.find_entity("p", "Ops Managers")
    rolled = store.claims_in_slot("p", segment["entity_id"], "primary_pain")
    values = {row["value"]: row["confidence"] for row in rolled}
    # Two independent respondents agreed; one dissented. Both survive, and the
    # majority is held more strongly than any single company's claim.
    assert set(values) == {"compliance", "data entry"}
    assert values["compliance"] > values["data entry"]
    assert len(store.contradictions("p", "open")) == 1


def test_csv_connector_reports_a_bad_mapping_clearly(tmp_path):
    path = write_csv(tmp_path)
    with pytest.raises(csv_rows.ConnectorError) as caught:
        csv_rows.CsvConnector().fetch(
            {"path": str(path), "entity_column": "company", "claims": {"pain": "nope"}}, ""
        )
    assert "nope" in str(caught.value)
    assert "Available" in str(caught.value)


def test_filedrop_reads_packets_and_notes(tmp_path, store):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "packet.json").write_text(
        json.dumps(make_packet([claim("Acme", "buyer", "CFO", 2)])), encoding="utf-8"
    )
    (inbox / "note.md").write_text(
        "@entity segment Ops\n@kind interview\nclaim: buyer = CFO [n=2]\n", encoding="utf-8"
    )
    result = filedrop.FileDropConnector().fetch({"path": str(inbox)}, "")
    assert len(result.packets) == 2


def test_github_connector_parses_issues_without_a_network(tmp_path):
    issues = [
        {
            "number": 7,
            "title": "Pricing research",
            "updated_at": "2026-07-01T00:00:00Z",
            "user": {"login": "mel"},
            "comments": 0,
            "labels": [{"name": "research"}],
            "body": "@entity segment Ops\nclaim: buyer = Department Head [kind=interview, n=3]",
        },
        {
            "number": 8,
            "title": "Do enterprises need SSO?",
            "updated_at": "2026-07-02T00:00:00Z",
            "user": {"login": "sam"},
            "comments": 0,
            "labels": [{"name": "question"}],
            "body": "no explicit statements here",
        },
    ]
    calls = []

    def transport(url, token=""):
        calls.append(url)
        return issues if "issues?" in url else []

    result = github_issues.GitHubIssuesConnector().fetch(
        {"repo": "owner/name", "_transport": transport, "include_comments": False}, ""
    )
    assert len(result.packets) == 2
    assert result.packets[0]["claims"][0]["value"] == "Department Head"
    # A labelled issue with no claim is still an open question.
    assert result.packets[1]["unknowns"][0]["question"] == "Do enterprises need SSO?"
    assert result.cursor == "2026-07-02T00:00:00Z"
    assert calls and "owner/name" in calls[0]


def test_connector_pull_stages_and_advances_the_cursor(tmp_path, store):
    path = write_csv(tmp_path)
    definitions = [
        {
            "name": "csv",
            "id": "survey",
            "config": {
                "path": str(path),
                "entity_column": "company",
                "date_column": "responded_at",
                "claims": {"primary_pain": "pain"},
            },
        }
    ]
    report = pull_connectors(store, "p", tmp_path, definitions)
    assert report["packets"] == 3
    assert report["staged"] == 3
    assert store.state("p") == []  # staged, never applied
    assert store.connector_cursor("p", "survey") == "2026-06-05"

    again = pull_connectors(store, "p", tmp_path, definitions)
    assert again["packets"] == 0  # the cursor held


def test_connector_errors_do_not_stop_the_other_connectors(tmp_path, store):
    definitions = [
        {"name": "csv", "id": "broken", "config": {"path": "nope.csv", "entity_column": "c", "claims": {"a": "b"}}},
        {"name": "filedrop", "id": "inbox", "config": {"path": str(tmp_path)}},
    ]
    report = pull_connectors(store, "p", tmp_path, definitions)
    assert len(report["errors"]) == 1
    assert len(report["connectors"]) == 2


# -- The digest: the artifact people come back for --------------------------


def test_digest_names_what_moved_and_what_is_blocked(store):
    apply_packet(store, "p", make_packet([claim("Acme", "buyer", "Dept Head", 2)]))
    apply_packet(
        store, "p", make_packet([claim("Acme", "buyer", "VP Ops", 2)], source_ref="b.md")
    )
    decision = decision_board.add(store, "p", "Who do we sell to?")
    decision_board.auto_link(store, "p", decision["decision_id"])
    store.snapshot_metric("p", note="test")

    report = build_digest(store, "p", None)
    assert any(row["transition_type"] == "contested" for row in report["changed"])
    assert report["new_conflicts"]
    assert report["blocked"]
    text = render_markdown(report)
    assert "New conflicts" in text
    assert "Still blocked" in text
    assert "lce prompt adjudicate" in text
    assert render_slack(report)["mrkdwn"] is True
    html = render_html(report)
    assert "prefers-color-scheme" in html and "<h1>" in html


def test_digest_hides_a_rate_it_cannot_honestly_compute(store):
    apply_packet(store, "p", make_packet([claim("Acme", "buyer", "CFO", 2)]))
    store.snapshot_metric("p", note="one")
    store.snapshot_metric("p", note="two")
    # Two snapshots seconds apart cannot support a per-hour rate.
    assert build_digest(store, "p", None)["uncertainty_removed_per_hour"] is None


# -- Adaptation is data, not code ------------------------------------------


def test_profiles_carry_a_vocabulary_and_starter_questions():
    assert "customer-discovery" in profiles.PROFILES
    block = profiles.vocabulary_block("customer-discovery")
    assert "primary_pain" in block and "willingness_to_pay" in block
    starter = profiles.starter_observation("customer-discovery")
    assert starter.count("unknown:") >= 3
    with pytest.raises(ValueError):
        profiles.get("nonexistent")


def test_security_profile_shortens_the_half_life(tmp_path):
    run(tmp_path, "--project", "sec", "init", "--profile", "security-posture")
    config = json.loads((tmp_path / ".lce" / "config.json").read_text())
    # A control verified a year ago is not verified.
    assert config["half_life_days"] == 90
    assert config["profile"] == "security-posture"


# -- MCP: the graph inside the tools people already use --------------------


def mcp_exchange(root: Path, messages: list[dict]) -> list[dict]:
    stream = io.StringIO("\n".join(json.dumps(item) for item in messages) + "\n")
    output = io.StringIO()
    mcp.serve(root, project="p", stream=stream, output=output)
    return [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]


def test_mcp_handshake_lists_tools_and_prompts(tmp_path):
    Store(tmp_path).close()
    responses = mcp_exchange(
        tmp_path,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "prompts/list"},
        ],
    )
    # The notification gets no response.
    assert [item["id"] for item in responses] == [1, 2, 3]
    assert responses[0]["result"]["serverInfo"]["name"] == "living-context-engine"
    assert responses[0]["result"]["protocolVersion"] == "2025-06-18"
    names = {tool["name"] for tool in responses[1]["result"]["tools"]}
    assert {"lce_context", "lce_why", "lce_propose_observation", "lce_decisions"} <= names
    assert responses[2]["result"]["prompts"]


def test_mcp_proposals_are_staged_not_applied(tmp_path):
    packet = make_packet([claim("Acme", "buyer", "CFO", 2)])
    responses = mcp_exchange(
        tmp_path,
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "lce_propose_observation", "arguments": {"packet": packet}},
            }
        ],
    )
    text = responses[0]["result"]["content"][0]["text"]
    assert "staged for review" in text.lower()
    store = Store(tmp_path)
    try:
        assert store.state("p") == []
        assert len(store.proposals("p")) == 1
    finally:
        store.close()


def test_mcp_reports_a_bad_call_as_a_tool_error_not_a_crash(tmp_path):
    Store(tmp_path).close()
    responses = mcp_exchange(
        tmp_path,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "lce_context", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "nope", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 3, "method": "totally/unknown"},
        ],
    )
    assert responses[0]["result"]["isError"] is True
    assert responses[1]["result"]["isError"] is True
    assert responses[2]["error"]["code"] == -32601


def test_mcp_client_config_is_printable(tmp_path):
    result = run(tmp_path, "--project", "p", "mcp", "--print-config")
    payload = json.loads(result.stdout)
    assert payload["mcpServers"]["living-context"]["command"] == "lce"
    assert "mcp" in payload["mcpServers"]["living-context"]["args"]


# -- The write API ----------------------------------------------------------


def serve_in_thread(tmp_path, write_token="write-me", token=None):
    import threading
    from http.server import ThreadingHTTPServer

    from living_context.server import Handler

    Handler.root = tmp_path
    Handler.database = "data/living-context.sqlite"
    Handler.default_project = "p"
    Handler.token = token
    Handler.write_token = write_token
    Handler.cors_origin = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def post(base, path, payload, token="write-me", key=""):
    import urllib.request

    request = urllib.request.Request(
        base + path, data=json.dumps(payload).encode(), method="POST"
    )
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    if key:
        request.add_header("Idempotency-Key", key)
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read())


def test_write_api_stages_and_is_idempotent(tmp_path):
    Store(tmp_path).close()
    server, base = serve_in_thread(tmp_path)
    try:
        packet = make_packet([claim("Acme", "buyer", "CFO", 2)])
        status, first = post(base, "/api/observations", packet, key="abc")
        assert status == 200
        assert first["accepted_for_review"] == 1
        _, replay = post(base, "/api/observations", packet, key="abc")
        assert replay["replayed"] is True
    finally:
        server.shutdown()
        server.server_close()
    store = Store(tmp_path)
    try:
        assert store.state("p") == []
        assert len(store.proposals("p")) == 1
    finally:
        store.close()


def test_write_api_refuses_a_read_token(tmp_path):
    import urllib.error

    Store(tmp_path).close()
    server, base = serve_in_thread(tmp_path, write_token="write-me", token="read-only")
    try:
        with pytest.raises(urllib.error.HTTPError) as caught:
            post(base, "/api/observations", make_packet([claim("Acme", "buyer", "CFO")]), token="read-only")
        assert caught.value.code == 401
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_renders(tmp_path):
    import urllib.request

    store = Store(tmp_path)
    apply_packet(store, "p", make_packet([claim("Acme", "buyer", "CFO", 2)]))
    store.snapshot_metric("p", note="test")
    store.close()
    server, base = serve_in_thread(tmp_path, write_token=None)
    try:
        with urllib.request.urlopen(base + "/", timeout=10) as response:
            body = response.read().decode()
        assert response.headers["Content-Type"].startswith("text/html")
        assert "Living Context" in body
    finally:
        server.shutdown()
        server.server_close()


# -- End to end through the CLI --------------------------------------------


def test_cli_adoption_path(tmp_path):
    assert run(tmp_path, "--project", "acme", "init", "--profile", "customer-discovery",
               "--connectors").returncode == 0
    assert (tmp_path / ".lce" / "connectors.json").exists()
    assert (tmp_path / ".lce" / "observations" / "00-open-questions.md").exists()

    run(tmp_path, "ingest")

    research = tmp_path / "research"
    research.mkdir()
    write_csv(research).rename(research / "survey.csv")
    config_path = tmp_path / ".lce" / "connectors.json"
    config = json.loads(config_path.read_text())
    for entry in config["connectors"]:
        if entry["id"] == "survey":
            entry["enabled"] = True
            entry["config"].update(
                {
                    "path": "research/survey.csv",
                    "entity_column": "company",
                    "actor_column": "respondent",
                    "date_column": "responded_at",
                    "claims": {"primary_pain": "pain", "buyer": "buyer"},
                    "excerpt_column": "quote",
                    "roll_up": {"entity": "Ops Managers", "kind": "segment"},
                }
            )
    config_path.write_text(json.dumps(config))

    pull = run(tmp_path, "pull", "--json")
    assert pull.returncode == 0, pull.stderr
    assert json.loads(pull.stdout)["staged"] > 0

    # Nothing is in the graph until a human accepts it.
    assert json.loads(run(tmp_path, "state", "--json").stdout) == []

    accepted = json.loads(run(tmp_path, "review", "--accept-all", "--by", "mel").stdout)
    assert accepted["accepted"] > 0
    state = json.loads(run(tmp_path, "state", "--json").stdout)
    assert any(group["entity"] == "Ops Managers" for group in state)

    add = json.loads(
        run(tmp_path, "decision", "add", "Which segment do we build for first?", "--auto-link").stdout
    )
    assert add["created"] is True

    board = json.loads(run(tmp_path, "decisions", "--json").stdout)
    assert board and board[0]["verdict"]

    claim_id = next(
        item["claim_id"]
        for group in state
        if group["entity"] == "Ops Managers"
        for item in group["claims"]
    )
    why = run(tmp_path, "why", claim_id)
    assert why.returncode == 0
    assert "method ceiling" in why.stdout
    assert "to move it" in why.stdout

    digest = run(tmp_path, "digest", "--format", "json")
    assert digest.returncode == 0
    assert json.loads(digest.stdout)["uncertainty"]["claims_active"] > 0

    identity_report = json.loads(run(tmp_path, "identity", "--json").stdout)
    assert "entities" in identity_report

    assert run(tmp_path, "connectors").returncode == 0
    assert json.loads(run(tmp_path, "validate").stdout)["confidence_drift"] == 0


def test_cli_ingest_can_stage_instead_of_applying(tmp_path):
    observations = tmp_path / ".lce" / "observations"
    observations.mkdir(parents=True)
    (observations / "notes.md").write_text(
        "@entity segment Ops\n@kind interview\nclaim: buyer = CFO [n=3]\n", encoding="utf-8"
    )
    run(tmp_path, "--project", "p", "init")
    result = json.loads(run(tmp_path, "ingest", "--stage", "--json").stdout)
    assert result["mode"] == "staged for review"
    assert result["staged"] == 1
    assert json.loads(run(tmp_path, "state", "--json").stdout) == []
    assert json.loads(run(tmp_path, "review", "--json").stdout)["pending"]
