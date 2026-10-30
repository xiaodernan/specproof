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
  NOT_RUN  the run executed no tests (build/toolchain failure, or a
           selector that matched nothing) → nothing was measured

Surviving mutants are NOT reported as findings — they are reported as
TEST WEAKNESSES (the spec: "存活变异体不自动视为 Bug").

Only a run that executed tests can kill or spare a mutant (backlog #532).
Before this unit ``killed = exit_code != 0``, so a mutant that failed to
compile — or any toolchain error — was booked as KILLED. The mutation
score's denominator is therefore the executed mutants (killed + survived);
not_run is published as its own count so the campaign's coverage of the
mutant set is visible instead of being folded into a rate.
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
    tests_executed: int = 0
    error: str = ""

    @property
    def not_run(self) -> bool:
        return self.tests_executed == 0


@dataclass
class MutationReport:
    file: str
    mutants_total: int
    killed: int
    survived: int
    results: list[MutationResult]
    not_run: int = 0

    def to_dict(self) -> dict[str, Any]:
        executed = self.killed + self.survived
        return {
            "file": self.file,
            "mutants_total": self.mutants_total,
            "killed": self.killed,
            "survived": self.survived,
            "not_run": self.not_run,
            "mutation_score": (
                round(self.killed / executed, 3) if executed else 0.0
            ),
            "results": [
                {
                    "mutant_id": r.mutant_id,
                    "operator": r.operator,
                    "description": r.description,
                    "killed": r.killed,
                    "test_exit_code": r.test_exit_code,
                    "tests_executed": r.tests_executed,
                    "not_run": r.not_run,
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
    test_runner: Callable[[str], tuple[int, str, int]],
    max_mutants: int = 20,
) -> MutationReport:
    """Mutate source, run the test on each mutant, classify kill/survive.

    test_runner(content) -> (exit_code, error, tests_executed): runs the
    generated test against a workspace where the source file was replaced by
    content. Zero executed tests means the run never measured the mutant —
    a build failure or a selector that matched nothing — and is recorded as
    not_run; only an executed run can KILL (non-zero) or SURVIVE (zero).
    """
    mutants = generate_mutants(source_content, max_mutants)
    results: list[MutationResult] = []
    for mutant in mutants:
        exit_code, error, tests_executed = test_runner(mutant.content)
        executed = tests_executed > 0
        killed = executed and exit_code != 0
        results.append(MutationResult(
            mutant_id=mutant.mutant_id,
            operator=mutant.operator,
            description=mutant.description,
            killed=killed,
            test_exit_code=exit_code,
            tests_executed=tests_executed,
            error=error,
        ))
    return MutationReport(
        file=source_path,
        mutants_total=len(mutants),
        killed=sum(1 for r in results if r.killed),
        survived=sum(1 for r in results if r.tests_executed > 0 and not r.killed),
        not_run=sum(1 for r in results if r.not_run),
        results=results,
    )
