"""P4 — source-level mutation testing (scoped to the PR impact area).

Mutation answers the question the demo pipeline cannot: ARE THE TESTS ANY
GOOD? A regression the verifier misses may exist because no test would
fail on it. The mutation campaign introduces artificial defects into the
HEAD workspace (annotation removal, boolean flips, null-check removal,
return-value flips) and runs the generated counterexample test against
each mutant:

  KILLED   the test failed on the mutant → the test would catch this class
           of defect
  SURVIVED the test passed on the mutant → test weakness (a real gap in
           the verification coverage)

Surviving mutants are NOT reported as findings — they are reported as
TEST WEAKNESSES (the spec: "存活变异体不自动视为 Bug").
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class Mutant:
    mutant_id: str
    operator: str
    description: str
    content: str


# ── Operators (text-level, deterministic) ──────────────────────

_ANNOTATION_LINE = re.compile(
    r"^\s*@(PreAuthorize|Secured|RolesAllowed|Transactional)\b[^\n]*\n",
    re.M,
)


def mutate_remove_annotation(content: str) -> list[Mutant]:
    mutants: list[Mutant] = []
    for i, m in enumerate(_ANNOTATION_LINE.finditer(content), start=1):
        mutated = content[:m.start()] + content[m.end():]
        mutants.append(Mutant(
            mutant_id=f"ANN-{i:02d}",
            operator="remove_annotation",
            description=f"removed {m.group(0).strip()}",
            content=mutated,
        ))
    return mutants


def mutate_flip_boolean(content: str) -> list[Mutant]:
    mutants: list[Mutant] = []
    for i, m in enumerate(re.finditer(r"==|!=", content), start=1):
        flipped = "!=" if m.group(0) == "==" else "=="
        mutants.append(Mutant(
            mutant_id=f"BOOL-{i:02d}",
            operator="flip_boolean",
            description=f"flipped '{m.group(0)}' to '{flipped}' at offset {m.start()}",
            content=content[:m.start()] + flipped + content[m.end():],
        ))
    return mutants


def mutate_remove_null_check(content: str) -> list[Mutant]:
    mutants: list[Mutant] = []
    for i, m in enumerate(
        re.finditer(r"^\s*if\s*\(\s*\w+\s*(?:==|!=)\s*null\s*\)\s*\{[^}]*\}\n", content, re.M),
        start=1,
    ):
        mutants.append(Mutant(
            mutant_id=f"NULL-{i:02d}",
            operator="remove_null_check",
            description="removed null check: " + m.group(0).strip()[:60],
            content=content[:m.start()] + content[m.end():],
        ))
    return mutants


def mutate_return_flip(content: str) -> list[Mutant]:
    mutants: list[Mutant] = []
    for i, m in enumerate(re.finditer(r"return\s+(true|false)\s*;", content), start=1):
        flipped = "false" if m.group(1) == "true" else "true"
        mutants.append(Mutant(
            mutant_id=f"RET-{i:02d}",
            operator="return_flip",
            description=f"flipped return {m.group(1)} -> {flipped}",
            content=(
                content[:m.start()] + "return " + flipped + ";"
                + content[m.end():]
            ),
        ))
    return mutants


OPERATORS: list[tuple[str, Callable[[str], list[Mutant]]]] = [
    ("remove_annotation", mutate_remove_annotation),
    ("flip_boolean", mutate_flip_boolean),
    ("remove_null_check", mutate_remove_null_check),
    ("return_flip", mutate_return_flip),
]


# ── Campaign ────────────────────────────────────────────────────

@dataclass
class MutationResult:
    mutant_id: str
    operator: str
    description: str
    killed: bool
    test_exit_code: int
    error: str = ""


@dataclass
class MutationReport:
    file: str
    mutants_total: int
    killed: int
    survived: int
    results: list[MutationResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "mutants_total": self.mutants_total,
            "killed": self.killed,
            "survived": self.survived,
            "mutation_score": (
                round(self.killed / self.mutants_total, 3)
                if self.mutants_total else 0.0
            ),
            "results": [
                {
                    "mutant_id": r.mutant_id,
                    "operator": r.operator,
                    "description": r.description,
                    "killed": r.killed,
                    "test_exit_code": r.test_exit_code,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


def generate_mutants(content: str, max_mutants: int = 20) -> list[Mutant]:
    """Apply all operators; cap the campaign size for bounded runtime."""
    mutants: list[Mutant] = []
    for _name, operator_fn in OPERATORS:
        mutants.extend(operator_fn(content))
        if len(mutants) >= max_mutants:
            return mutants[:max_mutants]
    return mutants[:max_mutants]


def run_mutation_campaign(
    source_path: str,
    source_content: str,
    test_runner: Callable[[str], tuple[int, str]],
    max_mutants: int = 20,
) -> MutationReport:
    """Mutate source, run the test on each mutant, classify kill/survive.

    test_runner(content) -> (exit_code, error): runs the generated test
    against a workspace where the source file was replaced by content.
    0 = test passed = mutant SURVIVED; non-zero = KILLED.
    """
    mutants = generate_mutants(source_content, max_mutants)
    results: list[MutationResult] = []
    for mutant in mutants:
        exit_code, error = test_runner(mutant.content)
        killed = exit_code != 0
        results.append(MutationResult(
            mutant_id=mutant.mutant_id,
            operator=mutant.operator,
            description=mutant.description,
            killed=killed,
            test_exit_code=exit_code,
            error=error,
        ))
    return MutationReport(
        file=source_path,
        mutants_total=len(mutants),
        killed=sum(1 for r in results if r.killed),
        survived=sum(1 for r in results if not r.killed and not r.error),
        results=results,
    )
