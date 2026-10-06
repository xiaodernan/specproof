"""Prepare-node execution tests (#193) — honest counters at both prepare
node boundaries, written WITH the landing (not backfilled).

``prepare_base_node`` and ``prepare_head_node`` are verbatim twins (same
structure, one ref and one state key apart), so every case runs against
both modules via parametrization.  The safety check, the worktree marker
writer, the git invocation and the temp-dir factory are stubbed at the
node module's own import names; everything else runs for real.  One case
per outcome word in PREPARE_OUTCOMES:

- prepared: safety passed and git worktree add exited 0 — the workspace
  path is handed to the graph (witness: the recorded argv ends with this
  node's own ref, read from its own state key);
- safety_failed: the safety report refused — the marker writer and the
  git invocation are never reached (witness: both recorders stay empty);
- checkout_failed: safety passed, git exited non-zero — the workspace is
  discarded and the error names the ref;
- prepare_error: the git invocation raised — same discard, error names
  the exception;

plus <node>_runs_total on every path and a drift gate binding both parity
families' regex words to the two declarations (which must stay equal —
twins) and to the source literals.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from observability.metrics import snapshot

ROOT = Path(__file__).resolve().parents[2]

NODE_NAMES = ("prepare_base", "prepare_head")
#: The twins' only content differences: state key, ref key, default ref.
WORKSPACE_KEY = {"prepare_base": "base_workspace", "prepare_head": "head_workspace"}
REF_KEY = {"prepare_base": "base_ref", "prepare_head": "head_ref"}


def _node_module(name: str) -> Any:
    return importlib.import_module(f"agent.nodes.{name}")


def _counters(node_name: str) -> tuple[str, ...]:
    # Derived from the declaration — a new word extends the delta table.
    module = _node_module(node_name)
    return (f"{node_name}_runs_total",) + tuple(
        f"{node_name}_outcomes_{word}_total"
        for word in sorted(module.PREPARE_OUTCOMES)
    )


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


def _before(node_name: str) -> dict[str, float]:
    return {name: _counter(name) for name in _counters(node_name)}


def _deltas(node_name: str, before: dict[str, float]) -> dict[str, float]:
    return {name: _counter(name) - start for name, start in before.items()}


def _only(node_name: str, *words: str) -> dict[str, float]:
    """Expected deltas: runs+1 and exactly the named outcome words +1."""
    deltas = dict.fromkeys(_counters(node_name), 0.0)
    deltas[f"{node_name}_runs_total"] = 1.0
    for word in words:
        deltas[f"{node_name}_outcomes_{word}_total"] = 1.0
    return deltas


class _Recorder:
    """Stub callable that records every invocation and can raise instead."""

    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if self.error is not None:
            raise self.error
        return self.result


def _stub_environment(
    monkeypatch: pytest.MonkeyPatch,
    node_name: str,
    tmp_path: Path,
    *,
    report_ok: bool,
    git_rc: int = 0,
    git_error: Exception | None = None,
) -> tuple[Path, _Recorder, _Recorder, _Recorder]:
    """Stub the four external seams on the node module's own import names.

    Returns (workspace, git_recorder, marker_recorder, safety_recorder).
    The workspace dir is pre-created empty, so a discarded workspace is
    observable as the directory disappearing.
    """
    module = _node_module(node_name)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    class _Report:
        ok = report_ok
        warnings: list[str] = []
        fail_reason = "stub refusal"

    safety = _Recorder(result=_Report())
    monkeypatch.setattr(module, "check_repo_safety", safety)

    marker = _Recorder(result=tmp_path / "marker")
    monkeypatch.setattr(module, "write_worktree_marker", marker)

    git = _Recorder(
        result=SimpleNamespace(returncode=git_rc, stderr="stub stderr"),
        error=git_error,
    )
    monkeypatch.setattr(module, "subprocess", SimpleNamespace(run=git))

    monkeypatch.setattr(
        module,
        "tempfile",
        SimpleNamespace(mkdtemp=lambda prefix: str(workspace)),
    )
    return workspace, git, marker, safety


def _state(node_name: str, tmp_path: Path) -> dict[str, Any]:
    # A non-default ref per node proves the ref is read from its OWN state
    # key: a cross-wired twin would fall back to the other default.
    return {
        "repo_path": str(tmp_path / "repo"),
        "job_id": "job-193",
        REF_KEY[node_name]: f"test/{node_name}",
    }


@pytest.mark.parametrize("node_name", NODE_NAMES)
def test_prepared_hands_over_the_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, node_name: str
) -> None:
    workspace, git, marker, _ = _stub_environment(
        monkeypatch, node_name, tmp_path, report_ok=True
    )
    state = _state(node_name, tmp_path)
    before = _before(node_name)

    result = getattr(_node_module(node_name), f"{node_name}_node")(state)

    assert result[WORKSPACE_KEY[node_name]] == str(workspace)
    assert "errors" not in result
    assert len(marker.calls) == 1
    assert len(git.calls) == 1
    (positional, _kwargs), = git.calls
    (argv,) = positional
    assert argv == [
        "git", "-C", state["repo_path"], "worktree", "add", "--detach",
        str(workspace), state[REF_KEY[node_name]],
    ]
    assert _deltas(node_name, before) == _only(node_name, "prepared")


@pytest.mark.parametrize("node_name", NODE_NAMES)
def test_safety_refusal_never_reaches_marker_or_git(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, node_name: str
) -> None:
    workspace, git, marker, _ = _stub_environment(
        monkeypatch, node_name, tmp_path, report_ok=False
    )
    state = _state(node_name, tmp_path)
    before = _before(node_name)

    result = getattr(_node_module(node_name), f"{node_name}_node")(state)

    assert result[WORKSPACE_KEY[node_name]] == ""
    assert "Repository safety check failed" in result["errors"][-1]
    assert marker.calls == [], "a refused safety check must not register a claim"
    assert git.calls == [], "a refused safety check must not reach git"
    assert not workspace.exists(), "the never-handed workspace must be discarded"
    assert _deltas(node_name, before) == _only(node_name, "safety_failed")


@pytest.mark.parametrize("node_name", NODE_NAMES)
def test_checkout_failure_discards_the_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, node_name: str
) -> None:
    workspace, _, marker, _ = _stub_environment(
        monkeypatch, node_name, tmp_path, report_ok=True, git_rc=1
    )
    state = _state(node_name, tmp_path)
    before = _before(node_name)

    result = getattr(_node_module(node_name), f"{node_name}_node")(state)

    assert result[WORKSPACE_KEY[node_name]] == ""
    assert "Failed to checkout" in result["errors"][-1]
    assert state[REF_KEY[node_name]] in result["errors"][-1]
    assert len(marker.calls) == 1
    assert not workspace.exists(), "the failed workspace must be discarded"
    assert _deltas(node_name, before) == _only(node_name, "checkout_failed")


@pytest.mark.parametrize("node_name", NODE_NAMES)
def test_git_exception_discards_the_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, node_name: str
) -> None:
    workspace, _, _, _ = _stub_environment(
        monkeypatch, node_name, tmp_path,
        report_ok=True, git_error=OSError("stub git missing"),
    )
    state = _state(node_name, tmp_path)
    before = _before(node_name)

    result = getattr(_node_module(node_name), f"{node_name}_node")(state)

    assert result[WORKSPACE_KEY[node_name]] == ""
    assert "Error preparing" in result["errors"][-1]
    assert "stub git missing" in result["errors"][-1]
    assert not workspace.exists(), "the errored workspace must be discarded"
    assert _deltas(node_name, before) == _only(node_name, "prepare_error")


def test_outcome_vocabulary_matches_parity_and_source() -> None:
    from tests.unit.test_observability_metric_parity import CONCATENATED_FAMILIES

    base = _node_module("prepare_base")
    head = _node_module("prepare_head")
    assert base.PREPARE_OUTCOMES == head.PREPARE_OUTCOMES, (
        "twin prepare nodes drifted: base vocabulary "
        f"{sorted(base.PREPARE_OUTCOMES)} != head vocabulary "
        f"{sorted(head.PREPARE_OUTCOMES)}"
    )

    for node_name in NODE_NAMES:
        module = _node_module(node_name)
        source = (ROOT / "agent" / "nodes" / f"{node_name}.py").read_text(
            encoding="utf-8"
        )
        literals = set(
            re.findall(
                rf'incr\("{node_name}_outcomes_([a-z_]+)_total"\)', source
            )
        )
        assert literals == set(module.PREPARE_OUTCOMES), (
            f"{node_name} source literals {sorted(literals)} != declared "
            f"vocabulary {sorted(module.PREPARE_OUTCOMES)}"
        )
        assert source.count(f'incr("{node_name}_runs_total")') == 1

        pattern, _ = CONCATENATED_FAMILIES[node_name]
        parity_words = set(
            re.search(r"\(([^()]+)\)", pattern.pattern).group(1).split("|")  # type: ignore[union-attr]
        )
        assert parity_words == set(module.PREPARE_OUTCOMES), (
            f"{node_name} parity family words {sorted(parity_words)} != "
            f"declared vocabulary {sorted(module.PREPARE_OUTCOMES)}"
        )
