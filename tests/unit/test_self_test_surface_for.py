"""Direct tests for ``_self_test_surface_for``: the fail-closed surface
classification that decides whether the self-test differential may run by
default or must stop at the operator gate.

The two production outcomes were pinned in #589 (docker+docker →
docker_sandbox; any local → local_host_no_sandbox; empty → unconfirmed).
This file pins the **failure surfaces** that had no test:

- ``registry.get`` raises → ``(False, "host", reason[:300])``;
- ``runs_in_sandbox`` raises → ``(False, "host", reason[:300])``;
- ``execution_surface_of`` raises → same fail-closed shape;
- the reason is truncated to 300 characters (undecidable surface never
  leaks a long traceback into a diff_results entry).
"""

from __future__ import annotations

from typing import Any

import pytest

from agent.nodes import run_differential as rd


class _PassThruRegistry:
    def get(self, snap: Any) -> Any:
        return object()


class _ExplodingRegistry:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def get(self, snap: Any) -> Any:
        raise self.exc


def _patch_adapters(
    monkeypatch: pytest.MonkeyPatch,
    *,
    registry: Any,
    runs_in_sandbox: Any = lambda adapter: True,
    execution_surface_of: Any = lambda adapter: "docker_sandbox",
) -> None:
    import experiments.adapters as adapters

    monkeypatch.setattr(adapters, "RepositorySnapshot", lambda path: path)
    monkeypatch.setattr(adapters, "registry", registry)
    monkeypatch.setattr(adapters, "runs_in_sandbox", runs_in_sandbox)
    monkeypatch.setattr(adapters, "execution_surface_of", execution_surface_of)


# ── fail-closed: registry.get raises ───────────────────────────────────────


def test_registry_get_failure_reports_host_and_truncated_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_adapters(
        monkeypatch,
        registry=_ExplodingRegistry(RuntimeError("no adapter registered for this path")),
    )

    sandboxed, surface, reason = rd._self_test_surface_for("/some/repo")

    assert sandboxed is False
    assert surface == "host"
    assert reason == "no adapter registered for this path"


# ── fail-closed: runs_in_sandbox raises ────────────────────────────────────


def test_runs_in_sandbox_failure_reports_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(adapter: Any) -> bool:
        raise OSError("docker socket unreachable")

    _patch_adapters(
        monkeypatch,
        registry=_PassThruRegistry(),
        runs_in_sandbox=boom,
    )

    sandboxed, surface, reason = rd._self_test_surface_for("/some/repo")

    assert sandboxed is False
    assert surface == "host"
    assert reason == "docker socket unreachable"


# ── fail-closed: execution_surface_of raises ───────────────────────────────


def test_execution_surface_of_failure_reports_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(adapter: Any) -> str:
        raise ValueError("cannot read adapter profile")

    _patch_adapters(
        monkeypatch,
        registry=_PassThruRegistry(),
        runs_in_sandbox=lambda adapter: True,
        execution_surface_of=boom,
    )

    sandboxed, surface, reason = rd._self_test_surface_for("/some/repo")

    assert sandboxed is False
    assert surface == "host"
    assert reason == "cannot read adapter profile"


# ── reason truncation: undecidable surface never leaks a long traceback ----


def test_reason_is_truncated_to_300_chars(monkeypatch: pytest.MonkeyPatch) -> None:
    long_message = "x" * 500
    _patch_adapters(
        monkeypatch,
        registry=_ExplodingRegistry(RuntimeError(long_message)),
    )

    _sandboxed, _surface, reason = rd._self_test_surface_for("/some/repo")

    assert reason == long_message[:300]
    assert len(reason) == 300


# ── happy path: sandboxed adapter with a real surface ----------------------


def test_sandboxed_adapter_reports_its_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_adapters(
        monkeypatch,
        registry=_PassThruRegistry(),
        runs_in_sandbox=lambda adapter: True,
        execution_surface_of=lambda adapter: "docker_sandbox",
    )

    sandboxed, surface, reason = rd._self_test_surface_for("/some/repo")

    assert sandboxed is True
    assert surface == "docker_sandbox"
    assert reason == ""
