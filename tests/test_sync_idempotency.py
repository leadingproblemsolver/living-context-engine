"""Resyncing unchanged sources must not create duplicate rows."""
from lce.main import main
from lce.storage.sqlite_store import SQLiteStore


def test_resync_unchanged_produces_no_new_rows(tmp_lce_env):
    settings, _corpus_root = tmp_lce_env
    assert main(["init"]) == 0
    assert main(["sync", "."]) == 0
    store = SQLiteStore(settings.db_path)
    docs1 = {d["doc_id"] for d in store.scan_documents()}
    sigs1 = {s["signal_id"] for s in store.get_signals()}
    rus1 = {r["ru_id"] for r in store.get_rus()}
    assert docs1 and sigs1 and rus1

    assert main(["sync", "."]) == 0
    docs2 = {d["doc_id"] for d in store.scan_documents()}
    sigs2 = {s["signal_id"] for s in store.get_signals()}
    rus2 = {r["ru_id"] for r in store.get_rus()}

    assert docs1 == docs2
    assert sigs1 == sigs2
    assert rus1 == rus2
