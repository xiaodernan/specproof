"""specproof demo — 零配置体验: 准备演示仓库并跑第一次真实验证.

The bundled sample (demo/spring-backend) ships without a .git directory,
so the verification pipeline (which diffs two git refs) cannot run against
it out of the box. This command initialises a local git history for it:

    base          original implementation (permission checks intact)
    head-v1       removes the @PreAuthorize guard from changeEmail

and optionally runs `specproof verify` against it, so a new user sees a
real BLOCKED verdict with findings and evidence in minutes.

Idempotent: existing refs are reused; the working tree is restored to the
original (base) content after the demo commit is created.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import click

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEMO_REPO = _PROJECT_ROOT / "demo" / "spring-backend"
DEMO_SPEC = _PROJECT_ROOT / "demo" / "requirement.txt"
BASE_REF = "base"
HEAD_REF = "head-v1"
_GUARD_ANCHOR = '@PreAuthorize("isAuthenticated()")'
_CONTROLLER = (
    Path("src/main/java/com/specproof/demo/controller/UserController.java")
)


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if check and proc.returncode != 0:
        raise click.ClickException(
            f"git {' '.join(args)} 失败: {proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc


def _ref_exists(repo: Path, ref: str) -> bool:
    return _git(repo, "rev-parse", "--verify", "--quiet", ref, check=False).returncode == 0


def prepare_demo_repo(repo: Path = DEMO_REPO) -> bool:
    """Create base / head-v1 refs in the demo repo. Returns True if created."""
    if not repo.is_dir():
        raise click.ClickException(f"未找到演示仓库目录: {repo}")
    if not DEMO_SPEC.is_file():
        raise click.ClickException(f"未找到演示需求文件: {DEMO_SPEC}")

    if _ref_exists(repo, BASE_REF) and _ref_exists(repo, HEAD_REF):
        return False

    if not (repo / ".git").exists():
        _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "SpecProof Demo")
    _git(repo, "config", "user.email", "demo@specproof.local")

    # base: original implementation
    _git(repo, "add", "-A")
    if _git(repo, "diff", "--cached", "--quiet", check=False).returncode != 0:
        _git(repo, "commit", "-q", "-m", "demo: 原始实现 (权限检查完整)")
    _git(repo, "tag", "-f", BASE_REF)

    # head: remove the permission guard from changeEmail
    controller = repo / _CONTROLLER
    content = controller.read_text(encoding="utf-8")
    if _GUARD_ANCHOR not in content:
        raise click.ClickException(
            "权限检查注解已不在源文件中, 无法构造演示改动。\n"
            f"如想重置演示仓库, 删除 {repo / '.git'} 并还原文件后重试。"
        )
    mutated = re.sub(
        r"\s*" + re.escape(_GUARD_ANCHOR) + r"\r?\n", "\n", content
    )
    try:
        controller.write_text(mutated, encoding="utf-8")
        _git(repo, "add", "-A")
        if _git(repo, "diff", "--cached", "--quiet", check=False).returncode != 0:
            _git(repo, "commit", "-q", "-m", "demo: 移除邮箱修改接口的权限检查 (演示回归)")
        _git(repo, "tag", "-f", HEAD_REF)
    finally:
        _git(repo, "checkout", "-q", "--", ".")
        _git(repo, "checkout", "-q", BASE_REF, check=False)
    return True


@click.command("demo")
@click.option(
    "--run",
    is_flag=True,
    default=False,
    help="准备完演示仓库后立即运行真实验证 (specproof verify --no-llm, FAST 档)",
)
def demo(run: bool) -> None:
    """零配置体验 SpecProof: 准备演示仓库, 跑一次真实验证.

    \b
    演示内容: demo/spring-backend 的 head-v1 版本移除了邮箱修改接口的
    权限检查, 与 demo/requirement.txt 中「所有接口必须认证」的需求冲突,
    预期验证结论为 BLOCKED, 并给出风险描述与证据。
    """
    click.echo("==> 准备演示仓库 (demo/spring-backend) ...")
    created = prepare_demo_repo()
    if created:
        click.echo(f"    [ok] 已创建 git 历史: {BASE_REF} -> {HEAD_REF}")
    else:
        click.echo(f"    [..] git 历史已存在 ({BASE_REF} / {HEAD_REF}), 直接使用")

    click.echo("")
    click.echo(f"  仓库路径   : {DEMO_REPO}")
    click.echo(f"  基准版本   : {BASE_REF}          (权限检查完整)")
    click.echo(f"  待检查版本 : {HEAD_REF}   (移除了权限检查)")
    click.echo(f"  需求文件   : {DEMO_SPEC}")

    if not run:
        click.echo("")
        click.echo("下一步 (二选一):")
        click.echo("")
        click.echo("  1) 命令行直接跑验证:")
        click.echo(
            "     specproof demo --run"
        )
        click.echo("")
        click.echo("  2) 网页体验 (基础设施更完整, 需要 Docker):")
        click.echo("     pwsh scripts/start_local.ps1")
        click.echo("     打开 http://localhost:5173 -> 变更验收 -> 新建验证 -> 点「填入演示案例」")
        click.echo("")
        return

    click.echo("")
    click.echo("==> 运行真实验证 (FAST 档, 确定性检查, 不调用模型) ...")
    click.echo("    首次运行会编译演示项目, 可能需要几分钟。")
    click.echo("")
    from cli.specproof.commands.verify import verify

    ctx = click.Context(verify)
    ctx.invoke(
        verify,
        repo=str(DEMO_REPO),
        base_ref=BASE_REF,
        head_ref=HEAD_REF,
        spec_path=str(DEMO_SPEC),
        depth="FAST",
        output_dir="./reports",
        app_dir="",
        use_llm=False,
        keep_worktrees=False,
        use_approved_contracts=False,
        publish_check=False,
    )
    click.echo("")
    click.echo("演示完成: 上方 VERDICT 应为 BLOCKED — 需求要求认证, 而演示改动移除了它。")
    click.echo("报告与证据见 ./reports 目录。")
