"""The README's language table must name every language the matrix ships.

`COMPATIBILITY_MATRIX` is the product's own statement of what Verify can run,
and it declared five 「已支持」 rows: Java/Maven, Java/Gradle,
JavaScript/TypeScript, Python/pip, Go/go. The README table — the only place a
new user learns *which languages Verify can actually run their tests in* —
listed three. **Go and Java/Gradle were supported and undiscoverable**, which is
the "declared but not visible" shape this repo keeps finding, pointed at the
front door instead of at the code.

The gate reads both sides mechanically rather than trusting either:

* the matrix (code) for the languages marked 「已支持」;
* the first column of the markdown table under 「按语言区分执行面」 (docs).

Matching is on a ``/`` boundary: the matrix says ``Java``, the README row says
``Java/Maven``, and a plain ``startswith`` would let ``Java`` be satisfied by the
``JavaScript/TypeScript`` row.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from experiments.adapters import COMPATIBILITY_MATRIX

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / "README.md"

#: The sentence that introduces the table, used to find it without depending on
#: line numbers (the README is edited by hand).
_TABLE_ANCHOR = "按语言区分执行面"


def _readme_rows() -> list[list[str]]:
    """Cells of every row of the language table under ``_TABLE_ANCHOR``."""
    lines = README.read_text(encoding="utf-8").splitlines()
    start = next(
        (i for i, line in enumerate(lines) if _TABLE_ANCHOR in line),
        None,
    )
    if start is None:
        pytest.fail(f"README no longer contains the anchor {_TABLE_ANCHOR!r}")

    rows: list[list[str]] = []
    started = False
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not started:
            # The anchor sentence is followed by a blank line before the table.
            if not stripped:
                continue
            if not stripped.startswith("|"):
                pytest.fail(f"expected the table right after {_TABLE_ANCHOR!r}, got {stripped!r}")
            started = True
        if not stripped.startswith("|"):
            break
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(set(cell) <= {"-", ":"} and cell for cell in cells):
            continue  # the | --- | separator
        rows.append(cells)
    return rows[1:]  # drop the header row


def _cell_names(cell: str, language: str) -> bool:
    """True when a README cell names ``language`` on a ``/`` boundary."""
    return cell == language or cell.startswith(language + "/")


def _shipped_languages() -> set[str]:
    return {
        row.language
        for row in COMPATIBILITY_MATRIX
        if row.status.startswith("已支持")
    }


_ROWS = _readme_rows()
_SHIPPED = _shipped_languages()


def test_the_matrix_still_ships_more_than_one_language() -> None:
    """Anti-vacuity: one shipped language would make the reconciliation trivial."""
    assert len(_SHIPPED) >= 2, _SHIPPED


def test_the_readme_table_was_actually_found() -> None:
    """Anti-vacuity: an empty parse would make both directions below vacuous."""
    assert _ROWS, "no rows parsed out of the README language table"


@pytest.mark.parametrize("language", sorted(_SHIPPED))
def test_every_shipped_language_is_named_in_the_readme_table(language: str) -> None:
    """A language the matrix calls 「已支持」 must be discoverable from the front door."""
    cells = [row[0] for row in _ROWS]

    assert any(_cell_names(cell, language) for cell in cells), (
        f"COMPATIBILITY_MATRIX ships {language!r} as 已支持 but no README row "
        f"names it; the table's first column is {cells}"
    )


@pytest.mark.parametrize("row", _ROWS, ids=lambda row: row[0])
def test_every_readme_row_names_a_shipped_language(row: list[str]) -> None:
    """The other direction: no README row may advertise something not shipped."""
    cell = row[0]

    assert any(_cell_names(cell, language) for language in _SHIPPED), (
        f"README advertises {cell!r} but COMPATIBILITY_MATRIX ships only {sorted(_SHIPPED)}"
    )


@pytest.mark.parametrize("row", _ROWS, ids=lambda row: row[0])
def test_every_readme_row_says_what_runs_and_where(row: list[str]) -> None:
    """A row with an empty middle or last cell tells a reader nothing."""
    assert len(row) >= 3, row
    assert row[1].strip(), f"{row[0]!r} has an empty 「跑仓库自带测试」 cell"
    assert row[2].strip(), f"{row[0]!r} has an empty 「执行面」 cell"
