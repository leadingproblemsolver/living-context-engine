"""`lce --help` and every subcommand's --help must exit 0 with no exceptions.

Catches bugs like the historical cmd_context() that only surfaced at
invocation time, not at import time.
"""
import pytest

from lce.main import build_parser

SUBCOMMANDS = ["init", "doctor", "sync", "query", "brief", "compile", "log", "accept", "reject", "status", "export"]


def test_top_level_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--help"])
    assert exc.value.code == 0


@pytest.mark.parametrize("cmd", SUBCOMMANDS)
def test_subcommand_help_exits_zero(cmd):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args([cmd, "--help"])
    assert exc.value.code == 0


def test_no_command_exits_nonzero():
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args([])
    assert exc.value.code != 0
