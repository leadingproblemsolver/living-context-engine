"""Every item in a compiled artifact must trace to a source_path that
actually exists in the corpus and actually contains matching content."""
from lce.continuity.compile import compile_artifact
from lce.continuity.packet import build_context_packet
from lce.main import main
from lce.storage.sqlite_store import SQLiteStore


def test_every_artifact_item_traces_to_a_real_source(tmp_lce_env):
    settings, corpus_root = tmp_lce_env
    assert main(["init"]) == 0
    assert main(["sync", "."]) == 0
    store = SQLiteStore(settings.db_path)

    packet = build_context_packet(settings, store, query="blocker", intent="blockers")
    artifact = compile_artifact(packet)
    d = artifact.to_dict()

    checked = 0
    for section_name in ("decisions", "blockers", "next_actions", "evidence"):
        for item in d["sections"][section_name]:
            src = item["source_path"]
            assert src, f"missing source_path in {section_name}: {item}"
            full = corpus_root / src
            assert full.exists(), f"{src} referenced by artifact does not exist on disk"
            file_text = full.read_text(encoding="utf-8").lower()
            snippet = item["content"].strip().lower()[:40]
            assert snippet in file_text, f"claimed content not found verbatim in {src}"
            checked += 1
    assert checked > 0

    for src in d["metadata"]["source_lineage"]:
        assert (corpus_root / src).exists()
