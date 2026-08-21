"""Symbol-level structured diff (计划书 §14.5: ast_edit 的输出 schema).

compute_structured_diff(before_text, after_text, path) is pure: no filesystem
or network access, deterministic on its inputs. It returns a plain,
JSON-serializable schema:

    {
        "path": "<relative path>",
        "mode": "python" | "text",
        "hunks": [
            {"kind": str, "before": str, "after": str, "symbols": [str, ...]},
            ...
        ],
    }

Python paths (*.py / *.pyi) are diffed at symbol level through the ast:
top-level statements are aligned by symbol key, a renamed definition is
recognized as kind="rename_symbol" with symbols=[old_name, new_name],
imports surface as insert_import/delete_import/modify_import, class bodies
are compared at method level (insert_method/delete_method/modify_method),
and everything else is labelled insert_<symbol>/delete_<symbol>/
modify_<symbol> with the affected symbol names in `symbols`.

Non-Python paths — and Python files that fail to parse — fall back to line
level, honestly labelled: mode="text" with kinds delete_lines /
insert_lines / replace_lines and symbols=[].
"""

from __future__ import annotations

import ast
import difflib
import re
from dataclasses import dataclass
from typing import Any, Protocol

PYTHON_SUFFIXES: tuple[str, ...] = (".py", ".pyi")

_RENAMABLE_KINDS = ("function", "async_function", "class")

_DEF_KINDS = ("function", "async_function", "class")


@dataclass(frozen=True)
class _Symbol:
    """One aligned top-level statement: kind, name, key, text, node, lines."""

    kind: str
    name: str
    key: tuple[str, str]
    text: str
    node: ast.stmt
    lines: list[str]


@dataclass
class _Op:
    tag: str
    before: _Symbol | None
    after: _Symbol | None


def compute_structured_diff(before_text: str, after_text: str, path: str) -> dict[str, Any]:
    """Symbol-level diff for Python, line-level (honestly labelled) otherwise."""
    before_text = before_text.replace("\r\n", "\n").replace("\r", "\n")
    after_text = after_text.replace("\r\n", "\n").replace("\r", "\n")
    if not _looks_python(path):
        return _text_diff(path, before_text, after_text)
    try:
        before_tree = ast.parse(before_text)
        after_tree = ast.parse(after_text)
    except SyntaxError:
        return _text_diff(path, before_text, after_text)
    before_lines = before_text.split("\n")
    after_lines = after_text.split("\n")
    before_symbols = [_symbol_for(stmt, before_lines) for stmt in before_tree.body]
    after_symbols = [_symbol_for(stmt, after_lines) for stmt in after_tree.body]
    ops = _pair_renames(_align(before_symbols, after_symbols))
    hunks: list[dict[str, Any]] = []
    for op in ops:
        hunks.extend(_op_hunks(op))
    return {"path": path, "mode": "python", "hunks": hunks}


def _looks_python(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized.endswith(PYTHON_SUFFIXES)


class _Located(Protocol):
    """Minimal position surface shared by every ast node _slice accepts."""

    lineno: int
    end_lineno: int | None


def _slice(node: _Located, lines: list[str]) -> str:
    end = node.end_lineno if node.end_lineno is not None else node.lineno
    return "\n".join(lines[node.lineno - 1 : end])


def _definition_kind(node: ast.stmt) -> str:
    if isinstance(node, ast.FunctionDef):
        return "function"
    if isinstance(node, ast.AsyncFunctionDef):
        return "async_function"
    if isinstance(node, ast.ClassDef):
        return "class"
    raise ValueError(f"意外的节点类型: {type(node).__name__}")


def _import_key(node: ast.Import | ast.ImportFrom) -> str:
    if isinstance(node, ast.ImportFrom):
        aliases = ",".join(_alias_text(alias) for alias in node.names)
        return f"{node.module or ''}:{aliases}"
    return ",".join(_alias_text(alias) for alias in node.names)


def _alias_text(alias: ast.alias) -> str:
    if alias.asname is not None:
        return f"{alias.name} as {alias.asname}"
    return alias.name


def _collect_target_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for item in target.elts:
            names.extend(_collect_target_names(item))
        return names
    return []


def _target_names(targets: list[ast.expr]) -> list[str]:
    names: list[str] = []
    for target in targets:
        names.extend(_collect_target_names(target))
    return names


def _symbol_for(stmt: ast.stmt, lines: list[str]) -> _Symbol:
    text = _slice(stmt, lines)
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        kind = _definition_kind(stmt)
        return _Symbol(kind, stmt.name, (kind, stmt.name), text, stmt, lines)
    if isinstance(stmt, (ast.Import, ast.ImportFrom)):
        name = _import_key(stmt)
        return _Symbol("import", name, ("import", name), text, stmt, lines)
    if isinstance(stmt, ast.Assign):
        names = _target_names(stmt.targets)
        name = ",".join(names)
        return _Symbol("assignment", name, ("assignment", name), text, stmt, lines)
    if isinstance(stmt, ast.AnnAssign):
        names = _target_names([stmt.target])
        name = ",".join(names)
        return _Symbol("assignment", name, ("assignment", name), text, stmt, lines)
    if isinstance(stmt, ast.AugAssign):
        names = _target_names([stmt.target])
        name = ",".join(names)
        return _Symbol("assignment", name, ("assignment", name), text, stmt, lines)
    return _Symbol("statement", text, ("statement", text), text, stmt, lines)


def _import_names(node: ast.stmt) -> list[str]:
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        return [
            f"{module}.{alias.asname or alias.name}" if module else (alias.asname or alias.name)
            for alias in node.names
        ]
    if isinstance(node, ast.Import):
        return [alias.asname or alias.name for alias in node.names]
    return []


def _symbol_names(record: _Symbol) -> list[str]:
    if record.kind in _DEF_KINDS:
        return [record.name]
    if record.kind == "import":
        return _import_names(record.node)
    if record.kind == "assignment":
        return [name for name in record.name.split(",") if name]
    return []


def _find_key(records: list[_Symbol], start: int, key: tuple[str, str]) -> int | None:
    for index in range(start, len(records)):
        if records[index].key == key:
            return index
    return None


def _align(before: list[_Symbol], after: list[_Symbol]) -> list[_Op]:
    ops: list[_Op] = []
    cursor = 0
    for after_symbol in after:
        match_index = _find_key(before, cursor, after_symbol.key)
        if match_index is None:
            ops.append(_Op("insert", None, after_symbol))
            continue
        for skipped in before[cursor:match_index]:
            ops.append(_Op("delete", skipped, None))
        ops.append(_Op("pair", before[match_index], after_symbol))
        cursor = match_index + 1
    for rest in before[cursor:]:
        ops.append(_Op("delete", rest, None))
    return ops


def _pair_renames(ops: list[_Op]) -> list[_Op]:
    """Turn a delete + an insert of the same def kind into one rename_symbol.

    A delete and an insert pair as a rename when the inserted text equals
    the deleted text with the old name replaced by the new name (definition
    line and in-body references all move together).
    """
    used: set[int] = set()
    for index, op in enumerate(ops):
        if op.tag != "delete" or op.before is None:
            continue
        if op.before.kind not in _RENAMABLE_KINDS:
            continue
        old_name = op.before.name
        for candidate_index, candidate in enumerate(ops):
            if candidate_index == index or candidate_index in used:
                continue
            if candidate.tag != "insert" or candidate.after is None:
                continue
            if candidate.after.kind != op.before.kind:
                continue
            new_name = candidate.after.name
            if old_name == new_name:
                continue
            if _replace_word(op.before.text, old_name, new_name) != candidate.after.text:
                continue
            ops[index] = _Op("rename", op.before, candidate.after)
            used.add(candidate_index)
            break
    return [op for index, op in enumerate(ops) if index not in used]


def _replace_word(text: str, old: str, new: str) -> str:
    """Replace a whole identifier (word-boundary aware — 'def f()' keeps 'def')."""
    return re.sub(rf"\b{re.escape(old)}\b", new, text)


def _op_hunks(op: _Op) -> list[dict[str, Any]]:
    if op.tag == "rename":
        assert op.before is not None and op.after is not None
        return [
            {
                "kind": "rename_symbol",
                "before": op.before.text,
                "after": op.after.text,
                "symbols": [op.before.name, op.after.name],
            }
        ]
    if op.tag == "delete":
        assert op.before is not None
        return [
            {
                "kind": f"delete_{op.before.kind}",
                "before": op.before.text,
                "after": "",
                "symbols": _symbol_names(op.before),
            }
        ]
    if op.tag == "insert":
        assert op.after is not None
        return [
            {
                "kind": f"insert_{op.after.kind}",
                "before": "",
                "after": op.after.text,
                "symbols": _symbol_names(op.after),
            }
        ]
    assert op.before is not None and op.after is not None
    if op.before.text == op.after.text:
        return []
    if op.before.kind == "class":
        return _class_method_hunks(op.before, op.after)
    return [
        {
            "kind": f"modify_{op.before.kind}",
            "before": op.before.text,
            "after": op.after.text,
            "symbols": _symbol_names(op.before),
        }
    ]


def _is_method(stmt: ast.stmt) -> bool:
    return isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))


def _class_method_hunks(before: _Symbol, after: _Symbol) -> list[dict[str, Any]]:
    """Class pair: method-level hunks when only methods changed, otherwise one
    honest modify_class hunk (class attributes and docstrings stay whole)."""
    before_node = before.node
    after_node = after.node
    assert isinstance(before_node, ast.ClassDef) and isinstance(after_node, ast.ClassDef)
    before_others = [
        _slice(stmt, before.lines) for stmt in before_node.body if not _is_method(stmt)
    ]
    after_others = [
        _slice(stmt, after.lines) for stmt in after_node.body if not _is_method(stmt)
    ]
    if before_others != after_others:
        return [
            {
                "kind": "modify_class",
                "before": before.text,
                "after": after.text,
                "symbols": [before.name],
            }
        ]
    before_methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    after_methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
    for stmt in before_node.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            before_methods[stmt.name] = stmt
    for stmt in after_node.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            after_methods[stmt.name] = stmt
    hunks: list[dict[str, Any]] = []
    prefix = before.name
    for name, method in after_methods.items():
        old = before_methods.get(name)
        new_text = _slice(method, after.lines)
        old_text = _slice(old, before.lines) if old is not None else ""
        if old is None:
            hunks.append(
                {
                    "kind": "insert_method",
                    "before": "",
                    "after": new_text,
                    "symbols": [f"{prefix}.{name}"],
                }
            )
        elif old_text != new_text:
            hunks.append(
                {
                    "kind": "modify_method",
                    "before": old_text,
                    "after": new_text,
                    "symbols": [f"{prefix}.{name}"],
                }
            )
    for name, method in before_methods.items():
        if name not in after_methods:
            hunks.append(
                {
                    "kind": "delete_method",
                    "before": _slice(method, before.lines),
                    "after": "",
                    "symbols": [f"{prefix}.{name}"],
                }
            )
    return hunks


def _text_diff(path: str, before_text: str, after_text: str) -> dict[str, Any]:
    before_lines = before_text.split("\n")
    after_lines = after_text.split("\n")
    hunks: list[dict[str, Any]] = []
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        kind = {"delete": "delete_lines", "insert": "insert_lines", "replace": "replace_lines"}[tag]
        hunks.append(
            {
                "kind": kind,
                "before": "\n".join(before_lines[i1:i2]),
                "after": "\n".join(after_lines[j1:j2]),
                "symbols": [],
            }
        )
    return {"path": path, "mode": "text", "hunks": hunks}


__all__ = ["PYTHON_SUFFIXES", "compute_structured_diff"]
