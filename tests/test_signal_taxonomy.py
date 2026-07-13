"""No signal row may ever be persisted with a null or invalid signal_type."""
from lce.main import main
from lce.pipeline.signals import VALID_SIGNAL_TYPES
from lce.storage.sqlite_store import SQLiteStore


def test_no_null_or_invalid_signal_types_persisted(tmp_lce_env):
    settings, _corpus_root = tmp_lce_env
    assert main(["init"]) == 0
    assert main(["sync", "."]) == 0
    store = SQLiteStore(settings.db_path)

    signals = store.get_signals()
    assert signals
    for s in signals:
        assert s["signal_type"] is not None
        assert s["signal_type"] in VALID_SIGNAL_TYPES

    with store.conn() as db:
        null_count = db.execute("SELECT COUNT(*) FROM signals WHERE signal_type IS NULL").fetchone()[0]
    assert null_count == 0

    validation = store.validation_report()
    assert validation["null_signal_types"] == 0
    assert validation["ok"] is True
