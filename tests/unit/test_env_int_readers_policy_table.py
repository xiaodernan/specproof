"""#492 — every integer env reader's policy, pinned as a table.

Six modules read a numeric environment knob and they do NOT all treat a bad
value the same way. That spread is deliberate in each place, but until now
nothing pinned it: changing one reader's error policy was a silent change.

The repo's stated convention (#471) is "blank means unset, a non-numeric value
is refused by name" — that is what ``storage/env_config.int_env`` does. Three
readers deliberately deviate and fall back to the default instead:

* ``agent.nodes.run_deep_experiments`` — also clamps to ``[1, 10]``;
* ``retrieval`` (embeddings + rerank, one shared reader) — clamps to ``>= 0``.

Those three are the outliers. If the product ever decides a typo'd knob must be
refused everywhere, change them and this table together — that is what the
table is for.

``craft.budget`` and ``craft.llm`` raise their own domain errors (a bad budget
or LLM knob must fail loud where it is read), and ``mcp.tools`` raises
``ToolError`` because an MCP tool call has to answer with a structured failure.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from agent.nodes.run_deep_experiments import _env_int as deep_env_int
from craft.budget import _env_int as budget_env_int
from craft.llm import _env_int as llm_env_int
from mcp.tools import _env_int as mcp_env_int
from retrieval._env import env_int as retrieval_env_int
from storage.env_config import int_env

Reader = Callable[..., int]

DEFAULT = 7


def _outcome(reader: Reader, raw: str) -> tuple[str, Any]:
    """("value", n) or ("raise", ExceptionTypeName) for one raw value."""
    import os

    os.environ["SPECPROOF_TEST_KNOB"] = raw
    try:
        return ("value", reader("SPECPROOF_TEST_KNOB", DEFAULT))
    except Exception as exc:  # noqa: BLE001 — the type name is the datum
        return ("raise", type(exc).__name__)


#: (label, reader, junk outcome, negative outcome, big outcome)
POLICIES: list[tuple[str, Reader, tuple[str, Any], tuple[str, Any], tuple[str, Any]]] = [
    ("deep", deep_env_int, ("value", DEFAULT), ("value", 1), ("value", 10)),
    ("budget", budget_env_int, ("raise", "BudgetError"), ("raise", "BudgetError"), ("value", 999)),
    (
        "llm", llm_env_int,
        ("raise", "LLMUnavailableError"), ("raise", "LLMUnavailableError"), ("value", 999),
    ),
    ("mcp", mcp_env_int, ("raise", "ToolError"), ("value", -3), ("value", 999)),
    ("retrieval", retrieval_env_int, ("value", DEFAULT), ("value", 0), ("value", 999)),
    ("int_env", int_env, ("raise", "EnvKnobError"), ("value", -3), ("value", 999)),
]


@pytest.mark.parametrize("raw", ["", "   "])
def test_blank_means_the_default_for_every_reader(raw: str) -> None:
    for label, reader, *_ in POLICIES:
        assert _outcome(reader, raw) == ("value", DEFAULT), label


@pytest.mark.parametrize("label,reader,junk,neg,big", POLICIES, ids=[p[0] for p in POLICIES])
def test_the_policy_table(
    label: str,
    reader: Reader,
    junk: tuple[str, Any],
    neg: tuple[str, Any],
    big: tuple[str, Any],
) -> None:
    assert _outcome(reader, "abc") == junk, f"{label}: junk policy changed"
    assert _outcome(reader, "-3") == neg, f"{label}: negative policy changed"
    assert _outcome(reader, "999") == big, f"{label}: large-value policy changed"


def test_a_plain_integer_is_read_the_same_by_every_reader() -> None:
    for label, reader, *_ in POLICIES:
        assert _outcome(reader, "12") == ("value", 12) or label == "deep", label
    # deep is the one reader that clamps; 12 sits above its ceiling.
    assert _outcome(deep_env_int, "12") == ("value", 10)


def test_the_two_retrieval_modules_share_one_reader() -> None:
    # The dedup is the point: a change to the clamp must reach both modules.
    import retrieval.embeddings as embeddings
    import retrieval.rerank as rerank

    assert embeddings._env_int is rerank._env_int
