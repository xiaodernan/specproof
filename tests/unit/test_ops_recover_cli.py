"""#68 — `specproof ops recover` must be the production caller of the reclaimers.

The two reclaim functions shipped with zero callers for months, so a test that
only exercised them directly proved a guard nobody could reach. These tests
drive the CLI: the command must actually invoke both worker functions, must
keep "cannot judge" apart from "nothing is stuck", and must not exit 0 when a
pass could not be judged.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from click.testing import CliRunner

import agent.worker as worker_module
import cli.specproof.main as main_module
from cli.specproof.commands.ops import ops_cmd
from storage.mysql import ReclaimOutcome


def _outcome(
    *,
    reclaimed: list[dict[str, Any]] | None = None,
    candidates: int = 0,
    lease_probe_error: str | None = None,
    exhausted: list[dict[str, Any]] | None = None,
) -> ReclaimOutcome:
    rows = reclaimed or []
    return ReclaimOutcome(
        reclaimed=rows,
        exhausted=exhausted or [],
        candidates=candidates,
        probed=candidates if lease_probe_error is None else max(candidates - 1, 0),
        lease_probe_error=lease_probe_error,
    )


_RECLAIMED_ROW = {
    "id": "j-stale",
    "retry_count": 1,
    "max_retries": 3,
}


class Recorder:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[Any] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.fixture
def patched(monkeypatch: pytest.MonkeyPatch) -> dict[str, Recorder]:
    reclaim = Recorder(_outcome(reclaimed=[dict(_RECLAIMED_ROW)], candidates=2))
    recover = Recorder([("j-parked", "QUEUED")])
    monkeypatch.setattr(worker_module, "reclaim_stale_running_jobs", reclaim)
    monkeypatch.setattr(worker_module, "recover_waiting_for_provider_jobs", recover)
    return {"reclaim": reclaim, "recover": recover}


def _invoke(args: list[str]) -> Any:
    return CliRunner().invoke(ops_cmd, args)


def test_recover_invokes_both_worker_reclaimers(patched: dict[str, Recorder]) -> None:
    result = _invoke(["recover"])

    assert result.exit_code == 0, result.output
    assert len(patched["reclaim"].calls) == 1
    assert len(patched["recover"].calls) == 1
    assert "j-stale" in result.output
    assert "j-parked→QUEUED" in result.output
    assert "本轮改动了 2 个作业" in result.output


def test_flags_select_single_pass(patched: dict[str, Recorder]) -> None:
    assert _invoke(["recover", "--running-only"]).exit_code == 0
    assert len(patched["recover"].calls) == 0

    fresh = _invoke(["recover", "--provider-wait-only"])
    assert fresh.exit_code == 0
    assert len(patched["reclaim"].calls) == 1  # --provider-wait-only skips pass 1


def test_mutually_exclusive_flags_are_rejected(patched: dict[str, Recorder]) -> None:
    result = _invoke(["recover", "--running-only", "--provider-wait-only"])

    assert result.exit_code != 0
    assert "互斥" in result.output
    assert patched["reclaim"].calls == []


def test_lease_ttl_is_carried_to_the_reclaimer(patched: dict[str, Recorder]) -> None:
    assert _invoke(["recover", "--lease-ttl", "120"]).exit_code == 0

    assert patched["reclaim"].calls[0][1] == {"lease_ttl_seconds": 120}


def test_unknown_lease_exits_nonzero_and_reports_partial_pass(
    patched: dict[str, Recorder], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Already-requeued rows stay reported when the pass stops: the count is not lost."""
    monkeypatch.setattr(
        worker_module,
        "reclaim_stale_running_jobs",
        Recorder(
            _outcome(
                reclaimed=[dict(_RECLAIMED_ROW)],
                candidates=3,
                lease_probe_error="ConnectionError: redis down",
            )
        ),
    )

    result = _invoke(["recover", "--running-only"])

    assert result.exit_code == 1
    assert "无法判定租约" in result.output
    assert "停止抢回" in result.output
    assert "已抢回 1 个" in result.output
    assert "未发现" not in result.output


def test_candidates_with_live_leases_are_not_reported_as_reclaimed(
    patched: dict[str, Recorder], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        worker_module,
        "reclaim_stale_running_jobs",
        Recorder(_outcome(candidates=4)),
    )

    result = _invoke(["recover", "--running-only"])

    assert result.exit_code == 0
    assert "4 个候选本轮未被改动" in result.output
    assert "已抢回" not in result.output
    assert "FAILED" not in result.output


def test_database_failure_is_never_read_as_no_stuck_jobs(
    patched: dict[str, Recorder], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        worker_module,
        "reclaim_stale_running_jobs",
        Recorder(RuntimeError("connect timeout")),
    )

    result = _invoke(["recover"])

    assert result.exit_code == 1
    assert "无法判定" in result.output
    assert "这不等于没有卡住的作业" in result.output
    # the second pass still ran and its own judgement stands on its own
    assert len(patched["recover"].calls) == 1


def test_empty_but_judged_pass_says_so(
    patched: dict[str, Recorder], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        worker_module, "reclaim_stale_running_jobs", Recorder(_outcome())
    )
    monkeypatch.setattr(worker_module, "recover_waiting_for_provider_jobs",
                        Recorder([]))

    result = _invoke(["recover"])

    assert result.exit_code == 0
    assert "未发现无更新超过 30 秒的 RUNNING 作业" in result.output
    assert "没有等待模型服务的作业" in result.output
    assert "判定有效" in result.output


def test_json_report_is_machine_readable(
    patched: dict[str, Recorder], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        worker_module,
        "reclaim_stale_running_jobs",
        Recorder(
            _outcome(
                reclaimed=[dict(_RECLAIMED_ROW)],
                candidates=3,
                lease_probe_error="ConnectionError: redis down",
            )
        ),
    )

    result = _invoke(["recover", "--json"])

    assert result.exit_code == 1
    report = json.loads(result.output)
    assert report["judged"] is False
    assert report["lease_ttl_seconds"] == 30
    assert report["running"]["reclaimed_job_ids"] == ["j-stale"]
    assert report["running"]["candidates"] == 3
    assert report["acted"] == 2


def test_budget_exhausted_recovery_names_the_failed_jobs(
    patched: dict[str, Recorder], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        worker_module,
        "recover_waiting_for_provider_jobs",
        Recorder([("j-a", "QUEUED"), ("j-b", "FAILED")]),
    )

    result = _invoke(["recover", "--provider-wait-only"])

    assert result.exit_code == 0
    assert "j-b→FAILED" in result.output
    assert "重试预算耗尽" in result.output


def test_command_is_reachable_from_the_main_cli() -> None:
    """A command no entry point registers is the same dead code as a dead function."""
    result = CliRunner().invoke(main_module.cli, ["ops", "--help"])

    assert result.exit_code == 0
    assert "recover" in result.output



def test_budget_exhausted_candidate_is_reported_as_failed_not_requeued(
    patched: dict[str, Recorder], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A job the reclaimer ended must not be described as one that came back."""
    dead = {"id": "j-dead", "retry_count": 3, "max_retries": 3}
    monkeypatch.setattr(
        worker_module,
        "reclaim_stale_running_jobs",
        Recorder(_outcome(candidates=1, exhausted=[dead])),
    )

    result = _invoke(["recover", "--running-only"])

    assert result.exit_code == 0, result.output
    assert "重试预算已耗尽" in result.output
    assert "j-dead(已用 3/3)" in result.output
    assert "需人工重新提交" in result.output
    assert "已抢回并重新入队" not in result.output
    assert "未被改动" not in result.output  # 1 candidate, and it was acted on


def test_mixed_pass_reports_both_branches_and_counts_both_as_acted(
    patched: dict[str, Recorder], monkeypatch: pytest.MonkeyPatch
) -> None:
    alive = dict(_RECLAIMED_ROW)
    dead = {"id": "j-dead", "retry_count": 5, "max_retries": 5}
    monkeypatch.setattr(
        worker_module,
        "reclaim_stale_running_jobs",
        Recorder(
            _outcome(reclaimed=[alive], exhausted=[dead], candidates=2)
        ),
    )

    result = _invoke(["recover", "--running-only"])

    assert result.exit_code == 0, result.output
    assert "已抢回并重新入队 1 个: j-stale(重试 1/3)" in result.output
    assert "1 个重试预算已耗尽" in result.output
    assert "本轮改动了 2 个作业" in result.output


def test_json_report_separates_exhausted_from_reclaimed(
    patched: dict[str, Recorder], monkeypatch: pytest.MonkeyPatch
) -> None:
    dead = {"id": "j-dead", "retry_count": 3, "max_retries": 3}
    monkeypatch.setattr(
        worker_module,
        "reclaim_stale_running_jobs",
        Recorder(_outcome(candidates=1, exhausted=[dead])),
    )

    result = _invoke(["recover", "--running-only", "--json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["running"]["exhausted_job_ids"] == ["j-dead"]
    assert data["running"]["reclaimed_job_ids"] == []
    assert data["acted"] == 1
    assert data["judged"] is True


def test_candidates_acted_on_never_shrink_below_the_candidate_count(
    patched: dict[str, Recorder], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two candidates, two actions: the 'not touched' line must stay silent."""
    alive = dict(_RECLAIMED_ROW)
    dead = {"id": "j-dead", "retry_count": 3, "max_retries": 3}
    monkeypatch.setattr(
        worker_module,
        "reclaim_stale_running_jobs",
        Recorder(_outcome(reclaimed=[alive], exhausted=[dead], candidates=3)),
    )

    result = _invoke(["recover", "--running-only"])

    assert "1 个候选本轮未被改动" in result.output
