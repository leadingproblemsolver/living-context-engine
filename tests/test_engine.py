import json
import os
import subprocess
import sys
from pathlib import Path

from living_context.extract import extract_path, records_from_text
from living_context.packs import build_pack
from living_context.store import Store


def test_classification():
    records = records_from_text(
        "Decision: use SQLite\nBlocker: missing key\nWhat is next?",
        "a.md",
        "p",
        "h",
        "2026-01-01",
    )
    assert [record.kind for record in records] == ["decision", "blocker", "question"]


def test_lineage():
    record = records_from_text(
        "Action: ship it", "docs/a.md", "p", "hash", "2026-01-01"
    )[0]
    assert record.source_line == 1
    assert record.source_hash == "hash"


def test_ingest_and_status(tmp_path):
    source = tmp_path / "notes.md"
    source.write_text("Decision: one\nAction: two\n", encoding="utf-8")
    store = Store(tmp_path)
    store.ingest(extract_path(source, "p", tmp_path))
    assert store.status()["records"] == 2
    store.close()


def test_source_replacement(tmp_path):
    source = tmp_path / "notes.md"
    source.write_text("Decision: one\n", encoding="utf-8")
    store = Store(tmp_path)
    store.ingest(extract_path(source, "p", tmp_path))
    source.write_text("Decision: changed\nAction: next\n", encoding="utf-8")
    store.ingest(extract_path(source, "p", tmp_path))
    assert store.status()["records"] == 2
    assert not store.query("one")
    store.close()


def test_query_filter(tmp_path):
    source = tmp_path / "notes.md"
    source.write_text(
        "Decision: SQLite storage\nBlocker: cloud credentials\n", encoding="utf-8"
    )
    store = Store(tmp_path)
    store.ingest(extract_path(source, "p", tmp_path))
    assert store.query("SQLite", kinds={"decision"})[0]["kind"] == "decision"
    store.close()


def test_pack(tmp_path):
    source = tmp_path / "notes.md"
    source.write_text("Decision: SQLite storage\n", encoding="utf-8")
    store = Store(tmp_path)
    store.ingest(extract_path(source, "p", tmp_path))
    result = build_pack(store, "SQLite", tmp_path / "pack.md", "p")
    assert result["items"] == 1
    assert (tmp_path / "pack.json").exists()
    store.close()


def test_directory_formats(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"decision": "use local"}), encoding="utf-8")
    (tmp_path / "b.txt").write_text("Risk: stale data", encoding="utf-8")
    assert len(extract_path(tmp_path, "p", tmp_path)) >= 2


def test_cli_smoke(tmp_path):
    source = tmp_path / "notes.md"
    source.write_text(
        "Decision: local first\nBlocker: missing deployment\n", encoding="utf-8"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    commands = [
        ("ingest", str(source), "--project", "demo"),
        ("query", "local", "--project", "demo", "--json"),
        ("timeline", "--project", "demo", "--json"),
        (
            "pack",
            "deployment",
            "--project",
            "demo",
            "--output",
            str(tmp_path / "pack.md"),
        ),
        ("export", "--project", "demo", "--output", str(tmp_path / "out.json")),
        ("status",),
    ]
    for command in commands:
        result = subprocess.run(
            [sys.executable, "-m", "living_context.cli", "--root", str(tmp_path), *command],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "pack.md").exists()
    assert (tmp_path / "out.json").exists()


def test_public_bind_requires_token(tmp_path, monkeypatch):
    from living_context.server import serve
    monkeypatch.delenv("LCE_API_TOKEN", raising=False)
    try:
        serve(tmp_path, "0.0.0.0", 0)
    except RuntimeError as error:
        assert "LCE_API_TOKEN" in str(error)
    else:
        raise AssertionError("public bind should require a token")


def test_same_source_name_is_isolated_by_project(tmp_path):
    source = tmp_path / "notes.md"
    source.write_text("Decision: shared text\n", encoding="utf-8")
    store = Store(tmp_path)
    store.ingest(extract_path(source, "alpha", tmp_path))
    store.ingest(extract_path(source, "beta", tmp_path))
    assert store.status()["records"] == 2
    assert store.query("shared", project="alpha")[0]["project"] == "alpha"
    assert store.query("shared", project="beta")[0]["project"] == "beta"
    store.close()


def test_source_paths_do_not_leak_absolute_machine_paths(tmp_path):
    folder = tmp_path / "inputs"
    folder.mkdir()
    (folder / "notes.md").write_text("Action: ship\n", encoding="utf-8")
    record = extract_path(folder, "p", tmp_path)[0]
    assert record.source_path == "notes.md"
    assert not record.source_path.startswith("/")


def test_single_file_source_paths_include_parent_directory(tmp_path):
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir(); right.mkdir()
    (left / "notes.md").write_text("Decision: left\n", encoding="utf-8")
    (right / "notes.md").write_text("Decision: right\n", encoding="utf-8")
    store = Store(tmp_path)
    store.ingest(extract_path(left / "notes.md", "p", tmp_path))
    store.ingest(extract_path(right / "notes.md", "p", tmp_path))
    paths = {item["source_path"] for item in store.timeline("p")}
    assert paths == {"left/notes.md", "right/notes.md"}
    store.close()


def test_delete_project_is_isolated(tmp_path):
    source = tmp_path / "notes.md"
    source.write_text("Decision: keep context\n", encoding="utf-8")
    store = Store(tmp_path)
    store.ingest(extract_path(source, "alpha", tmp_path))
    store.ingest(extract_path(source, "beta", tmp_path))
    result = store.delete_project("alpha")
    assert result["records_deleted"] == 1
    assert not store.query("context", project="alpha")
    assert store.query("context", project="beta")
    assert [item["project"] for item in store.projects()] == ["beta"]
    store.close()


def test_symlink_sources_are_rejected(tmp_path):
    source = tmp_path / "source.md"
    source.write_text("Decision: no symlink\n", encoding="utf-8")
    link = tmp_path / "link.md"
    try:
        link.symlink_to(source)
    except (OSError, NotImplementedError):
        return
    try:
        extract_path(link, "p", tmp_path)
    except ValueError as error:
        assert "symlink" in str(error)
    else:
        raise AssertionError("symlink source should be rejected")
