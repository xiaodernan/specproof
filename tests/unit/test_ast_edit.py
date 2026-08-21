"""craft/ast_edit.py unit tests — AST-structured edits, stale guard, backup +
audit pipeline, structured diff output, and ast_edit registry dispatch
(计划书 §14.5 / task 6 第三项)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from craft.ast_edit import AstEditError, AstEditor, AstParseError
from craft.editor import EditError, Editor, StaleContextError, sha256_digest
from craft.executor import Executor
from craft.schemas import ToolResult
from craft.tools import (
    CODE_AST_PARSE_FAILED,
    CODE_INVALID_ARGUMENTS,
    CODE_PATH_OUT_OF_RANGE,
    CODE_STALE_CONTEXT,
    ToolRegistry,
)

FIXED_CLOCK = "2026-08-18T00:00:00+00:00"


def make_editor(tmp_path: Path) -> Editor:
    return Editor(
        tmp_path,
        backup_dir=tmp_path / ".specraft" / "backup",
        audit_path=tmp_path / ".specraft" / "audit.jsonl",
        clock=lambda: FIXED_CLOCK,
    )


def make_ast(tmp_path: Path) -> AstEditor:
    return AstEditor(make_editor(tmp_path))


def make_registry(tmp_path: Path, **kwargs: Any) -> ToolRegistry:
    kwargs.setdefault("executor", Executor(tmp_path, mode="local"))
    return ToolRegistry(tmp_path, **kwargs)


def call(registry: ToolRegistry, tool: str, arguments: dict[str, Any]) -> ToolResult:
    return registry.dispatch(registry.build_tool_call(tool, arguments))


# -- rename_symbol ----------------------------------------------------------------


def test_rename_symbol_updates_definition_and_references(tmp_path: Path) -> None:
    source = (
        "# header comment survives\n"
        "def compute(x):\n"
        "    return compute(x) * 2\n"
        "\n"
        "\n"
        "def other():\n"
        "    return compute(1)\n"
    )
    (tmp_path / "calc.py").write_text(source, encoding="utf-8")
    diff = make_ast(tmp_path).rename_symbol("calc.py", "compute", "calculate")
    result = (tmp_path / "calc.py").read_text(encoding="utf-8")
    assert "def calculate(x):" in result
    assert "return calculate(x) * 2" in result
    assert "return calculate(1)" in result
    assert "compute" not in result
    assert "# header comment survives" in result
    compile(result, "calc.py", "exec")
    assert diff["path"] == "calc.py"
    rename = next(hunk for hunk in diff["hunks"] if hunk["kind"] == "rename_symbol")
    assert rename["symbols"] == ["compute", "calculate"]
    assert "modify_function" in [hunk["kind"] for hunk in diff["hunks"]]


def test_rename_symbol_updates_from_import_alias(tmp_path: Path) -> None:
    source = "from util import step\n\n\ndef call():\n    return step(1)\n"
    (tmp_path / "calc.py").write_text(source, encoding="utf-8")
    make_ast(tmp_path).rename_symbol("calc.py", "step", "stride")
    result = (tmp_path / "calc.py").read_text(encoding="utf-8")
    assert "from util import stride" in result
    assert "return stride(1)" in result
    assert "step" not in result


def test_rename_symbol_leaves_attribute_and_keyword_untouched(tmp_path: Path) -> None:
    source = (
        "class Point:\n"
        "    def move(self, step):\n"
        "        return self.step + step\n"
        "\n"
        "\n"
        "def step():\n"
        "    return 1\n"
        "\n"
        "\n"
        "def call():\n"
        "    return step(step=2)\n"
    )
    (tmp_path / "calc.py").write_text(source, encoding="utf-8")
    make_ast(tmp_path).rename_symbol("calc.py", "step", "stride")
    result = (tmp_path / "calc.py").read_text(encoding="utf-8")
    assert "def move(self, stride):" in result
    assert "return self.step + stride" in result
    assert "stride(step=2)" in result
    assert "def stride():" in result
    assert "def step" not in result
    compile(result, "calc.py", "exec")


def test_rename_symbol_requires_a_match(tmp_path: Path) -> None:
    source = "def alpha():\n    return 1\n"
    target = tmp_path / "calc.py"
    target.write_text(source, encoding="utf-8")
    editor = make_editor(tmp_path)
    with pytest.raises(AstEditError, match="未命中"):
        AstEditor(editor).rename_symbol("calc.py", "missing", "found")
    assert target.read_text(encoding="utf-8") == source
    assert not (tmp_path / ".specraft" / "backup").exists()
    refusals = [entry for entry in editor.audit if "拒绝" in entry.detail]
    assert refusals and refusals[0].action == "ast_edit"


def test_rename_symbol_stale_digest_refuses_without_writing(tmp_path: Path) -> None:
    target = tmp_path / "calc.py"
    target.write_bytes(b"def f():\n    return 1\n")
    editor = make_editor(tmp_path)
    with pytest.raises(StaleContextError, match="STALE_CONTEXT") as exc_info:
        AstEditor(editor).rename_symbol(
            "calc.py", "f", "g", expected_digest=sha256_digest(b"stale\n")
        )
    assert isinstance(exc_info.value, EditError)
    assert target.read_bytes() == b"def f():\n    return 1\n"
    assert not (tmp_path / ".specraft" / "backup").exists()
    refused = [entry for entry in editor.audit if "STALE_CONTEXT" in entry.detail]
    assert refused


def test_rename_symbol_parse_failure_raises_ast_parse_error(tmp_path: Path) -> None:
    target = tmp_path / "calc.py"
    target.write_text("def broken(:\n", encoding="utf-8")
    editor = make_editor(tmp_path)
    with pytest.raises(AstParseError, match="语法错误"):
        AstEditor(editor).rename_symbol("calc.py", "broken", "fixed")
    assert target.read_text(encoding="utf-8") == "def broken(:\n"
    refusals = [entry for entry in editor.audit if "拒绝" in entry.detail]
    assert refusals


def test_rename_symbol_backs_up_and_audits_digests(tmp_path: Path) -> None:
    raw_source = b"def f():\n    return f()\n"
    target = tmp_path / "calc.py"
    target.write_bytes(raw_source)
    editor = make_editor(tmp_path)
    AstEditor(editor).rename_symbol("calc.py", "f", "g")
    backups = list((tmp_path / ".specraft" / "backup").iterdir())
    assert len(backups) == 1
    assert backups[0].read_bytes() == raw_source
    entries = [entry for entry in editor.audit if entry.action == "ast_edit"]
    assert len(entries) == 1
    assert entries[0].before_digest == sha256_digest(raw_source)
    assert entries[0].after_digest == sha256_digest(target.read_bytes())


def test_rename_symbol_rejects_non_identifiers(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    ast_editor = make_ast(tmp_path)
    with pytest.raises(AstEditError, match="标识符"):
        ast_editor.rename_symbol("calc.py", "f", "1bad")
    with pytest.raises(AstEditError, match="标识符"):
        ast_editor.rename_symbol("calc.py", "f", "class")
    with pytest.raises(AstEditError, match="相同"):
        ast_editor.rename_symbol("calc.py", "f", "f")


# -- insert_import -----------------------------------------------------------------


def test_insert_import_after_existing_imports(tmp_path: Path) -> None:
    source = '"""module docstring."""\nimport os\n\n\ndef main():\n    return os.getcwd()\n'
    (tmp_path / "calc.py").write_text(source, encoding="utf-8")
    diff = make_ast(tmp_path).insert_import("calc.py", "os.path", ["join"])
    result = (tmp_path / "calc.py").read_text(encoding="utf-8")
    assert "from os.path import join" in result
    assert result.index("import os") < result.index("from os.path import join")
    assert result.index("from os.path import join") < result.index("def main")
    assert result.startswith('"""module docstring."""')
    compile(result, "calc.py", "exec")
    hunk = next(h for h in diff["hunks"] if h["kind"] == "insert_import")
    assert hunk["symbols"] == ["os.path.join"]


def test_insert_import_after_docstring_when_no_imports(tmp_path: Path) -> None:
    source = '"""doc."""\n\n\ndef f():\n    return 1\n'
    (tmp_path / "calc.py").write_text(source, encoding="utf-8")
    make_ast(tmp_path).insert_import("calc.py", "math", ["sqrt"])
    result = (tmp_path / "calc.py").read_text(encoding="utf-8")
    assert result.startswith('"""doc."""')
    assert result.index("from math import sqrt") < result.index("def f")


def test_insert_import_duplicate_refuses_without_writing(tmp_path: Path) -> None:
    source = "from os.path import join\nx = join\n"
    target = tmp_path / "calc.py"
    target.write_text(source, encoding="utf-8")
    editor = make_editor(tmp_path)
    with pytest.raises(AstEditError, match="已导入"):
        AstEditor(editor).insert_import("calc.py", "os.path", ["join"])
    assert target.read_text(encoding="utf-8") == source


def test_insert_import_rejects_bad_module_or_names(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text("x = 1\n", encoding="utf-8")
    ast_editor = make_ast(tmp_path)
    with pytest.raises(AstEditError, match="模块路径非法"):
        ast_editor.insert_import("calc.py", "not a module", ["x"])
    with pytest.raises(AstEditError, match="标识符"):
        ast_editor.insert_import("calc.py", "os", ["1bad"])
    with pytest.raises(AstEditError, match="names 不能为空"):
        ast_editor.insert_import("calc.py", "os", [])


# -- insert_method -----------------------------------------------------------------


def test_insert_method_compiles_and_appends_with_indentation(tmp_path: Path) -> None:
    source = "class Calculator:\n    def add(self, a, b):\n        return a + b\n"
    (tmp_path / "calc.py").write_text(source, encoding="utf-8")
    method_source = "def multiply(self, a, b):\n    return a * b\n"
    diff = make_ast(tmp_path).insert_method("calc.py", "Calculator", method_source)
    result = (tmp_path / "calc.py").read_text(encoding="utf-8")
    assert "    def multiply(self, a, b):" in result
    assert "        return a * b" in result
    compile(result, "calc.py", "exec")
    hunk = next(h for h in diff["hunks"] if h["kind"] == "insert_method")
    assert hunk["symbols"] == ["Calculator.multiply"]


def test_insert_method_missing_class_refuses(tmp_path: Path) -> None:
    source = "class Other:\n    def a(self):\n        return 1\n"
    target = tmp_path / "calc.py"
    target.write_text(source, encoding="utf-8")
    editor = make_editor(tmp_path)
    with pytest.raises(AstEditError, match="类不存在"):
        AstEditor(editor).insert_method(
            "calc.py", "Calculator", "def b(self):\n    return 2\n"
        )
    assert target.read_text(encoding="utf-8") == source


def test_insert_method_duplicate_name_refuses(tmp_path: Path) -> None:
    source = "class Calculator:\n    def add(self):\n        return 1\n"
    target = tmp_path / "calc.py"
    target.write_text(source, encoding="utf-8")
    editor = make_editor(tmp_path)
    with pytest.raises(AstEditError, match="方法已存在"):
        AstEditor(editor).insert_method(
            "calc.py", "Calculator", "def add(self):\n    return 2\n"
        )
    assert target.read_text(encoding="utf-8") == source


def test_insert_method_source_must_be_single_def(tmp_path: Path) -> None:
    source = "class C:\n    x = 1\n"
    target = tmp_path / "calc.py"
    target.write_text(source, encoding="utf-8")
    ast_editor = make_ast(tmp_path)
    with pytest.raises(AstEditError, match="单个函数定义"):
        ast_editor.insert_method("calc.py", "C", "x = 1\n")
    with pytest.raises(AstParseError, match="语法错误"):
        ast_editor.insert_method("calc.py", "C", "def broken(:\n    return 1\n")
    assert target.read_text(encoding="utf-8") == source


# -- diff schema -------------------------------------------------------------------


def test_ops_return_serializable_structured_diff(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    diff = make_ast(tmp_path).rename_symbol("calc.py", "f", "g")
    payload = json.loads(json.dumps(diff))
    assert set(payload) >= {"path", "mode", "hunks"}
    for hunk in payload["hunks"]:
        assert set(hunk) == {"kind", "before", "after", "symbols"}


# -- registry dispatch --------------------------------------------------------------


def test_registry_ast_edit_dispatches_rename(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text("def f():\n    return f()\n", encoding="utf-8")
    result = call(
        make_registry(tmp_path),
        "ast_edit",
        {"op": "rename_symbol", "path": "calc.py", "names": ["f", "g"]},
    )
    assert result.status == "ok"
    assert "1 hunks" in result.summary
    payload = json.loads(result.output_head)
    assert any(hunk["kind"] == "rename_symbol" for hunk in payload["hunks"])
    assert "def g()" in (tmp_path / "calc.py").read_text(encoding="utf-8")


def test_registry_ast_edit_dispatches_insert_import_and_method(tmp_path: Path) -> None:
    source = "class C:\n    def a(self):\n        return 1\n"
    (tmp_path / "calc.py").write_text(source, encoding="utf-8")
    registry = make_registry(tmp_path)
    imported = call(
        registry,
        "ast_edit",
        {"op": "insert_import", "path": "calc.py", "names": ["math", "sqrt"]},
    )
    assert imported.status == "ok"
    assert "from math import sqrt" in (tmp_path / "calc.py").read_text(encoding="utf-8")
    method = call(
        registry,
        "ast_edit",
        {"op": "insert_method", "path": "calc.py", "names": ["C", "def b(self):\n    return 2\n"]},
    )
    assert method.status == "ok"
    compile((tmp_path / "calc.py").read_text(encoding="utf-8"), "calc.py", "exec")


def test_registry_ast_edit_argument_validation(tmp_path: Path) -> None:
    target = tmp_path / "calc.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    registry = make_registry(tmp_path)
    cases = [
        {"op": "explode", "path": "calc.py", "names": ["f", "g"]},
        {"op": "rename_symbol", "path": "calc.py", "names": ["f"]},
        {"op": "rename_symbol", "path": "calc.py", "names": "fg"},
        {"op": "rename_symbol", "path": "calc.py", "names": ["f", "g"], "bogus": 1},
        {"op": "rename_symbol", "path": "calc.py"},
    ]
    for arguments in cases:
        result = call(registry, "ast_edit", arguments)
        assert result.status == "error", arguments
        assert result.summary.startswith(f"[{CODE_INVALID_ARGUMENTS}]"), arguments
    assert target.read_text(encoding="utf-8") == "def f():\n    return 1\n"


def test_registry_ast_edit_out_of_owned_path_is_denied(tmp_path: Path) -> None:
    registry = make_registry(tmp_path, owned_paths=["src/**"])
    target = tmp_path / "other.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    result = call(
        registry,
        "ast_edit",
        {"op": "rename_symbol", "path": "other.py", "names": ["f", "g"]},
    )
    assert result.status == "denied"
    assert result.summary.startswith(f"[{CODE_PATH_OUT_OF_RANGE}]")
    assert target.read_text(encoding="utf-8") == "def f():\n    return 1\n"


def test_registry_ast_edit_stale_context_maps_to_stable_code(tmp_path: Path) -> None:
    target = tmp_path / "calc.py"
    target.write_text("def f():\n    return 1\n", encoding="utf-8")
    result = call(
        make_registry(tmp_path),
        "ast_edit",
        {
            "op": "rename_symbol",
            "path": "calc.py",
            "names": ["f", "g"],
            "expected_digest": sha256_digest(b"stale\n"),
        },
    )
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_STALE_CONTEXT}]")
    assert target.read_text(encoding="utf-8") == "def f():\n    return 1\n"


def test_registry_ast_edit_parse_failure_maps_to_stable_code(tmp_path: Path) -> None:
    target = tmp_path / "calc.py"
    target.write_text("def broken(:\n", encoding="utf-8")
    result = call(
        make_registry(tmp_path),
        "ast_edit",
        {"op": "rename_symbol", "path": "calc.py", "names": ["broken", "fixed"]},
    )
    assert result.status == "error"
    assert result.summary.startswith(f"[{CODE_AST_PARSE_FAILED}]")
    assert target.read_text(encoding="utf-8") == "def broken(:\n"


def test_registry_ast_edit_spec_risk_and_envelope(tmp_path: Path) -> None:
    registry = make_registry(tmp_path)
    spec = registry.get("ast_edit")
    assert spec is not None
    assert spec.version == 1
    assert spec.risk == "low_write"
    assert {param.name for param in spec.params} == {"op", "path", "names", "expected_digest"}
    required = {param.name for param in spec.params if param.required}
    assert required == {"op", "path", "names"}
    assert "ast_edit" in registry.tool_names()
    assert "ast_edit v1 [low_write" in registry.envelope_block()
