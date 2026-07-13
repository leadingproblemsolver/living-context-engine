"""Every retrieval hit must match the canonical schema exactly."""
from lce.main import main
from lce.pipeline.signals import VALID_SIGNAL_TYPES
from lce.retrieval import VALID_TYPES
from lce.retrieval import query as run_query
from lce.storage.sqlite_store import SQLiteStore

CANONICAL_KEYS = {"type", "score", "signal_type", "content", "source_path", "doc_id", "ru_id", "signal_id", "domain", "reasons"}


def test_hits_match_canonical_schema(tmp_lce_env):
    settings, _corpus_root = tmp_lce_env
    assert main(["init"]) == 0
    assert main(["sync", "."]) == 0
    store = SQLiteStore(settings.db_path)

    hits = run_query(store, "blocker payment queue", top_k=50)
    assert hits, "expected at least one hit for a term present in the golden corpus"

    for h in hits:
        d = h.to_dict()
        assert set(d.keys()) == CANONICAL_KEYS
        assert d["type"] in VALID_TYPES
        assert d["signal_type"] is None or d["signal_type"] in VALID_SIGNAL_TYPES
        assert isinstance(d["reasons"], list)


def test_noisy_context_does_not_outrank_real_signals(tmp_lce_env):
    settings, _corpus_root = tmp_lce_env
    assert main(["init"]) == 0
    assert main(["sync", "."]) == 0
    store = SQLiteStore(settings.db_path)

    hits = run_query(store, "blocker", top_k=10)
    assert hits
    top = hits[0]
    assert top.signal_type == "blocker", f"expected a blocker to rank first, got {top.to_dict()}"
