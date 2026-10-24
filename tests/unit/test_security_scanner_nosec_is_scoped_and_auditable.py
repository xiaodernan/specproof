"""`agent/security_scanner` 的逐行豁免：`# specproof-nosec <模式名>` 必须**可审计**。

#443 量到：扫描器**没有任何逐行豁免机制**，于是 5 条「意图上的假阳性」（测试夹具
`"secret-value"`、文档示例 `"demo-key"`、docstring 里演示 `redis://[:password@]…`
格式……）无处安放——只能把字面量加进全局占位符清单，越加越宽。

本门钉住新机制的契约，形状抄本仓库已经付过学费的那一套
（`test_bandit_suppressions_are_earned.py`）：

1. **原因在前、模式名在后**。原因写在指令之后会变成 names 的一部分 ⇒ 抑制失效
   （bandit 那课的原样重演：理由变成一堆疯 id，行为退化成裸指令）。
2. **必须点名**。裸指令什么都不藏；点名一个此处不会触发的模式也什么都不藏。
   唯一能消音的办法是完整写下模式名 —— 这才让指令可审计。
3. **一行命中两个模式就得点两个名**（下面 `test_...two_patterns...` 那条）。
4. **行作用域**。只影响那一行。
5. **两条扫描路径同一把尺**（目录路径与 zip 路径）——#404 修的就是这两条漂移。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from agent.security_scanner import scan_capsule_zips, scan_directory

#: 运行时拼接，避免本文件自己变成一个真 secret（pre-commit 的 secret scanner 会读它）。
_FAKE_KEY = "sk-" + "a" * 40

#: 只命中「OpenAI/LLM API Key」一行的形状（不带 api_key= 前缀，免得同时命中
#: 「API Key Assignment」——一行两模式的行为由专门那条用例钉）。
_SINGLE = 'token = "{key}"'


def _write(tmp_path: Path, name: str, body: str) -> None:
    (tmp_path / name).write_text(body, encoding="utf-8")


def test_a_named_suppression_hides_exactly_that_pattern(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "a.yml",
        _SINGLE.format(key=_FAKE_KEY) + "  # specproof-nosec OpenAI/LLM API Key\n",
    )
    result = scan_directory(str(tmp_path))
    assert result.findings == []
    assert result.passed is True


def test_naming_a_pattern_that_does_not_fire_hides_nothing(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "b.yml",
        _SINGLE.format(key=_FAKE_KEY) + "  # specproof-nosec AWS Access Key ID\n",
    )
    result = scan_directory(str(tmp_path))
    assert [f.pattern_name for f in result.findings] == ["OpenAI/LLM API Key"]
    assert result.passed is False


def test_a_bare_directive_hides_nothing(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "c.yml",
        _SINGLE.format(key=_FAKE_KEY) + "  # specproof-nosec\n",
    )
    result = scan_directory(str(tmp_path))
    assert [f.pattern_name for f in result.findings] == ["OpenAI/LLM API Key"]


def test_a_reason_after_the_directive_does_not_suppress(tmp_path: Path) -> None:
    """原因写在指令之后 ⇒ 它变成 names 的一部分 ⇒ 抑制失效（必须把原因放前面）。"""
    _write(
        tmp_path,
        "e.yml",
        _SINGLE.format(key=_FAKE_KEY) + "  # specproof-nosec 这是测试夹具不是真密钥\n",
    )
    result = scan_directory(str(tmp_path))
    assert [f.pattern_name for f in result.findings] == ["OpenAI/LLM API Key"]


def test_a_line_firing_two_patterns_needs_both_named(tmp_path: Path) -> None:
    """一行同时命中两个模式时，只点名一个 ⇒ 另一个照报；两个都点名才静音。"""
    line = f'api_key: "{_FAKE_KEY}"'
    one = tmp_path / "one"
    both = tmp_path / "both"
    one.mkdir()
    both.mkdir()

    _write(one, "g.yml", line + "  # specproof-nosec OpenAI/LLM API Key\n")
    result = scan_directory(str(one))
    assert [f.pattern_name for f in result.findings] == ["API Key Assignment"]

    _write(
        both,
        "h.yml",
        line + "  # specproof-nosec OpenAI/LLM API Key API Key Assignment\n",
    )
    result = scan_directory(str(both))
    assert result.findings == []


def test_the_suppression_is_line_scoped(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "f.yml",
        _SINGLE.format(key=_FAKE_KEY) + "  # specproof-nosec OpenAI/LLM API Key\n"
        + _SINGLE.format(key=_FAKE_KEY) + "\n",
    )
    result = scan_directory(str(tmp_path))
    assert [(f.line, f.pattern_name) for f in result.findings] == [
        (2, "OpenAI/LLM API Key")
    ]


def test_the_zip_path_honours_the_same_directive(tmp_path: Path) -> None:
    """#404 的教训：两条扫描路径必须同一把尺，否则又会长漂移。"""
    zip_path = tmp_path / "capsule.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(
            "suppressed.yml",
            _SINGLE.format(key=_FAKE_KEY) + "  # specproof-nosec OpenAI/LLM API Key\n",
        )
        zf.writestr("plain.yml", _SINGLE.format(key=_FAKE_KEY) + "\n")

    findings = scan_capsule_zips(str(tmp_path))
    assert [f.path for f in findings] == ["capsule.zip::plain.yml"]
