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
        # #441: 本地环境 / 工具缓存 / 暂存工作树 —— 永不发布，且实测霸占全树遍历
        ".local/llm.json",
        ".venv/lib/python3.14/site-packages/pkg/mod.py",
        "venv/lib/x.py",
        ".scratch/wt134/agent/foo.py",
        ".mypy_cache/3.12/x.json",
        ".pytest_cache/v/cache/lastfailed",
        ".ruff_cache/0.14.0/x.json",
        # #443：.venv 的前缀家族 —— 本仓库的虚拟环境叫 .venv312，#441 只列了精确名
        ".venv312/Lib/site-packages/pkg/mod.py",
        ".venv-py312/lib/x.py",
    ],
)
def test_a_directory_named_exactly_is_still_excluded(path: str) -> None:
    assert _should_exclude(path) is True


@pytest.mark.parametrize(
    "path",
    [
        ".venue/hall/seat.py",
        ".vendor/pkg/mod.py",
        "src/venue.py",
        "apps/prevenue/x.ts",
    ],
)
def test_the_venv_prefix_does_not_swallow_similar_names(path: str) -> None:
    """`.venv` 前缀规则不能顺手吃掉 `.venue` / `.vendor` —— 前导点就是为这个。

    #443 量到：本仓库 venv 叫 `.venv312`，所以精确名清单漏了它；改成前缀规则后
    必须同时证明它没有变成新的过宽匹配（#440 那一类）。
    """
    assert _should_exclude(path) is False


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


def test_module_and_test_side_agree_on_the_local_exemption() -> None:
    """#441：两份清单描述同一个政策，漂移过。

    `tests/security/test_no_key_leak.py::_is_source_file` 早就排除了 `.local`
    （理由写在它的 docstring 里：`.local/.gitignore` 是 `*`，那里面什么都提交不了），
    而 `agent/security_scanner.py` 的清单**漏了它**——后果是 `run_full_security_scan`
    把 `.local/llm.json` 连同它的 `.bak` 报成两条 CRITICAL 假阳性。这条把两边钉到一起。
    """
    from tests.security.test_no_key_leak import _is_source_file

    assert _is_source_file(".local/llm.json") is False
    assert _should_exclude(".local/llm.json") is True
    # 正向控制：一个真该扫的路径两边都放行，防止上面两条只是「两边都排一切」。
    assert _is_source_file("experiments/external_state.py") is True
    assert _should_exclude("experiments/external_state.py") is False
