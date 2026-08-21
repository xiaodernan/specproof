"""devtools.docs — deterministic documentation generation (DevMind port).

Generates Markdown docs from Python source via stdlib ast:
- "api": one section per module — functions/classes with signatures,
  annotation names and docstring summaries;
- "readme": project overview (name/version from pyproject.toml when present),
  two-level structure tree, code stats and an install section.

Deterministic and offline. Unannotated parameters are rendered as
"(未标注)" — annotations are never invented.
"""

from __future__ import annotations

import ast
from pathlib import Path

from devtools.quality import analyze, collect_python_files

_API_FILENAME = "API.md"
_README_FILENAME = "README.generated.md"


def _annotation_name(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except (ValueError, RecursionError):
        return None


def _signature(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    args: list[str] = []
    for arg in func.args.args:
        ann = _annotation_name(arg.annotation)
        args.append(f"{arg.arg}: {ann}" if ann else f"{arg.arg} (未标注)")
    if func.args.vararg:
        args.append("*" + func.args.vararg.arg)
    for arg in func.args.kwonlyargs:
        ann = _annotation_name(arg.annotation)
        args.append(f"{arg.arg}: {ann}" if ann else f"{arg.arg} (未标注)")
    if func.args.kwarg:
        args.append("**" + func.args.kwarg.arg)
    returns = _annotation_name(func.returns)
    tail = f" -> {returns}" if returns else ""
    return f"({", ".join(args)}){tail}"


def _module_doc(module: str, tree: ast.Module) -> str:
    lines = ["### 模块 `" + module + "`", ""]
    doc = ast.get_docstring(tree)
    if doc:
        lines.append(doc.splitlines()[0])
        lines.append("")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not (
            node.name.startswith("_")
        ):
            lines.append("#### `" + node.name + _signature(node) + "`")
            fdoc = ast.get_docstring(node)
            if fdoc:
                lines.append("")
                lines.append(fdoc.splitlines()[0])
            lines.append("")
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            lines.append("#### `class " + node.name + "`")
            cdoc = ast.get_docstring(node)
            if cdoc:
                lines.append("")
                lines.append(cdoc.splitlines()[0])
            methods = [
                n for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not n.name.startswith("_")
            ]
            if methods:
                lines.append("")
                lines.append("**方法:**")
                lines.append("")
                for method in methods:
                    lines.append("- `" + method.name + _signature(method) + "`")
            lines.append("")
    return "\n".join(lines)


def generate_api(root: Path) -> str:
    parts = ["# API 参考文档", ""]
    files = collect_python_files(root)
    for path in files:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.name
        module = rel[:-3].replace("/", ".")
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        parts.append(_module_doc(module, tree))
    if len(parts) == 1:
        parts.append("(未找到可解析的 Python 源文件)")
    return "\n".join(parts)


def _project_meta(root: Path) -> dict[str, str]:
    meta: dict[str, str] = {}
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if "[project]" in text:
            for key in ("name", "version"):
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith(key + " =") and "=" in stripped:
                        value = stripped.split("=", 1)[1].strip().strip("\"")
                        meta[key] = value
                        break
    return meta


def _structure_tree(root: Path) -> str:
    lines: list[str] = []
    entries = sorted(
        [p for p in root.iterdir() if not p.name.startswith(".")],
        key=lambda p: (p.is_file(), p.name),
    )
    for entry in entries:
        if entry.is_dir():
            children = sorted(entry.iterdir(), key=lambda p: p.name)
            lines.append("- " + entry.name + "/")
            for child in children[:8]:
                marker = "/" if child.is_dir() else ""
                lines.append("  - " + child.name + marker)
            if len(children) > 8:
                lines.append("  - … (" + str(len(children) - 8) + " more)")
        else:
            lines.append("- " + entry.name)
    return "\n".join(lines)


def generate_readme(root: Path) -> str:
    meta = _project_meta(root)
    name = meta.get("name") or root.name
    version = meta.get("version", "0.1.0")
    report = analyze(root)
    summary = report["summary"]
    lines = [
        "# " + name,
        "",
        "> 版本 " + version + " · 由 `specproof devtools docs` 确定性生成, "
        "不含任何模型推断内容。",
        "",
        "## 项目结构",
        "",
        "```text",
        _structure_tree(root),
        "```",
        "",
        "## 代码统计 (Python)",
        "",
        "- 文件数: " + str(summary["file_count"]),
        "- 代码行: " + str(summary["total_lines"]),
        "- 函数数: " + str(summary["function_count"]),
        "- 类数量: " + str(summary["class_count"]),
        "- 平均质量分: " + str(summary["avg_score"]) + "/10",
        "",
        "## 安装",
        "",
        "```bash",
        "pip install -e .",
        "```",
        "",
        "## 使用",
        "",
        "(在此补充项目用法 — 生成器不编造用法说明。)",
        "",
    ]
    return "\n".join(lines)


def generate(root: Path, doc_type: str) -> tuple[str, str]:
    """Returns (markdown_content, file_name) for the requested doc type."""
    if doc_type == "api":
        return generate_api(root), _API_FILENAME
    if doc_type == "readme":
        return generate_readme(root), _README_FILENAME
    raise ValueError(f"unsupported doc_type: {doc_type}")
