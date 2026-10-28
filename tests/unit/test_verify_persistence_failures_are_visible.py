"""`specproof verify` must not print the same thing for "no database" and "database refused".

The job-summary write was ``try: ... except Exception: pass``. So a laptop run
with no MySQL and an operator whose configured MySQL is down / misconfigured /
pointing at a missing schema produced byte-identical output: nothing. The
dashboard simply stayed empty, and the only way to find out why was to read the
source. That is the failure mode this repo keeps calling out — "跳过 ≠ 通过" —
applied to an outlet instead of a gate.

Persistence is still best-effort on purpose: the verdict is about the code
change, not about MySQL, so these legs also pin that the exit code does not
move. What is pinned here:

* the reason is printed (host:port/database, exception type, first message line);
* it goes to STDERR, so ``specproof verify | grep VERDICT`` is unaffected;
* the password never appears in it;
* a store that returns "not recorded" is reported too — the certificate path
  ignored that return value, so a down store left the certificate findable only
  by path with nothing said out loud.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from cli.specproof.commands.verify import _record_certificate_metadata, verify
from observability.metrics import snapshot as metrics_snapshot


def _passing_matrix() -> dict[str, Any]:
    return {
        "rows": [{
            "contract_id": "C-1", "result": "PASS",
            "evidence_refs": ["ev-1"], "experiment_ids": ["DIFF-01"],
        }],
        "total_contracts": 1, "passed": 1, "failed": 0, "unverified": 0,
        "total_rows": 1,
    }


def _fake_state() -> dict[str, Any]:
    return {
        "matrix": _passing_matrix(),
        "contracts": [{"id": "C-1"}],
        "contract_results": [],
        "confirmed_findings": [],
        "errors": [],
        "capsules": [],
        "release_results": {},
    }


@pytest.fixture()
def run_verify(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Drive the real command with a fake graph, so the real tail runs."""

    class _FakeGraph:
        def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
            return _fake_state()

    monkeypatch.setattr("agent.graph.build_phase0_graph", lambda: _FakeGraph())
    monkeypatch.setattr("agent.preflight.detect_language", lambda *_a, **_k: "python")
    monkeypatch.setattr(
        "agent.preflight.run_preflight",
        lambda *_a, **_k: type("P", (), {"passed": True})(),
    )
    monkeypatch.setattr(
        "agent.preflight.format_preflight_report", lambda *_a, **_k: "preflight ok"
    )

    def _run() -> Any:
        spec = tmp_path / "spec.txt"
        spec.write_text("要求: 邮箱变更需要认证\n", encoding="utf-8")
        return CliRunner().invoke(verify, [
            "--repo", str(tmp_path),
            "--base", "base", "--head", "head",
            "--spec", str(spec),
            "--output-dir", str(tmp_path / "out"),
            "--no-llm",
        ])

    return _run


class _RefusingStore:
    """A MySQLStore whose write fails the way a refused connection does."""

    def __init__(self, *_a: Any, **_k: Any) -> None:
        return None

    def save_job_summary(self, *_a: Any, **_k: Any) -> None:
        raise ConnectionRefusedError(111, "Connection refused")


class _AcceptingStore:
    def __init__(self, *_a: Any, **_k: Any) -> None:
        self.saved: list[tuple[Any, ...]] = []

    def save_job_summary(self, *args: Any, **_k: Any) -> None:
        self.saved.append(args)


def test_a_database_that_refuses_is_not_reported_as_success(
    run_verify, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("storage.mysql.MySQLStore", _RefusingStore)

    result = run_verify()

    assert "Job summary NOT persisted" in result.stderr, (
        "the write failed and nothing said so; stderr was: " + repr(result.stderr)
    )
    assert "ConnectionRefusedError" in result.stderr
    assert "persisted to MySQL" not in result.output.replace("NOT persisted", "")


def test_the_failure_line_names_where_it_tried(
    run_verify, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYSQL_HOST", "db.internal")
    monkeypatch.setenv("MYSQL_PORT", "3307")
    monkeypatch.setenv("MYSQL_DATABASE", "specproof_prod")
    monkeypatch.setattr("storage.mysql.MySQLStore", _RefusingStore)

    result = run_verify()

    assert "db.internal:3307/specproof_prod" in result.stderr, (
        "the line must name the host the user configured (or the default, which "
        "is itself the answer to 'did I configure anything'); stderr was: "
        + repr(result.stderr)
    )


def test_the_failure_line_never_carries_the_password(
    run_verify, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MYSQL_PASSWORD", "hunter2-must-not-leak")
    monkeypatch.setattr("storage.mysql.MySQLStore", _RefusingStore)

    result = run_verify()

    assert "hunter2-must-not-leak" not in result.stderr
    assert "hunter2-must-not-leak" not in result.output


def test_the_verdict_stays_on_stdout_and_the_exit_code_does_not_move(
    run_verify, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("storage.mysql.MySQLStore", _RefusingStore)

    result = run_verify()

    assert "VERDICT: VERIFIED" in result.output
    assert "VERDICT" not in result.stderr
    assert result.exit_code == 0, "a missing dashboard row must not change the verdict"


def test_a_working_store_still_says_so(
    run_verify, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("storage.mysql.MySQLStore", _AcceptingStore)

    result = run_verify()

    assert "Job summary persisted to MySQL." in result.output
    assert "NOT persisted" not in result.stderr


def test_the_failure_moves_a_counter(
    run_verify, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("storage.mysql.MySQLStore", _RefusingStore)
    before = metrics_snapshot()["counters"].get(
        "verify_job_summary_persist_failures_total", 0
    )

    run_verify()

    after = metrics_snapshot()["counters"].get(
        "verify_job_summary_persist_failures_total", 0
    )
    assert after > before


def test_a_metadata_store_that_says_not_recorded_prints_to_stderr(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    cert = tmp_path / "certificate.json"
    cert.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "storage.object_metadata.record_file_object_best_effort",
        lambda *_a, **_k: None,
    )

    _record_certificate_metadata(cert, "job-1", ["C-1"])

    captured = capsys.readouterr()
    assert "Certificate metadata NOT recorded" in captured.err
    assert "intact" in captured.err
    assert str(cert) in captured.err
