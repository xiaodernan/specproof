"""run_differential honest fallback and self-test execution surface (Phase 2).

The counterexample generator emits Java/JUnit tests only. When no generated
test exists, a repository whose own tests would run on the HOST must NOT get a
vague "nothing to run" — it is told plainly that executable differential is
unsupported for its language and reported UNVERIFIED, never as a pass.

A repository whose adapter declares a container sandbox is the other case
(#54): running its own tests base-vs-head is safe by default and can yield a
real REGRESSION verdict, so the node takes that path instead of degrading.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import agent.nodes.run_differential as run_differential_module
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


def _node_pair(tmp_path: Path) -> tuple[str, str]:
    base = _mk_repo(tmp_path / "base", {"package.json": "{}"})
    head = _mk_repo(tmp_path / "head", {"package.json": "{}"})
    return base, head


def _diff_entry(out: dict[str, Any]) -> dict[str, Any]:
    return next(
        d for d in out["diff_results"] if d.get("contract_id") == "DIFF-01"
    )


# ── Honest degradation when the adapter's surface is the host ─────────────


def test_host_surface_repo_gets_language_honest_unverified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SPECPROOF_ALLOW_LOCAL_TEST_EXEC", raising=False)
    registry = _RecordingRegistry(_FakeAdapter(_GREEN_VS_RED))
    monkeypatch.setattr(adapters, "registry", registry)
    base, head = _node_pair(tmp_path)

    out = run_differential_node(_state(base, head))  # type: ignore[arg-type]
    entry = _diff_entry(out)

    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert entry.get("language") == "node"
    assert "node project" in entry["detail"]
    assert "counterexample generator emits" in entry["detail"]
    assert "UNVERIFIED" in entry["detail"]
    assert entry.get("adapter_surface") == adapters.SURFACE_HOST
    # Honest: differential must never be reported as a pass here.
    assert out.get("contract_results", []) == []


def test_java_repo_keeps_generic_no_test_detail(tmp_path: Path) -> None:
    base = _mk_repo(tmp_path / "base", {"pom.xml": "<project/>"})
    head = _mk_repo(tmp_path / "head", {"pom.xml": "<project/>"})

    out = run_differential_node(_state(base, head))  # type: ignore[arg-type]
    entry = _diff_entry(out)
    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert "language" not in entry  # java path is the generic one
    assert entry["detail"].startswith("No generated counterexample")


def test_python_repo_resolves_to_the_sandboxed_surface_by_default(
    tmp_path: Path,
) -> None:
    """#26 flipped the REAL Python adapter to a sandboxed surface: the same
    pure file inspection that used to say "host, gated off" must now resolve
    the adapter as container-sandboxed, so a Python repo runs its own
    differential without an operator flag. The execution itself is covered by
    the fakes above; this locks the DECISION that lets it run."""
    base = _mk_repo(tmp_path / "base", {"requirements.txt": "pytest\n"})

    sandboxed, surface, reason = run_differential_module._self_test_surface_for(
        str(base)
    )

    assert sandboxed is True
    assert surface == adapters.SURFACE_DOCKER_SANDBOX
    assert reason == ""


# ── Fakes ────────────────────────────────────────────────────────────────

_TAP_BASE_GREEN = "# tests 5\n# pass 5\n# fail 0\n"
_TAP_HEAD_FAIL = "# tests 5\n# pass 4\n# fail 1\n"
_GREEN_VS_RED = {"base": _TAP_BASE_GREEN, "head": _TAP_HEAD_FAIL}
_EMPTY = {"base": "", "head": ""}


class _FakeAdapter:
    """Minimal ExecutionAdapter returning canned node --test summaries.

    Counts every entry point separately so a test can prove the executor was
    not merely unobserved but never reached.
    """

    def __init__(
        self,
        tails: dict[str, str],
        *,
        mode: str = "local",
        surface: str = adapters.SURFACE_HOST,
    ) -> None:
        self._tails = tails
        self._mode = mode
        self.EXECUTION_SURFACE = surface
        self.detect_calls = 0
        self.prepare_calls = 0
        self.run_calls = 0

    def detect(self, repo: Any) -> Any:
        self.detect_calls += 1
        # Deliberately the adapter's own reporter vocabulary, not preflight's
        # marker vocabulary — see test_self_test_parser_covers_both_vocabularies.
        return SimpleNamespace(language="javascript/typescript")

    def prepare(self, request: Any) -> Any:
        self.prepare_calls += 1
        return request  # ExecutionRequest already carries .workspace

    def run(self, prepared: Any) -> Any:
        self.run_calls += 1
        ws = prepared.workspace
        key = "head" if "head" in Path(ws).name else "base"
        return SimpleNamespace(
            exit_code=0,
            stdout_tail=self._tails[key],
            stderr_tail="",
            mode=self._mode,
            sandbox_resources={"sandbox": self.EXECUTION_SURFACE},
            error="",
        )


class _RecordingRegistry:
    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter
        self.get_calls = 0

    def get(self, repo: Any) -> Any:
        self.get_calls += 1
        return self._adapter


class _RaisingRegistry:
    def __init__(self, error: Exception) -> None:
        self._error = error
        self.get_calls = 0

    def get(self, repo: Any) -> Any:
        self.get_calls += 1
        raise self._error


# ── The safety lock, restated for a per-surface policy ───────────────────
#
# #50 locked "gate off => the adapter is never even constructed". That was the
# right lock while BOTH non-Java adapters ran on the host. #54 made the Node
# adapter declare a container sandbox, and resolving that declaration requires
# constructing the adapter — which executes nothing (registry.get + a class
# attribute read). So the invariant moved from "never constructed" to the one
# that actually protects the host: "never PREPARED or RUN off-sandbox".


def test_gate_off_host_adapter_is_never_executed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SPECPROOF_ALLOW_LOCAL_TEST_EXEC", raising=False)
    adapter = _FakeAdapter(_GREEN_VS_RED, surface=adapters.SURFACE_HOST)
    registry = _RecordingRegistry(adapter)
    monkeypatch.setattr(adapters, "registry", registry)
    base, head = _node_pair(tmp_path)

    out = run_differential_node(_state(base, head))  # type: ignore[arg-type]
    entry = _diff_entry(out)

    # Resolution is allowed (it runs no code); execution is not.
    assert registry.get_calls == 1
    assert adapter.detect_calls == 0
    assert adapter.prepare_calls == 0
    assert adapter.run_calls == 0
    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert entry.get("self_test_gate") == "off"
    # The degraded message still names the only way in, honestly.
    assert "SPECPROOF_ALLOW_LOCAL_TEST_EXEC=1" in entry["detail"]
    assert "UNVERIFIED" in entry["detail"]


def test_sandboxed_adapter_runs_the_self_test_with_the_gate_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#54's headline: a container-sandboxed language needs no operator opt-in.

    This is the path that previously could not exist without crossing the
    "no untrusted code on the host" red line.
    """
    monkeypatch.delenv("SPECPROOF_ALLOW_LOCAL_TEST_EXEC", raising=False)
    adapter = _FakeAdapter(
        _GREEN_VS_RED, mode="docker", surface=adapters.SURFACE_DOCKER_SANDBOX
    )
    registry = _RecordingRegistry(adapter)
    monkeypatch.setattr(adapters, "registry", registry)
    base, head = _node_pair(tmp_path)

    out = run_differential_node(_state(base, head))  # type: ignore[arg-type]
    entry = _diff_entry(out)

    assert adapter.run_calls == 2  # base + head, both inside the sandbox
    assert entry["verdict"] == "REGRESSION"
    assert entry["evidence_type"] == "self_test_diff"
    assert entry["execution_surface"] == adapters.SURFACE_DOCKER_SANDBOX
    assert "容器沙箱执行" in entry["detail"]
    # A real regression is never silently paired with a pass elsewhere.
    assert out.get("contract_results", []) == []


def test_surface_label_comes_from_the_run_not_the_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A sandbox-declared adapter that never produced a completed run must not
    be reported as having run in a sandbox."""
    monkeypatch.delenv("SPECPROOF_ALLOW_LOCAL_TEST_EXEC", raising=False)
    adapter = _FakeAdapter(_EMPTY, mode="", surface=adapters.SURFACE_DOCKER_SANDBOX)
    monkeypatch.setattr(adapters, "registry", _RecordingRegistry(adapter))
    base, head = _node_pair(tmp_path)

    entry = _diff_entry(run_differential_node(_state(base, head)))  # type: ignore[arg-type]

    assert entry["execution_surface"] == "unconfirmed"
    assert entry["execution_surface"] != adapters.SURFACE_DOCKER_SANDBOX
    assert "执行面未确认" in entry["detail"]
    assert entry["verdict"] == "NON_REPRODUCIBLE"


def test_gate_off_unresolvable_adapter_fails_closed_to_unverified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No adapter, no surface => nothing may run, even though the node could
    have optimistically assumed a sandbox."""
    monkeypatch.delenv("SPECPROOF_ALLOW_LOCAL_TEST_EXEC", raising=False)
    registry = _RaisingRegistry(adapters.AdapterNotImplemented("no adapter for this repo"))
    monkeypatch.setattr(adapters, "registry", registry)
    base, head = _node_pair(tmp_path)

    entry = _diff_entry(run_differential_node(_state(base, head)))  # type: ignore[arg-type]

    assert registry.get_calls == 1
    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert "no adapter for this repo" in entry["detail"]
    assert entry.get("adapter_surface") == adapters.SURFACE_HOST


# ── Operator-enabled host execution stays honest ─────────────────────────


def test_self_test_gate_on_computes_honest_regression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SPECPROOF_ALLOW_LOCAL_TEST_EXEC", "1")
    registry = _RecordingRegistry(_FakeAdapter(_GREEN_VS_RED))
    monkeypatch.setattr(adapters, "registry", registry)
    base, head = _node_pair(tmp_path)

    out = run_differential_node(_state(base, head))  # type: ignore[arg-type]
    entry = _diff_entry(out)

    # 1 surface resolution + 2 actual runs.
    assert registry.get_calls == 3
    assert entry["verdict"] == "REGRESSION"
    assert entry["evidence_type"] == "self_test_diff"
    # Honest execution surface: local mode means host, no sandbox.
    assert entry["execution_surface"] == "local_host_no_sandbox"
    assert "本机执行·无沙箱" in entry["detail"]


def test_self_test_gate_on_unparseable_summary_is_not_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A command that ran but printed no counts is "no evidence", which the
    # verdict math must report NON_REPRODUCIBLE, never COMPLIANT.
    monkeypatch.setenv("SPECPROOF_ALLOW_LOCAL_TEST_EXEC", "1")
    registry = _RecordingRegistry(_FakeAdapter(_EMPTY))
    monkeypatch.setattr(adapters, "registry", registry)
    base, head = _node_pair(tmp_path)

    entry = _diff_entry(run_differential_node(_state(base, head)))  # type: ignore[arg-type]

    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert entry["execution_surface"] == "local_host_no_sandbox"


def test_self_test_gate_on_missing_adapter_stays_honest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = _RaisingRegistry(adapters.AdapterNotImplemented("no adapter for this repo"))
    monkeypatch.setenv("SPECPROOF_ALLOW_LOCAL_TEST_EXEC", "1")
    monkeypatch.setattr(adapters, "registry", registry)
    base, head = _node_pair(tmp_path)

    entry = _diff_entry(run_differential_node(_state(base, head)))  # type: ignore[arg-type]

    assert registry.get_calls == 3  # detection + base + head each attempt
    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert "no adapter for this repo" in entry["detail"]
    assert "UNVERIFIED" in entry["detail"]
    # Nothing ran, so nothing may claim a sandbox either.
    assert entry["execution_surface"] == "unconfirmed"


# ── Declared surfaces of the real adapters ───────────────────────────────


def test_real_adapters_declare_their_execution_surface() -> None:
    assert adapters.execution_surface_of(adapters.JavaMavenAdapter()) == (
        adapters.SURFACE_DOCKER_SANDBOX
    )
    assert adapters.execution_surface_of(adapters.NodeAdapter()) == (
        adapters.SURFACE_DOCKER_SANDBOX
    )
    assert adapters.execution_surface_of(adapters.PythonAdapter()) == (
        adapters.SURFACE_DOCKER_SANDBOX
    )
    assert adapters.runs_in_sandbox(adapters.NodeAdapter()) is True
    assert adapters.runs_in_sandbox(adapters.PythonAdapter()) is True


def test_surface_of_fails_closed_when_an_adapter_forgets_to_declare() -> None:
    """A new adapter that omits EXECUTION_SURFACE must be treated as the
    dangerous case, never the safe one."""
    assert adapters.execution_surface_of(object()) == adapters.SURFACE_HOST
    assert adapters.runs_in_sandbox(object()) is False


# ── The two language vocabularies must select the same parser ────────────
#
# agent/preflight names a repository by its marker file ("node"), while a
# RuntimeProfile names it by its reporter ("javascript/typescript"). The
# self-test path reads the latter, so a single-vocabulary lookup silently fed
# Node TAP output to the Maven Surefire parser: every Node differential would
# have reported "no evidence" forever, honestly but uselessly.


def test_self_test_parser_covers_both_vocabularies() -> None:
    from agent.nodes.run_differential import _self_test_parse_for
    from experiments.adapters import (
        parse_node_test_summary,
        parse_pytest_summary,
        parse_surefire_summary,
    )

    assert _self_test_parse_for("node") is parse_node_test_summary
    assert _self_test_parse_for("javascript/typescript") is parse_node_test_summary
    assert _self_test_parse_for("JAVASCRIPT/TypeScript") is parse_node_test_summary
    assert _self_test_parse_for("python") is parse_pytest_summary
    assert _self_test_parse_for("java") is parse_surefire_summary
    assert _self_test_parse_for("") is parse_surefire_summary


def test_real_node_profile_language_parses_a_real_tap_summary(
    tmp_path: Path,
) -> None:
    """End-to-end over the seam: the real adapter's own language value must
    resolve to a parser that reads the real reporter's output."""
    from agent.nodes.run_differential import _self_test_parse_for

    repo = _mk_repo(
        tmp_path / "app",
        {"package.json": '{"name":"p","scripts":{"test":"node --test"}}'},
    )
    profile = adapters.NodeAdapter().detect(adapters.RepositorySnapshot(path=repo))
    counts = _self_test_parse_for(profile.language)(_TAP_HEAD_FAIL)

    assert profile.language == "javascript/typescript"
    assert (counts["tests"], counts["passed"], counts["failed"]) == (5, 4, 1)

