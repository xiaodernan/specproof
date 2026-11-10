"""specproof ops recover — 把卡住的验收作业拉回队列 (#68).

`reclaim_stale_running_jobs` / `recover_waiting_for_provider_jobs` lived in
agent/worker.py with no production caller: a worker that died left its job in
RUNNING forever, and a job parked in WAITING_FOR_PROVIDER during a provider
outage could only be freed by editing the database by hand. This command is
the operator-triggered entry point for both passes.

``--dry-run`` (#74) answers "is anything stuck?" without moving a job:
same candidate query, same lease probe, same budget predicate as the real
pass, and no UPDATE / audit / re-delivery at all. Finding out used to
require doing.

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
HELP_DRY_RUN = "只判定、不改动：列出这轮会动哪些作业（零 UPDATE / 零重投）"


def _ids(rows: list[dict[str, Any]], noun: str) -> str:
    """Render "job(已用 n/m)" per row — the budget is what an operator reads."""
    return " ".join(
        f"{row['id']}({noun} {int(row.get('retry_count') or 0)}/"
        f"{int(row.get('max_retries') or 0)})"
        for row in rows
    )


def _plan_ids(rows: list[dict[str, Any]], verdict: str, noun: str) -> str:
    """Render the plan rows for one verdict — same shape as `_ids`.

    Mirrors `_ids`'s `None`-tolerant rendering: a row with a missing or
    null `retry_count`/`max_retries` must not raise, it renders as 0/0.
    """
    return " ".join(
        f"{row['job_id']}({noun} {int(row.get('retry_count') or 0)}/"
        f"{int(row.get('max_retries') or 0)})"
        for row in rows
        if row.get("verdict") == verdict
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
@click.option("--dry-run", "dry_run", is_flag=True, help=HELP_DRY_RUN)
@click.pass_context
def recover_cmd(
    ctx: click.Context,
    lease_ttl_seconds: int,
    running_only: bool,
    provider_wait_only: bool,
    as_json: bool,
    dry_run: bool,
) -> None:
    """回收卡住的验收作业：过期 RUNNING 回 QUEUED，搁置的等模型服务作业恢复。

    \b
    specproof ops recover --dry-run        只判定：这轮会动哪些作业，不做任何改动
    specproof ops recover                  三步都跑（含超期作业清理）
    specproof ops recover --running-only   只救 worker 崩掉后留在 RUNNING 的作业
    specproof ops recover --lease-ttl 120  与自定义租约 TTL 的 worker 对齐
    """
    from agent.worker import (
        expire_overdue_jobs,
        reclaim_stale_running_jobs,
        recover_waiting_for_provider_jobs,
    )

    if running_only and provider_wait_only:
        raise click.ClickException("--running-only 与 --provider-wait-only 互斥")

    if dry_run:
        _recover_dry_run(
            ctx,
            lease_ttl_seconds=lease_ttl_seconds,
            running_only=running_only,
            provider_wait_only=provider_wait_only,
            as_json=as_json,
        )
        return

    report: dict[str, Any] = {"lease_ttl_seconds": lease_ttl_seconds, "judged": True}
    lines: list[str] = []
    acted = 0

    # The steps that will actually run, and their numbering.
    #
    # The numbering is COMPUTED from the steps that run, not hardcoded: a
    # run with --running-only must not print a "[2/3]" for a step that
    # never happens, and a skipped step must not steal a number from the
    # ones that do run.
    #
    # The expiry runs in the FULL sweep only. Both flags say "only": the
    # expiry answers a different question ("is anything over budget?")
    # from the two reclaimers ("did the worker die?" / "is the provider
    # back?"), so running it under --running-only would make the flag
    # lie about what it did.
    step_names: list[str] = []
    if not provider_wait_only:
        step_names.append("running")
    if not running_only:
        step_names.append("provider_wait")
    if not running_only and not provider_wait_only:
        step_names.append("expired")
    step_total = len(step_names)
    step_no = {name: i + 1 for i, name in enumerate(step_names)}

    if not provider_wait_only:
        lines.append(
            f"[{step_no['running']}/{step_total}] 过期 RUNNING 回收"
            f"（租约 TTL {lease_ttl_seconds}s）"
        )
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
        lines.append(
            f"[{step_no['provider_wait']}/{step_total}] WAITING_FOR_PROVIDER 恢复"
        )
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

    # The execution-budget expiry. The worker's reclaim tick runs it
    # automatically; an operator running this command by hand must reach
    # the same conclusion, or the manual path would answer a DIFFERENT
    # question than the automatic one ("is anything stuck?" vs "is
    # anything over budget?"). A job that is expired is TERMINAL — it is
    # not re-queued and not re-delivered.
    if "expired" in step_no:
        lines.append(
            f"[{step_no['expired']}/{step_total}] 超期作业清理（执行期限预算）"
        )
        try:
            expired_ids = expire_overdue_jobs()
        except Exception as exc:  # noqa: BLE001 — 同上
            report["judged"] = False
            report["expired"] = {
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            }
            lines.append(
                f"  无法判定：数据库查询失败（{type(exc).__name__}: "
                f"{str(exc)[:200]}）—— 这不等于没有超期作业"
            )
        else:
            report["expired"] = {"job_ids": expired_ids}
            acted += len(expired_ids)
            if expired_ids:
                lines.append(
                    f"  {len(expired_ids)} 个作业超过执行期限预算，已置为 EXPIRED"
                    "（终态，不重投）: " + ",".join(expired_ids)
                )
            else:
                lines.append("  没有超期作业")

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


def _recover_dry_run(
    ctx: click.Context,
    *,
    lease_ttl_seconds: int,
    running_only: bool,
    provider_wait_only: bool,
    as_json: bool,
) -> None:
    """Print what `recover` WOULD do; change nothing (#74).

    Every number here comes from the same readers the mutating passes use, so
    a plan that says "会抢回" is a promise the real run keeps. The one thing it
    does not answer is whether the model provider is back — that probe is
    per-process and default-off, so claiming it would be an invented verdict.
    """
    from agent.worker import (
        preview_overdue_jobs,
        preview_stale_running_jobs,
        preview_waiting_for_provider_jobs,
    )
    from storage.mysql import (
        PLAN_FAIL_BUDGET,
        PLAN_LEASE_ALIVE,
        PLAN_NOT_JUDGED,
        PLAN_REQUEUE,
    )

    report: dict[str, Any] = {
        "lease_ttl_seconds": lease_ttl_seconds,
        "dry_run": True,
        "judged": True,
        "acted": 0,
    }
    lines: list[str] = []
    would = 0

    # The same computed numbering the mutating path uses, so a dry-run
    # and the real run name the same steps the same way.
    step_names: list[str] = []
    if not provider_wait_only:
        step_names.append("running")
    if not running_only:
        step_names.append("provider_wait")
    if not running_only and not provider_wait_only:
        step_names.append("expired")
    step_total = len(step_names)
    step_no = {name: i + 1 for i, name in enumerate(step_names)}

    if not provider_wait_only:
        lines.append(
            f"[{step_no['running']}/{step_total}] 过期 RUNNING 回收判定"
            f"（租约 TTL {lease_ttl_seconds}s，只读）"
        )
        try:
            plan = preview_stale_running_jobs(
                lease_ttl_seconds=lease_ttl_seconds
            )
        except Exception as exc:  # noqa: BLE001 — 判定失败必须说原因
            report["judged"] = False
            report["running"] = {
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            }
            lines.append(
                f"  无法判定：数据库/租约查询失败（{type(exc).__name__}: "
                f"{str(exc)[:200]}）—— 这不等于没有卡住的作业"
            )
        else:
            rows = plan.rows

            def by(verdict: str) -> list[dict[str, Any]]:
                return [r for r in rows if r["verdict"] == verdict]

            requeue, spent = by(PLAN_REQUEUE), by(PLAN_FAIL_BUDGET)
            alive, unknown = by(PLAN_LEASE_ALIVE), by(PLAN_NOT_JUDGED)
            report["running"] = {
                "candidates": len(rows),
                "would_requeue_job_ids": [str(r["job_id"]) for r in requeue],
                "would_fail_budget_job_ids": [str(r["job_id"]) for r in spent],
                "lease_alive_job_ids": [str(r["job_id"]) for r in alive],
                "not_judged_job_ids": [str(r["job_id"]) for r in unknown],
                "lease_probe_error": plan.lease_probe_error,
            }
            would += len(requeue) + len(spent)
            if plan.lease_probe_error is not None:
                report["judged"] = False
                lines.append(
                    f"  无法判定租约（{plan.lease_probe_error}）：{len(unknown)} 个"
                    f"候选记为未判定 —— 真跑也只会在此前已判定的 "
                    f"{len(rows) - len(unknown)}/{len(rows)} 个之后停止"
                )
            if not rows:
                lines.append(
                    f"  未发现无更新超过 {lease_ttl_seconds} 秒的 RUNNING 作业"
                )
            if requeue:
                lines.append(
                    f"  会抢回并重新入队 {len(requeue)} 个: "
                    + _plan_ids(rows, PLAN_REQUEUE, "重试")
                )
            if spent:
                lines.append(
                    f"  会因重试预算耗尽判 FAILED {len(spent)} 个"
                    f"（需人工重新提交）: "
                    + _plan_ids(rows, PLAN_FAIL_BUDGET, "已用")
                )
            if alive:
                lines.append(f"  {len(alive)} 个租约仍在续：不会改动")

    if not running_only:
        lines.append(
            f"[{step_no['provider_wait']}/{step_total}] WAITING_FOR_PROVIDER "
            "恢复判定（只读）"
        )
        try:
            parked = preview_waiting_for_provider_jobs()
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
                "parked": len(parked),
                "would_requeue_job_ids": [
                    str(r["job_id"]) for r in parked
                    if r["verdict"] == PLAN_REQUEUE
                ],
                "would_fail_budget_job_ids": [
                    str(r["job_id"]) for r in parked
                    if r["verdict"] == PLAN_FAIL_BUDGET
                ],
                "provider_ready": "not_probed",
            }
            would += len(parked)
            if not parked:
                lines.append("  没有等待模型服务的作业")
            else:
                requeue_n = len(report["provider_wait"]["would_requeue_job_ids"])
                spent_n = len(report["provider_wait"]["would_fail_budget_job_ids"])
                if requeue_n:
                    lines.append(
                        f"  会重新入队 {requeue_n} 个: "
                        + _plan_ids(parked, PLAN_REQUEUE, "重试")
                    )
                if spent_n:
                    lines.append(
                        f"  会因重试预算耗尽判 FAILED {spent_n} 个: "
                        + _plan_ids(parked, PLAN_FAIL_BUDGET, "已用")
                    )
                lines.append(
                    "  注：模型服务是否已恢复不在判定范围内（熔断器是进程内的），"
                    "真跑时服务未恢复则这些作业继续搁置"
                )

    if not running_only and not provider_wait_only:
        lines.append("[3/3] 超期作业清理判定（执行期限预算，只读）")
        try:
            overdue = preview_overdue_jobs()
        except Exception as exc:  # noqa: BLE001 — 同上
            report["judged"] = False
            report["expired"] = {
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            }
            lines.append(
                f"  无法判定：数据库查询失败（{type(exc).__name__}: "
                f"{str(exc)[:200]}）—— 这不等于没有超期作业"
            )
        else:
            report["expired"] = {
                "overdue": len(overdue),
                "would_expire_job_ids": [str(r["id"]) for r in overdue],
            }
            would += len(overdue)
            if not overdue:
                lines.append("  没有超期作业")
            else:
                lines.append(
                    f"  会置为 EXPIRED {len(overdue)} 个（终态，不重投）: "
                    + " ".join(
                        f"{r['id']}(预算 {int(r.get('max_execution_seconds') or 0)}s"
                        f"，当前 {r.get('status')}）"
                        for r in overdue
                    )
                )

    report["would_act"] = would
    if as_json:
        click.echo(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        summary = (
            "至少一轮无法判定，请检查 MySQL/Redis 后重跑（退出码 1）。"
            if not report["judged"]
            else (
                f"只读判定：真跑会改动 {would} 个作业；本轮未改动任何作业。"
                if would
                else "只读判定：没有作业需要改动；本轮未改动任何作业。"
            )
        )
        click.echo("\n".join(lines))
        click.echo(f"\n{summary}")
    ctx.exit(0 if report["judged"] else 1)


@ops_cmd.command("replay-notifications")
@click.option(
    "--job", "job_id", default=None,
    help="只回放该作业的死信通知 (缺省=全部)",
)
def replay_notifications_cmd(job_id: str | None) -> None:
    """把死信通知重新入队给 notify relay (清死信标记, relay 下轮认领)。

    死因未除 (接收端仍未配置/仍故障) 时 relay 会再次死信且 attempts 续计
    ——回放可见, 不静默。先列出死信行, 再回放, 输出回放的行 id。
    """
    from storage.mysql import MySQLStore

    store = MySQLStore()
    dead = store.list_dead_notifications(job_id)
    if not dead:
        click.echo("没有死信通知 (dead_lettered_at IS NOT NULL 的行为 0)。")
        return
    click.echo(f"死信通知 {len(dead)} 行:")
    for row in dead:
        click.echo(
            f"  #{row['id']} job={row['job_id']} verdict={row['verdict']} "
            f"attempts={row['attempts']} error={str(row['last_error'])[:80]}"
        )
    replayed = store.replay_dead_notifications(job_id)
    click.echo(f"已回放 {len(replayed)} 行 (id: {replayed})——relay 下轮认领。")


@ops_cmd.command("notify-stats")
@click.option(
    "--job", "job_id", default=None,
    help="只看该作业的通知行 (缺省=汇总 + 全部死信)",
)
def notify_stats_cmd(job_id: str | None) -> None:
    """Outbox 车道的运营可见性: 汇总 (pending/dead_letters/retries/
    last_success) + 死信行明细——RUNBOOK 读法的入口 (先看接收端,
    再看 pending 是否在涨, 死信非 0 即有通知未送达)。"""
    from storage.mysql import MySQLStore

    store = MySQLStore()
    stats = store.notify_outbox_stats()
    click.echo(
        f"pending={stats['pending']} dead_letters={stats['dead_letters']} "
        f"retries={stats['retries']} "
        f"last_success={stats['last_success'] or '—'}"
    )
    dead = store.list_dead_notifications(job_id)
    if not dead:
        click.echo("死信通知: 0 行。")
        return
    click.echo(f"死信通知 {len(dead)} 行 (回放: specproof ops replay-notifications"
               + (f" --job {job_id}" if job_id else "") + "):")
    for row in dead:
        click.echo(
            f"  #{row['id']} job={row['job_id']} verdict={row['verdict']} "
            f"attempts={row['attempts']} error={str(row['last_error'])[:80]}"
        )


@ops_cmd.command("reconcile-buckets")
@click.option(
    "--bucket", "buckets", multiple=True,
    help="要扫描的桶 (缺省=对象存储的三个生产桶)",
)
@click.option(
    "--json", "as_json", is_flag=True,
    help="输出机读 JSON",
)
def reconcile_buckets_cmd(buckets: tuple[str, ...], as_json: bool) -> None:
    """对象存储与索引的对账: 桶里有而索引没有的幽灵 / 索引指向而桶里没有的 / 字节变了的。

    只报告, **不删任何东西**——删除是另一次明确动作 (与本地 payload 目录的
    orphan 扫描同一纪律: 按启发式删证据, 就是这个项目要避免的失败模式)。
    """
    import json as _json

    from evidence.bucket_reconcile import reconcile_buckets
    from storage.minio import MinIOClient
    from storage.object_metadata import default_object_metadata_store

    objects = MinIOClient()
    names = tuple(buckets) if buckets else tuple(objects.BUCKETS)
    report = reconcile_buckets(objects, default_object_metadata_store(), names)
    if as_json:
        click.echo(_json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return
    click.echo(
        f"扫描 {len(names)} 个桶: 对象 {report.scanned_objects} 个, "
        f"索引行 {report.scanned_records} 行。"
    )
    if report.is_clean():
        click.echo("桶与索引一致: 没有幽灵、没有断链、没有摘要不符。")
        return
    for finding in report.findings:
        click.echo(f"  [{finding.kind}] {finding.bucket}/{finding.object_name}: {finding.detail}")


@ops_cmd.command("rollback-migrations")
@click.option(
    "--to", "target", type=int, required=True,
    help="目标版本 (仅回滚 version > --to 的迁移)",
)
@click.option(
    "--dry-run", "dry_run", is_flag=True, default=False,
    help="只打印计划, 不执行任何 SQL",
)
@click.option(
    "--i-am-sure-rolling-back", "allow_production", is_flag=True, default=False,
    help="允许执行到非测试库 (需要人工明确同意, 默认拒绝)",
)
@click.pass_context
def rollback_migrations_cmd(
    ctx: click.Context, target: int, dry_run: bool, allow_production: bool
) -> None:
    """回滚数据库迁移。

    `infra/mysql/migrations/down/` 里的降级脚本此前只是文档, 本命令把它变成可执行操作。
    默认 `--dry-run` 时只打印计划; 真实执行要求目标库为 `specproof_test*` 家族,
    否则必须显式传 `--i-am-sure-rolling-back`。按版本倒序 (最高版本先回) 执行,
    每个版本降级后删除 `schema_migrations` 对应行。

    拒绝语义: 缺 down 脚本、或目标库非测试库 (且未传 --i-am-sure-rolling-back) —
    任何拒绝都以退出码 1 结束, 且打印具体原因, 不静默。
    """
    from storage.rollback_migrations import MigrationRollbackRunner, RollbackError

    try:
        runner = MigrationRollbackRunner()
        report = runner.apply(target, dry_run=dry_run, allow_production=allow_production)
    except RollbackError as exc:
        click.echo(f"回滚拒绝: {exc}", err=True)
        ctx.exit(1)
        return

    if not report:
        click.echo("没有需要回滚的迁移 (目标版本已在不回滚区间内)。")
        ctx.exit(0)
        return

    for item in report:
        if dry_run:
            stmts = "; ".join(item["statements"])  # noqa: E501
            click.echo(
                f"[dry] rollback {item['version']:04d} {item['name']} "
                f"({item['statement_count']} statements): {stmts[:120]}"
            )
        else:
            click.echo(f"[done] rollback {item['version']:04d} {item['name']}")
    ctx.exit(0)


