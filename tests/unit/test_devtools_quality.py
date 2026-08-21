"""Unit tests for devtools.quality — offline, deterministic."""

from pathlib import Path

from devtools.quality import analyze, collect_python_files

GOOD = '''
"""A clean module."""

import os
from pathlib import Path


def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


class Calculator:
    """A simple calculator."""

    def multiply(self, a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b
'''


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_analyze_good_module_scores_high(tmp_path: Path) -> None:
    _write(tmp_path / "calc.py", GOOD)
    report = analyze(tmp_path)
    assert report["summary"]["file_count"] == 1
    assert report["summary"]["function_count"] == 2
    assert report["summary"]["class_count"] == 1
    assert report["summary"]["avg_score"] >= 9.0


def test_long_function_is_flagged(tmp_path: Path) -> None:
    body = "\n".join(f"    line{i} = {i}" for i in range(60))
    source = "def big():\n" + body + "\n"
    _write(tmp_path / "big.py", source)
    report = analyze(tmp_path)
    subtypes = {i["subtype"] for f in report["files"] for i in f["issues"]}
    assert "long_function" in subtypes
    assert "missing_docstring" in subtypes


def test_too_many_params_flagged(tmp_path: Path) -> None:
    params = ", ".join(f"p{i}" for i in range(8))
    _write(tmp_path / "many.py", f"def f({params}):\n    pass\n")
    report = analyze(tmp_path)
    subtypes = {i["subtype"] for f in report["files"] for i in f["issues"]}
    assert "too_many_params" in subtypes


def test_cyclomatic_complexity_detected(tmp_path: Path) -> None:
    lines = ['"""doc"""', "", "", "def f(x):", '    """doc"""']
    for i in range(1, 12):
        lines.append("    " * i + "if x > " + str(i) + ":")
    lines.append("    " * 12 + "return 1")
    lines.append("    return 0")
    _write(tmp_path / "complex.py", "\n".join(lines) + "\n")
    report = analyze(tmp_path)
    subtypes = {i["subtype"] for f in report["files"] for i in f["issues"]}
    assert "high_cyclomatic_complexity" in subtypes


def test_syntax_error_reported(tmp_path: Path) -> None:
    _write(tmp_path / "broken.py", "def broken(\n")
    report = analyze(tmp_path)
    subtypes = {i["subtype"] for f in report["files"] for i in f["issues"]}
    assert "syntax_error" in subtypes


def test_collect_skips_venv_and_caches(tmp_path: Path) -> None:
    _write(tmp_path / "ok.py", "x = 1\n")
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    _write(venv / "junk.py", "y = 2\n")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    _write(cache / "junk.py", "z = 3\n")
    assert [p.name for p in collect_python_files(tmp_path)] == ["ok.py"]


def test_empty_tree_honest_note(tmp_path: Path) -> None:
    report = analyze(tmp_path)
    assert report["summary"]["file_count"] == 0
    assert "no .py files" in report["summary"]["note"]
