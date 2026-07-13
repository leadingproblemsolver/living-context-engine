"""Shared pytest fixtures: an isolated tmp corpus + tmp state dir per test.

No test touches real user data or a real home-directory .lce/ -- everything
runs inside pytest's tmp_path.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "golden_corpus"


@pytest.fixture()
def tmp_lce_env(tmp_path, monkeypatch):
    corpus_root = tmp_path / "project"
    corpus_root.mkdir()
    for f in FIXTURES_DIR.iterdir():
        if f.is_file():
            shutil.copy(f, corpus_root / f.name)

    state_dir = tmp_path / "state" / ".lce"
    monkeypatch.setenv("LCE_STATE_DIR", str(state_dir))
    monkeypatch.delenv("LCE_DB_PATH", raising=False)
    monkeypatch.delenv("LCE_CONTINUITY_DIR", raising=False)
    monkeypatch.chdir(corpus_root)

    from lce.core.config import Settings

    settings = Settings.load(".")

    return settings, corpus_root
