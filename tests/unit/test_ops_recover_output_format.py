"""`ops recover` 的输出格式化函数栅栏（#282 队列点名的鲁棒性不一致腿）。

`_ids` / `_plan_ids` 决定运维人员在终端读到的「job(已用 n/m)」形态；`_human_running`
/ `_human_provider_wait` 决定两轮判定的可读性文案。这些函数本应**永不因一行缺字段而崩**
——运维命令在 DB 连接抖动、某行缺 `retry_count` 时仍要给出可读结论，而不是裸 traceback。

本批把此契约钉死，并消掉 `_ids`(用 `.get(...) or 0`) 与老版 `_plan_ids`(直接 `row[...]`)
对 None/missing retry 计数**鲁棒性不一致**的潜伏 bug：修复后 `_plan_ids` 与 `_ids` 同样兜底 0/0。
"""

from __future__ import annotations

from cli.specproof.commands import ops


def _row(row_id: str, retry_count=None, max_retries=None) -> dict:
    return {"id": row_id, "retry_count": retry_count, "max_retries": max_retries}


def test_ids_renders_present_counts() -> None:
    out = ops._ids([_row("job-1", 1, 3), _row("job-2", 2, 3)], "重试")
    assert out == "job-1(重试 1/3) job-2(重试 2/3)"


def test_ids_tolerates_none_and_missing_counts() -> None:
    # 老版 _ids 用 .get(...) or 0；None / 缺键都必须兜成 0/0，不能 KeyError/TypeError
    out = ops._ids(
        [_row("a", None, None), _row("b", 0, 0), {"id": "c"}],
        "已用",
    )
    assert out == "a(已用 0/0) b(已用 0/0) c(已用 0/0)"


def test_ids_empty_rows_render_empty() -> None:
    assert ops._ids([], "重试") == ""


def test_plan_ids_renders_only_matching_verdict() -> None:
    rows = [
        {"job_id": "j1", "verdict": "RECLAIM", "retry_count": 1, "max_retries": 3},
        {"job_id": "j2", "verdict": "EXHAUST", "retry_count": 3, "max_retries": 3},
        {"job_id": "j3", "verdict": "RECLAIM", "retry_count": 0, "max_retries": 5},
    ]
    assert ops._plan_ids(rows, "RECLAIM", "已用") == "j1(已用 1/3) j3(已用 0/5)"
    assert ops._plan_ids(rows, "EXHAUST", "已用") == "j2(已用 3/3)"


def test_plan_ids_tolerates_none_and_missing_counts() -> None:
    # 修复后 _plan_ids 必须与 _ids 同样兜底 0/0；缺失 verdict 键不 KeyError
    rows = [
        {"job_id": "a", "verdict": "RECLAIM", "retry_count": None, "max_retries": None},
        {"job_id": "b", "verdict": "RECLAIM", "retry_count": 0, "max_retries": 0},
        {"job_id": "c", "verdict": "RECLAIM"},
    ]
    assert ops._plan_ids(rows, "RECLAIM", "已用") == "a(已用 0/0) b(已用 0/0) c(已用 0/0)"
    # 缺 verdict 键的行被安全过滤，而不是让整批崩
    assert ops._plan_ids([{"job_id": "x"}], "RECLAIM", "已用") == ""


class _Outcome:
    """Minimal stand-in for a reclaim outcome (only the fields renderers read)."""

    def __init__(
        self,
        *,
        candidates: int,
        probed: int = 0,
        reclaimed: list | None = None,
        exhausted: list | None = None,
        lease_probe_error=None,
    ) -> None:
        self.candidates = candidates
        self.probed = probed
        self.reclaimed = reclaimed or []
        self.exhausted = exhausted or []
        self.lease_probe_error = lease_probe_error


def test_human_running_no_candidates() -> None:
    lines, judged = ops._human_running(_Outcome(candidates=0), lease_ttl_seconds=30)
    assert judged is True
    assert any("未发现无更新超过 30 秒的 RUNNING 作业" in ln for ln in lines)


def test_human_running_lease_probe_error_marks_unjudged() -> None:
    outcome = _Outcome(
        candidates=3,
        probed=1,
        reclaimed=[_row("job-1", 1, 3)],
        lease_probe_error="redis timeout",
    )
    lines, judged = ops._human_running(outcome, lease_ttl_seconds=30)
    assert judged is False
    assert any("无法判定租约" in ln for ln in lines)
    # 已抢回的行仍如实报告（不因为后面的探针失败而消失）
    assert any("已抢回并重新入队" in ln for ln in lines)


def test_human_running_reclaims_and_exhausts() -> None:
    outcome = _Outcome(
        candidates=5,
        reclaimed=[_row("job-1", 1, 3)],
        exhausted=[_row("job-2", 3, 3)],
    )
    lines, judged = ops._human_running(outcome, lease_ttl_seconds=30)
    assert judged is True
    assert any("已抢回并重新入队 1 个" in ln for ln in lines)
    assert any("重试预算已耗尽" in ln and "job-2" in ln for ln in lines)
    # 5 - 1 - 1 = 3 个未动
    assert any("3 个候选本轮未被改动" in ln for ln in lines)


def test_human_provider_wait_empty() -> None:
    assert ops._human_provider_wait([]) == ["  没有等待模型服务的作业"]


def test_human_provider_wait_marks_failures() -> None:
    lines = ops._human_provider_wait(
        [("job-1", "FIXED"), ("job-2", "FAILED"), ("job-3", "FAILED")]
    )
    assert any("恢复 3 个" in ln for ln in lines)
    assert any("2 个因重试预算耗尽转为 FAILED" in ln for ln in lines)
