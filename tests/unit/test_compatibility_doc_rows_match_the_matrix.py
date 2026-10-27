"""The architecture doc's compatibility table must agree with the shipped matrix.

Measured before this gate: the doc's table said **`规划 (planned)`** for
Java/Gradle, with `—` for the image, `待定` for the toolchain and
「detect 抛 AdapterNotImplemented; 无执行器」 for the limits — while
`GradleAdapter` in `experiments/adapters.py` implements `detect` (matches
`build.gradle` / `build.gradle.kts`), `prepare` (`run_test`), and `run` (Docker
sandbox, `local` refused). The code matrix said `已支持 (Docker 沙箱)`; the
architecture doc said the feature did not exist. Four cells of one row were
stale, and that row is the reference a user reads before trying Gradle at all.

The gate is one-directional on purpose — **code → doc**:

* every row of `COMPATIBILITY_MATRIX` must have a doc row with the same
  `language` + `build_tool` and the same status;
* a doc row that the matrix does not model may only be a known-limitation row —
  it may not claim a `已支持` tier.

Doc-only rows are legitimate (`Java (本地回退, JDK ≥ 22)` documents a fallback
path, not an adapter), which is why the reverse direction is not asserted as
"must exist in code".
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from experiments.adapters import COMPATIBILITY_MATRIX

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "architecture" / "EXECUTION_COMPATIBILITY.md"

_HEADER_MARKER = "支持状态"
_SUPPORTED_PREFIX = "已支持"


def _split_row(line: str) -> list[str]:
    """Cells of a markdown row, honouring escaped ``\\|`` inside a cell.

    The JavaScript/TypeScript row's test-runner cell is
    ``jest \\| vitest \\| node:test``; splitting on every pipe shifts every
    later column by two and the status would be read out of the wrong cell.
    """
    body = line.strip()
    assert body.startswith("|") and body.endswith("|"), body
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", body)[1:-1]]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(cell and set(cell) <= {"-", ":"} for cell in cells)


def _doc_rows() -> list[dict[str, str]]:
    """``{language, build_tool, status}`` for every data row of the main table."""
    lines = DOC.read_text(encoding="utf-8").splitlines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if line.strip().startswith("|") and _HEADER_MARKER in line
        ),
        None,
    )
    if start is None:
        pytest.fail(f"the doc has no table with a {_HEADER_MARKER!r} column")

    rows: list[dict[str, str]] = []
    for line in lines[start + 1 :]:
        if not line.strip().startswith("|"):
            break
        cells = _split_row(line)
        if _is_separator(cells):
            continue
        if len(cells) < 4:
            continue
        rows.append(
            {
                "language": cells[0],
                "build_tool": cells[1],
                "status": cells[3].replace("*", "").strip(),
            }
        )
    return rows


def _norm(status: str) -> str:
    return status.replace("*", "").strip()


_ROWS = _doc_rows()


def test_the_doc_table_was_actually_found() -> None:
    """Anti-vacuity: an empty parse would make both checks below vacuous."""
    assert _ROWS, "no data rows parsed out of the compatibility table"


@pytest.mark.parametrize(
    "row",
    COMPATIBILITY_MATRIX,
    ids=lambda row: f"{row.language}/{row.build_tool}",
)
def test_every_matrix_row_agrees_with_the_doc(row) -> None:
    """The doc must not contradict the shipped matrix on any row it shares."""
    matching = [
        doc
        for doc in _ROWS
        if doc["language"] == row.language and doc["build_tool"] == row.build_tool
    ]

    assert matching, (
        f"COMPATIBILITY_MATRIX ships {row.language}/{row.build_tool} but the doc "
        f"table has no row for it; doc rows are "
        f"{[(d['language'], d['build_tool']) for d in _ROWS]}"
    )
    assert len(matching) == 1, f"duplicate doc rows for {row.language}/{row.build_tool}"
    assert _norm(matching[0]["status"]) == _norm(row.status), (
        f"{row.language}/{row.build_tool}: the matrix says {row.status!r} but the "
        f"doc says {matching[0]['status']!r}"
    )


def test_a_doc_only_row_does_not_claim_a_supported_tier() -> None:
    """A row the matrix does not model may be a known limitation, not a capability.

    `Java (本地回退, JDK ≥ 22)` is the live example: it documents a fallback path
    whose status is 「编译可用, 跑测试起不来」. If such a row ever claimed
    `已支持 …`, the doc would be advertising an adapter the registry cannot
    produce.
    """
    modelled = {(row.language, row.build_tool) for row in COMPATIBILITY_MATRIX}
    offenders = [
        doc
        for doc in _ROWS
        if (doc["language"], doc["build_tool"]) not in modelled
        and doc["status"].startswith(_SUPPORTED_PREFIX)
    ]

    assert offenders == [], (
        "these doc rows claim a supported tier but no matrix row models them: "
        f"{[(d['language'], d['build_tool'], d['status']) for d in offenders]}"
    )
