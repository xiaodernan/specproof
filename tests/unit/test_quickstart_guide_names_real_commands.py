"""Fence: ``quickstart``'s guide must only name commands that really exist.

``_GUIDE`` is hand-written prose listing ``specproof <cmd>`` lines. If a
command is renamed or removed, the guide goes stale and a first-time user is
told to run something that no longer exists — the "声称 ≠ 使用" drift class.
This pins every mentioned command against the real click registry
(``cli.commands``), which is built in ``cli/specproof/main.py``.
"""

import re

from click.testing import CliRunner

from cli.specproof.commands.quickstart import _GUIDE, quickstart
from cli.specproof.main import cli

#: A line such as ``   specproof demo --run      直接执行...``.
_MENTION_RE = re.compile(r"^\s+specproof\s+([a-z][a-z0-9-]*)\s", re.MULTILINE)


def _mentioned() -> set[str]:
    return set(_MENTION_RE.findall(_GUIDE))


def test_guide_mentions_only_registered_commands():
    mentioned = _mentioned()
    # non-empty denominator: an empty extraction must not read as "clean"
    assert len(mentioned) >= 5
    unknown = mentioned - set(cli.commands)
    assert not unknown, f"quickstart names unregistered commands: {sorted(unknown)}"


def test_guide_mentions_the_core_flow():
    # the seven commands the 30-second path relies on
    assert {"demo", "verify", "fix", "craft", "probe", "eval", "replay"} <= _mentioned()


def test_quickstart_prints_banner_and_guide():
    result = CliRunner().invoke(quickstart, [])
    assert result.exit_code == 0
    assert "SpecProof" in result.output
    assert "specproof demo" in result.output


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
