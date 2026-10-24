"""`agent/security_scanner._should_exclude` 的目录排除必须按**整段**匹配。

#440 量到：`/` 结尾的排除模式用的是 `pattern in normalized`（**子串**匹配），于是
`my_tests/helper.py`、`legacy_scripts/setup.py`、`old_artifacts/x.json` 全都从
秘密扫描里消失。本仓库实测受影响目录 **34 个**，包括全部 `bench/tasks/*-tests/`
夹具树——它们的父目录名只是**以 "tests" 结尾**，整棵树就被顺手跳过了（不是有意排除，
`bench/` 根本不在排除清单里）。

修后：`/` 结尾的模式按路径**段**精确匹配。本门钉住两侧：
- 该排除的仍排除（`tests/`、`__pycache__/`、`agent/security_scanner.py`、`.env`、`*.zip`）；
- 不该排除的不再被顺手扫掉（`my_tests/`、`latest_tests/`、`legacy_scripts/`、
  `old_artifacts/`、`mytarget/`）。

只加测试；`agent/security_scanner.py` 的排除清单本身一字未动（#404 已统一过两条
扫描路径的占位符清单，本号只管「段 vs 子串」这一处匹配语义）。
"""

from __future__ import annotations

import pytest

from agent.security_scanner import _should_exclude


@pytest.mark.parametrize(
    "path",
    [
        "tests/x.py",
        "tests/a/b.py",
        "agent/tests/x.py",
        "__pycache__/x.pyc",
        "node_modules/pkg/index.js",
        "target/classes/A.class",
        "artifacts/legacy-invalid/capsule/a.json",
        "scripts/p0_5_closed_loop.py",
        ".git/config",
    ],
)
def test_a_directory_named_exactly_is_still_excluded(path: str) -> None:
    assert _should_exclude(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "app/my_tests/helper.py",
        "src/latest_tests/x.py",
        "deploy/my_scripts/setup.py",
        "web/legacy_scripts/a.js",
        "data/old_artifacts/x.json",
        "build/mytarget/out.bin",
        "bench/tasks/task-05-add-tests/fixture/repo/App.java",
    ],
)
def test_a_directory_whose_name_merely_ends_with_an_excluded_word_is_scanned(
    path: str,
) -> None:
    """这些路径**不该**被排除 —— 段名只是以某个被排除词结尾，不是那个词本身。"""
    assert _should_exclude(path) is False


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "config/.env",
        "agent/security_scanner.py",
        "deep/nested/agent/security_scanner.py",
        "a/b.zip",
        "a/b.pyc",
        "a/b.jar",
    ],
)
def test_non_directory_patterns_still_match_by_suffix(path: str) -> None:
    """不带 `/` 的模式（`.env`、自引用文件）与 `*.ext` 仍按后缀匹配 —— 未改动。"""
    assert _should_exclude(path) is True


@pytest.mark.parametrize(
    ("path", "excluded"),
    [
        ("tests\\x.py", True),
        ("agent\\tests\\x.py", True),
        ("app\\my_tests\\x.py", False),
        ("build\\mytarget\\out.bin", False),
    ],
)
def test_windows_separators_are_normalized(path: str, excluded: bool) -> None:
    assert _should_exclude(path) is excluded
