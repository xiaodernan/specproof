"""Direct tests for the dependency-install provenance aggregation and the
execution-surface classification inside ``_self_test_differential_entry``.

The reused-head-run and the warning path are covered elsewhere; the two
disclosures a reader relies on to know *where the dependencies came from*
and *where the test really ran* had no pinning.
"""

from __future__ import annotations

from typing import Any

import pytest

from agent.nodes import run_differential as rd

PASSING = {"passed": 10, "failed": 0, "skipped": 0, "errors": 0}
FAILING = {"passed": 9, "failed": 1, "skipped": 0, "errors": 0}


def _runs(
    monkeypatch: pytest.MonkeyPatch, base: dict[str, Any], head: dict[str, Any]
) -> None:
    seq = iter([base, head])
    monkeypatch.setattr(rd, "run_with_cancel_checks", lambda *a, **k: next(seq))


def _entry(
    monkeypatch: pytest.MonkeyPatch, base: dict[str, Any], head: dict[str, Any]
) -> dict[str, Any]:
    base = {"ok": True, "counts": dict(PASSING), "mode": "docker", "error": "",
            **base}
    head = {"ok": True, "counts": dict(PASSING), "mode": "docker", "error": "",
            **head}
    _runs(monkeypatch, base, head)
    return rd._self_test_differential_entry({}, "/base", "/head", "python")  # type: ignore[arg-type]


# ── dependency_install aggregation ──────────────────────────────────────────


def test_identical_install_disclosures_collapse_to_one_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _entry(
        monkeypatch,
        {"dependency_install": "offline cache"},
        {"dependency_install": "offline cache"},
    )
    assert entry["dependency_install"] == "offline cache"


def test_differing_install_disclosures_name_both_sides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _entry(
        monkeypatch,
        {"dependency_install": "offline cache"},
        {"dependency_install": "online registry"},
    )
    disclosure = entry["dependency_install"]
    assert "base: offline cache" in disclosure
    assert "head: online registry" in disclosure


def test_one_side_absent_still_discloses_the_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _entry(
        monkeypatch,
        {"dependency_install": "offline cache"},
        {"dependency_install": ""},
    )
    disclosure = entry["dependency_install"]
    assert disclosure.startswith("base: offline cache")
    assert "head:" in disclosure


def test_absent_install_disclosures_are_not_shown_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _entry(monkeypatch, {}, {})
    assert "dependency_install" not in entry


# ── execution surface classification ─────────────────────────────────────────


def test_both_docker_runs_report_docker_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _entry(monkeypatch, {"mode": "docker"}, {"mode": "docker"})
    assert entry["execution_surface"] == "docker_sandbox"


def test_any_local_mode_fails_closed_to_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _entry(monkeypatch, {"mode": "local"}, {"mode": "docker"})
    assert entry["execution_surface"] == "local_host_no_sandbox"
    entry = _entry(monkeypatch, {"mode": "docker"}, {"mode": "local"})
    assert entry["execution_surface"] == "local_host_no_sandbox"


def test_no_mode_anywhere_is_unconfirmed_not_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _entry(monkeypatch, {"mode": ""}, {"mode": ""})
    assert entry["execution_surface"] == "unconfirmed"


# ── verdict wiring ──────────────────────────────────────────────────────────


def test_base_green_head_red_reads_as_regression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _entry(monkeypatch, {}, {"counts": dict(FAILING)})
    assert entry["verdict"] == "REGRESSION"
