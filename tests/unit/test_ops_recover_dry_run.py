"""#74 — `specproof ops recover --dry-run` must answer "is anything stuck?"
without touching a single job row.

Why this file exists: on 2026-09-25 the only way to find out whether the
reclaimer had work to do was to run the mutating command. It wrote to the
live MySQL and re-delivered a job while the operator was still reading the
candidate list. A read-only mode is only worth anything if the plan it
prints is the plan the mutating pass would actually carry out, so every
judgement here is checked twice: once as a dry-run verdict, once against the
real CAS path.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from agent import worker
from storage.mysql import (
    MySQLStore,
    ReclaimOutcome,
    retry_budget_spent,
)

REPO = Path(__file__).resolve().parents[2]

WRITE_KEYWORDS = ("UPDATE", "INSERT", "DELETE", "REPLACE")


def _row(
    job_id: str,
    *,
    retry_count: int = 0,
    max_retries: int = 3,
    status: str = "RUNNING",
    repo_path: str = "/repo/app",
) -> dict[str, Any]:
    return {
        "id": job_id,
        "repo_path": repo_path,
        "base_ref": "main",
        "head_ref": "feature",
        "spec_path": "spec.md",
        "depth": 2,
        "retry_count": retry_count,
        "max_retries": max_retries,
        "worker_id": "worker-1" if status == "RUNNING" else None,
        "status": status,
        "updated_at": None,
    }


class RecordingStore:
    """A store that logs SQL and refuses to be the one that writes.

    Every read the dry-run needs is served; every write shape records the
    statement so a test can assert the log is read-only. `record_audit` is a
    tripwire: dry-run must never produce an audit row, because an audit row
    means a transition was claimed.
    """

    def __init__(
        self,
        *,
        stale: list[dict[str, Any]] | None = None,
        waiting: list[dict[str, Any]] | None = None,
    ) -> None:
        self.stale = [copy.deepcopy(r) for r in (stale or [])]
        self.waiting = [copy.deepcopy(r) for r in (waiting or [])]
        self.statements: list[str] = []
        self.audits: list[dict[str, Any]] = []
        self.reclaims_called = 0
        self.closed = 0

    # ── reads ────────────────────────────────────────────────────
    def list_stale_running_candidates(
        self, lease_ttl_seconds: int
    ) -> list[dict[str, Any]]:
        self.statements.append(
            f"SELECT stale RUNNING ttl={lease_ttl_seconds}"
        )
        return copy.deepcopy(self.stale)

    def get_jobs_by_status(self, status: str) -> list[dict[str, Any]]:
        assert status == "WAITING_FOR_PROVIDER"
        self.statements.append(f"SELECT {status}")
        return copy.deepcopy(self.waiting)

    # ── writes: recorded, never silently allowed ─────────────────
    def reclaim_stale_running(self, *_a: Any, **_k: Any) -> ReclaimOutcome:
        self.reclaims_called += 1
        raise AssertionError("dry-run must not call the mutating reclaim pass")

    def recover_provider_wait(self, *_a: Any, **_k: Any) -> tuple[bool, str | None]:
        raise AssertionError("dry-run must not call the mutating provider pass")

    def record_audit(self, **kwargs: Any) -> None:
        self.audits.append(kwargs)

    def close(self) -> None:
        self.closed += 1

    # A real store exposes connection(); if dry-run reaches for it we want the
    # AttributeError to surface as a red, not as an untested pass.
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"dry-run touched an unexpected store member: {name}")


class LeaseProbe:
    """Redis lease answers, optionally with the failure the operator hits."""

    def __init__(
        self,
        *,
        alive: set[str] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.alive = set(alive or ())
        self.error = error
        self.probed: list[str] = []

    def get_lease_owner(self, job_id: str) -> str | None:
        self.probed.append(job_id)
        if self.error is not None:
            raise self.error
        return "worker-1" if job_id in self.alive else None

    def close(self) -> None:
        return None


def _wire(
    monkeypatch: pytest.MonkeyPatch, store: RecordingStore
) -> RecordingStore:
    monkeypatch.setattr(worker, "MySQLStore", lambda *a, **k: store)
    monkeypatch.setattr(worker, "RedisStore", lambda *a, **k: LeaseProbe())
    # ops.recover_cmd imports these from agent.worker inside the function
    # body, so the only patch that lands is the one on worker itself.
    monkeypatch.setattr(worker, "reclaim_stale_running_jobs", _never("reclaim"))
    monkeypatch.setattr(
        worker, "recover_waiting_for_provider_jobs", _never("recover")
    )
    return store


# ── the reader itself is read-only ───────────────────────────────


def test_dry_run_reads_candidates_with_the_same_query_as_the_real_pass() -> None:
    """The candidate set must not be a hand-copied second opinion.

    `reclaim_stale_running` selects through `_stale_running_candidates`; if
    the dry-run used its own WHERE clause, the two could disagree about what
    "stale" means and the plan would describe a run that never happens.
    """
    src = (REPO / "storage" / "mysql.py").read_text(encoding="utf-8")
    body = src.split("def list_stale_running_candidates", 1)[1]
    body = body.split("\n    def ", 1)[0]
    assert "_stale_running_candidates(" in body, body
    assert "UPDATE " not in body.upper(), body


def test_preview_emits_no_write_statement_and_no_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _wire(
        monkeypatch,
        RecordingStore(stale=[_row("j-fresh"), _row("j-spent", retry_count=3)]),
    )

    plan = worker.preview_stale_running_jobs(lease_ttl_seconds=30)

    assert plan.rows, "the plan must describe the candidates it was given"
    assert not [s for s in store.statements if s.upper().startswith(WRITE_KEYWORDS)]
    assert store.audits == []
    assert store.reclaims_called == 0


# ── the plan agrees with the mutating pass ───────────────────────


def test_plan_verdicts_split_on_the_same_budget_rule_the_cas_uses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _wire(
        monkeypatch,
        RecordingStore(
            stale=[
                _row("j-requeue", retry_count=0, max_retries=3),
                _row("j-spent", retry_count=3, max_retries=3),
                _row("j-edge", retry_count=2, max_retries=3),
            ]
        ),
    )
    verdicts = {
        row["job_id"]: row["verdict"]
        for row in worker.preview_stale_running_jobs(lease_ttl_seconds=30).rows
    }

    # One read, no writes: the plan asks the candidate question and nothing else.
    assert store.statements == ["SELECT stale RUNNING ttl=30"], store.statements
    assert store.audits == []

    assert verdicts == {
        "j-requeue": worker.PLAN_REQUEUE,
        "j-spent": worker.PLAN_FAIL_BUDGET,
        "j-edge": worker.PLAN_REQUEUE,
    }


def test_budget_rule_is_one_predicate_not_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dry-run and the CAS must not each carry their own copy of `>=`.

    A second implementation of the comparison is how a plan drifts from the
    action it describes: the fix in #71 put the cap in storage, so the plan
    has to ask storage for it.
    """
    cases = [
        (_row("a", retry_count=0, max_retries=3), False),
        (_row("b", retry_count=2, max_retries=3), False),
        (_row("c", retry_count=3, max_retries=3), True),
        (_row("d", retry_count=4, max_retries=3), True),
        (_row("e", retry_count=1, max_retries=1), True),
        (_row("f", retry_count=0, max_retries=0), True),
        (_row("g", retry_count=0, max_retries=5), False),
    ]
    for row, spent in cases:
        assert retry_budget_spent(row) is spent, row

    src = (REPO / "storage" / "mysql.py").read_text(encoding="utf-8")
    reclaim = src.split("def reclaim_stale_running", 1)[1].split("\n    def ", 1)[0]
    provider = src.split("def recover_provider_wait", 1)[1].split("\n    def ", 1)[0]
    assert "retry_budget_spent(" in reclaim, reclaim
    assert "retry_budget_spent(" in provider, provider
    for body in (reclaim, provider):
        assert "retry_count >= max_retries" not in body, body


def test_plan_marks_a_live_lease_as_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale updated_at with a live lease is not a hung job.

    Without this row-level verdict a dry-run would report every aged RUNNING
    row as recoverable and the operator would read a false alarm.
    """
    _wire(
        monkeypatch,
        RecordingStore(stale=[_row("j-alive"), _row("j-dead")]),
    )
    monkeypatch.setattr(
        worker, "RedisStore", lambda *a, **k: LeaseProbe(alive={"j-alive"})
    )

    rows = worker.preview_stale_running_jobs(lease_ttl_seconds=30).rows
    by_id = {r["job_id"]: r for r in rows}

    assert by_id["j-alive"]["verdict"] == worker.PLAN_LEASE_ALIVE
    assert by_id["j-alive"]["lease"] == "alive"
    assert by_id["j-dead"]["verdict"] == worker.PLAN_REQUEUE
    assert by_id["j-dead"]["lease"] == "lost"


def test_unknown_lease_stays_unknown_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Redis cannot answer → the plan stops guessing, like the real pass."""
    _wire(
        monkeypatch,
        RecordingStore(stale=[_row("j-1"), _row("j-2")]),
    )
    monkeypatch.setattr(
        worker,
        "RedisStore",
        lambda *a, **k: LeaseProbe(error=ConnectionError("redis down")),
    )

    plan = worker.preview_stale_running_jobs(lease_ttl_seconds=30)

    assert plan.lease_probe_error is not None
    assert {r["verdict"] for r in plan.rows} == {worker.PLAN_NOT_JUDGED}
    assert {r["lease"] for r in plan.rows} == {"unknown"}


# ── provider-wait dry-run ───────────────────────────────────────


def test_provider_wait_plan_uses_the_job_own_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire(
        monkeypatch,
        RecordingStore(
            waiting=[
                _row("j-wait-1", status="WAITING_FOR_PROVIDER", retry_count=0),
                _row("j-wait-2", status="WAITING_FOR_PROVIDER", retry_count=3),
            ]
        ),
    )
    rows = worker.preview_waiting_for_provider_jobs()
    by_id = {r["job_id"]: r for r in rows}

    assert by_id["j-wait-1"]["verdict"] == worker.PLAN_REQUEUE
    assert by_id["j-wait-2"]["verdict"] == worker.PLAN_FAIL_BUDGET
    # Parking is a provider-health question, not a per-job one: the plan must
    # not invent a "provider is fine" answer it never probed.
    assert all("provider_ready" not in r for r in rows)


# ── the CLI ─────────────────────────────────────────────────────


def _invoke(store: RecordingStore, args: list[str]):
    from cli.specproof.main import cli

    return CliRunner().invoke(cli, args, catch_exceptions=False)


def _never(name: str):
    def _boom(*_a: Any, **_k: Any) -> None:
        raise AssertionError(f"--dry-run called the mutating pass: {name}")

    return _boom


def test_cli_dry_run_never_reaches_the_mutating_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _wire(monkeypatch, RecordingStore(stale=[_row("j-a", retry_count=9)]))

    result = _invoke(store, ["ops", "recover", "--dry-run", "--json"])

    assert result.exit_code == 0, result.output
    import json

    report = json.loads(result.output)
    assert report["dry_run"] is True
    assert report["acted"] == 0
    assert report["running"]["would_requeue_job_ids"] == []
    assert report["running"]["would_fail_budget_job_ids"] == ["j-a"]
    assert store.audits == []


def test_cli_dry_run_prints_the_verdicts_it_did_not_apply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _wire(
        monkeypatch,
        RecordingStore(
            stale=[
                _row("j-ok", retry_count=0, max_retries=3),
                _row("j-spent", retry_count=3, max_retries=3),
            ],
            waiting=[_row("j-w", status="WAITING_FOR_PROVIDER", retry_count=1)],
        ),
    )

    result = _invoke(store, ["ops", "recover", "--dry-run"])

    out = result.output
    assert result.exit_code == 0, out
    assert "j-ok" in out and "j-spent" in out and "j-w" in out
    assert "未改动" in out
    # The point of the flag: nothing may be claimed as already done.
    assert "已抢回" not in out
    assert "本轮改动了" not in out


def test_dry_run_and_real_run_share_the_requeue_wording_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`会抢回` vs `已抢回` — the tense is the safety property.

    If dry-run reused the mutating pass's wording, an operator who read a
    dry-run would believe the job had already been moved.
    """
    store = _wire(
        monkeypatch, RecordingStore(stale=[_row("j-ok", retry_count=0)])
    )
    dry = _invoke(store, ["ops", "recover", "--dry-run"]).output
    assert "会" in dry, dry


def test_cli_dry_run_reports_an_unanswerable_query_as_undecided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A MySQL failure is 无法判定, exit 1 — not "nothing is stuck"."""
    from cli.specproof.main import cli

    def _raise(*_a: Any, **_k: Any) -> None:
        raise ConnectionError("mysql down")

    monkeypatch.setattr(worker, "MySQLStore", _raise)
    monkeypatch.setattr(worker, "RedisStore", lambda *a, **k: LeaseProbe())
    monkeypatch.setattr(worker, "reclaim_stale_running_jobs", _never("reclaim"))
    monkeypatch.setattr(
        worker, "recover_waiting_for_provider_jobs", _never("recover")
    )

    result = CliRunner().invoke(
        cli, ["ops", "recover", "--dry-run"], catch_exceptions=False
    )

    assert result.exit_code == 1, result.output
    assert "无法判定" in result.output
    assert "不等于没有卡住的作业" in result.output


def test_mysql_store_exposes_the_read_only_selector() -> None:
    """The plan is reachable from the store an operator can hold read-only."""
    assert callable(MySQLStore.list_stale_running_candidates)
    assert callable(MySQLStore.reclaim_stale_running)
