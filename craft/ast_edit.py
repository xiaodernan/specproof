"""AST-level structured edits (商业化计划书 §14.5 / 计划书 task 6 第三项).

ast_edit 是 apply_patch 之外的**新工具版本**: 旧工具 (apply_patch /
create_file) 的替换语义一字未动; 本模块只在 editor 之上叠加 AST 级能力:

- rename_symbol(path, old_name, new_name): 重命名定义 (函数 / 异步函数 /
  类名) 与其全部标识符引用 (Name 节点、参数绑定 ast.arg、from-import
  别名). 变更集由 ast.NodeTransformer 收集, 落盘却是**最小 span 替换**
  — 原始文本的注释、排版与字符串字面量逐字节保留. 属性名 (obj.old)、
  关键字实参 (fn(old=...))、global/nonlocal 声明与 except 别名是歧义引
  用, 有意不参与重命名; 同名标识符 (含局部遮蔽) 一律同改, 不做作用域
  消歧.
- insert_import(path, module, names): 在最后一个现有 import (或模块
  docstring) 之后插入 `from module import names`; 重复导入被拒绝.
- insert_method(path, class_name, method_source): method_source 先经
  ast.parse 校验为单个函数定义, 再按类体缩进追加; 类必须唯一存在且
  不得已有同名方法.

每个操作共用 editor 的护栏, 顺序与 apply_edit 完全一致:
expected_digest stale 检查 (STALE_CONTEXT) -> 校验 (AstParseError ->
AST_PARSE_FAILED, 其余 AstEditError -> EDIT_REJECTED) -> 备份 ->
原子写 -> 审计. 每个操作返回 craft.structured_diff 的结构化 diff schema.
"""

from __future__ import annotations

import ast
import keyword
import textwrap
from pathlib import Path
from typing import Any

from .editor import EditError, Editor
from .structured_diff import compute_structured_diff

AST_EDIT_ACTION = "ast_edit"


class AstEditError(EditError):
    """An AST-structured edit could not be applied (nothing was written)."""


class AstParseError(AstEditError):
    """The source (or a constructed edit) does not parse — AST_PARSE_FAILED."""

    def __init__(self, path: str, message: str, lineno: int | None = None) -> None:
        location = f" line {lineno}" if lineno is not None else ""
        super().__init__(f"ast_edit: {path} 语法错误{location}: {message}; 拒绝写入")
        self.path = path
        self.message = message
        self.lineno = lineno


def _check_identifier(name: str, label: str) -> None:
    if not name or not name.isidentifier() or keyword.iskeyword(name):
        raise AstEditError(f"ast_edit 参数非法: {label} 不是合法标识符 ({name!r})")


def _check_module(module: str) -> None:
    parts = module.split(".")
    if not module or any(not part.isidentifier() or keyword.iskeyword(part) for part in parts):
        raise AstEditError(f"ast_edit 参数非法: 模块路径非法 ({module!r})")


def _line_start_offsets(text: str) -> list[int]:
    offsets = [0]
    for index, char in enumerate(text):
        if char == "\n":
            offsets.append(index + 1)
    return offsets


def _apply_spans(
    text: str,
    line_starts: list[int],
    spans: list[tuple[int, int, int, int]],
    old_name: str,
    new_name: str,
) -> str:
    """Replace minimal identifier spans (bottom-up) on the original text."""
    offsets: list[tuple[int, int]] = []
    for start_line, start_col, end_line, end_col in spans:
        start = line_starts[start_line - 1] + start_col
        end = line_starts[end_line - 1] + end_col
        if end < start or text[start:end] != old_name:
            raise AstEditError(
                f"ast_edit 拒绝: span 内容与符号不匹配 "
                f"(line {start_line}, 期望 {old_name!r}, 实际 {text[start:end]!r}), 未落盘"
            )
        offsets.append((start, end))
    result = text
    for start, end in sorted(offsets, key=lambda pair: pair[0], reverse=True):
        result = result[:start] + new_name + result[end:]
    return result


def _validate_compiles(path: str, text: str) -> None:
    try:
        compile(text, path, "exec")
    except SyntaxError as exc:
        raise AstParseError(path, exc.msg, exc.lineno) from exc


class _RenameCollector(ast.NodeTransformer):
    """Collects the minimal identifier spans for a symbol rename.

    ast.NodeTransformer 是访问机制: 它决定"哪些节点要改"; 写盘只替换这
    些 span, 因此注释、排版与字符串字面量不会被重新打印破坏.
    """

    def __init__(self, old_name: str) -> None:
        self.old_name = old_name
        self.spans: list[tuple[int, int, int, int]] = []

    def _record(self, line: int, col: int, end_line: int | None, end_col: int | None) -> None:
        resolved_end_line = end_line if end_line is not None else line
        resolved_end_col = end_col if end_col is not None else col
        self.spans.append((line, col, resolved_end_line, resolved_end_col))

    def visit_Name(self, node: ast.Name) -> ast.AST | None:
        if node.id == self.old_name:
            self._record(node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST | None:
        if node.name == self.old_name:
            line = node.lineno + len(node.decorator_list)
            col = node.col_offset + 4  # "def "
            self._record(line, col, line, col + len(node.name))
        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> ast.AST | None:
        if node.name == self.old_name:
            line = node.lineno + len(node.decorator_list)
            col = node.col_offset + 10  # "async def "
            self._record(line, col, line, col + len(node.name))
        self.generic_visit(node)
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST | None:
        if node.name == self.old_name:
            line = node.lineno + len(node.decorator_list)
            col = node.col_offset + 6  # "class "
            self._record(line, col, line, col + len(node.name))
        self.generic_visit(node)
        return node

    def visit_arg(self, node: ast.arg) -> ast.AST | None:
        if node.arg == self.old_name:
            self._record(node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)
        return node

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST | None:
        for alias in node.names:
            if alias.asname is None and alias.name == self.old_name:
                self._record(alias.lineno, alias.col_offset, alias.end_lineno, alias.end_col_offset)
        self.generic_visit(node)
        return node


def _already_imported(tree: ast.Module, module: str, names: list[str]) -> bool:
    for stmt in tree.body:
        if not isinstance(stmt, ast.ImportFrom):
            continue
        if stmt.module != module:
            continue
        imported = {alias.asname or alias.name for alias in stmt.names}
        if any(name in imported for name in names):
            return True
    return False


def _import_insert_line(tree: ast.Module) -> int:
    """0-based insertion index: right after the last import (or the docstring)."""
    last_import_line = 0
    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            end = stmt.end_lineno if stmt.end_lineno is not None else stmt.lineno
            last_import_line = max(last_import_line, end)
    if last_import_line:
        return last_import_line
    if tree.body:
        first = tree.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            return first.end_lineno if first.end_lineno is not None else first.lineno
    return 0


def _parse_single_method(
    method_source: str, path: str
) -> ast.FunctionDef | ast.AsyncFunctionDef:
    try:
        parsed = ast.parse(method_source)
    except SyntaxError as exc:
        raise AstParseError(path, f"method_source 语法错误 ({exc.msg})", exc.lineno) from exc
    body = parsed.body
    if len(body) != 1 or not isinstance(body[0], (ast.FunctionDef, ast.AsyncFunctionDef)):
        raise AstEditError("ast_edit 参数非法: method_source 必须是单个函数定义")
    return body[0]


def _class_body_indent(class_node: ast.ClassDef) -> str:
    for stmt in class_node.body:
        return " " * stmt.col_offset
    return " " * (class_node.col_offset + 4)


class AstEditor:
    """AST-structured edits over one Editor (same workspace/backup/audit).

    与 apply_edit 的管线逐项对齐: path 越界由 editor._resolve 拒绝, stale
    由 editor._check_expected_digest 拒绝 (并审计), 成功后 editor 备份 +
    原子写 + 审计. 本模块是 craft 包内组件, 直接复用这些内部 API 即为
    "reuse editor digest API" 的单一事实来源, 不再复制实现.
    """

    def __init__(self, editor: Editor) -> None:
        self._editor = editor

    def _prepare(self, path: str, expected_digest: str | None) -> tuple[Path, str, str]:
        target = self._editor._resolve(path)
        if not target.is_file():
            raise AstEditError(f"文件不存在: {path}")
        before = self._editor._check_expected_digest(
            AST_EDIT_ACTION, path, target, expected_digest
        )
        text = target.read_text(encoding="utf-8")
        return target, text, before

    def _parse_module(self, path: str, text: str, before_digest: str) -> ast.Module:
        try:
            return ast.parse(text)
        except SyntaxError as exc:
            self._editor._audit(
                AST_EDIT_ACTION,
                path,
                f"拒绝: 源文件语法错误 ({exc.msg})",
                before_digest=before_digest,
            )
            raise AstParseError(path, exc.msg, exc.lineno) from exc

    def _refuse(self, path: str, before_digest: str, detail: str) -> None:
        self._editor._audit(AST_EDIT_ACTION, path, f"拒绝: {detail}", before_digest=before_digest)

    def _finish(
        self,
        path: str,
        target: Path,
        original: str,
        before_digest: str,
        new_text: str,
        detail: str,
    ) -> dict[str, Any]:
        try:
            _validate_compiles(path, new_text)
        except AstParseError as exc:
            self._refuse(path, before_digest, f"编辑结果语法错误 ({exc.message})")
            raise
        style = self._editor._detect_newline(target)
        self._editor._backup(target)
        self._editor._atomic_write(target, new_text, style)
        after = self._editor.file_digest(path)
        self._editor._audit(
            AST_EDIT_ACTION, path, detail, before_digest=before_digest, after_digest=after
        )
        return compute_structured_diff(original, new_text, path)

    # -- ops -----------------------------------------------------------------

    def rename_symbol(
        self,
        path: str,
        old_name: str,
        new_name: str,
        *,
        expected_digest: str | None = None,
    ) -> dict[str, Any]:
        """Rename a symbol definition plus its identifier references.

        定义未命中但有引用 (如已导入符号) 时同样重命名; 两者都没有时
        拒绝且不落盘.
        """
        _check_identifier(old_name, "old_name")
        _check_identifier(new_name, "new_name")
        if old_name == new_name:
            raise AstEditError("ast_edit 参数非法: old_name 与 new_name 相同")
        target, text, before = self._prepare(path, expected_digest)
        tree = self._parse_module(path, text, before)
        collector = _RenameCollector(old_name)
        collector.visit(tree)
        if not collector.spans:
            self._refuse(path, before, f"符号未命中 ({old_name})")
            raise AstEditError(f"ast_edit 拒绝: 符号未命中 ({old_name}), 未落盘 ({path})")
        new_text = _apply_spans(
            text, _line_start_offsets(text), collector.spans, old_name, new_name
        )
        return self._finish(
            path,
            target,
            text,
            before,
            new_text,
            f"rename_symbol {old_name}→{new_name}: {len(collector.spans)} 处替换",
        )

    def insert_import(
        self,
        path: str,
        module: str,
        names: list[str],
        *,
        expected_digest: str | None = None,
    ) -> dict[str, Any]:
        """Insert `from module import names` after the last existing import."""
        _check_module(module)
        if not names:
            raise AstEditError("ast_edit 参数非法: names 不能为空")
        for name in names:
            _check_identifier(name, "导入名")
        target, text, before = self._prepare(path, expected_digest)
        tree = self._parse_module(path, text, before)
        if _already_imported(tree, module, names):
            self._refuse(path, before, f"{module} 已导入 {names}")
            raise AstEditError(f"ast_edit 拒绝: {module} 已导入 {names}, 未落盘 ({path})")
        import_stmt = ast.ImportFrom(
            module=module, names=[ast.alias(name=name) for name in names], level=0
        )
        import_text = ast.unparse(import_stmt)
        lines = text.split("\n")
        insert_at = min(_import_insert_line(tree), len(lines))
        new_text = "\n".join(lines[:insert_at] + [import_text] + lines[insert_at:])
        return self._finish(
            path,
            target,
            text,
            before,
            new_text,
            f"insert_import {module}: {', '.join(names)}",
        )

    def insert_method(
        self,
        path: str,
        class_name: str,
        method_source: str,
        *,
        expected_digest: str | None = None,
    ) -> dict[str, Any]:
        """Append a single method (parsed from source) to a uniquely named class."""
        _check_identifier(class_name, "class_name")
        target, text, before = self._prepare(path, expected_digest)
        tree = self._parse_module(path, text, before)
        method_node = _parse_single_method(method_source, path)
        classes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == class_name
        ]
        if not classes:
            self._refuse(path, before, f"类不存在 ({class_name})")
            raise AstEditError(f"ast_edit 拒绝: 类不存在 ({class_name}), 未落盘 ({path})")
        if len(classes) > 1:
            self._refuse(path, before, f"类名不唯一 ({class_name}: {len(classes)} 处)")
            raise AstEditError(
                f"ast_edit 拒绝: 类名不唯一 ({class_name}: {len(classes)} 处), 未落盘 ({path})"
            )
        class_node = classes[0]
        existing = {
            stmt.name
            for stmt in class_node.body
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if method_node.name in existing:
            self._refuse(path, before, f"方法已存在 ({class_name}.{method_node.name})")
            raise AstEditError(
                f"ast_edit 拒绝: 方法已存在 ({class_name}.{method_node.name}), 未落盘 ({path})"
            )
        body_indent = _class_body_indent(class_node)
        method_lines = [
            body_indent + line for line in textwrap.dedent(method_source).splitlines()
        ]
        lines = text.split("\n")
        class_end = (
            class_node.end_lineno if class_node.end_lineno is not None else class_node.lineno
        )
        insert_at = min(class_end, len(lines))
        new_text = "\n".join(lines[:insert_at] + [""] + method_lines + lines[insert_at:])
        return self._finish(
            path,
            target,
            text,
            before,
            new_text,
            f"insert_method {class_name}.{method_node.name}",
        )


__all__ = ["AST_EDIT_ACTION", "AstEditError", "AstEditor", "AstParseError"]
