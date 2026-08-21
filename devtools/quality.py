"""devtools.quality — deterministic Python code-quality analysis (DevMind port).

Port of the DevMind code-analysis capability into SpecProof form:
AST structure extraction, McCabe cyclomatic complexity, code smells and a
1-10 quality score. Deterministic and offline by construction — no LLM, no
network, no side effects.

Honesty contract (matches the repo's adapter discipline):
- Python only, via the stdlib ast module. Other languages are reported as
  not_supported (fail-closed), never guessed at.
- Every finding carries file/line/function coordinates; the score is derived
  only from those findings with fixed severity weights.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_EXCLUDE_PARTS = (
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "node_modules",
    ".tox",
)

_SEVERITY_WEIGHTS = {"critical": 2.0, "high": 1.0, "medium": 0.5, "low": 0.2}


@dataclass
class FunctionMetric:
    name: str
    line: int
    line_count: int
    param_count: int
    has_docstring: bool
    cyclomatic_complexity: int


@dataclass
class ClassMetric:
    name: str
    line: int
    line_count: int
    method_count: int


@dataclass
class FileMetrics:
    rel: str
    total_lines: int = 0
    code_lines: int = 0
    blank_lines: int = 0
    comment_lines: int = 0
    functions: list[FunctionMetric] = field(default_factory=list)
    classes: list[ClassMetric] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    score: float = 10.0


def _excluded(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    return any(part in _EXCLUDE_PARTS for part in parts)


def collect_python_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix == ".py" else []
    return sorted(
        p for p in root.rglob("*.py") if not _excluded(p.relative_to(root).as_posix())
    )


def _cyclomatic_complexity(node: ast.AST) -> int:
    """McCabe complexity: 1 + branch points (if/for/while/except/boolop/ifexp/comprehension)."""
    count = 1
    for sub in ast.walk(node):
        if isinstance(sub, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)):
            count += 1
        elif isinstance(sub, ast.BoolOp):
            count += len(sub.values) - 1
        elif isinstance(sub, ast.IfExp):
            count += 1
        elif isinstance(sub, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            count += sum(len(g.ifs) for g in sub.generators)
    return count


def _line_count(node: ast.AST) -> int:
    start = int(getattr(node, "lineno", 0) or 0)
    end = int(getattr(node, "end_lineno", 0) or start)
    return end - start + 1


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _analyze_file(path: Path, rel: str) -> FileMetrics:
    metrics = FileMetrics(rel=rel)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        metrics.issues.append({
            "type": "read_error", "subtype": "unreadable_file",
            "severity": "low", "file": rel, "message": f"cannot read: {exc}",
        })
        return metrics
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        metrics.issues.append({
            "type": "syntax", "subtype": "syntax_error",
            "severity": "high", "file": rel,
            "line": exc.lineno or 0, "message": f"syntax error: {exc.msg}",
        })
        return metrics

    lines = text.splitlines()
    metrics.total_lines = len(lines)
    for line in lines:
        stripped = line.strip()
        if not stripped:
            metrics.blank_lines += 1
        elif stripped.startswith("#"):
            metrics.comment_lines += 1
        else:
            metrics.code_lines += 1

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)) and isinstance(
            getattr(node, "lineno", 0), int
        ):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            else:
                module = node.module or ""
                names = [module + "." + a.name for a in node.names] if module else [
                    a.name for a in node.names
                ]
            for name in names:
                if name not in metrics.imports:
                    metrics.imports.append(name)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = FunctionMetric(
                name=node.name,
                line=node.lineno,
                line_count=_line_count(node),
                param_count=len(node.args.args),
                has_docstring=(
                    ast.get_docstring(node) is not None
                ),
                cyclomatic_complexity=_cyclomatic_complexity(node),
            )
            metrics.functions.append(func)
        elif isinstance(node, ast.ClassDef):
            methods = [
                n for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            cls = ClassMetric(
                name=node.name,
                line=node.lineno,
                line_count=_line_count(node),
                method_count=len(methods),
            )
            metrics.classes.append(cls)
            for method in methods:
                func = FunctionMetric(
                    name=method.name,
                    line=method.lineno,
                    line_count=_line_count(method),
                    param_count=len(method.args.args),
                    has_docstring=ast.get_docstring(method) is not None,
                    cyclomatic_complexity=_cyclomatic_complexity(method),
                )
                metrics.functions.append(func)

    _detect_smells(metrics, text)
    metrics.score = _score(metrics)
    return metrics


def _detect_smells(metrics: FileMetrics, text: str) -> None:
    for func in metrics.functions:
        if func.line_count > 50:
            metrics.issues.append({
                "type": "code_smell", "subtype": "long_function",
                "severity": "medium", "file": metrics.rel, "line": func.line,
                "message": (
                    f"function '{func.name}' is too long "
                    f"({func.line_count} lines)"
                ),
                "suggestion": "split into smaller single-purpose functions",
            })
        if func.param_count > 5:
            metrics.issues.append({
                "type": "code_smell", "subtype": "too_many_params",
                "severity": "low", "file": metrics.rel, "line": func.line,
                "message": (
                    f"function '{func.name}' has too many parameters "
                    f"({func.param_count})"
                ),
                "suggestion": "use a parameter object or config class",
            })
        if not func.has_docstring and _is_public(func.name):
            metrics.issues.append({
                "type": "style", "subtype": "missing_docstring",
                "severity": "low", "file": metrics.rel, "line": func.line,
                "message": f"function '{func.name}' lacks a docstring",
                "suggestion": "document purpose, params and return value",
            })
        if func.cyclomatic_complexity > 10:
            metrics.issues.append({
                "type": "complexity", "subtype": "high_cyclomatic_complexity",
                "severity": "medium", "file": metrics.rel, "line": func.line,
                "message": (
                    f"function '{func.name}' has cyclomatic complexity "
                    f"{func.cyclomatic_complexity}"
                ),
                "suggestion": "simplify control flow, reduce branching",
            })
    for i, line in enumerate(text.splitlines(), 1):
        if len(line) > 120:
            metrics.issues.append({
                "type": "style", "subtype": "long_line",
                "severity": "low", "file": metrics.rel, "line": i,
                "message": f"line too long ({len(line)} chars)",
                "suggestion": "split the long line",
            })


def _score(metrics: FileMetrics) -> float:
    score = 10.0
    for issue in metrics.issues:
        score -= _SEVERITY_WEIGHTS.get(issue.get("severity", "low"), 0.2)
    return max(1.0, min(10.0, round(score, 1)))


def analyze(root: Path) -> dict[str, Any]:
    """Analyze a Python file or directory; returns the JSON report schema."""
    files = collect_python_files(root)
    if not files:
        return {
            "root": str(root),
            "supported": "python",
            "files": [],
            "summary": {
                "file_count": 0, "total_lines": 0, "function_count": 0,
                "class_count": 0, "issue_count": 0, "avg_score": 0.0,
                "note": "no .py files found under the given path",
            },
        }
    metrics = []
    for path in files:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.name
        metrics.append(_analyze_file(path, rel))
    issue_count = sum(len(m.issues) for m in metrics)
    total_lines = sum(m.total_lines for m in metrics)
    function_count = sum(len(m.functions) for m in metrics)
    class_count = sum(len(m.classes) for m in metrics)
    avg = (
        round(sum(m.score for m in metrics) / len(metrics), 1)
        if metrics else 0.0
    )
    return {
        "root": str(root),
        "supported": "python",
        "files": [
            {
                "file": m.rel, "total_lines": m.total_lines,
                "code_lines": m.code_lines, "blank_lines": m.blank_lines,
                "comment_lines": m.comment_lines,
                "function_count": len(m.functions),
                "class_count": len(m.classes),
                "score": m.score,
                "issues": m.issues,
            }
            for m in metrics
        ],
        "summary": {
            "file_count": len(metrics), "total_lines": total_lines,
            "function_count": function_count, "class_count": class_count,
            "issue_count": issue_count, "avg_score": avg,
        },
    }
