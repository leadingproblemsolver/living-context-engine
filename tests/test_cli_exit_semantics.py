"""Success and failure must be machine-distinguishable exit codes.

Historically main() printed a traceback and returned 0 regardless -- this
guards against that regression.
"""
from lce.main import main


def test_success_exits_zero(tmp_lce_env):
    assert main(["init"]) == 0


def test_doctor_before_init_exits_nonzero(tmp_lce_env):
    assert main(["doctor"]) != 0


def test_query_before_init_exits_nonzero(tmp_lce_env):
    assert main(["query", "--text", "blocker"]) != 0


def test_invalid_record_transition_exits_nonzero(tmp_lce_env):
    assert main(["init"]) == 0
    assert main(["sync", "."]) == 0
    assert main(["accept", "cr_does_not_exist"]) != 0


def test_double_accept_exits_nonzero(tmp_lce_env):
    from lce.continuity import ledger
    from lce.storage.sqlite_store import SQLiteStore

    settings, _corpus_root = tmp_lce_env
    assert main(["init"]) == 0
    assert main(["sync", "."]) == 0
    store = SQLiteStore(settings.db_path)
    record = ledger.log_outcome(store, content="Do the thing.", outcome_type="decision")
    assert main(["accept", record["record_id"]]) == 0
    assert main(["accept", record["record_id"]]) != 0
