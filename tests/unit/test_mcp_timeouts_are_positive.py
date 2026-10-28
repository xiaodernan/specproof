"""A zero or negative MCP timeout fires before the command starts — and used to say otherwise.

``subprocess.run(timeout=0)`` and ``timeout=-1`` raise ``TimeoutExpired``
immediately: the child is never spawned. ``mcp/tools.py`` fed those straight
into the ``TimeoutExpired`` branch, which reports

    command timed out after -1s (the run may still be in progress): ...

Two false statements in one line: nothing was started, so no run is in
progress, and "-1s" is not a duration anybody can act on. ``SPECPROOF_MCP_VERIFY_TIMEOUT``
and ``SPECPROOF_MCP_CRAFT_TIMEOUT`` are operator knobs, so a bad value is an
operator mistake and is now refused with the value in the message.

The last leg keeps the wiring honest: the knobs must go through the
positive-only reader, or the refusal never runs.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from mcp.tools import ToolError, _env_positive_int, _run_cli

_TOOLS = Path(__file__).resolve().parents[2] / "mcp" / "tools.py"
_TIMEOUT_KNOBS = ("SPECPROOF_MCP_VERIFY_TIMEOUT", "SPECPROOF_MCP_CRAFT_TIMEOUT")


@pytest.mark.parametrize("raw", ["-1", "0", "-3600"])
def test_a_non_positive_knob_is_refused_with_its_value(
    monkeypatch: pytest.MonkeyPatch, raw: str,
) -> None:
    monkeypatch.setenv("SPECPROOF_MCP_VERIFY_TIMEOUT", raw)

    with pytest.raises(ToolError) as caught:
        _env_positive_int("SPECPROOF_MCP_VERIFY_TIMEOUT", 1800)

    message = str(caught.value)
    assert "positive" in message
    assert raw in message, "the message must quote the value the operator set"
    assert "would fire before the command starts" in message


def test_a_positive_knob_is_returned_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECPROOF_MCP_VERIFY_TIMEOUT", "45")

    assert _env_positive_int("SPECPROOF_MCP_VERIFY_TIMEOUT", 1800) == 45


def test_an_unset_knob_keeps_its_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPECPROOF_MCP_VERIFY_TIMEOUT", raising=False)

    assert _env_positive_int("SPECPROOF_MCP_VERIFY_TIMEOUT", 1800) == 1800


@pytest.mark.parametrize("bad", [-1, 0])
def test_run_cli_refuses_a_non_positive_timeout_instead_of_faking_a_timeout(bad: int) -> None:
    with pytest.raises(ToolError) as caught:
        _run_cli(["echo", "hi"], bad)

    message = str(caught.value)
    assert "invalid timeout" in message
    assert "not started" in message
    assert "in progress" not in message, (
        "nothing was started, so claiming a run may be in progress is false"
    )
    assert "timed out" not in message


def test_a_valid_timeout_still_runs_the_command() -> None:
    completed = _run_cli(["echo", "hi"], 30)

    assert completed.stdout.strip() == "hi"


def test_the_timeout_knobs_are_read_through_the_positive_only_reader() -> None:
    """If a knob goes back to plain `_env_int`, the refusal above never runs."""
    tree = ast.parse(_TOOLS.read_text(encoding="utf-8"))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id != "_env_int" or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and first.value in _TIMEOUT_KNOBS:
            offenders.append(f"line {node.lineno}: _env_int({first.value!r})")

    assert not offenders, (
        "timeout knobs must use _env_positive_int (zero/negative fires before the "
        "command starts): " + "; ".join(offenders)
    )
