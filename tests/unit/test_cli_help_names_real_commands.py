"""Fence: the CLI's hand-written command lists must name real commands.

``main.py`` carries TWO prose lists of commands — the module docstring and
``HELP_EPILOG`` (what a user sees on ``specproof --help``). Neither is generated
from the click registry, so a rename or retirement leaves the help text telling
users to run something that no longer exists (the "声称 ≠ 使用" drift class,
same as the quickstart guide fence in #294).

Only the first token after ``specproof`` is checked: ``specproof craft run``
means the ``craft`` command, and sub-command existence is a different layer.
"""

import re

from click.testing import CliRunner

import cli.specproof.main as main
from cli.specproof.main import HELP_EPILOG, cli

_MENTION_RE = re.compile(r"^\s+specproof\s+([a-z][a-z0-9-]*)\s", re.MULTILINE)


def _mentioned(text: str) -> set[str]:
    return set(_MENTION_RE.findall(text))


def test_help_epilog_names_only_registered_commands():
    mentioned = _mentioned(HELP_EPILOG)
    # non-empty denominator: an empty extraction must not read as "clean"
    assert len(mentioned) >= 3
    unknown = mentioned - set(cli.commands)
    assert not unknown, f"HELP_EPILOG names unregistered commands: {sorted(unknown)}"


def test_module_docstring_names_only_registered_commands():
    mentioned = _mentioned(main.__doc__ or "")
    assert len(mentioned) >= 3
    unknown = mentioned - set(cli.commands)
    assert not unknown, f"module docstring names unregistered commands: {sorted(unknown)}"


def test_help_epilog_covers_the_first_run_path():
    assert {"quickstart", "demo"} <= _mentioned(HELP_EPILOG)


def test_cli_help_renders_the_epilog():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0, result.output
    assert "第一次使用" in result.output
    assert "specproof quickstart" in result.output


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
