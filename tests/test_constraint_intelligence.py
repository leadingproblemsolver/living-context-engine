import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "build_constraint_intelligence.py"
SPEC = spec_from_file_location("build_constraint_intelligence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


TAXONOMY = {
    "constraints": [
        {
            "id": "operational-truth-divergence",
            "name": "Operational truth divergence",
            "keywords": ["published", "dead trigger", "manual restart", "healthy"],
        },
        {
            "id": "side-effect-integrity",
            "name": "Ambiguous or duplicate side effects",
            "keywords": ["duplicate", "retry", "timeout", "partial delivery"],
        },
    ]
}


def test_classifies_operational_truth_divergence():
    record = {
        "title": "Workflow remains Published while dead trigger requires manual restart",
        "body": "Health remains healthy although the runtime stopped serving events.",
    }
    match = MODULE.classify_constraint(record, TAXONOMY)
    assert match.constraint_id == "operational-truth-divergence"
    assert match.match_score >= 54
    assert "published" in match.matched_terms


def test_high_value_saturated_signal_stays_corpus_only_or_watch():
    record = {
        "repository": "example/workflows",
        "number": 9,
        "title": "Production duplicate customer sends after timeout and retry",
        "body": "Enterprise production workflow duplicates customer actions and needs manual reconciliation.",
        "comments": 30,
        "saturated": True,
        "fix_in_progress": True,
        "production": True,
        "unresolved": True,
    }
    compiled = MODULE.compile_record(record, TAXONOMY, 1, 61)
    assert compiled.constraint_value >= 45
    assert compiled.intervention_value < compiled.constraint_value
    assert compiled.intervention in {"corpus_only", "watch", "ask_diagnostic_question"}


def test_high_value_unsaturated_signal_escalates_intervention():
    record = {
        "repository": "example/workflows",
        "number": 10,
        "title": "Production duplicate customer sends after timeout and retry",
        "body": (
            "Enterprise production customer workflow repeatedly duplicates actions. "
            "Manual restart and reconciliation required daily. Steps to reproduce and logs attached."
        ),
        "comments": 1,
        "production": True,
        "unresolved": True,
        "contribution_gap": True,
        "author_role": "automation engineer",
    }
    compiled = MODULE.compile_record(record, TAXONOMY, 1, 61)
    assert compiled.constraint_id == "side-effect-integrity"
    assert compiled.constraint_value >= 60
    assert compiled.intervention_value >= 60
    assert compiled.intervention in {
        "precision_comment",
        "build_reproduction",
        "build_patch_or_diagnostic",
        "operator_assistance_or_offer",
    }


def test_generality_increases_across_repositories():
    raw = [
        {"repository": "a/one", "title": "duplicate retry timeout"},
        {"repository": "b/two", "title": "duplicate retry timeout"},
        {"repository": "c/three", "title": "duplicate retry timeout"},
    ]
    mapping = MODULE.generality_map(raw, TAXONOMY)
    assert mapping["side-effect-integrity"] > 25


def test_constraint_state_promotes_with_repeated_strong_evidence():
    base = {
        "source_platform": "github",
        "number": 1,
        "url": "",
        "title": "Production duplicate retry causes customer impact and manual restart",
        "author": "operator",
        "observed_at": "2026-08-08T00:00:00+00:00",
        "production_evidence": 100,
        "economic_consequence": 90,
        "workaround_burden": 80,
        "recurrence": 80,
        "cross_system_generality": 70,
        "buyer_proximity": 80,
        "serviceability": 70,
        "proof_feasibility": 70,
        "urgency": 70,
        "commodity_penalty": 0,
        "solved_penalty": 0,
        "weak_evidence_penalty": 0,
        "constraint_value": 82,
        "intervention_value": 75,
        "intervention": "build_reproduction",
        "constraint_id": "side-effect-integrity",
        "constraint_name": "Ambiguous or duplicate side effects",
        "constraint_match_score": 80,
        "constraint_terms": ["duplicate", "retry"],
        "economic_chain": ["failure", "constraint", "ops", "economic", "workaround"],
        "saturation_state": "emerging",
        "reason": "test",
    }
    records = []
    for index, repo in enumerate(("a/one", "b/two", "c/three"), 1):
        data = dict(base)
        data["signal_id"] = f"github:{repo}#{index}"
        data["repository"] = repo
        data["number"] = index
        records.append(MODULE.IntelligenceRecord(**data))
    promoted = MODULE.apply_constraint_states(records)
    assert all(item.saturation_state == "confirmed" for item in promoted)
