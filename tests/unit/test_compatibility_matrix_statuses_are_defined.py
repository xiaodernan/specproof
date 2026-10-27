"""The compatibility matrix's statuses must be *defined*, and 实测 must point at a record.

Two gaps this closes, both measured on the tree before the fix:

1. `COMPATIBILITY_MATRIX` used **two** statuses — 「已支持 (实测)」 and
   「已支持 (Docker 沙箱)」 — while `docs/architecture/EXECUTION_COMPATIBILITY.md`
   declared a vocabulary block that defined only the second. A reader who wants
   to know what 「实测」 promises, and what it does not, had nowhere to look.
2. The doc's 「验证记录」 carried dated end-to-end records for Python and Node —
   both *smoke* runs on **temporarily constructed** projects — while the only row
   claiming 「已支持 (实测)」 was Java/Maven, whose evidence is the integration
   differential against the **real** `demo/spring-backend`. The word 实测 was
   doing two different jobs in the same file.

The vocabulary now says which tier each claim belongs to, and the records say
which tier they are. These gates keep both true:

* every status the code ships must appear in the vocabulary block;
* every row claiming 实测 must have a 「验证记录」 line that names it.

Both are mechanical. Neither can be satisfied by adding a word to a table.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from experiments.adapters import COMPATIBILITY_MATRIX

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "architecture" / "EXECUTION_COMPATIBILITY.md"

_VOCAB_ANCHOR = "状态词汇"
_RECORD_HEADING = "## 验证记录"


def _doc_lines() -> list[str]:
    return DOC.read_text(encoding="utf-8").splitlines()


def _vocabulary_block() -> list[str]:
    """The blockquote that declares the status words.

    Bounded by the ``>`` prefix on purpose: the same words appear later in the
    table and in prose, and "it is mentioned somewhere" is exactly the check that
    let 「实测」 stay undefined while being used.
    """
    lines = _doc_lines()
    start = next((i for i, line in enumerate(lines) if _VOCAB_ANCHOR in line), None)
    if start is None:
        pytest.fail(f"the doc no longer contains {_VOCAB_ANCHOR!r}")
    block: list[str] = []
    for line in lines[start:]:
        if not line.lstrip().startswith(">"):
            break
        block.append(line)
    return block


def _record_lines() -> list[str]:
    """Lines of the 「验证记录」 section, or an empty list when it is absent."""
    lines = _doc_lines()
    start = next((i for i, line in enumerate(lines) if line.strip() == _RECORD_HEADING), None)
    if start is None:
        return []
    out: list[str] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        out.append(line)
    return out


_STATUSES = sorted({row.status for row in COMPATIBILITY_MATRIX})
_BLOCK = "\n".join(_vocabulary_block())


def test_the_matrix_ships_at_least_one_status() -> None:
    assert _STATUSES, "COMPATIBILITY_MATRIX has no rows"


def test_the_vocabulary_block_was_actually_found() -> None:
    """Anti-vacuity: an empty block would make every check below vacuous."""
    assert _BLOCK.strip(), "the status vocabulary blockquote was not found"


@pytest.mark.parametrize("status", _STATUSES)
def test_every_matrix_status_is_defined_in_the_vocabulary(status: str) -> None:
    """A status used in code but not defined here cannot be interpreted."""
    assert status in _BLOCK, (
        f"COMPATIBILITY_MATRIX ships {status!r} but the doc's status vocabulary "
        f"does not define it; the block is:\n{_BLOCK}"
    )


_MEASURED = [row for row in COMPATIBILITY_MATRIX if "实测" in row.status]


def test_the_measured_tier_is_not_empty() -> None:
    """If no row claims 实测, the pointer check below would be vacuous."""
    assert _MEASURED, "no row claims 实测 — either drop this gate or record one"


@pytest.mark.parametrize(
    "row",
    _MEASURED,
    ids=lambda row: f"{row.language}/{row.build_tool}",
)
def test_a_measured_row_points_at_a_record(row) -> None:
    """`已支持 (实测)` has to name the run that measured it.

    The pointer is a 「验证记录」 line starting with `- 实测` that names the row
    as `language/build_tool`. A dated smoke entry for a temporary project does
    not satisfy it — the vocabulary says so, and this asserts it stays that way.
    """
    records = [line for line in _record_lines() if line.lstrip().startswith("- 实测")]

    assert records, "the 「验证记录」 section has no `- 实测` line at all"
    named = f"{row.language}/{row.build_tool}"
    assert any(named in line for line in records), (
        f"the row {named!r} claims 实测 but no 「验证记录」 line starting with "
        f"`- 实测` names it; found: {[line[:60] for line in records]}"
    )
