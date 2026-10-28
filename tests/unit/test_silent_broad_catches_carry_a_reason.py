"""A broad catch that says nothing is the dangerous kind — it must say why.

The repo has 283 `except Exception` / bare handlers and no ruff rule enforcing
BLE001, so the convention "justify a blind except at the site" was voluntary:
168 carried `# noqa: BLE001 — <reason>` and 115 did not. Most of the 115 are
fine because they *do* something visible afterwards (log, re-raise, return a
value the caller checks).

The subset this gate covers is narrower and sharper: a blind catch whose body
is **silent** — `pass`, `continue`, an empty body, or `return None` / `return ""`
and nothing else. There is no trace anywhere, so a NameError, an AttributeError
from a typo, or a real dependency failure all read exactly like "nothing to do
here". That is the shape that produced #505 (a database that refused to connect
and a database that was never configured printing the same nothing).

Measured before this gate: 34 such handlers, 17 with a reason and **17 without**.
All 17 turned out to be legitimate best-effort paths — the defect was that the
reason existed only in the author's head. Each one now carries it at the site,
and this gate keeps the next one from arriving unexplained.

Why not just enable ruff's BLE001? Because it fires on all 283, and 249 of them
are not silent; requiring a `# noqa` on those would generate a hundred markers
that mean nothing. A rule that everybody silences enforces nothing.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROOTS = (
    "agent", "api", "cli", "craft", "evidence", "experiments", "integrations",
    "mcp", "observability", "providers", "sandbox", "storage", "retrieval",
)
_MIN_REASON = 12
_MARKER = "BLE001"


def _is_blind(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    return isinstance(handler.type, ast.Name) and handler.type.id in ("Exception", "BaseException")


def _is_silent(handler: ast.ExceptHandler) -> bool:
    """True when the handler's whole body leaves no trace."""
    body = [
        node for node in handler.body
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str))
    ]
    if not body:
        return True
    if len(body) != 1:
        return False
    only = body[0]
    if isinstance(only, (ast.Pass, ast.Continue)):
        return True
    if isinstance(only, ast.Return):
        value = only.value
        return value is None or (isinstance(value, ast.Constant) and value.value in (None, ""))
    return False


def _reason_of(line: str) -> str | None:
    """The justification text on an `except` line, or None when absent/thin."""
    if _MARKER not in line:
        return None
    tail = line.split(_MARKER, 1)[1]
    for dash in ("\u2014", "--", "-"):
        if dash in tail:
            text = tail.split(dash, 1)[1].strip()
            return text if len(text) >= _MIN_REASON else None
    return None


def _scan(source: str, filename: str = "<mem>") -> list[tuple[int, str | None]]:
    """(lineno, reason-or-None) for every silent blind catch in `source`."""
    lines = source.splitlines()
    found: list[tuple[int, str | None]] = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        if isinstance(node, ast.ExceptHandler) and _is_blind(node) and _is_silent(node):
            line = lines[node.lineno - 1] if node.lineno - 1 < len(lines) else ""
            found.append((node.lineno, _reason_of(line)))
    return found


def _production_files() -> list[Path]:
    files: list[Path] = []
    for root in _ROOTS:
        files.extend(p for p in (_REPO_ROOT / root).rglob("*.py") if "__pycache__" not in p.parts)
    return files


# ── the gate's own detector: it must see the four shapes differently ────────


def test_the_detector_separates_silent_from_visible() -> None:
    silent_unexplained = """
def f():
    try:
        return g()
    except Exception:
        pass
"""
    silent_explained = """
def f():
    try:
        return g()
    except Exception:  # noqa: BLE001 — optional dependency, honest degradation
        return None
"""
    visible = """
def f():
    try:
        return g()
    except Exception as exc:
        log.warning("g failed: %s", exc)
"""
    narrow = """
def f():
    try:
        return g()
    except OSError:
        return None
"""

    assert _scan(silent_unexplained) == [(5, None)]
    assert _scan(silent_explained) == [(5, "optional dependency, honest degradation")]
    assert _scan(visible) == [], "a handler that logs leaves a trace"
    assert _scan(narrow) == [], "a narrow catch is not a blind catch"


def test_a_thin_marker_does_not_count_as_a_reason() -> None:
    too_short = """
def f():
    try:
        return g()
    except Exception:  # noqa: BLE001 — ok
        pass
"""

    assert _scan(too_short) == [(5, None)], "`— ok` is a marker, not a justification"


# ── the repo itself ─────────────────────────────────────────────────────────


def test_every_silent_broad_catch_says_why() -> None:
    offenders: list[str] = []
    scanned = 0
    for path in _production_files():
        scanned += 1
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            found = _scan(source, str(path))
        except SyntaxError:  # pragma: no cover — a broken file fails elsewhere
            continue
        for lineno, reason in found:
            if reason is None:
                offenders.append(f"{path.relative_to(_REPO_ROOT)}:{lineno}")

    assert scanned > 100, f"the scan only reached {scanned} files — is the walk broken?"
    assert not offenders, (
        "these blind catches swallow everything and leave no trace; either narrow "
        "the catch, do something visible (log / counter / re-raise), or state why "
        "silence is correct as `# noqa: BLE001 \u2014 <reason>`: " + ", ".join(offenders)
    )


def test_the_scan_reaches_the_sites_that_were_measured() -> None:
    """A guard against the gate quietly matching nothing after a refactor."""
    explained = 0
    for path in _production_files():
        source = path.read_text(encoding="utf-8", errors="replace")
        try:
            explained += sum(1 for _, reason in _scan(source, str(path)) if reason)
        except SyntaxError:  # pragma: no cover
            continue

    assert explained >= 34, (
        f"only {explained} justified silent catches found; #508 measured 34 — if "
        "handlers were narrowed or removed on purpose, lower this floor in the "
        "same change"
    )
