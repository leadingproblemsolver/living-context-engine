"""Every lce/* module must import cleanly with zero third-party dependencies.

Directly guards against the historical failure where every command was
import-broken because lce/core/ didn't exist.
"""
import importlib
import pkgutil

import lce


def test_all_lce_modules_import_cleanly():
    failures = []
    for _finder, name, _ispkg in pkgutil.walk_packages(lce.__path__, prefix="lce."):
        try:
            importlib.import_module(name)
        except Exception as e:  # noqa: BLE001 - we want to report every failure
            failures.append((name, repr(e)))
    assert not failures, f"modules failed to import: {failures}"
