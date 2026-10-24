"""Tests for Mutation engine (Phase 4)."""

import tempfile
from pathlib import Path

import pytest

from craft.mutation import (
    OPERATORS_BY_LANGUAGE,
    Mutant,
    MutationEngine,
    MutationOperator,
    MutationReport,
    MutationStatus,
)


def test_operators_by_language_defined() -> None:
    """All supported languages have operator lists."""
    assert "java" in OPERATORS_BY_LANGUAGE
    assert "python" in OPERATORS_BY_LANGUAGE
    assert "go" in OPERATORS_BY_LANGUAGE
    assert "javascript" in OPERATORS_BY_LANGUAGE
    assert "typescript" in OPERATORS_BY_LANGUAGE
    # All operators should be present for Java
    assert len(OPERATORS_BY_LANGUAGE["java"]) == len(MutationOperator)


def test_mutation_engine_init() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = MutationEngine(
            project_root=Path(tmpdir),
            language="python",
            test_command=["python", "-m", "pytest"],
            max_mutants=10,
        )
        assert engine.language == "python"
        assert engine.max_mutants == 10
        assert MutationOperator.CONDITIONAL_NEGATION in engine.operators


def test_mutation_report_score() -> None:
    report = MutationReport(project_root=Path("/tmp"), language="python")
    report.killed = 8
    report.survived = 2
    assert report.mutation_score == 80.0

    report2 = MutationReport(project_root=Path("/tmp"), language="python")
    report2.killed = 5
    report2.survived = 5
    report2.equivalent = 2
    assert report2.mutation_score == 50.0
    # mutation_score_with_equivalent = 5 / (5+5+2) * 100 = 41.666... rounded to 41.67
    assert report2.mutation_score_with_equivalent == 41.67


def test_mutation_report_to_dict() -> None:
    report = MutationReport(project_root=Path("/tmp"), language="python")
    report.total_mutants = 10
    report.killed = 8
    report.survived = 2
    d = report.to_dict()
    assert d["mutation_score"] == 80.0
    assert d["language"] == "python"


def test_mutant_creation() -> None:
    mutant = Mutant(
        id="M0001",
        operator=MutationOperator.CONDITIONAL_NEGATION,
        file_path=Path("src/main.py"),
        original_line="if a > b:",
        mutated_line="if a <= b:",
        line_number=10,
        original_code="if a > b:\n    pass",
        mutated_code="if a <= b:\n    pass",
    )
    assert mutant.id == "M0001"
    assert mutant.operator == MutationOperator.CONDITIONAL_NEGATION
    assert mutant.status == MutationStatus.ERROR  # default


def test_python_conditional_negation() -> None:
    """Test conditional negation mutation for Python."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        source = tmp_path / "example.py"
        source.write_text(
            "def foo(a, b):\n    if a > b:\n        return a\n    return b\n",
            encoding="utf-8",
        )

        engine = MutationEngine(
            project_root=tmp_path,
            language="python",
            test_command=["python", "-m", "pytest"],
            max_mutants=10,
        )
        mutants = engine.generate_mutants([source])
        # Should find at least one conditional negation mutant
        assert len(mutants) >= 1
        cond_mutants = [m for m in mutants if m.operator == MutationOperator.CONDITIONAL_NEGATION]
        assert len(cond_mutants) >= 1
        assert "a > b" in cond_mutants[0].original_line
        assert "a <= b" in cond_mutants[0].mutated_line


def test_python_arithmetic_replacement() -> None:
    """Test arithmetic replacement mutation for Python."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        source = tmp_path / "math.py"
        source.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

        engine = MutationEngine(
            project_root=tmp_path,
            language="python",
            test_command=["python", "-m", "pytest"],
            max_mutants=10,
        )
        mutants = engine.generate_mutants([source])
        arith_mutants = [
            m for m in mutants
            if m.operator == MutationOperator.ARITHMETIC_REPLACEMENT
        ]
        assert len(arith_mutants) >= 1
        assert "+" in arith_mutants[0].original_line
        assert "-" in arith_mutants[0].mutated_line


def test_python_constant_replacement() -> None:
    """Test constant replacement mutation for Python."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        source = tmp_path / "consts.py"
        source.write_text('def check():\n    return True\n', encoding="utf-8")

        engine = MutationEngine(
            project_root=tmp_path,
            language="python",
            test_command=["python", "-m", "pytest"],
            max_mutants=10,
        )
        mutants = engine.generate_mutants([source])
        const_mutants = [m for m in mutants if m.operator == MutationOperator.CONSTANT_REPLACEMENT]
        assert len(const_mutants) >= 1
        assert "True" in const_mutants[0].original_line
        assert "False" in const_mutants[0].mutated_line


def test_java_generic_mutation() -> None:
    """Test generic regex-based mutation for Java."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        source = tmp_path / "Example.java"
        java_code = (
            "public class Example {\n"
            "    public int max(int a, int b) {\n"
            "        if (a > b) return a;\n"
            "        return b;\n"
            "    }\n}"
        )
        source.write_text(java_code, encoding="utf-8")

        engine = MutationEngine(
            project_root=tmp_path,
            language="java",
            test_command=["./gradlew", "test"],
            max_mutants=10,
        )
        mutants = engine.generate_mutants([source])
        # Should find conditional negation via regex
        cond_mutants = [m for m in mutants if m.operator == MutationOperator.CONDITIONAL_NEGATION]
        assert len(cond_mutants) >= 1


def test_max_mutants_limit() -> None:
    """Test that max_mutants limit is respected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        # Create a file with many mutation opportunities
        lines = [
            f"def func{i}(a, b):\n    if a > b:\n        return a\n    return b\n"
            for i in range(20)
        ]
        source = tmp_path / "many.py"
        source.write_text("\n".join(lines), encoding="utf-8")

        engine = MutationEngine(
            project_root=tmp_path,
            language="python",
            test_command=["python", "-m", "pytest"],
            max_mutants=5,
        )
        mutants = engine.generate_mutants([source])
        assert len(mutants) <= 5


def test_test_file_exclusion() -> None:
    """Test that test files are excluded from mutation in run_mutation_testing."""
    # This tests the filtering logic in run_mutation_testing, not generate_mutants
    from pathlib import Path

    from craft.mutation import _is_test_file

    assert _is_test_file(Path("test_main.py"), "python") is True
    assert _is_test_file(Path("main_test.py"), "python") is True
    assert _is_test_file(Path("conftest.py"), "python") is True
    assert _is_test_file(Path("main.py"), "python") is False

    assert _is_test_file(Path("ExampleTest.java"), "java") is True
    assert _is_test_file(Path("Example.java"), "java") is False

    assert _is_test_file(Path("foo_test.go"), "go") is True
    assert _is_test_file(Path("foo.go"), "go") is False

    assert _is_test_file(Path("foo.test.js"), "javascript") is True
    assert _is_test_file(Path("foo.spec.ts"), "typescript") is True
    assert _is_test_file(Path("foo.js"), "javascript") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
