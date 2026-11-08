"""Ratchet: no *.py or *.sql in the repo orders by a bare time column.

Measured on the Windows host running the full suite: the timer advances in
~15.6 ms ticks (1999/1999 consecutive ``time.time()`` calls returned the same
value). MySQL/SQLite ``TIMESTAMP DEFAULT CURRENT_TIMESTAMP`` columns are only
second-granular, so two statements committed inside one tick get identical
``created_at`` and any ``ORDER BY created_at`` with no second key then breaks
on whatever the planner did that hour — a payout order, an operator preview,
a retry queue, all swapping.

The house rule is simple and narrow: a time column is only legal as the FIRST
ordering key when a stable second key follows. ``ORDER BY created_at, id``
and friends always qualify. This gate goes red the moment a bare
``ORDER BY <time-col>`` re-enters any shipped source file — eight instances
were found and fixed across ``storage/mysql.py`` and ``api/routes/web.py``
(2026-11-08, #1515), so the ratchet is born at zero.

Docstrings and comments mentioning the shape are fine *only if* a second key
follows — an unanchored ``ORDER BY ... LIMIT`` in prose is the same claim.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: skips matching the rest of the repo's file-scanner gates
SKIP_DIRS = {
    ".git", "node_modules", ".venv", ".venv312", ".scratch", "dist",
    ".mypy_cache", ".pytest_cache", "__pycache__", "worktrees",
    ".specraft", ".local",
}

#: a bare-time ORDER BY: one time key, no second key before the SQL terminator
BARE_TIME_ORDER_BY = re.compile(
    r"ORDER\s+BY\s+"
    r"(?:[a-z][\w]*\.)?"                 # optional table alias
    r"(created_at|updated_at|happened_at|recorded_at|observed_at)"
    r"(?:\s+(?:ASC|DESC))?"
    r"\s*"
    r"(?=LIMIT|OFFSET|\)|;|\"|'|$|\n)",
    re.IGNORECASE,
)


def _shipped_text_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith((".py", ".sql")):
                found.append(Path(dirpath) / name)
    return sorted(found)


def test_no_shipped_file_orders_by_a_bare_time_column() -> None:
    offenders = []
    for path in _shipped_text_files(REPO):
        rel = path.relative_to(REPO).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            offenders.append(f"{rel}: not utf-8")
            continue
        for match in BARE_TIME_ORDER_BY.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{rel}:{line}: ...{match.group(0)}\n")
    assert not offenders, (
        "bare-time ORDER BY found — on a 15.6 ms wall clock two rows written "
        "in one tick get identical timestamps and this order is arbitrary:\n"
        + "".join(offenders)
    )


_COL = "created_at"


def test_the_gate_matches_a_bare_call(tmp_path: Path) -> None:
    """Reverse control: a known-bare claim triggers the regex."""
    sample = f'"FROM findings WHERE job_id = %s ORDER BY {_COL}", (job_id,)'
    assert BARE_TIME_ORDER_BY.search(sample) is not None


def test_the_gate_tolerates_a_tiebroken_call(tmp_path: Path) -> None:
    """The allowed shape (a stable second key) does not trigger."""
    sample = f'"FROM findings WHERE job_id = %s ORDER BY {_COL}, id", (job_id,)'
    assert BARE_TIME_ORDER_BY.search(sample) is None


def test_the_gate_tolerates_a_reordered_pair(tmp_path: Path) -> None:
    """Ordering by a non-time key first is outside this gate entirely."""
    sample = f'"FROM findings WHERE job_id = %s ORDER BY id, {_COL}", (job_id,)'
    assert BARE_TIME_ORDER_BY.search(sample) is None
