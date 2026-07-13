"""Syncing a subdirectory must never mark documents outside it as missing."""
from lce.main import main
from lce.storage.sqlite_store import SQLiteStore


def test_partial_sync_does_not_mark_unrelated_docs_missing(tmp_lce_env):
    settings, corpus_root = tmp_lce_env
    sub = corpus_root / "sub"
    sub.mkdir()
    (sub / "note.md").write_text("Decision: the subdirectory decision was recorded.", encoding="utf-8")

    assert main(["init"]) == 0
    assert main(["sync", "."]) == 0
    store = SQLiteStore(settings.db_path)
    before = {d["source_path"]: d["status"] for d in store.scan_documents()}
    assert all(status == "active" for status in before.values())
    assert any(p.startswith("sub/") for p in before)

    assert main(["sync", "sub"]) == 0
    after = {d["source_path"]: d["status"] for d in store.scan_documents()}

    for path, status in before.items():
        if not path.startswith("sub/"):
            assert after[path] == "active", f"{path} was wrongly marked {after[path]!r} by a scoped sync of 'sub'"
