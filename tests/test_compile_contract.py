"""Compiled artifacts must match the strict schema, be deterministic given
fixed DB state, and show an honest empty state rather than failing when
there is no evidence."""
from lce.continuity.compile import compile_artifact
from lce.continuity.packet import build_context_packet
from lce.main import main
from lce.storage.sqlite_store import SQLiteStore

METADATA_KEYS = {"artifact_type", "mode", "topic", "created_at", "corpus_freshness", "source_lineage"}
SECTION_KEYS = {
    "what_matters_now",
    "decisions",
    "blockers",
    "next_actions",
    "assumptions_and_uncertainties",
    "evidence",
    "next_operator_action",
}


def test_compiled_artifact_matches_schema_and_is_deterministic(tmp_lce_env):
    settings, _corpus_root = tmp_lce_env
    assert main(["init"]) == 0
    assert main(["sync", "."]) == 0
    store = SQLiteStore(settings.db_path)

    packet = build_context_packet(settings, store, query="blocker", intent="blockers")
    a1 = compile_artifact(packet)
    a2 = compile_artifact(packet)
    d1, d2 = a1.to_dict(), a2.to_dict()

    assert set(d1["metadata"].keys()) == METADATA_KEYS
    assert set(d1["sections"].keys()) == SECTION_KEYS
    assert d1["metadata"]["source_lineage"], "expected non-empty lineage when evidence exists"

    d1["metadata"].pop("created_at")
    d2["metadata"].pop("created_at")
    assert d1 == d2, "compile must be deterministic given the same packet"


def test_compile_on_no_evidence_is_honest_not_hidden(tmp_lce_env):
    settings, _corpus_root = tmp_lce_env
    assert main(["init"]) == 0
    assert main(["sync", "."]) == 0
    store = SQLiteStore(settings.db_path)

    packet = build_context_packet(settings, store, query="zzz_nonexistent_topic_zzz")
    artifact = compile_artifact(packet)
    d = artifact.to_dict()

    assert set(d["sections"].keys()) == SECTION_KEYS  # keys always present, even when empty
    assert d["sections"]["decisions"] == []
    assert d["sections"]["blockers"] == []
    assert any("no evidence found" in u for u in d["sections"]["assumptions_and_uncertainties"])


def test_compile_cli_exits_zero_on_empty_evidence(tmp_lce_env):
    settings, _corpus_root = tmp_lce_env
    assert main(["init"]) == 0
    assert main(["sync", "."]) == 0
    assert main(["compile", "--topic", "zzz_nonexistent_topic_zzz"]) == 0
