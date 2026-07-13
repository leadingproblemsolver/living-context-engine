"""An accepted continuity outcome must be recoverable after resynchronization."""
from lce.continuity import ledger
from lce.main import main
from lce.retrieval import query as run_query
from lce.storage.sqlite_store import SQLiteStore


def test_accept_survives_resync_and_is_recoverable(tmp_lce_env):
    settings, _corpus_root = tmp_lce_env
    assert main(["init"]) == 0
    assert main(["sync", "."]) == 0
    store = SQLiteStore(settings.db_path)

    record = ledger.log_outcome(
        store,
        content="Adopt the second worker pool fix permanently for the retry queue.",
        outcome_type="decision",
    )
    assert main(["accept", record["record_id"]]) == 0

    rec = store.get_continuity_record(record["record_id"])
    assert rec["state"] == "accepted"
    assert rec["reingest_path"]

    assert main(["sync", "."]) == 0  # resync must pick the reingest file back up

    hits = run_query(store, "second worker pool fix permanently retry queue", top_k=50)
    matches = [h for h in hits if "second worker pool fix permanently" in h.content.lower()]
    assert matches, "accepted outcome was not recoverable after resync"
    assert any("origin=continuity" in " ".join(h.reasons) for h in matches)
