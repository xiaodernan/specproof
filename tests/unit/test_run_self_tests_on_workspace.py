"""Direct tests for ``_run_self_tests_on_workspace`` failure surfaces and
the happy path.

This function is the one place where untrusted repo tests actually execute
(via an adapter). It is covered by nothing except integration: this file pins
the three branches — ``AdapterNotImplemented`` (adapter knows nothing about
the repo), a generic crash (never laundered into a verdict), and the ok path
(counts/mode/sandbox/dependency_install/error faithfully forwarded).
"""

from __future__ import annotations

from typing import Any

import pytest

from agent.nodes import run_differential as rd


class FakeProfile:
    def __init__(self, language: str) -> None:
        self.language = language


class FakeResult:
    def __init__(
        self,
        *,
        stdout_tail: str = "",
        stderr_tail: str = "",
        mode: str = "docker",
        sandbox: str = "container",
        dependency_install: str = "offline cache",
        error: str = "",
    ) -> None:
        self.stdout_tail = stdout_tail
        self.stderr_tail = stderr_tail
        self.mode = mode
        self.sandbox_resources = {
            "sandbox": sandbox,
            "dependency_install": dependency_install,
        }
        self.error = error


class FakeAdapter:
    def __init__(
        self,
        *,
        profile: FakeProfile | None = None,
        run_result: FakeResult | None = None,
        detect_error: Exception | None = None,
        prepare_error: Exception | None = None,
        run_error: Exception | None = None,
    ) -> None:
        self.profile = profile or FakeProfile("python")
        self.run_result = run_result or FakeResult()
        self.detect_error = detect_error
        self.prepare_error = prepare_error
        self.run_error = run_error

    def detect(self, snap: Any) -> FakeProfile:
        if self.detect_error:
            raise self.detect_error
        return self.profile

    def prepare(self, request: Any) -> Any:
        if self.prepare_error:
            raise self.prepare_error
        return request

    def run(self, prepared: Any) -> FakeResult:
        if self.run_error:
            raise self.run_error
        return self.run_result


class FakeRegistry:
    def __init__(
        self,
        *,
        adapter: Any | None = None,
        get_error: Exception | None = None,
    ) -> None:
        self.adapter = adapter
        self.get_error = get_error

    def get(self, snap: Any) -> Any:
        if self.get_error:
            raise self.get_error
        if self.adapter is None:
            raise AdapterNotImplementedPlaceholderError("no adapter for this repo")
        return self.adapter


class AdapterNotImplementedPlaceholderError(Exception):
    pass


def _patch_adapters(monkeypatch: pytest.MonkeyPatch, registry: Any) -> None:
    import experiments.adapters as adapters

    monkeypatch.setattr(adapters, "RepositorySnapshot", lambda path: path)
    monkeypatch.setattr(adapters, "registry", registry)
    monkeypatch.setattr(
        adapters, "AdapterNotImplemented", AdapterNotImplementedPlaceholderError
    )
    monkeypatch.setattr(adapters, "ExecutionRequest", lambda **kw: kw)


# ── AdapterNotImplemented path: error recorded, nothing else touched -------


def test_adapter_not_implemented_records_error_and_returns_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import experiments.adapters as adapters

    _patch_adapters(monkeypatch, FakeRegistry())
    adapter_not_implemented = adapters.AdapterNotImplemented
    registry = FakeRegistry(
        get_error=adapter_not_implemented("no adapter for this repo")
    )
    monkeypatch.setattr(adapters, "registry", registry)
    monkeypatch.setattr(rd, "_self_test_parse_for", lambda language: lambda text: {})

    out = rd._run_self_tests_on_workspace("/some/repo")

    assert out["ok"] is False
    assert out["counts"] is None
    assert out["mode"] == ""
    assert out["sandbox"] == ""
    assert out["error"] == "no adapter for this repo"


# ── Generic crash path: never laundered into a verdict ----------------------


def test_generic_exception_becomes_self_test_execution_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = FakeRegistry(get_error=RuntimeError("boom"))
    _patch_adapters(monkeypatch, registry)
    monkeypatch.setattr(rd, "_self_test_parse_for", lambda language: lambda text: {})

    out = rd._run_self_tests_on_workspace("/some/repo")

    assert out["ok"] is False
    assert out["counts"] is None
    assert out["mode"] == ""
    assert out["sandbox"] == ""
    assert out["error"].startswith("self-test execution failed: ")
    assert "boom" in out["error"]


# ── Happy path: counts/mode/sandbox/dependency_install/error forwarded ------


def test_ok_path_forwards_everything(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = FakeAdapter(
        run_result=FakeResult(
            stdout_tail="# tests 5\n# pass 4\n# fail 1\n",
            mode="docker",
            sandbox="container",
            dependency_install="offline cache",
            error="",
        )
    )
    registry = FakeRegistry(adapter=adapter)
    _patch_adapters(monkeypatch, registry)
    monkeypatch.setattr(
        rd,
        "_self_test_parse_for",
        lambda language: lambda text: {"tests": 5, "passed": 4, "failed": 1},
    )

    out = rd._run_self_tests_on_workspace("/some/repo")

    assert out["ok"] is True
    assert out["counts"] == {"tests": 5, "passed": 4, "failed": 1}
    assert out["mode"] == "docker"
    assert out["sandbox"] == "container"
    assert out["dependency_install"] == "offline cache"
    assert out["error"] == ""


def test_adapter_error_is_stored_while_ok_stays_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ok=True with a non-empty error: counts are real, warning is kept."""
    adapter = FakeAdapter(
        run_result=FakeResult(
            stdout_tail="# tests 5\n# pass 5\n# fail 0\n",
            mode="docker",
            dependency_install="offline cache",
            error="sandbox: no-new-privileges could not be applied",
        )
    )
    registry = FakeRegistry(adapter=adapter)
    _patch_adapters(monkeypatch, registry)
    monkeypatch.setattr(
        rd,
        "_self_test_parse_for",
        lambda language: lambda text: {"tests": 5, "passed": 5, "failed": 0},
    )

    out = rd._run_self_tests_on_workspace("/some/repo")

    assert out["ok"] is True
    assert out["counts"] == {"tests": 5, "passed": 5, "failed": 0}
    assert out["error"] == "sandbox: no-new-privileges could not be applied"
