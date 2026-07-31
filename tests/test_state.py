"""Tests for the state-transition loop, organised by the invariant each protects."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from living_context import actions as action_router
from living_context.context import build_context, render_markdown
from living_context.delta import apply_packet
from living_context.models import confidence_from_evidence
from living_context.observe import packet_from_text, validate_packet
from living_context.store import Store


def make_packet(claims, source_ref="notes.md", kind="interview", actor="jane", unknowns=None):
    entities = sorted({claim["entity"] for claim in claims})
    return {
        "source": {
            "ref": source_ref,
            "kind": kind,
            "actor": actor,
            "observed_at": "2026-07-01T00:00:00+00:00",
        },
        "entities": [{"name": name, "kind": "segment", "aliases": []} for name in entities],
        "claims": claims,
        "relationships": [],
        "unknowns": unknowns or [],
    }


def claim(entity, attribute, value, evidence_count=1, kind="interview", importance=0.7):
    return {
        "entity": entity,
        "attribute": attribute,
        "value": value,
        "importance": importance,
        "evidence": [
            {
                "excerpt": f"{entity} {attribute} {value} #{index}",
                "kind": kind,
                "actor": f"respondent-{index}",
                "locator": f"line {index}",
            }
            for index in range(evidence_count)
        ],
    }


@pytest.fixture()
def store(tmp_path):
    instance = Store(tmp_path)
    yield instance
    instance.close()


# -- Invariant 1: everything represents state, not content -------------------


def test_prose_produces_no_state_only_explicit_statements():
    prose = "We had a good call today. The team seemed happy about the roadmap.\n"
    packet = packet_from_text(prose, "call.md")
    assert packet["claims"] == []
    assert packet["entities"] == []


def test_claim_lines_become_entities_and_claims():
    text = (
        "@entity segment Ops Managers\n"
        "@kind interview\n"
        "claim: primary_pain = compliance reporting risk [importance=0.9]\n"
    )
    packet = packet_from_text(text, "notes.md")
    assert packet["entities"] == [
        {"name": "Ops Managers", "kind": "segment", "aliases": []}
    ]
    assert packet["claims"][0]["attribute"] == "primary_pain"
    assert packet["claims"][0]["value"] == "compliance reporting risk"
    assert packet["claims"][0]["importance"] == 0.9


def test_fenced_examples_are_documentation_not_assertions():
    text = "Here is the syntax:\n\n```\nclaim: Acme / buyer = CFO\n```\n\nclaim: Acme / buyer = CTO\n"
    packet = packet_from_text(text, "README.md")
    values = [item["value"] for item in packet["claims"]]
    assert values == ["CTO"]


# -- Invariant 2: every claim carries provenance -----------------------------


def test_claim_without_evidence_is_rejected():
    packet = make_packet([{"entity": "Acme", "attribute": "buyer", "value": "CFO", "evidence": []}])
    assert any("evidence" in problem for problem in validate_packet(packet))


def test_stored_claim_keeps_who_said_it_and_when(store, tmp_path):
    apply_packet(store, "p", make_packet([claim("Acme", "buyer", "CFO")]))
    rows = store.state("p")[0]["claims"]
    evidence = store.evidence_for(rows[0]["claim_id"])
    assert evidence[0]["actor"] == "respondent-0"
    assert evidence[0]["source_ref"] == "notes.md"
    assert evidence[0]["locator"] == "line 0"
    assert evidence[0]["kind"] == "interview"
    assert evidence[0]["observed_at"].startswith("2026-07-01")


def test_method_ceiling_caps_what_a_source_kind_can_ever_prove():
    many_interviews = [
        {"kind": "interview", "actor": f"person-{index}"} for index in range(50)
    ]
    assert confidence_from_evidence(many_interviews) <= 0.85
    assert confidence_from_evidence(
        many_interviews + [{"kind": "transaction", "actor": "billing"}]
    ) > 0.85


def test_repeating_one_voice_is_not_corroboration():
    one_person = [{"kind": "interview", "actor": "same"} for _ in range(10)]
    ten_people = [{"kind": "interview", "actor": f"p{index}"} for index in range(10)]
    assert confidence_from_evidence(one_person) < confidence_from_evidence(ten_people)


# -- Invariant 3: the graph updates from reality -----------------------------


def test_new_value_with_stronger_evidence_revises_the_belief(store):
    apply_packet(store, "p", make_packet([claim("Acme", "buyer", "Department Head", 1)]))
    report = apply_packet(
        store,
        "p",
        make_packet(
            [claim("Acme", "buyer", "Procurement", 6)], source_ref="round-two.md"
        ),
    )
    types = [item["transition_type"] for item in report["transitions"]]
    assert types == ["revised"]
    active = [c["value"] for c in store.state("p")[0]["claims"]]
    assert active == ["Procurement"]
    assert "outweighs the prior belief" in report["transitions"][0]["rationale"]


def test_reingesting_the_same_source_changes_nothing(store):
    packet = make_packet([claim("Acme", "buyer", "CFO", 3)])
    first = apply_packet(store, "p", packet)
    second = apply_packet(store, "p", packet)
    assert first["evidence_added"] == 3
    assert second["evidence_added"] == 0
    assert second["transitions"] == []


def test_a_second_independent_source_reinforces(store):
    apply_packet(store, "p", make_packet([claim("Acme", "buyer", "CFO", 2)]))
    before = store.state("p")[0]["claims"][0]["confidence"]
    report = apply_packet(
        store, "p", make_packet([claim("Acme", "buyer", "CFO", 2)], source_ref="other.md")
    )
    after = store.state("p")[0]["claims"][0]["confidence"]
    assert report["transitions"][0]["transition_type"] == "reinforced"
    assert after > before


# -- Invariant 4: contradictions are first-class -----------------------------


def test_evenly_matched_conflict_keeps_both_beliefs(store):
    apply_packet(store, "p", make_packet([claim("Acme", "primary_pain", "automation", 3)]))
    report = apply_packet(
        store,
        "p",
        make_packet([claim("Acme", "primary_pain", "compliance risk", 3)], source_ref="b.md"),
    )
    assert report["transitions"][0]["transition_type"] == "contested"
    assert len(report["contradictions_opened"]) == 1
    values = {c["value"] for c in store.state("p")[0]["claims"]}
    assert values == {"automation", "compliance risk"}
    assert len(store.contradictions("p", "open")) == 1


def test_a_multivalued_attribute_does_not_manufacture_conflict(store):
    apply_packet(store, "p", make_packet([claim("Acme", "blockers[]", "procurement", 2)]))
    report = apply_packet(
        store, "p", make_packet([claim("Acme", "blockers[]", "budget", 2)], source_ref="b.md")
    )
    assert report["transitions"][0]["transition_type"] == "established"
    assert store.contradictions("p", "open") == []


def test_resolving_a_contradiction_is_recorded(store):
    apply_packet(store, "p", make_packet([claim("Acme", "primary_pain", "automation", 3)]))
    apply_packet(
        store,
        "p",
        make_packet([claim("Acme", "primary_pain", "compliance risk", 3)], source_ref="b.md"),
    )
    open_row = store.contradictions("p", "open")[0]
    store.resolve_contradiction(open_row["contradiction_id"], "different sub-segments")
    assert store.contradictions("p", "open") == []
    resolved = store.contradictions("p", "resolved")[0]
    assert resolved["resolution"] == "different sub-segments"


# -- Invariant 5: retrieval is task-specific ---------------------------------


def test_two_questions_retrieve_two_different_packs(store):
    apply_packet(
        store,
        "p",
        make_packet(
            [
                claim("Acme", "pricing_model", "per seat", 2),
                claim("Acme", "onboarding_time", "six weeks", 2),
            ]
        ),
    )
    pricing = build_context(store, "p", "what pricing model should we use")
    onboarding = build_context(store, "p", "how long does onboarding take")
    top_pricing = pricing["entities"][0]["claims"][0]["attribute"]
    top_onboarding = onboarding["entities"][0]["claims"][0]["attribute"]
    assert top_pricing == "pricing_model"
    assert top_onboarding == "onboarding_time"


def test_context_pack_renders_with_sources_and_limits(store):
    apply_packet(store, "p", make_packet([claim("Acme", "buyer", "CFO", 2)]))
    text = render_markdown(build_context(store, "p", "who is the buyer"))
    assert "notes.md" in text
    assert "## Boundary" in text
    assert "Absence from this pack is not evidence of absence" in text


# -- Invariant 6: every uncertainty produces an action -----------------------


def test_an_open_unknown_produces_a_ranked_action(store):
    apply_packet(
        store,
        "p",
        make_packet(
            [claim("Acme", "buyer", "CFO")],
            unknowns=[
                {"question": "Who signs the contract?", "impact": 0.9, "blocks_decision": "pricing"}
            ],
        ),
    )
    proposals = action_router.propose_actions(store, "p")
    targets = {item.target_kind for item in proposals}
    assert "unknown" in targets
    assert proposals[0].priority > 0


def test_behavioural_questions_route_to_an_experiment_not_an_interview(store):
    apply_packet(
        store,
        "p",
        make_packet(
            [claim("Acme", "buyer", "CFO")],
            unknowns=[{"question": "Will customers pay $2k a month?", "impact": 0.9}],
        ),
    )
    proposals = action_router.propose_actions(store, "p")
    pay_action = next(item for item in proposals if "pay" in item.title)
    assert pay_action.kind == "experiment"


def test_an_open_contradiction_produces_a_reconcile_action(store):
    apply_packet(store, "p", make_packet([claim("Acme", "primary_pain", "automation", 3)]))
    apply_packet(
        store,
        "p",
        make_packet([claim("Acme", "primary_pain", "compliance risk", 3)], source_ref="b.md"),
    )
    proposals = action_router.propose_actions(store, "p")
    assert any(item.kind == "reconcile" for item in proposals)


def test_low_confidence_important_claims_get_a_verification_action(store):
    apply_packet(
        store,
        "p",
        make_packet([claim("Acme", "willingness_to_pay", "$2k", 1, kind="assertion", importance=0.9)]),
    )
    proposals = action_router.propose_actions(store, "p")
    assert any(item.target_kind == "claim" for item in proposals)


# -- Invariant 7: memory compounds -------------------------------------------


def test_uncertainty_falls_when_a_question_is_answered(store):
    apply_packet(
        store,
        "p",
        make_packet(
            [claim("Acme", "buyer", "CFO", 2)],
            unknowns=[{"question": "Who signs?", "impact": 0.9}],
        ),
    )
    before = store.uncertainty("p")["uncertainty"]
    unknown_id = store.unknowns("p")[0]["unknown_id"]
    store.resolve_unknown(unknown_id, "the CFO signs")
    after = store.uncertainty("p")["uncertainty"]
    assert after < before


def test_uncertainty_falls_as_evidence_accumulates(store):
    apply_packet(store, "p", make_packet([claim("Acme", "buyer", "CFO", 1)]))
    before = store.uncertainty("p")["uncertainty"]
    apply_packet(
        store, "p", make_packet([claim("Acme", "buyer", "CFO", 5)], source_ref="more.md")
    )
    assert store.uncertainty("p")["uncertainty"] < before


def test_metric_snapshots_accumulate(store):
    apply_packet(store, "p", make_packet([claim("Acme", "buyer", "CFO")]))
    store.snapshot_metric("p", note="one")
    store.snapshot_metric("p", note="two")
    assert len(store.metrics("p")) == 2


def test_projects_are_isolated(store):
    apply_packet(store, "alpha", make_packet([claim("Acme", "buyer", "CFO")]))
    apply_packet(store, "beta", make_packet([claim("Acme", "buyer", "CTO")]))
    assert store.state("alpha")[0]["claims"][0]["value"] == "CFO"
    assert store.state("beta")[0]["claims"][0]["value"] == "CTO"
    store.delete_project("alpha")
    assert store.state("alpha") == []
    assert store.state("beta")[0]["claims"][0]["value"] == "CTO"


# -- End to end through the CLI ----------------------------------------------


def run(root: Path, *command: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return subprocess.run(
        [sys.executable, "-m", "living_context.cli", "--root", str(root), *command],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_runs_the_whole_loop(tmp_path):
    observations = tmp_path / ".lce" / "observations"
    observations.mkdir(parents=True)
    (observations / "round-one.md").write_text(
        "@entity segment Ops Managers\n"
        "@kind interview\n"
        "claim: primary_pain = automation [n=3]\n"
        "unknown: Will they pay $2k a month? [impact=0.9]\n",
        encoding="utf-8",
    )

    assert run(tmp_path, "--project", "demo", "init").returncode == 0
    assert (tmp_path / ".lce" / "config.json").exists()

    ingest = run(tmp_path, "ingest", "--json")
    assert ingest.returncode == 0, ingest.stderr
    summary = json.loads(ingest.stdout)
    assert summary["claims_seen"] >= 1
    assert summary["transition_counts"]["established"] >= 1

    (observations / "round-two.md").write_text(
        "@entity segment Ops Managers\n"
        "@kind interview\n"
        "claim: primary_pain = compliance reporting [n=9]\n",
        encoding="utf-8",
    )
    second = json.loads(run(tmp_path, "ingest", "--json").stdout)
    assert second["transition_counts"].get("revised") == 1

    delta = json.loads(run(tmp_path, "delta", "--json").stdout)
    assert delta[0]["transition_type"] == "revised"
    assert "outweighs" in delta[0]["rationale"]

    state = json.loads(run(tmp_path, "state", "--json").stdout)
    assert state[0]["claims"][0]["value"] == "compliance reporting"

    actions = json.loads(run(tmp_path, "actions", "--refresh", "--json").stdout)
    assert actions and actions[0]["priority"] > 0

    context = run(tmp_path, "context", "should we build this", "--output", str(tmp_path / "c.md"))
    assert context.returncode == 0
    assert (tmp_path / "c.md").exists()
    assert (tmp_path / "c.json").exists()

    metric = json.loads(run(tmp_path, "metric", "--json").stdout)
    assert metric["current"]["uncertainty"] > 0

    prompt = run(tmp_path, "prompt", "extract")
    assert prompt.returncode == 0
    assert "observation packet" in prompt.stdout or "state update" in prompt.stdout
    assert "Ops Managers" in prompt.stdout

    guide = run(tmp_path, "prompt", "interview-guide")
    assert guide.returncode == 0
    assert "pay $2k" in guide.stdout

    export = run(tmp_path, "export", "--output", str(tmp_path / "state.csv"), "--format", "csv")
    assert export.returncode == 0
    assert "compliance reporting" in (tmp_path / "state.csv").read_text(encoding="utf-8")


def test_cli_validate_reports_graph_invariants(tmp_path):
    observations = tmp_path / ".lce" / "observations"
    observations.mkdir(parents=True)
    (observations / "notes.md").write_text(
        "@entity segment Ops\n@kind interview\nclaim: buyer = CFO [n=2]\n", encoding="utf-8"
    )
    run(tmp_path, "--project", "demo", "init")
    run(tmp_path, "ingest")
    result = run(tmp_path, "validate")
    payload = json.loads(result.stdout)
    assert payload["claims_without_evidence"] == 0
    assert payload["confidence_drift"] == 0
    assert payload["orphan_claims"] == 0


def test_absorb_reads_a_model_written_packet(tmp_path):
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(
        json.dumps(make_packet([claim("Acme", "buyer", "CFO", 3)], source_ref="call.txt")),
        encoding="utf-8",
    )
    run(tmp_path, "--project", "demo", "init")
    result = run(tmp_path, "absorb", str(packet_path))
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["claims_seen"] == 1
    assert summary["evidence_added"] == 3


def test_absorb_rejects_a_packet_with_unsupported_claims(tmp_path):
    packet_path = tmp_path / "bad.json"
    packet_path.write_text(
        json.dumps(
            make_packet([{"entity": "Acme", "attribute": "buyer", "value": "CFO", "evidence": []}])
        ),
        encoding="utf-8",
    )
    run(tmp_path, "--project", "demo", "init")
    result = run(tmp_path, "absorb", str(packet_path))
    assert result.returncode == 2
    assert "evidence" in result.stderr


def test_doctor_reports_readiness(tmp_path):
    run(tmp_path, "--project", "demo", "init")
    result = run(tmp_path, "doctor")
    payload = json.loads(result.stdout)
    names = {item["check"] for item in payload["checks"]}
    assert {"config", "sources", "database", "state"} <= names


def test_http_api_serves_the_state_layer(tmp_path):
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    from living_context.server import Handler

    store = Store(tmp_path)
    apply_packet(
        store,
        "demo",
        make_packet(
            [claim("Acme", "buyer", "CFO", 3)],
            unknowns=[{"question": "Who signs?", "impact": 0.8}],
        ),
    )
    action_router.refresh_actions(store, "demo")
    store.close()

    Handler.root = tmp_path
    Handler.database = "data/living-context.sqlite"
    Handler.default_project = "demo"
    Handler.token = None
    Handler.cors_origin = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        def get(path):
            with urllib.request.urlopen(base + path, timeout=10) as response:
                assert response.status == 200
                return json.loads(response.read())

        assert get("/health")["status"] == "ok"
        assert get("/api/state")["items"][0]["claims"][0]["value"] == "CFO"
        assert get("/api/unknowns")["items"][0]["impact"] == 0.8
        assert get("/api/actions")["items"]
        assert get("/api/metric")["current"]["uncertainty"] > 0
        pack = get("/api/context?task=who%20is%20the%20buyer")
        assert pack["entities"][0]["claims"][0]["attribute"] == "buyer"
    finally:
        server.shutdown()
        server.server_close()


def test_http_api_requires_a_project_for_state_endpoints(tmp_path):
    import threading
    import urllib.error
    import urllib.request
    from http.server import ThreadingHTTPServer

    from living_context.server import Handler

    Handler.root = tmp_path
    Handler.default_project = None
    Handler.token = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with pytest.raises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(base + "/api/state", timeout=10)
        assert caught.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
