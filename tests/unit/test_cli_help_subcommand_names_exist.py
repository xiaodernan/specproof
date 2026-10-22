"""`--help` epilog 里点名的「二级命令」必须真实存在（无幽灵子命令）。

#332 只核对了 `specproof <cmd>` 的第一个 token —— 即顶层命令是否存在。但 epilog 里
还出现了带子命令的写法：`specproof craft run` 和 `specproof ops recover`。`craft` / `ops`
是 Group，它们的子命令（`run` / `recover`）同样是「写在帮助文本里、用户会照着敲」的契约。
如果有人把 `run` 改名成 `execute` 却忘了改 epilog，用户敲 `specproof craft run` 会先被
click 顶层接受、再在 Group 层吃到 `No such command 'run'` —— 帮助文本自己变成了错误信息源。

本门把 #332 的尺子往下延了一层：对 epilog 里 `specproof <cmd> <sub>` 形式的提及
（`<sub>` 不以 `-` 开头，从而排除 `demo --run` 这类选项），要求 `<cmd>` 是 Group 且
`<sub>` ∈ `cli.commands[cmd].commands`。

范围边界（诚实，不假装）：
- 只加测试，`main.py` 一字未动。
- 只核对 epilog 里的二级命令提及。模块 docstring 的 `Commands:` 块是「顶层命令 + 描述」
  的扁平索引（如 `specproof quickstart  print the zero-config ...`），那里没有调用式
  的二级命令，已被 #332 在顶层命令层面钉住，本批不重复扫它（扫了反而会把描述句的首词
  误判成子命令）。
- 不要求每个 Group 子命令都出现在 epilog（epilog 是精选），只要求「写出来的二级命令都真」。
"""

from __future__ import annotations

import re

import click

from cli.specproof import main as cli_main

_MENTION_RE = re.compile(
    r"^\s+specproof\s+([a-z][a-z0-9-]*)(?:\s+([a-z][a-z0-9-]+))?",
    re.MULTILINE,
)


def _mentions(text: str) -> list[tuple[str, str | None]]:
    """Return ``(cmd, sub)`` for every `specproof <cmd> [<sub>]` line mention."""
    out: list[tuple[str, str | None]] = []
    for m in _MENTION_RE.finditer(text):
        out.append((m.group(1), m.group(2)))
    return out


def _phantom_subcommands(text: str) -> list[str]:
    """Return mentions whose second token is not a real subcommand of a Group."""
    bad: list[str] = []
    for cmd, sub in _mentions(text):
        if sub is None:
            continue
        command = cli_main.cli.commands.get(cmd)
        if not isinstance(command, click.Group):
            bad.append(f"{cmd} (not a Group, so '{sub}' cannot be its subcommand)")
            continue
        if sub not in command.commands:
            bad.append(f"specproof {cmd} {sub} (no such subcommand)")
    return bad


def test_help_epilog_subcommand_names_exist() -> None:
    mentioned = _mentions(cli_main.HELP_EPILOG)
    # 真空保护：必须至少扫到一个带子命令的提及，否则删光二级命令会假绿
    subs = [sub for _, sub in mentioned if sub]
    assert subs, "epilog has no `specproof <cmd> <sub>` mention; the walk is broken"
    # 我们确实扫到了真实写出来的那两个（若有人把 epilog 里的二级命令整段删掉，这里红）
    assert "run" in subs and "recover" in subs
    assert not _phantom_subcommands(cli_main.HELP_EPILOG)


def test_cli_help_renders_subcommand_mentions() -> None:
    """epilog 真的被 click 渲染，且里面写出来的两个二级命令在真实命令树里接得住。"""
    from click.testing import CliRunner

    result = CliRunner().invoke(cli_main.cli, ["--help"])
    assert result.exit_code == 0, result.output
    assert "craft run" in result.output
    assert "ops recover" in result.output
    # 反向控制：epilog 写出来的这两个二级命令，在真实命令树里确实存在
    craft = cli_main.cli.commands["craft"]
    ops = cli_main.cli.commands["ops"]
    assert isinstance(craft, click.Group) and "run" in craft.commands
    assert isinstance(ops, click.Group) and "recover" in ops.commands
