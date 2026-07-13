"""The full canonical loop, proven in one isolated test:

init -> doctor -> sync -> query/compile -> log accepted -> log rejected ->
resync -> recover accepted, confirm rejected never resurfaces.

Nothing in this path may raise, and every step's exit code must be 0
(except the deliberately-invalid ones, which must be non-zero).
"""
from lce.continuity import ledger
from lce.main import main
from lce.retrieval import query as run_query
from lce.storage.sqlite_store import SQLiteStore


def test_full_canonical_loop(tmp_lce_env):
    settings, corpus_root = tmp_lce_env

    assert main(["init"]) == 0
    assert main(["doctor"]) == 0
    assert main(["sync", "."]) == 0
    assert main(["doctor"]) == 0

    store = SQLiteStore(settings.db_path)
    hits = run_query(store, "blocker", top_k=20)
    assert hits

    out_path = corpus_root.parent / "dossier.json"
    assert main(["compile", "--topic", "blocker", "--intent", "blockers", "--out", str(out_path)]) == 0
    assert out_path.exists()

    accepted = ledger.log_outcome(
        store,
        content="Adopt the second worker pool fix permanently for the retry queue.",
        outcome_type="decision",
        source_artifact=str(out_path),
    )
    rejected = ledger.log_outcome(
        store,
        content="Roll back the checkout redesign entirely and revert to the old flow.",
        outcome_type="decision",
        source_artifact=str(out_path),
    )

    assert main(["accept", accepted["record_id"]]) == 0
    assert main(["reject", rejected["record_id"]]) == 0

    assert main(["sync", "."]) == 0  # resynchronize

    recovered = run_query(store, "second worker pool fix permanently retry queue", top_k=50)
    assert any("second worker pool fix permanently" in h.content.lower() for h in recovered), "accepted outcome not recovered"

    not_recovered = run_query(store, "roll back the checkout redesign entirely revert old flow", top_k=50)
    assert not any("roll back the checkout redesign entirely" in h.content.lower() for h in not_recovered), "rejected outcome wrongly resurfaced"

    assert main(["status"]) == 0
    assert main(["export", "--out", str(corpus_root.parent / "export.json")]) == 0
