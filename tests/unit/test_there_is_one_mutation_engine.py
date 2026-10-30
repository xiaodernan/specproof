"""#535 — one mutation engine, and it is the one a caller actually reaches.

Measured at HEAD before this change: two engines. `experiments/mutation.py` is
the Java operator set the benchmark calls (`scripts/mutation_bench_lib.py`
imports `generate_mutants`), and `craft/mutation.py` was a 537-line second
engine for Python/Go/JS/TS whose only readers were its own unit test, a codec
pin, and a local runner's file list. Its KILLED criterion was
`returncode != 0`, so a compile error or a selector that matched nothing
booked a kill — exactly the defect #532 fixed in the shipped engine — and its
own test asserted that shape (`MutationStatus.KILLED` from a fake failing
child that never executed a test).

Deleting it was chosen over wiring it in: the benchmark's producer already
imports the shipped engine, and the "a run counts only if tests executed"
pins for that engine already live in
`tests/unit/test_zero_test_runs_are_not_verdicts.py`. A second engine would
have needed its own sandbox, its own counting contract and its own readers
before it could say anything the shipped one does not.

This gate keeps the next one from arriving silently. It does not hard-code the
engine path: it derives it from the bench's import, then requires every module
in the shipped-package roster (`pyproject.toml`'s `packages.find.include`) that
defines a mutation-shaped top-level symbol — a function or class whose name
contains `mutant` or `mutation` — to be that module. The rule is structural,
not a list of the deleted engine's names: `MutationEngine` +
`run_mutation_testing` (the deleted shape) and `generate_mutants` +
`run_mutation_campaign` (the shipped shape) must both be seen, and both are
fixture-tested below. Measured against the shipped roster when this gate
landed: exactly one module matched.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BENCH = "scripts/mutation_bench_lib.py"
ENGINE_FUNCTIONS = ("generate_mutants", "run_mutation_campaign")
ENGINE_NAME_PARTS = ("mutant", "mutation")


def _engine_definitions(source: str) -> set[str]:
    """Mutation-shaped top-level functions and classes defined by `source`."""
    return {
        node.name
        for node in ast.parse(source).body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and any(part in node.name.lower() for part in ENGINE_NAME_PARTS)
    }


def _bench_import() -> str:
    """The module `scripts/mutation_bench_lib.py` imports its engine from."""
    tree = ast.parse((REPO / BENCH).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and any(alias.name in ENGINE_FUNCTIONS for alias in node.names)
        ):
            return node.module
    raise AssertionError(
        f"{BENCH} no longer imports a mutation engine; the gate's engine path "
        "cannot be derived — update this gate with the new producer"
    )


def _shipped_roots() -> list[Path]:
    cfg = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    include = cfg["tool"]["setuptools"]["packages"]["find"]["include"]
    roots = [REPO / pattern.rstrip("*") for pattern in include]
    missing = [str(root) for root in roots if not root.is_dir()]
    assert not missing, f"pyproject include names missing packages: {missing}"
    return roots


def _engine_modules() -> tuple[dict[str, set[str]], int]:
    """(module path -> defined mutation symbols, files scanned)."""
    found: dict[str, set[str]] = {}
    scanned = 0
    for root in _shipped_roots():
        for path in root.rglob("*.py"):
            if "__pycache__" in path.relative_to(REPO).parts:
                continue
            scanned += 1
            definitions = _engine_definitions(
                path.read_text(encoding="utf-8", errors="replace")
            )
            if definitions:
                found[path.relative_to(REPO).as_posix()] = definitions
    return found, scanned


# ── the detector: a definition is not a mention, and both shapes count ──────


def test_a_definition_counts_and_a_mention_does_not() -> None:
    shipped_shape = """
class Mutant:
    pass

def generate_mutants(content, max_mutants=20):
    return []

def run_mutation_campaign(source_path, source_content, test_runner):
    return None
"""
    deleted_shape = """
class MutationEngine:
    def generate_mutants(self, files):
        return []

def run_mutation_testing(project_root, language, test_command):
    return None
"""
    importing = "from experiments.mutation import generate_mutants\n"
    mentioning = (
        '"""The bench calls generate_mutants; run_mutation_campaign is next."""\n'
        "# MutationEngine lived here once; run_mutation_testing was its entry\n"
        "def helper(mutation_score):\n"
        "    return generate_mutants\n"
    )
    nested = """
def outer():
    class MutationEngine:
        pass
    def generate_mutants():
        return []
    return MutationEngine, generate_mutants
"""

    assert _engine_definitions(shipped_shape) == {
        "Mutant", "generate_mutants", "run_mutation_campaign",
    }
    assert _engine_definitions(deleted_shape) == {
        "MutationEngine", "run_mutation_testing",
    }
    assert _engine_definitions(importing) == set()
    assert _engine_definitions(mentioning) == set()
    assert _engine_definitions(nested) == set(), "an inner helper is not an engine entry"


# ── the repo itself ─────────────────────────────────────────────────────────


def test_the_bench_reaches_the_one_engine_and_it_defines_both_entries() -> None:
    module = _bench_import()
    assert module == "experiments.mutation", (
        f"the bench imports {module}; re-derive this gate if the producer moved"
    )
    source = (REPO / (module.replace(".", "/") + ".py")).read_text(encoding="utf-8")
    assert set(ENGINE_FUNCTIONS) <= _engine_definitions(source)


def test_no_shipped_module_defines_a_second_mutation_engine() -> None:
    engine = _bench_import().replace(".", "/") + ".py"
    found, scanned = _engine_modules()
    assert scanned > 100, f"the census only reached {scanned} shipped modules"
    assert engine in found, f"the census did not reach {engine} — is the walk broken?"
    assert set(found) == {engine}, (
        "a second mutation engine is shipping without a caller: "
        + ", ".join(
            f"{path} defines {sorted(names)}"
            for path, names in sorted(found.items())
            if path != engine
        )
        + " — wire it to a real reader or delete it (#535); the shipped engine's "
        "kill criterion already requires an executed test"
    )
