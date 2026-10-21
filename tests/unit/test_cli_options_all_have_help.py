"""每个 CLI 选项都必须有一句 `--help` 文本：无 help 的选项就是神秘旋钮。

`specproof <cmd> --help` 是用户唯一能就地发现「这个开关是干什么的」的地方。一个
`@click.option` 若没写 `help=`，它在帮助里只显示开关名和默认值——用户只能靠猜，或者去读源码。
这不是外观问题：猜错的开关会真的改变行为（比如 `--base` 猜成「基线分支」而它其实是「用来 diff
的 git ref」）。

本门递归遍历 `cli.commands`（含 `craft`/`ops` 这类 Group 的子命令），对每个 `click.Option`
断言 `help` 非空。带两个正向控制：① 扫到的命令数 ≥ 10、选项数 ≥ 40（否则扫描器坏了会「全绿」
地什么也不验）；② 断言至少有一个已知选项被扫到（`fix --repo`），证明递归没漏掉子命令。

本门**不**检查 help 文本的**内容质量**（说得准不准是另一回事，机器判不了），只判「有没有」。
"""

from __future__ import annotations

from collections.abc import Iterator

import click

from cli.specproof import main as cli_main


def _walk_commands(cmd: click.Command, path: str = "") -> Iterator[tuple[str, click.Command]]:
    """Yield (dotted path, command) for ``cmd`` and every subcommand of a Group."""
    yield path or cmd.name or "?", cmd
    if isinstance(cmd, click.Group):
        for name, sub in sorted(cmd.commands.items()):
            child = f"{path} {name}".strip()
            yield from _walk_commands(sub, child)


def _options(cmd: click.Command) -> list[click.Option]:
    return [p for p in cmd.params if isinstance(p, click.Option)]


def test_every_option_has_help_text() -> None:
    commands = list(_walk_commands(cli_main.cli))
    assert len(commands) >= 10, f"walked only {len(commands)} commands; the walk is broken"

    total_options = 0
    missing: list[str] = []
    seen_fix_repo = False
    for path, cmd in commands:
        for opt in _options(cmd):
            total_options += 1
            if opt.opts and "--repo" in opt.opts and path.split()[:1] == ["fix"]:
                seen_fix_repo = True
            help_text = getattr(opt, "help", None)
            if not help_text or not str(help_text).strip():
                missing.append(f"{path} {'/'.join(opt.opts)}")

    # 正向控制 ①：扫到的选项足够多，证明遍历覆盖了子命令
    assert total_options >= 40, f"walked only {total_options} options; Group recursion is broken"
    # 正向控制 ②：一个已知存在于子命令里的选项确实被扫到
    assert seen_fix_repo, "did not reach `fix --repo`; the Group recursion missed subcommands"
    # 断言本体
    assert not missing, (
        "these CLI options have no --help text (users can only guess what they do): "
        + ", ".join(missing)
    )
