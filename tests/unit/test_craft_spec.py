"""craft/spec.py unit tests — three input forms plus error paths (M1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from craft.spec import (
    SpecParseError,
    TaskSpec,
    parse_spec,
    parse_spec_file,
    parse_spec_json,
    parse_spec_text,
)


def test_parse_plain_text_with_prefixes() -> None:
    text = (
        "修复 double 函数的逻辑错误\n"
        "修改 calc.py 让测试转绿\n"
        "验收: test_double 测试通过\n"
        "验收: 输入 4 返回 8\n"
        "禁止: 不改测试文件\n"
        "影响: calc.py"
    )
    spec = parse_spec_text(text)
    assert spec.title == "修复 double 函数的逻辑错误"
    assert spec.description == "修改 calc.py 让测试转绿"
    assert spec.acceptance_criteria == ["test_double 测试通过", "输入 4 返回 8"]
    assert spec.forbidden_changes == ["不改测试文件"]
    assert spec.affected_area_hint == "calc.py"


def test_parse_plain_text_without_prefixes_rest_is_description() -> None:
    spec = parse_spec_text("重构 UserService\n把重复逻辑抽成公共方法")
    assert spec.title == "重构 UserService"
    assert spec.description == "把重复逻辑抽成公共方法"
    assert spec.acceptance_criteria == []
    assert spec.forbidden_changes == []


def test_parse_text_is_deterministic() -> None:
    text = "标题\n描述\n验收: a\n禁止: b\n影响: c"
    assert parse_spec_text(text) == parse_spec_text(text)


def test_parse_text_crlf_is_normalized() -> None:
    spec = parse_spec_text("title\r\ndescription\r\n验收: a\r\n")
    assert spec.title == "title"
    assert spec.description == "description"
    assert spec.acceptance_criteria == ["a"]


def test_parse_text_empty_raises() -> None:
    with pytest.raises(SpecParseError, match="为空"):
        parse_spec_text("   \n \n")


def _valid_json() -> dict[str, object]:
    return {
        "title": "按邮箱查询用户端点",
        "description": "在 UserController 增加 GET /users/by-email",
        "acceptance_criteria": ["200 返回 UserResponse", "未知邮箱 404"],
        "forbidden_changes": ["不得移除 @PreAuthorize"],
        "affected_area_hint": "controller/service/repository",
    }


def test_parse_json_valid() -> None:
    spec = parse_spec_json(_valid_json())
    assert isinstance(spec, TaskSpec)
    assert spec.title == "按邮箱查询用户端点"
    assert spec.acceptance_criteria == ["200 返回 UserResponse", "未知邮箱 404"]
    assert spec.forbidden_changes == ["不得移除 @PreAuthorize"]


def test_parse_json_missing_field_raises_named_error() -> None:
    for field in (
        "title",
        "description",
        "acceptance_criteria",
        "forbidden_changes",
        "affected_area_hint",
    ):
        data = _valid_json()
        data.pop(field)
        with pytest.raises(SpecParseError, match=field):
            parse_spec_json(data)


def test_parse_json_wrong_field_types_raise() -> None:
    bad_title = _valid_json()
    bad_title["title"] = 123
    with pytest.raises(SpecParseError, match="'title' 类型错误"):
        parse_spec_json(bad_title)
    bad_list = _valid_json()
    bad_list["acceptance_criteria"] = "a, b"
    with pytest.raises(SpecParseError, match="'acceptance_criteria' 类型错误"):
        parse_spec_json(bad_list)
    bad_item = _valid_json()
    bad_item["acceptance_criteria"] = ["ok", 7]
    with pytest.raises(SpecParseError, match=r"acceptance_criteria\[1\]"):
        parse_spec_json(bad_item)
    bad_hint = _valid_json()
    bad_hint["affected_area_hint"] = []
    with pytest.raises(SpecParseError, match="'affected_area_hint' 类型错误"):
        parse_spec_json(bad_hint)
    bad_forbidden = _valid_json()
    bad_forbidden["forbidden_changes"] = None
    with pytest.raises(SpecParseError, match="'forbidden_changes' 类型错误"):
        parse_spec_json(bad_forbidden)


def test_parse_json_top_level_must_be_object() -> None:
    with pytest.raises(SpecParseError, match="顶层必须是对象"):
        parse_spec_json(["title", "x"])


def test_parse_json_ignores_unknown_fields() -> None:
    data = _valid_json()
    data["future_field"] = {"anything": 1}
    spec = parse_spec_json(data)
    assert spec.title == "按邮箱查询用户端点"


def test_parse_spec_file_markdown(tmp_path: Path) -> None:
    path = tmp_path / "task.md"
    path.write_text("给查询加缓存\n验收: 命中缓存不查库\n", encoding="utf-8")
    spec = parse_spec(str(path))
    assert spec.title == "给查询加缓存"
    assert spec.acceptance_criteria == ["命中缓存不查库"]


def test_parse_spec_file_json(tmp_path: Path) -> None:
    path = tmp_path / "task.json"
    path.write_text(json.dumps(_valid_json(), ensure_ascii=False), encoding="utf-8")
    spec = parse_spec_file(path)
    assert spec.title == "按邮箱查询用户端点"


def test_parse_spec_missing_file_is_clear_error(tmp_path: Path) -> None:
    with pytest.raises(SpecParseError, match="不存在"):
        parse_spec(str(tmp_path / "nope.md"))


def test_parse_spec_inline_json_literal() -> None:
    spec = parse_spec(json.dumps(_valid_json(), ensure_ascii=False))
    assert spec.title == "按邮箱查询用户端点"
    assert spec.affected_area_hint == "controller/service/repository"


def test_parse_spec_empty_input_raises() -> None:
    with pytest.raises(SpecParseError):
        parse_spec("   ")
