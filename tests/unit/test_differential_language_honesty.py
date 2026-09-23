"""run_differential honest fallback for non-Java repositories (roadmap Phase 2).

The counterexample generator emits Java/JUnit tests only. When no generated
test exists, a non-Java repository must NOT get a vague "nothing to run" —
it should be told plainly that executable differential is unsupported for its
language and reported UNVERIFIED, never as a pass.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import experiments.adapters as adapters
from agent.nodes.run_differential import run_differential_node


def _mk_repo(root: Path, markers: dict[str, str]) -> str:
    d = root
    d.mkdir(parents=True, exist_ok=True)
    for name, body in markers.items():
        (d / name).write_text(body, encoding="utf-8")
    return str(d)


def _state(base: str, head: str) -> dict[str, Any]:
    return {
        "base_workspace": base,
        "head_workspace": head,
        "app_dir": "",
        "changed_symbols": [],
        "generation_record": {},
        "contracts": [],
        # No generated test -> exercises the not-test_class branch.
        "generated_tests_path": "",
        "job_id": None,
    }


def test_non_java_repo_gets_language_honest_unverified(tmp_path: Path) -> None:
    base = _mk_repo(tmp_path / "base", {"package.json": "{}"})
    head = _mk_repo(tmp_path / "head", {"package.json": "{}"})

    out = run_differential_node(_state(base, head))  # type: ignore[arg-type]
    diff = out["diff_results"]
    entry = next(d for d in diff if d.get("contract_id") == "DIFF-01")

    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert entry.get("language") == "node"
    assert "counterexample generator emits" in entry["detail"]
    assert "UNVERIFIED" in entry["detail"]
    # Honest: differential must never be reported as a pass here.
    assert out.get("contract_results", []) == []


def test_java_repo_keeps_generic_no_test_detail(tmp_path: Path) -> None:
    base = _mk_repo(tmp_path / "base", {"pom.xml": "<project/>"})
    head = _mk_repo(tmp_path / "head", {"pom.xml": "<project/>"})

    out = run_differential_node(_state(base, head))  # type: ignore[arg-type]
    entry = next(
        d for d in out["diff_results"] if d.get("contract_id") == "DIFF-01"
    )
    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert "language" not in entry  # java path is the generic one
    assert entry["detail"].startswith("No generated counterexample")


def test_python_repo_names_python_not_node(tmp_path: Path) -> None:
    base = _mk_repo(tmp_path / "base", {"requirements.txt": "pytest\n"})
    head = _mk_repo(tmp_path / "head", {"requirements.txt": "pytest\n"})

    out = run_differential_node(_state(base, head))  # type: ignore[arg-type]
    entry = next(
        d for d in out["diff_results"] if d.get("contract_id") == "DIFF-01"
    )
    assert entry.get("language") == "python"
    assert "python project" in entry["detail"]


# ── #50: default-off local-test-exec self-test differential ──────────────
#
# The Node/Python adapters are local-first (no container), so running a repo's
# own tests executes untrusted code on the HOST. That path must stay OFF unless
# SPECPROOF_ALLOW_LOCAL_TEST_EXEC is explicitly enabled, and when enabled every
# outcome is honest — including "本机执行·无沙箱" labeling and never laundering a
# missing/zero-test run into a pass.

_TAP_BASE_GREEN = "# tests 5\n# pass 5\n# fail 0\n"
_TAP_HEAD_FAIL = "# tests 5\n# pass 4\n# fail 1\n"


class _FakeAdapter:
    """Minimal ExecutionAdapter that returns canned node --test summaries."""

    def __init__(self, tails: dict[str, str], *, mode: str = "local") -> None:
        self._tails = tails
        self._mode = mode

    def detect(self, repo: Any) -> Any:
        return SimpleNamespace(language="node")

    def prepare(self, request: Any) -> Any:
        return request  # ExecutionRequest already carries .workspace

    def run(self, prepared: Any) -> Any:
        ws = prepared.workspace
        key = "head" if "head" in Path(ws).name else "base"
        return SimpleNamespace(
            exit_code=0,
            stdout_tail=self._tails[key],
            stderr_tail="",
            mode=self._mode,
            sandbox_resources={
                "sandbox": "none (local-first execution on the host)"
            },
            error="",
        )


class _RecordingRegistry:
    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter
        self.get_calls = 0

    def get(self, repo: Any) -> Any:
        self.get_calls += 1
        return self._adapter


def _diff_entry(out: dict[str, Any]) -> dict[str, Any]:
    return next(
        d for d in out["diff_results"] if d.get("contract_id") == "DIFF-01"
    )


def test_self_test_gate_off_by_default_never_reaches_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SPECPROOF_ALLOW_LOCAL_TEST_EXEC", raising=False)
    registry = _RecordingRegistry(
        _FakeAdapter({"base": _TAP_BASE_GREEN, "head": _TAP_HEAD_FAIL})
    )
    monkeypatch.setattr(adapters, "registry", registry)
    base = _mk_repo(tmp_path / "base", {"package.json": "{}"})
    head = _mk_repo(tmp_path / "head", {"package.json": "{}"})

    out = run_differential_node(_state(base, head))  # type: ignore[arg-type]
    entry = _diff_entry(out)

    # The decisive safety lock: default-off ⇒ the host-execution adapter is
    # never constructed, so untrusted repo tests never run.
    assert registry.get_calls == 0
    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert entry.get("self_test_gate") == "off"
    assert "SPECPROOF_ALLOW_LOCAL_TEST_EXEC=1" in entry["detail"]
    assert "UNVERIFIED" in entry["detail"]


def test_self_test_gate_on_computes_honest_regression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SPECPROOF_ALLOW_LOCAL_TEST_EXEC", "1")
    registry = _RecordingRegistry(
        _FakeAdapter({"base": _TAP_BASE_GREEN, "head": _TAP_HEAD_FAIL})
    )
    monkeypatch.setattr(adapters, "registry", registry)
    base = _mk_repo(tmp_path / "base", {"package.json": "{}"})
    head = _mk_repo(tmp_path / "head", {"package.json": "{}"})

    out = run_differential_node(_state(base, head))  # type: ignore[arg-type]
    entry = _diff_entry(out)

    assert registry.get_calls == 2  # base + head both ran
    assert entry["verdict"] == "REGRESSION"
    assert entry["evidence_type"] == "self_test_diff"
    # Honest execution surface: local-first adapters mean host, no sandbox.
    assert entry["execution_surface"] == "local_host_no_sandbox"
    assert "本机执行·无沙箱" in entry["detail"]


def test_self_test_gate_on_unparseable_summary_is_not_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A command that ran but printed no counts is "no evidence", which the
    # verdict math must report NON_REPRODUCIBLE, never COMPLIANT.
    monkeypatch.setenv("SPECPROOF_ALLOW_LOCAL_TEST_EXEC", "1")
    registry = _RecordingRegistry(_FakeAdapter({"base": "", "head": ""}))
    monkeypatch.setattr(adapters, "registry", registry)
    base = _mk_repo(tmp_path / "base", {"package.json": "{}"})
    head = _mk_repo(tmp_path / "head", {"package.json": "{}"})

    out = run_differential_node(_state(base, head))  # type: ignore[arg-type]
    entry = _diff_entry(out)

    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert entry["execution_surface"] == "local_host_no_sandbox"


def test_self_test_gate_on_missing_adapter_stays_honest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _NoAdapterRegistry:
        def __init__(self) -> None:
            self.get_calls = 0

        def get(self, repo: Any) -> Any:
            self.get_calls += 1
            raise adapters.AdapterNotImplemented("no adapter for this repo")

    monkeypatch.setenv("SPECPROOF_ALLOW_LOCAL_TEST_EXEC", "1")
    registry = _NoAdapterRegistry()
    monkeypatch.setattr(adapters, "registry", registry)
    base = _mk_repo(tmp_path / "base", {"package.json": "{}"})
    head = _mk_repo(tmp_path / "head", {"package.json": "{}"})

    out = run_differential_node(_state(base, head))  # type: ignore[arg-type]
    entry = _diff_entry(out)

    assert registry.get_calls == 2  # base and head each attempt, then honest bail
    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert "no adapter for this repo" in entry["detail"]
    assert "UNVERIFIED" in entry["detail"]
