"""specproof ops recover — 把卡住的验收作业拉回队列 (#68).

`reclaim_stale_running_jobs` / `recover_waiting_for_provider_jobs` lived in
agent/worker.py with no production caller: a worker that died left its job in
RUNNING forever, and a job parked in WAITING_FOR_PROVIDER during a provider
outage could only be freed by editing the database by hand. This command is
the operator-triggered entry point for both passes.

Honesty rules (the whole point of this command's output shape):
- "没有卡住的作业" is only said when MySQL answered the query. A connection
  failure is reported as 无法判定, never as an empty result.
- A Redis lease probe that cannot answer is UNKNOWN, not "the lease expired".
  The reclaim pass stops at that candidate and this command says how far it got
  and how many it had already requeued — those rows are real and stay reported.
- Exit code 0 means every pass was judged; 1 means at least one pass could not
  be judged (or failed), so a cron/CI wrapper cannot read silence as success.
"""

from __future__ import annotations

import json
from typing import Any

import click

HELP_RUNNING = "只跑过期 RUNNING 回收"
HELP_PROVIDER_WAIT = "只跑 WAITING_FOR_PROVIDER 恢复"
HELP_JSON = "输出机器可读的 JSON"


def _ids(rows: list[dict[str, Any]], noun: str) -> str:
    """Render "job(已用 n/m)" per row — the budget is what an operator reads."""
    return " ".join(
        f"{row['id']}({noun} {int(row.get('retry_count') or 0)}/"
        f"{int(row.get('max_retries') or 0)})"
        for row in rows
    )


def _human_running(outcome: Any, lease_ttl_seconds: int) -> tuple[list[str], bool]:
    """Render pass 1; returns (lines, judged)."""
    lines: list[str] = []
    judged = True
    if outcome.lease_probe_error is not None:
        judged = False
        lines.append(
            f"  无法判定租约（{outcome.lease_probe_error}）：本轮在第 "
            f"{outcome.probed}/{outcome.candidates} 个候选处停止抢回，"
            f"在此之前已抢回 {len(outcome.reclaimed)} 个"
        )
    if outcome.candidates == 0:
        lines.append(
            f"  未发现无更新超过 {lease_ttl_seconds} 秒的 RUNNING 作业"
        )
        return lines, judged
    if outcome.reclaimed:
        lines.append(
            f"  已抢回并重新入队 {len(outcome.reclaimed)} 个: "
            + _ids(outcome.reclaimed, "重试"),
        )
    if outcome.exhausted:
        lines.append(
            f"  {len(outcome.exhausted)} 个重试预算已耗尽 → FAILED，"
            f"未重新入队（需人工重新提交）: {_ids(outcome.exhausted, '已用')}",
        )
    untouched = outcome.candidates - len(outcome.reclaimed) - len(
        outcome.exhausted
    )
    if untouched > 0:
        lines.append(
            f"  {untouched} 个候选本轮未被改动：租约仍在续，或已被其它路径更新"
        )
    return lines, judged


def _human_provider_wait(results: list[tuple[str, str]]) -> list[str]:
    if not results:
        return ["  没有等待模型服务的作业"]
    failed = [job_id for job_id, status in results if status == "FAILED"]
    lines = [
        f"  恢复 {len(results)} 个: "
        + " ".join(f"{job_id}→{status}" for job_id, status in results)
    ]
    if failed:
        lines.append(
            f"  其中 {len(failed)} 个因重试预算耗尽转为 FAILED，需人工重新提交"
        )
    return lines


@click.group("ops")
def ops_cmd() -> None:
    """运维恢复动作（需要能连上 MySQL/Redis）。"""


@ops_cmd.command("recover")
@click.option("--lease-ttl", "lease_ttl_seconds", default=30, show_default=True,
              type=click.IntRange(min=1),
              help="RUNNING 行被视为过期的无更新时长（秒），应与 worker 租约 TTL 一致")
@click.option("--running-only", is_flag=True, help=HELP_RUNNING)
@click.option("--provider-wait-only", is_flag=True, help=HELP_PROVIDER_WAIT)
@click.option("--json", "as_json", is_flag=True, help=HELP_JSON)
@click.pass_context
def recover_cmd(
    ctx: click.Context,
    lease_ttl_seconds: int,
    running_only: bool,
    provider_wait_only: bool,
    as_json: bool,
) -> None:
    """回收卡住的验收作业：过期 RUNNING 回 QUEUED，搁置的等模型服务作业恢复。

    \b
    specproof ops recover                  两轮都跑
    specproof ops recover --running-only   只救 worker 崩掉后留在 RUNNING 的作业
    specproof ops recover --lease-ttl 120  与自定义租约 TTL 的 worker 对齐
    """
    from agent.worker import (
        reclaim_stale_running_jobs,
        recover_waiting_for_provider_jobs,
    )

    if running_only and provider_wait_only:
        raise click.ClickException("--running-only 与 --provider-wait-only 互斥")

    report: dict[str, Any] = {"lease_ttl_seconds": lease_ttl_seconds, "judged": True}
    lines: list[str] = []
    acted = 0

    if not provider_wait_only:
        lines.append(f"[1/2] 过期 RUNNING 回收（租约 TTL {lease_ttl_seconds}s）")
        try:
            outcome = reclaim_stale_running_jobs(lease_ttl_seconds=lease_ttl_seconds)
        except Exception as exc:  # noqa: BLE001 — 运维命令要说出判定失败的原因
            report["judged"] = False
            report["running"] = {"error": f"{type(exc).__name__}: {str(exc)[:300]}"}
            lines.append(
                f"  无法判定：数据库/租约查询失败（{type(exc).__name__}: "
                f"{str(exc)[:200]}）—— 这不等于没有卡住的作业"
            )
        else:
            running_lines, judged = _human_running(outcome, lease_ttl_seconds)
            report["judged"] = report["judged"] and judged
            report["running"] = {
                "candidates": outcome.candidates,
                "probed": outcome.probed,
                "reclaimed_job_ids": [str(row["id"]) for row in outcome.reclaimed],
                "exhausted_job_ids": [str(row["id"]) for row in outcome.exhausted],
                "lease_probe_error": outcome.lease_probe_error,
            }
            acted += len(outcome.reclaimed) + len(outcome.exhausted)
            lines.extend(running_lines)

    if not running_only:
        lines.append("[2/2] WAITING_FOR_PROVIDER 恢复")
        try:
            results = recover_waiting_for_provider_jobs()
        except Exception as exc:  # noqa: BLE001 — 同上
            report["judged"] = False
            report["provider_wait"] = {
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            }
            lines.append(
                f"  无法判定：数据库查询失败（{type(exc).__name__}: "
                f"{str(exc)[:200]}）—— 这不等于没有搁置的作业"
            )
        else:
            report["provider_wait"] = {
                "recovered": [{"job_id": job_id, "to_status": status}
                              for job_id, status in results],
            }
            acted += len(results)
            lines.extend(_human_provider_wait(results))

    report["acted"] = acted
    if as_json:
        click.echo(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        summary = (
            "至少一轮无法判定，请检查 MySQL/Redis 后重跑（退出码 1）。"
            if not report["judged"]
            else (f"本轮改动了 {acted} 个作业。" if acted
                  else "判定有效：没有作业需要改动。")
        )
        click.echo("\n".join(lines))
        click.echo(f"\n{summary}")
    ctx.exit(0 if report["judged"] else 1)
