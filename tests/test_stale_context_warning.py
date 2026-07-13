"""A context packet built after a source file changes without resyncing
must flag itself as stale with a human-readable reason -- never silently
present outdated data as current."""
import time

from lce.continuity.packet import build_context_packet
from lce.main import main
from lce.storage.sqlite_store import SQLiteStore


def test_packet_flags_stale_after_unsynced_change(tmp_lce_env):
    settings, corpus_root = tmp_lce_env
    assert main(["init"]) == 0
    assert main(["sync", "."]) == 0
    store = SQLiteStore(settings.db_path)

    fresh = build_context_packet(settings, store, query="blocker")
    assert fresh.freshness.stale is False
    assert fresh.freshness.last_sync_at is not None

    target = corpus_root / "blockers.md"
    time.sleep(1.1)  # ensure a distinguishable mtime on coarse filesystems
    target.write_text(target.read_text(encoding="utf-8") + "\nBlocker: a brand new blocker appeared.\n", encoding="utf-8")

    stale = build_context_packet(settings, store, query="blocker")
    assert stale.freshness.stale is True
    assert stale.freshness.reason


def test_never_synced_corpus_is_stale(tmp_lce_env):
    settings, _corpus_root = tmp_lce_env
    assert main(["init"]) == 0
    store = SQLiteStore(settings.db_path)
    packet = build_context_packet(settings, store, query="blocker")
    assert packet.freshness.stale is True
    assert packet.freshness.reason
