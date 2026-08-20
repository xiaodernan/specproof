"""Unit tests for devtools.docs and devtools.archreview — offline."""

from pathlib import Path

from devtools.archreview import review
from devtools.docs import generate

MOD = '''
"""A sample package module."""

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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_generate_api_lists_signatures(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "calc.py", MOD)
    content, name = generate(tmp_path, "api")
    assert name == "API.md"
    assert "add(a: int, b: int) -> int" in content
    assert "class Calculator" in content
    assert "multiply" in content


def test_generate_readme_has_stats(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "calc.py", MOD)
    content, name = generate(tmp_path, "readme")
    assert name == "README.generated.md"
    assert "代码统计" in content
    assert "文件数: 1" in content


def test_generate_unsupported_type_raises(tmp_path: Path) -> None:
    try:
        generate(tmp_path, "architecture")
    except ValueError as exc:
        assert "unsupported doc_type" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_review_detects_cycle(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "a.py", "import pkg.b\n")
    _write(tmp_path / "pkg" / "b.py", "import pkg.a\n")
    report = review(tmp_path)
    assert report["module_count"] == 2  # pkg.a, pkg.b (no __init__.py)
    assert len(report["cycles"]) == 1


def test_review_reports_orphan(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "used.py", "x = 1\n")
    _write(tmp_path / "pkg" / "main.py", "import pkg.used\n")
    _write(tmp_path / "pkg" / "orphan.py", "y = 2\n")
    report = review(tmp_path)
    assert "pkg.orphan" in report["orphans"]


def test_review_layer_rules_opt_in(tmp_path: Path) -> None:
    _write(tmp_path / "domain" / "svc.py", "import infra.db\n")
    _write(tmp_path / "infra" / "db.py", "x = 1\n")
    # no rules -> no layering findings
    base = review(tmp_path)
    assert not any(f["subtype"] == "layer_violation" for f in base["findings"])
    # with rules -> violation fires
    ruled = review(
        tmp_path,
        layer_rules={"domain\\..*": "domain", "infra\\..*": "infra"},
        allowed_edges=[],
    )
    assert any(f["subtype"] == "layer_violation" for f in ruled["findings"])
    # allowed edge -> violation disappears
    allowed = review(
        tmp_path,
        layer_rules={"domain\\..*": "domain", "infra\\..*": "infra"},
        allowed_edges=[("domain", "infra")],
    )
    assert not any(
        f["subtype"] == "layer_violation" for f in allowed["findings"]
    )
