"""Collect-diff node execution tests (#194) — honest counters at the node
boundary, written WITH the landing (not backfilled).

The git seam (``_git``) is replaced by a dispatching fake; everything else
(the symbol extraction, the semantic hints, the binary/unresolved split,
the no-change sentinel) runs for real. One case per outcome word in
COLLECT_DIFF_OUTCOMES:

- scanned: the diff lists >=1 changed file — the three scopes are produced
  and the word stays scanned even when a per-file read fails (the partial
  case pins that continuation, errors included);
- no_changes: the diff lists zero files — the sentinel symbol is recorded
  and the word separates this from a failed diff;
- diff_failed: the top-level git diff raised — the node returns a two-key
  shape (no changed_files key at all) and the job does NOT stop (no error
  guard follows this node); the word is the only machine-readable record.

plus collect_diff_runs_total on every path and a drift gate binding the
parity family's regex words to COLLECT_DIFF_OUTCOMES and to the source
literals.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

import agent.nodes.collect_diff as collect_diff_module
from agent.nodes.collect_diff import COLLECT_DIFF_OUTCOMES, collect_diff_node
from observability.metrics import snapshot

ROOT = Path(__file__).resolve().parents[2]

# Derived from the declaration — a new word extends the delta table.
_COUNTERS = ("collect_diff_runs_total",) + tuple(
    f"collect_diff_outcomes_{word}_total"
    for word in sorted(COLLECT_DIFF_OUTCOMES)
)

_JAVA_DIFF = (
    "diff --git a/src/A.java b/src/A.java\n"
    "--- a/src/A.java\n"
    "+++ b/src/A.java\n"
    "@@ -1,3 +1,4 @@\n"
    "-    private int bar() {\n"
    "+    public void foo() {\n"
    '+    redisTemplate.set("k", "v");\n'
)


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


def _before() -> dict[str, float]:
    return {name: _counter(name) for name in _COUNTERS}


def _deltas(before: dict[str, float]) -> dict[str, float]:
    return {name: _counter(name) - start for name, start in before.items()}


def _only(*words: str) -> dict[str, float]:
    """Expected deltas: runs+1 and exactly the named outcome words +1."""
    deltas = dict.fromkeys(_COUNTERS, 0.0)
    deltas["collect_diff_runs_total"] = 1.0
    for word in words:
        deltas[f"collect_diff_outcomes_{word}_total"] = 1.0
    return deltas


class _FakeGit:
    """Dispatch on the argv tail: name-only / numstat / per-file diff."""

    def __init__(
        self,
        *,
        name_only: str = "",
        diffs: dict[str, str] | None = None,
        failing: frozenset[str] = frozenset(),
        name_only_error: str | None = None,
    ) -> None:
        self.name_only = name_only
        self.diffs = diffs or {}
        self.failing = failing
        self.name_only_error = name_only_error

    def __call__(self, repo_path: str, *args: str, timeout: int = 30) -> str:
        if args[0] == "diff" and args[1] == "--name-only":
            if self.name_only_error is not None:
                raise collect_diff_module._GitDiffError(self.name_only_error)
            return self.name_only
        if args[1] == "--numstat":
            f = args[-1]
            return f"1\t1\t{f}\n"
        f = args[-1]
        if f in self.failing:
            raise collect_diff_module._GitDiffError(f"stub failure for {f}")
        return self.diffs.get(f, "")


def _state() -> dict[str, Any]:
    return {
        "repo_path": "C:/stub/repo",
        "base_ref": "base",
        "head_ref": "head-v1",
        "errors": [],
    }


def _patch_git(monkeypatch: pytest.MonkeyPatch, fake: _FakeGit) -> None:
    monkeypatch.setattr(collect_diff_module, "_git", fake)


def test_scanned_counts_scanned(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_git(monkeypatch, _FakeGit(
        name_only="src/A.java\nREADME.md\n",
        diffs={"src/A.java": _JAVA_DIFF},
    ))
    before = _before()
    result = collect_diff_node(_state())  # type: ignore[arg-type]

    assert result["changed_files"] == ["src/A.java", "README.md"]
    assert "REMOVED: private int bar( in src/A.java" in result["changed_symbols"]
    assert "ADDED: public void foo( in src/A.java" in result["changed_symbols"]
    assert result["semantic_candidates"] == [
        {"file": "src/A.java", "hints": ["cache"], "hint_counts": {"cache": 1}}
    ]
    unresolved = result["unresolved_changes"]
    assert [u["file"] for u in unresolved] == ["README.md"]
    assert "language 'md'" in unresolved[0]["reason"]
    assert _deltas(before) == _only("scanned")


def test_no_changes_counts_no_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_git(monkeypatch, _FakeGit(name_only="\n"))
    before = _before()
    result = collect_diff_node(_state())  # type: ignore[arg-type]

    assert result["changed_files"] == []
    assert result["changed_symbols"] == [
        "No changes detected between base and head"
    ]
    assert _deltas(before) == _only("no_changes")


def test_diff_failed_returns_the_two_key_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_git(monkeypatch, _FakeGit(name_only_error="stub diff failure"))
    before = _before()
    result = collect_diff_node(_state())  # type: ignore[arg-type]

    # The early return carries NO changed_files / diff_by_file keys — the
    # downstream readers see the initial-state defaults, same as a
    # change-free pair of refs; only the outcome word separates the cases.
    assert set(result.keys()) == {"changed_symbols", "errors"}
    assert result["changed_symbols"] == []
    assert result["errors"] == ["git diff failed: stub diff failure"]
    assert _deltas(before) == _only("diff_failed")


def test_partial_file_read_failure_still_scans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_git(monkeypatch, _FakeGit(
        name_only="src/A.java\nsrc/B.java\n",
        diffs={"src/B.java": _JAVA_DIFF},
        failing=frozenset({"src/A.java"}),
    ))
    before = _before()
    result = collect_diff_node(_state())  # type: ignore[arg-type]

    assert result["changed_files"] == ["src/A.java", "src/B.java"]
    assert list(result["diff_by_file"]) == ["src/B.java"]
    assert result["errors"] == [
        "git diff for src/A.java failed: stub failure for src/A.java"
    ]
    assert "No changes detected between base and head" not in result["changed_symbols"]
    assert _deltas(before) == _only("scanned")


def test_outcome_vocabulary_matches_parity_and_source() -> None:
    from tests.unit.test_observability_metric_parity import CONCATENATED_FAMILIES

    source = (ROOT / "agent" / "nodes" / "collect_diff.py").read_text(
        encoding="utf-8"
    )
    literals = set(
        re.findall(r'incr\("collect_diff_outcomes_([a-z_]+)_total"\)', source)
    )
    assert literals == set(COLLECT_DIFF_OUTCOMES), (
        f"source literals {sorted(literals)} != declared vocabulary "
        f"{sorted(COLLECT_DIFF_OUTCOMES)}"
    )
    assert source.count('incr("collect_diff_runs_total")') == 1

    pattern, _ = CONCATENATED_FAMILIES["collect_diff"]
    parity_words = set(
        re.search(r"\(([^()]+)\)", pattern.pattern).group(1).split("|")  # type: ignore[union-attr]
    )
    assert parity_words == set(COLLECT_DIFF_OUTCOMES), (
        f"parity family words {sorted(parity_words)} != declared vocabulary "
        f"{sorted(COLLECT_DIFF_OUTCOMES)}"
    )
