"""A malformed file must not crash sync, pollute retrieval, or block other
files from being ingested; the failure must be visibly logged."""
from lce.main import main
from lce.storage.sqlite_store import SQLiteStore


def test_malformed_file_is_isolated(tmp_lce_env):
    settings, _corpus_root = tmp_lce_env
    assert main(["init"]) == 0
    assert main(["sync", "."]) == 0  # must not raise / must exit 0

    store = SQLiteStore(settings.db_path)
    docs = {d["source_path"] for d in store.scan_documents()}
    assert "malformed.json" not in docs, "malformed input must never become document content"
    assert any(p.endswith("decisions.md") for p in docs)
    assert any(p.endswith("blockers.md") for p in docs)

    runs = store.recent_runs(limit=1, command="sync")
    assert runs
    import json

    proof = json.loads(runs[0]["proof_json"]) if isinstance(runs[0].get("proof_json"), str) else runs[0]
    # proof is stored via add_run(payload) -> proof_json column holds payload['proof']
    with store.conn() as db:
        row = db.execute("SELECT proof_json FROM pipeline_runs WHERE run_id=?", (runs[0]["run_id"],)).fetchone()
    proof = json.loads(row["proof_json"])
    corpus_errors = proof.get("corpus", {}).get("errors", [])
    assert any("malformed.json" in e["path"] for e in corpus_errors), corpus_errors
