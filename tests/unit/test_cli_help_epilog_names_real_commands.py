"""`--help` 的 epilog 与模块 docstring 只能点名**真实存在**的子命令。

`cli/specproof/main.py` 有两份手写清单，都可能与真实命令集漂移：
1. 模块 docstring 的 "Commands:" 块；
2. `HELP_EPILOG`——`specproof --help` 结尾那段「常用任务」，用户照着敲命令的地方。

真实命令集从 click Group 的 `cli.commands` 读（`add_command` 的产物），不是另抄一份。
本门只钉**一个方向**：清单里出现的 `specproof <cmd>` 必须是真实命令（无幽灵命令）。
反方向（每个注册命令都必须在清单里）故意不钉——epilog 是「常用任务」精选，不是全量清单，
硬要求每个命令都出现会把文档变成噪声。

为什么不钉反方向却要钉这个方向：一句 `specproof foo` 写在 `--help` 里，用户敲下去得到
"No such command"——这比「某个命令没被介绍」伤得多，它把帮助文本本身变成了错误信息源。
"""

from __future__ import annotations

import re

from cli.specproof import main as cli_main

#: `specproof <word>` — the first token after `specproof ` is the command.
_MENTION = re.compile(r"specproof\s+([a-z][a-z0-9_-]*)")


def _registered_commands() -> set[str]:
    return set(cli_main.cli.commands)


def _mentioned_commands(text: str) -> set[str]:
    return set(_MENTION.findall(text))


def test_epilog_names_only_real_commands() -> None:
    registered = _registered_commands()
    mentioned = _mentioned_commands(cli_main.HELP_EPILOG)
    # 正向控制：解析器确实读到了命令（否则空集会让下面的断言恒真）
    assert len(mentioned) >= 3, (
        f"parsed only {sorted(mentioned)} from HELP_EPILOG; the mention regex is broken"
    )
    assert "craft" in mentioned  # 已知在 epilog 里出现的命令，证明解析正确
    phantom = mentioned - registered
    assert not phantom, (
        "HELP_EPILOG tells users to run commands that do not exist: "
        + ", ".join(sorted(phantom))
        + f" (registered: {sorted(registered)})"
    )


def test_module_docstring_commands_block_names_only_real_commands() -> None:
    registered = _registered_commands()
    mentioned = _mentioned_commands(cli_main.__doc__ or "")
    assert len(mentioned) >= 3, (
        f"parsed only {sorted(mentioned)} from the module docstring; regex is broken"
    )
    phantom = mentioned - registered
    assert not phantom, (
        "the module docstring's Commands: block names non-existent commands: "
        + ", ".join(sorted(phantom))
        + f" (registered: {sorted(registered)})"
    )


def test_registered_command_set_is_non_empty_and_parsed_by_the_gate() -> None:
    # 反向控制：真实命令集非空，且门读到的集合与 click 的 Group 一致
    registered = _registered_commands()
    assert len(registered) >= 10, f"only {len(registered)} commands registered — CLI wiring broke"
    # epilog 点名的命令必须全部是 registered 的子集（逐项再证一次，防止上面的集合运算写反）
    for name in _mentioned_commands(cli_main.HELP_EPILOG):
        assert name in registered, f"{name!r} is not a registered command"
