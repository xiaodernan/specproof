"""Spec text and report paths are read on a different OS than wrote them.

Both cases were measured on the Linux CI runner (run 36436188582, job
`tests-no-infra`) and neither can be reproduced by simply running on Windows:

  * `craft.spec.parse_spec` probed the filesystem with the spec *text*, and on
    POSIX `stat()` answers a name component longer than 255 bytes with
    `ENAMETOOLONG` instead of "not a file". `Path.is_file()` only swallows
    ENOENT/ENOTDIR/EBADF/ELOOP, so an inline JSON task spec crashed the CLI
    instead of parsing it. Measured as
    `OSError: [Errno 36] File name too long: '{"id": "task-01", ...}'`.
  * the MCP verify summary trimmed capsule paths with `Path(...).name`, which
    splits only on the running platform's separator. A Windows-style report read
    by a Linux MCP server put the whole server-side path in the tool payload.

The POSIX failure is reproduced here by arming it at the seam it came from:
`Path.is_file` raises the error a Linux kernel raises for that name. The fixture
returns the names it refused, and every case that depends on it asserts the list
is non-empty — a simulation that never fires would otherwise make the case green
for the wrong reason.
"""
from __future__ import annotations

import ast
import errno
import inspect
import json
from pathlib import Path

import pytest

import mcp.tools as mcp_tools
from craft.spec import SpecParseError, parse_spec

NAME_MAX = 255  # per-component limit on ext4, the filesystem the runner uses


def _longest_component(text: str) -> int:
    """Length of the longest path component `text` would present to `stat()`.

    Split on "/" only: on the Linux runner a backslash is an ordinary filename
    character, which is exactly why an escaped-Unicode JSON spec arrived as one
    665-byte component instead of many short ones.
    """
    return max((len(part) for part in text.split("/")), default=0)


_LONG_JSON = json.dumps(
    {
        "id": "task-01",
        "title": "按邮箱查找用户 (只读查询)",
        "description": "为目录服务实现 find_user_by_email: 按邮箱精确查找用户并返回显示名; "
        "未命中返回 None。查找必须是只读操作, 不得修改传入的 users 集合。"
        "邮箱本地部分按大小写不敏感匹配, 且不得把邮箱原文写进日志; "
        "目录为空时同样返回 None, 不得抛出异常、不得返回占位对象; "
        "调用方可能并发发起多个查询, 因此实现不得缓存任何可变状态。",
        "acceptance_criteria": ["find_user_by_email 命中时返回用户显示名", "未命中返回 None"],
        "forbidden_changes": ["不得删除或改写 user_count"],
        "affected_area_hint": "svc.py",
    },
    ensure_ascii=True,
)

_LONG_TEXT = "\n".join(
    [
        "按邮箱查找用户 (只读查询)",
        "为目录服务实现 find_user_by_email: 按邮箱精确查找用户并返回显示名; "
        "未命中返回 None。查找必须是只读操作, 不得修改传入的 users 集合。"
        "邮箱本地部分按大小写不敏感匹配, 且不得把邮箱原文写进日志; "
        "目录为空时同样返回 None, 不得抛出异常、不得返回占位对象; "
        "调用方可能并发发起多个查询, 因此实现不得缓存任何可变状态; "
        "如需索引只能按规范化后的邮箱建键, 且不得跨租户共享。",
        "验收: 命中时返回显示名",
        "禁止: 不得删除或改写 user_count",
        "影响: svc.py",
    ]
)


@pytest.fixture
def posix_name_limit(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Answer `is_file()` the way a POSIX kernel does, and report what was refused."""
    refused: list[str] = []
    original = Path.is_file

    def is_file(self: Path) -> bool:
        if _longest_component(str(self)) > NAME_MAX:
            refused.append(str(self)[:60])
            raise OSError(errno.ENAMETOOLONG, "File name too long", str(self))
        return original(self)

    monkeypatch.setattr(Path, "is_file", is_file)
    return refused


def test_fixtures_are_beyond_the_posix_component_limit() -> None:
    """The two inputs really do present a >255-byte component to `stat()`."""
    assert _longest_component(_LONG_JSON) > NAME_MAX
    assert _longest_component(_LONG_TEXT) > NAME_MAX


def test_inline_json_spec_survives_a_posix_name_limit(
    posix_name_limit: list[str],
) -> None:
    task = parse_spec(_LONG_JSON)
    assert posix_name_limit, "the POSIX name limit never fired; this case proved nothing"
    assert task.title == "按邮箱查找用户 (只读查询)"
    assert task.acceptance_criteria == [
        "find_user_by_email 命中时返回用户显示名",
        "未命中返回 None",
    ]
    assert task.forbidden_changes == ["不得删除或改写 user_count"]


def test_inline_plain_text_spec_survives_a_posix_name_limit(
    posix_name_limit: list[str],
) -> None:
    task = parse_spec(_LONG_TEXT)
    assert posix_name_limit, "the POSIX name limit never fired; this case proved nothing"
    assert task.title == "按邮箱查找用户 (只读查询)"
    assert task.acceptance_criteria == ["命中时返回显示名"]
    assert task.forbidden_changes == ["不得删除或改写 user_count"]
    assert task.affected_area_hint == "svc.py"


def test_an_existing_spec_file_is_still_parsed_as_a_file(tmp_path: Path) -> None:
    """The guarded probe must not have stopped recognising real paths."""
    spec = tmp_path / "task.spec"
    spec.write_text(_LONG_JSON, encoding="utf-8")
    assert parse_spec(str(spec)).title == "按邮箱查找用户 (只读查询)"


def test_a_spec_file_that_is_absent_is_still_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(SpecParseError, match="不存在"):
        parse_spec(str(tmp_path / "task.spec"))


# ── report paths written by one OS, read by another ──────────────────────────


def _stdout_with(capsules: list[str]) -> str:
    lines = [
        "Job ID: 11111111-2222-3333-4444-555555555555",
        "VERDICT: BLOCKED",
        f"Bug Capsules: {len(capsules)} generated",
    ]
    lines += [f"  {path}" for path in capsules]
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize(
    ("printed", "expected"),
    [
        (r"C:\tmp\reports\capsules\capsule-AUTH-01.zip", "capsule-AUTH-01.zip"),
        ("/tmp/reports/capsules/capsule-AUTH-01.zip", "capsule-AUTH-01.zip"),
        ("capsules/capsule-AUTH-01.zip", "capsule-AUTH-01.zip"),
        ("capsule-AUTH-01.zip", "capsule-AUTH-01.zip"),
    ],
)
def test_capsule_paths_become_names_whatever_wrote_them(
    printed: str, expected: str
) -> None:
    """The Windows case is only red on the platform that has the bug; the AST
    gate below is what holds on every platform."""
    payload = mcp_tools.parse_verify_stdout(_stdout_with([printed]))
    assert payload["capsules"] == [expected]
    for name in payload["capsules"]:
        assert "\\" not in name and "/" not in name, (
            "a capsule entry must be a name: the tool payload is shown to users, "
            "and a server-side absolute path is not an artefact identifier"
        )


def test_capsule_list_keeps_every_entry_from_a_mixed_report() -> None:
    payload = mcp_tools.parse_verify_stdout(
        _stdout_with(
            [
                r"C:\tmp\reports\capsules\capsule-AUTH-01.zip",
                "/tmp/reports/capsules/capsule-TRANSACTION-01.zip",
            ]
        )
    )
    assert payload["capsules"] == [
        "capsule-AUTH-01.zip",
        "capsule-TRANSACTION-01.zip",
    ]


def test_the_report_parser_does_not_split_paths_with_the_running_os() -> None:
    """`Path(...).name` inside the parser is the platform bug, in wait of a retry.

    The separator that splits a printed report path is decided by the machine
    that *wrote* the report, so the parser may not ask the running platform.
    """
    tree = ast.parse(inspect.getsource(mcp_tools.parse_verify_stdout))
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or node.attr != "name":
            continue
        value = node.value
        if isinstance(value, ast.Call) and getattr(value.func, "id", None) == "Path":
            offenders.append(node.lineno)
    assert offenders == [], f"Path(...).name at line(s) {offenders}"
