"""`_self_test_differential_entry`: the DIFF-01 evidence builder had no test.

This function is what §2.1 actually rests on — it produces the base-vs-head
self-test entry, including the ``execution_surface`` label that says where the
runs really happened. Until now nothing in the suite referenced it, so every
branch below was free to change silently.

The defect this pins (#245): an adapter may report a usable run *and* a warning
at once (``ok=True`` with a non-empty ``error`` — e.g. a sandbox resource the
runner could not apply). ``error`` was read only inside the ``not ok`` guard,
which never fires for that shape, so the write was dead and the entry certified
"tests pass on both sides" naming no warning. The sibling path at PROBE-01
surfaces its adapter error before consulting ``ok``; this one now matches.

The warning must NOT downgrade the verdict: the counts are real, and a reader is
entitled to see what qualified the run rather than have it dropped.
"""

from __future__ import annotations

import pytest

from agent.nodes import run_differential as rd

PASSING = {"passed": 10, "failed": 0, "skipped": 0, "errors": 0}


def _runs(monkeypatch, base: dict, head: dict) -> None:
    """Serve canned adapter results in place of the real (Docker) execution."""
    seq = iter([base, head])
    monkeypatch.setattr(rd, "run_with_cancel_checks",
                        lambda *a, **k: next(seq))


def test_an_ok_run_with_a_warning_says_so_without_downgrading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = {"ok": True, "counts": dict(PASSING), "mode": "docker", "error": ""}
    head = {"ok": True, "counts": dict(PASSING), "mode": "docker",
            "error": "sandbox: no-new-privileges could not be applied"}
    _runs(monkeypatch, base, head)

    entry = rd._self_test_differential_entry({}, "/base", "/head", "python")

    # The verdict stands: the counts are real and both sides agree.
    assert entry["verdict"] == "COMPLIANT"
    assert entry["execution_surface"] == "docker_sandbox"
    # But the warning is no longer dropped on the floor.
    assert "no-new-privileges could not be applied" in entry["detail"]
    assert "运行告警" in entry["detail"]


def test_a_warning_on_the_base_side_is_reported_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = {"ok": True, "counts": dict(PASSING), "mode": "docker",
            "error": "base: tmpfs mount refused"}
    head = {"ok": True, "counts": dict(PASSING), "mode": "docker", "error": ""}
    _runs(monkeypatch, base, head)

    entry = rd._self_test_differential_entry({}, "/base", "/head", "python")

    assert entry["verdict"] == "COMPLIANT"
    assert "tmpfs mount refused" in entry["detail"]


def test_a_clean_run_claims_no_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """The other half: no warning must not be decorated with an empty clause."""
    base = {"ok": True, "counts": dict(PASSING), "mode": "docker", "error": ""}
    head = {"ok": True, "counts": dict(PASSING), "mode": "docker", "error": ""}
    _runs(monkeypatch, base, head)

    entry = rd._self_test_differential_entry({}, "/base", "/head", "python")

    assert entry["verdict"] == "COMPLIANT"
    assert "运行告警" not in entry["detail"]


def test_a_failed_run_is_still_non_reproducible_not_warned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ok=False keeps its own verdict and message; the warning path is separate."""
    base = {"ok": False, "counts": None, "mode": "", "error": "boom"}
    head = {"ok": True, "counts": dict(PASSING), "mode": "docker", "error": ""}
    _runs(monkeypatch, base, head)

    entry = rd._self_test_differential_entry({}, "/base", "/head", "python")

    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert "boom" in entry["detail"]
    assert "运行告警" not in entry["detail"]
