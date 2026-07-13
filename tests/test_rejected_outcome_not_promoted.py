"""A rejected suggestion must never re-enter the corpus or resurface as
current accepted direction."""
from lce.continuity import ledger
from lce.main import main
from lce.retrieval import query as run_query
from lce.storage.sqlite_store import SQLiteStore


def test_reject_never_reingests_or_resurfaces(tmp_lce_env):
    settings, _corpus_root = tmp_lce_env
    assert main(["init"]) == 0
    assert main(["sync", "."]) == 0
    store = SQLiteStore(settings.db_path)

    record = ledger.log_outcome(
        store,
        content="Roll back the checkout redesign entirely and revert to the old flow.",
        outcome_type="decision",
    )
    assert main(["reject", record["record_id"]]) == 0

    rec = store.get_continuity_record(record["record_id"])
    assert rec["state"] == "rejected"
    assert rec["reingest_path"] is None
    assert not settings.continuity_dir.exists() or not any(settings.continuity_dir.iterdir())

    assert main(["sync", "."]) == 0

    hits = run_query(store, "roll back the checkout redesign entirely revert old flow", top_k=50)
    assert not any("roll back the checkout redesign entirely" in h.content.lower() for h in hits)
