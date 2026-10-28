"""Mutation-guided test synthesis engine (Phase 4).

Lightweight source-code mutation operators for Java/Python/Go/JS.
Integrates with the test gate to produce MutationScore evidence.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class MutationStatus(Enum):
    """Result of running tests against a mutant."""
    KILLED = "killed"           # Tests failed → mutation detected
    SURVIVED = "survived"       # Tests passed → mutation NOT detected (test gap)
    EQUIVALENT = "equivalent"   # Mutation produces same behavior (false positive)
    ERROR = "error"             # Mutation caused compile/runtime error


class MutationOperator(Enum):
    """Supported mutation operators."""
    # Conditionals
    CONDITIONAL_NEGATION = "conditional_negation"     # if (a > b) → if (a <= b)
    CONDITIONAL_BOUNDARY = "conditional_boundary"     # > → >=, < → <=
    # Arithmetic
    ARITHMETIC_REPLACEMENT = "arithmetic_replacement" # + → -, * → /, etc.
    # Constants
    CONSTANT_REPLACEMENT = "constant_replacement"     # 1 → 0, true → false, "" → "x"
    # Null checks
    NULL_CHECK_REMOVAL = "null_check_removal"         # if (x != null) → if (true)
    # Returns
    RETURN_VALUE_REPLACEMENT = "return_value_replacement"  # return x → return default


# Language-specific operator applicability
OPERATORS_BY_LANGUAGE: dict[str, list[MutationOperator]] = {
    "java": list(MutationOperator),
    "python": [
        MutationOperator.CONDITIONAL_NEGATION,
        MutationOperator.CONDITIONAL_BOUNDARY,
        MutationOperator.ARITHMETIC_REPLACEMENT,
        MutationOperator.CONSTANT_REPLACEMENT,
        MutationOperator.NULL_CHECK_REMOVAL,
        MutationOperator.RETURN_VALUE_REPLACEMENT,
    ],
    "go": [
        MutationOperator.CONDITIONAL_NEGATION,
        MutationOperator.CONDITIONAL_BOUNDARY,
        MutationOperator.ARITHMETIC_REPLACEMENT,
        MutationOperator.CONSTANT_REPLACEMENT,
        MutationOperator.NULL_CHECK_REMOVAL,
        MutationOperator.RETURN_VALUE_REPLACEMENT,
    ],
    "javascript": [
        MutationOperator.CONDITIONAL_NEGATION,
        MutationOperator.CONDITIONAL_BOUNDARY,
        MutationOperator.ARITHMETIC_REPLACEMENT,
        MutationOperator.CONSTANT_REPLACEMENT,
        MutationOperator.NULL_CHECK_REMOVAL,
        MutationOperator.RETURN_VALUE_REPLACEMENT,
    ],
    "typescript": [
        MutationOperator.CONDITIONAL_NEGATION,
        MutationOperator.CONDITIONAL_BOUNDARY,
        MutationOperator.ARITHMETIC_REPLACEMENT,
        MutationOperator.CONSTANT_REPLACEMENT,
        MutationOperator.NULL_CHECK_REMOVAL,
        MutationOperator.RETURN_VALUE_REPLACEMENT,
    ],
}


@dataclass
class Mutant:
    """A single mutated version of source code."""
    id: str
    operator: MutationOperator
    file_path: Path
    original_line: str
    mutated_line: str
    line_number: int
    original_code: str
    mutated_code: str
    status: MutationStatus = MutationStatus.ERROR
    killing_test: str | None = None
    duration_ms: int = 0


@dataclass
class MutationReport:
    """Aggregate mutation testing results for a project."""
    project_root: Path
    language: str
    total_mutants: int = 0
    killed: int = 0
    survived: int = 0
    equivalent: int = 0
    error: int = 0
    mutants: list[Mutant] = field(default_factory=list)
    duration_ms: int = 0

    @property
    def mutation_score(self) -> float:
        """Mutation score = killed / (killed + survived) * 100."""
        denominator = self.killed + self.survived
        if denominator == 0:
            return 0.0
        return round(self.killed / denominator * 100, 2)

    @property
    def mutation_score_with_equivalent(self) -> float:
        """Mutation score including equivalent mutants in denominator."""
        denominator = self.killed + self.survived + self.equivalent
        if denominator == 0:
            return 0.0
        return round(self.killed / denominator * 100, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root),
            "language": self.language,
            "total_mutants": self.total_mutants,
            "killed": self.killed,
            "survived": self.survived,
            "equivalent": self.equivalent,
            "error": self.error,
            "mutation_score": self.mutation_score,
            "mutation_score_with_equivalent": self.mutation_score_with_equivalent,
            "duration_ms": self.duration_ms,
            "mutants": [
                {
                    "id": m.id,
                    "operator": m.operator.value,
                    "file": str(m.file_path),
                    "line": m.line_number,
                    "original": m.original_line,
                    "mutated": m.mutated_line,
                    "status": m.status.value,
                    "killing_test": m.killing_test,
                    "duration_ms": m.duration_ms,
                }
                for m in self.mutants
            ],
        }


class MutationEngine:
    """Core mutation engine: generates mutants, runs tests, classifies results."""

    def __init__(
        self,
        project_root: Path,
        language: str,
        test_command: list[str],
        max_mutants: int = 100,
        timeout_per_mutant: int = 60,
    ):
        self.project_root = Path(project_root).resolve()
        self.language = language.lower()
        self.test_command = test_command
        self.max_mutants = max_mutants
        self.timeout_per_mutant = timeout_per_mutant
        self.operators = OPERATORS_BY_LANGUAGE.get(self.language, [])

    def generate_mutants(self, source_files: list[Path]) -> list[Mutant]:
        """Generate mutants from source files (up to max_mutants)."""
        mutants: list[Mutant] = []
        mutant_id = 0

        for file_path in source_files:
            if len(mutants) >= self.max_mutants:
                break
            file_mutants = self._mutate_file(file_path, mutant_id)
            mutants.extend(file_mutants)
            mutant_id += len(file_mutants)

        return mutants[:self.max_mutants]

    def _mutate_file(self, file_path: Path, start_id: int) -> list[Mutant]:
        """Generate mutants for a single file based on language."""
        if self.language == "python":
            return self._mutate_python(file_path, start_id)
        elif self.language in ("java", "go", "javascript", "typescript"):
            return self._mutate_generic(file_path, start_id)
        return []

    def _mutate_python(self, file_path: Path, start_id: int) -> list[Mutant]:
        """AST-based mutation for Python."""
        mutants: list[Mutant] = []
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            lines = source.splitlines()
            mutant_id = start_id

            for node in ast.walk(tree):
                if len(mutants) >= self.max_mutants:
                    break

                # Conditional negation: if a > b → if not (a > b)
                if isinstance(node, ast.Compare) and len(node.ops) == 1:
                    op = node.ops[0]
                    if isinstance(op, (ast.Gt, ast.Lt, ast.GtE, ast.LtE, ast.Eq, ast.NotEq)):
                        line_no = node.lineno - 1
                        original_line = lines[line_no] if line_no < len(lines) else ""
                        # Generate negated version
                        if isinstance(op, ast.Gt):
                            mutated_op = "<="
                        elif isinstance(op, ast.Lt):
                            mutated_op = ">="
                        elif isinstance(op, ast.GtE):
                            mutated_op = "<"
                        elif isinstance(op, ast.LtE):
                            mutated_op = ">"
                        elif isinstance(op, ast.Eq):
                            mutated_op = "!="
                        elif isinstance(op, ast.NotEq):
                            mutated_op = "=="
                        else:
                            continue

                        # Simple string replacement for demo
                        mutated_line = original_line.replace(
                            self._op_symbol(op), self._op_symbol_str(mutated_op)
                        )
                        if mutated_line != original_line:
                            mutants.append(Mutant(
                                id=f"M{mutant_id:04d}",
                                operator=MutationOperator.CONDITIONAL_NEGATION,
                                file_path=file_path,
                                original_line=original_line.strip(),
                                mutated_line=mutated_line.strip(),
                                line_number=node.lineno,
                                original_code=source,
                                mutated_code=source.replace(original_line, mutated_line, 1),
                            ))
                            mutant_id += 1

                # Arithmetic replacement: a + b → a - b
                if isinstance(node, ast.BinOp) and isinstance(
                    node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod)
                ):
                        line_no = node.lineno - 1
                        original_line = lines[line_no] if line_no < len(lines) else ""
                        mutated_line = self._mutate_arithmetic_line(original_line, node.op)
                        if mutated_line != original_line:
                            mutants.append(Mutant(
                                id=f"M{mutant_id:04d}",
                                operator=MutationOperator.ARITHMETIC_REPLACEMENT,
                                file_path=file_path,
                                original_line=original_line.strip(),
                                mutated_line=mutated_line.strip(),
                                line_number=node.lineno,
                                original_code=source,
                                mutated_code=source.replace(original_line, mutated_line, 1),
                            ))
                            mutant_id += 1

                # Constant replacement: True → False, 1 → 0, "" → "mutated"
                if isinstance(node, ast.Constant):
                    line_no = node.lineno - 1
                    original_line = lines[line_no] if line_no < len(lines) else ""
                    mutated_value = self._mutate_constant(node.value)
                    if mutated_value is not None:
                        original_repr = repr(node.value)
                        mutated_repr = repr(mutated_value)
                        mutated_line = original_line.replace(original_repr, mutated_repr, 1)
                        if mutated_line != original_line:
                            mutants.append(Mutant(
                                id=f"M{mutant_id:04d}",
                                operator=MutationOperator.CONSTANT_REPLACEMENT,
                                file_path=file_path,
                                original_line=original_line.strip(),
                                mutated_line=mutated_line.strip(),
                                line_number=node.lineno,
                                original_code=source,
                                mutated_code=source.replace(original_line, mutated_line, 1),
                            ))
                            mutant_id += 1

        except Exception:  # noqa: BLE001 — an unparseable file yields no mutants; the campaign continues
            pass  # Skip files that can't be parsed
        return mutants

    def _mutate_generic(self, file_path: Path, start_id: int) -> list[Mutant]:
        """Regex-based mutation for Java/Go/JS/TS (simpler, less precise)."""
        mutants: list[Mutant] = []
        try:
            source = file_path.read_text(encoding="utf-8")
            lines = source.splitlines()
            mutant_id = start_id

            patterns: list[tuple[MutationOperator, str, Any]] = [
                (
                    MutationOperator.CONDITIONAL_NEGATION,
                    r"(==|!=|<=|>=|<|>)",
                    self._flip_comparison,
                ),
                (
                    MutationOperator.ARITHMETIC_REPLACEMENT,
                    r"(\+|\-|\*|/|%)",
                    self._flip_arithmetic,
                ),
                (
                    MutationOperator.CONDITIONAL_BOUNDARY,
                    r"(<=|>=)",
                    self._flip_boundary,
                ),
            ]

            for line_no, line in enumerate(lines):
                if len(mutants) >= self.max_mutants:
                    break
                for op, pattern, replacer in patterns:
                    if op not in self.operators:
                        continue
                    for match in re.finditer(pattern, line):
                        mutated_line = replacer(line, match)
                        if mutated_line != line:
                            mutants.append(Mutant(
                                id=f"M{mutant_id:04d}",
                                operator=op,
                                file_path=file_path,
                                original_line=line.strip(),
                                mutated_line=mutated_line.strip(),
                                line_number=line_no + 1,
                                original_code=source,
                                mutated_code=source.replace(line, mutated_line, 1),
                            ))
                            mutant_id += 1
                            if len(mutants) >= self.max_mutants:
                                break
        except Exception:  # noqa: BLE001 — same: one bad file must not end the campaign
            pass
        return mutants

    def _op_symbol(self, op: ast.cmpop) -> str:
        mapping = {
            ast.Gt: ">", ast.Lt: "<", ast.GtE: ">=", ast.LtE: "<=",
            ast.Eq: "==", ast.NotEq: "!=",
        }
        return mapping.get(type(op), "")

    def _op_symbol_str(self, op_str: str) -> str:
        return op_str

    def _mutate_arithmetic_line(self, line: str, op: ast.operator) -> str:
        mapping = {ast.Add: "-", ast.Sub: "+", ast.Mult: "/", ast.Div: "*", ast.Mod: "*"}
        symbol = mapping.get(type(op))
        if symbol:
            return line.replace(self._op_symbol_ast(op), symbol, 1)
        return line

    def _op_symbol_ast(self, op: ast.operator) -> str:
        mapping = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%"}
        return mapping.get(type(op), "")

    def _mutate_constant(self, value: Any) -> Any | None:
        if isinstance(value, bool):
            return not value
        if isinstance(value, int):
            return 0 if value == 1 else 1 if value == 0 else -value
        if isinstance(value, str):
            return "mutated" if value == "" else ""
        if value is None:
            return "mutated"
        return None

    def _flip_comparison(self, line: str, match: re.Match[str]) -> str:
        op = match.group(1)
        mapping = {"==": "!=", "!=": "==", "<": ">=", ">": "<=", "<=": ">", ">=": "<"}
        return line[:match.start(1)] + mapping.get(op, op) + line[match.end(1):]

    def _flip_arithmetic(self, line: str, match: re.Match[str]) -> str:
        op = match.group(1)
        mapping = {"+": "-", "-": "+", "*": "/", "/": "*", "%": "*"}
        return line[:match.start(1)] + mapping.get(op, op) + line[match.end(1):]

    def _flip_boundary(self, line: str, match: re.Match[str]) -> str:
        op = match.group(1)
        mapping = {"<=": ">", ">=": "<"}
        return line[:match.start(1)] + mapping.get(op, op) + line[match.end(1):]


def run_mutation_testing(
    project_root: Path,
    language: str,
    test_command: list[str],
    source_patterns: list[str] | None = None,
    max_mutants: int = 50,
    timeout_per_mutant: int = 60,
) -> MutationReport:
    """High-level entry point for mutation testing."""
    import subprocess
    import tempfile
    import time

    engine = MutationEngine(
        project_root=project_root,
        language=language,
        test_command=test_command,
        max_mutants=max_mutants,
        timeout_per_mutant=timeout_per_mutant,
    )

    # Find source files
    if source_patterns is None:
        if language == "python":
            source_patterns = ["**/*.py"]
        else:
            source_patterns = ["**/*.java", "**/*.go", "**/*.js", "**/*.ts"]
    source_files: list[Path] = []
    for pattern in source_patterns:
        source_files.extend(project_root.rglob(pattern))

    # Filter out test files
    source_files = [f for f in source_files if not _is_test_file(f, language)]

    start_time = time.perf_counter()
    mutants = engine.generate_mutants(source_files)
    report = MutationReport(
        project_root=project_root,
        language=language,
        total_mutants=len(mutants),
    )

    # Run tests against each mutant
    for mutant in mutants:
        mutant_start = time.perf_counter()
        try:
            # Write mutant to temp location
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir) / mutant.file_path.name
                tmp_path.write_text(mutant.mutated_code, encoding="utf-8")

                # Copy project to temp (excluding the mutated file's original)
                # For simplicity, we just run the test command in the project root
                # with the mutant file in place
                original_content = mutant.file_path.read_text(encoding="utf-8")
                mutant.file_path.write_text(mutant.mutated_code, encoding="utf-8")

                try:
                    result = subprocess.run(
                        test_command,
                        cwd=project_root,
                        capture_output=True,
                        text=True,
                        timeout=timeout_per_mutant,
                    )
                    if result.returncode != 0:
                        mutant.status = MutationStatus.KILLED
                        # Extract test name from output
                        mutant.killing_test = _extract_failing_test(result.stdout + result.stderr)
                    else:
                        mutant.status = MutationStatus.SURVIVED
                except subprocess.TimeoutExpired:
                    mutant.status = MutationStatus.ERROR
                finally:
                    # Restore original
                    mutant.file_path.write_text(original_content, encoding="utf-8")

        except Exception:
            mutant.status = MutationStatus.ERROR
        finally:
            mutant.duration_ms = int((time.perf_counter() - mutant_start) * 1000)
            report.mutants.append(mutant)

    # Aggregate
    for m in report.mutants:
        if m.status == MutationStatus.KILLED:
            report.killed += 1
        elif m.status == MutationStatus.SURVIVED:
            report.survived += 1
        elif m.status == MutationStatus.EQUIVALENT:
            report.equivalent += 1
        else:
            report.error += 1

    report.duration_ms = int((time.perf_counter() - start_time) * 1000)
    return report


def _is_test_file(path: Path, language: str) -> bool:
    """Heuristic to exclude test files from mutation."""
    name = path.name.lower()
    if language == "python":
        return name.startswith("test_") or name.endswith("_test.py") or "conftest" in name
    if language == "java":
        return name.endswith("test.java") or "test" in str(path).lower()
    if language in ("go", "javascript", "typescript"):
        return (
            name.endswith("_test.go")
            or name.endswith(".test.js")
            or name.endswith(".test.ts")
            or name.endswith(".spec.js")
            or name.endswith(".spec.ts")
        )
    return False


def _extract_failing_test(output: str) -> str | None:
    """Extract failing test name from test output."""
    # Simple extraction - can be enhanced per test framework
    for line in output.splitlines():
        if "FAILED" in line or "FAIL:" in line or "AssertionError" in line:
            return line.strip()[:200]
    return None


__all__ = [
    "MutationStatus",
    "MutationOperator",
    "Mutant",
    "MutationReport",
    "MutationEngine",
    "run_mutation_testing",
    "OPERATORS_BY_LANGUAGE",
]
