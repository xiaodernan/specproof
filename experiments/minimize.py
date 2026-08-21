"""Delta-debugging minimizer (ddmin) for failing steps and input fixtures.

工业化指南 阶段 4 / W57: shrink a failure to a 1-minimal reproducer.

- ddmin_steps / reduce_list: Zeller & Hildebrandt ddmin over an ordered
  list of steps; the injected runner decides whether a candidate still
  reproduces the failure (True = reproduces).
- reduce_set / reduce_substring: the same engine over an unordered element
  set and over substrings of a text fixture.
- Every run records each granularity pass (IterationRecord — the iterations
  log), stops honestly when the test budget is exhausted
  (budget_exhausted=True, minimized=False, proof empty), and — when
  minimization completes — ships an unchanged-result proof: one recorded
  test per element of the final result showing that removing that element
  alone no longer reproduces the failure.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass

DEFAULT_MINIMIZE_BUDGET = 1000


@dataclass(frozen=True)
class IterationRecord:
    """One granularity pass of the ddmin loop (iterations-log entry).

    action is "drop" (a chunk complement still reproduced → chunk dropped),
    "keep_chunk" (a chunk alone reproduced → shrunk to the chunk),
    "refine" (no candidate reproduced → granularity doubled) or
    "budget_stop" (the test budget ran out mid-pass).
    """

    iteration: int
    granularity: int
    chunk_size: int
    action: str
    result_size: int
    tests_run: int


@dataclass(frozen=True)
class MinimizeResult[R]:
    """Outcome of one minimization run.

    minimized is True only when the result is proven 1-minimal within the
    budget: proof then carries one recorded "removing X does not
    reproduce" test per element of the reduced result. On budget stop the
    reduced candidate still reproduces the failure but is NOT proven
    minimal (minimized=False, budget_exhausted=True, proof empty).
    """

    minimized: bool
    reduced: R
    iterations: tuple[IterationRecord, ...]
    tests_run: int
    budget_exhausted: bool
    proof: tuple[str, ...]


def ddmin_steps[T](
    steps: Sequence[T],
    is_failing: Callable[[Sequence[T]], bool],
    max_tests: int = DEFAULT_MINIMIZE_BUDGET,
) -> MinimizeResult[tuple[T, ...]]:
    """ddmin (Zeller & Hildebrandt) over an ordered list of failing steps.

    Returns the order-preserving 1-minimal failing subsequence, the
    iterations log, the number of runner executions, and the
    unchanged-result proof. Raises ValueError when the initial input does
    not reproduce the failure (minimization requires a failing input).
    """
    if max_tests < 1:
        raise ValueError("max_tests must be >= 1")

    tests = 0

    def test(candidate: Sequence[T]) -> bool | None:
        """Run the injected runner; None once the budget is exhausted."""
        nonlocal tests
        if tests >= max_tests:
            return None
        tests += 1
        return is_failing(candidate)

    empty_reduced: tuple[T, ...] = ()
    empty_proof = ("empty input already reproduces the failure (test #1)",)

    if not steps:
        if test(()):
            return MinimizeResult(
                minimized=True,
                reduced=empty_reduced,
                iterations=(),
                tests_run=tests,
                budget_exhausted=False,
                proof=empty_proof,
            )
        raise ValueError(
            "input does not reproduce the failure — minimization requires a failing input"
        )

    if test(()):
        return MinimizeResult(
            minimized=True,
            reduced=empty_reduced,
            iterations=(),
            tests_run=tests,
            budget_exhausted=False,
            proof=empty_proof,
        )

    current = list(steps)
    if not test(current):
        raise ValueError(
            "input does not reproduce the failure — minimization requires a failing input"
        )

    iterations: list[IterationRecord] = []
    iteration = 1
    n = 2
    budget_exhausted = False
    while len(current) >= 2:
        chunk_size = (len(current) + n - 1) // n
        action = "refine"
        for start in range(0, len(current), chunk_size):
            chunk = current[start:start + chunk_size]
            complement = current[:start] + current[start + chunk_size:]
            if complement:
                outcome = test(complement)
                if outcome is None:
                    budget_exhausted = True
                    break
                if outcome:
                    current = complement
                    action = "drop"
                    break
            if chunk != current:
                outcome = test(chunk)
                if outcome is None:
                    budget_exhausted = True
                    break
                if outcome:
                    current = chunk
                    action = "keep_chunk"
                    break
        if budget_exhausted:
            action = "budget_stop"
        iterations.append(
            IterationRecord(
                iteration=iteration,
                granularity=n,
                chunk_size=chunk_size,
                action=action,
                result_size=len(current),
                tests_run=tests,
            )
        )
        iteration += 1
        if budget_exhausted:
            break
        if action == "refine":
            if n == len(current):
                break
            n = min(2 * n, len(current))
        else:
            n = max(n - 1, 2)

    if budget_exhausted:
        return MinimizeResult(
            minimized=False,
            reduced=tuple(current),
            iterations=tuple(iterations),
            tests_run=tests,
            budget_exhausted=True,
            proof=(),
        )

    # unchanged-result proof: removing any single element must stop
    # reproducing. Every line below is a real recorded test execution.
    proof: list[str] = []
    for index in range(len(current)):
        candidate = current[:index] + current[index + 1:]
        outcome = test(candidate)
        if outcome is None:
            return MinimizeResult(
                minimized=False,
                reduced=tuple(current),
                iterations=tuple(iterations),
                tests_run=tests,
                budget_exhausted=True,
                proof=(),
            )
        if outcome:
            # ddmin invariant violation — report honestly instead of
            # claiming a minimal result.
            return MinimizeResult(
                minimized=False,
                reduced=tuple(current),
                iterations=tuple(iterations),
                tests_run=tests,
                budget_exhausted=False,
                proof=(),
            )
        proof.append(
            f"removing {current[index]!r} does not reproduce the failure (test #{tests})"
        )
    return MinimizeResult(
        minimized=True,
        reduced=tuple(current),
        iterations=tuple(iterations),
        tests_run=tests,
        budget_exhausted=False,
        proof=tuple(proof),
    )


def reduce_list[T](
    items: Sequence[T],
    is_failing: Callable[[Sequence[T]], bool],
    max_tests: int = DEFAULT_MINIMIZE_BUDGET,
) -> MinimizeResult[tuple[T, ...]]:
    """List fixture reduction — alias of ddmin_steps, order-preserving."""
    return ddmin_steps(items, is_failing, max_tests)


def reduce_set[T](
    elements: Collection[T],
    is_failing: Callable[[frozenset[T]], bool],
    max_tests: int = DEFAULT_MINIMIZE_BUDGET,
) -> MinimizeResult[tuple[T, ...]]:
    """Set fixture reduction: the reduced tuple holds the surviving
    members; callers wrap it back with set()/frozenset() as needed."""
    ordered = tuple(elements)
    result = ddmin_steps(ordered, lambda subset: is_failing(frozenset(subset)), max_tests)
    return MinimizeResult(
        minimized=result.minimized,
        reduced=result.reduced,
        iterations=result.iterations,
        tests_run=result.tests_run,
        budget_exhausted=result.budget_exhausted,
        proof=result.proof,
    )


def reduce_substring(
    text: str,
    is_failing: Callable[[str], bool],
    max_tests: int = DEFAULT_MINIMIZE_BUDGET,
) -> MinimizeResult[str]:
    """Substring fixture reduction: ddmin over character positions, so the
    reduced string preserves the relative order of the surviving chars."""
    result = ddmin_steps(tuple(text), lambda chars: is_failing("".join(chars)), max_tests)
    return MinimizeResult(
        minimized=result.minimized,
        reduced="".join(result.reduced),
        iterations=result.iterations,
        tests_run=result.tests_run,
        budget_exhausted=result.budget_exhausted,
        proof=result.proof,
    )
