"""Unit tests — ddmin minimizer (experiments/minimize.py, 工业化指南 阶段 4 / W57).

All runners are injected fakes: pure in-memory predicates over the
candidates the engine proposes. No filesystem, no network. Covered: list
shrink to a 1-minimal failing subsequence (order-preserving), set and
substring fixture reduction, the iterations log, honest budget stop,
unchanged-result proof, and the passing-input/empty-input edge cases.
"""

from __future__ import annotations

from typing import Any

import pytest

from experiments.minimize import (
    DEFAULT_MINIMIZE_BUDGET,
    MinimizeResult,
    ddmin_steps,
    reduce_list,
    reduce_set,
    reduce_substring,
)


def _requires_2_and_5(items: Any) -> bool:
    return {2, 5} <= set(items)


class TestDdminSteps:
    def test_shrinks_list_to_minimal_failing_subset(self) -> None:
        result = ddmin_steps(list(range(8)), _requires_2_and_5)
        assert result.minimized
        assert not result.budget_exhausted
        assert result.reduced == (2, 5)
        assert result.tests_run >= 3
        assert result.iterations

    def test_reduced_preserves_relative_order(self) -> None:
        result = ddmin_steps([9, 2, 8, 5, 7], _requires_2_and_5)
        assert result.reduced == (2, 5)

    def test_keep_chunk_and_refine_actions_are_logged(self) -> None:
        result = ddmin_steps([2, 5, 0, 0, 0, 0, 0, 0], _requires_2_and_5)
        actions = {record.action for record in result.iterations}
        assert "keep_chunk" in actions
        assert "refine" in actions
        assert result.reduced == (2, 5)

    def test_iterations_log_shape(self) -> None:
        result = ddmin_steps(list(range(8)), _requires_2_and_5)
        assert [rec.iteration for rec in result.iterations] == list(
            range(1, len(result.iterations) + 1)
        )
        for record in result.iterations:
            assert record.granularity >= 2
            assert record.chunk_size >= 1
            assert record.action in {"drop", "keep_chunk", "refine", "budget_stop"}
        tests_so_far = [record.tests_run for record in result.iterations]
        assert tests_so_far == sorted(tests_so_far)
        assert result.iterations[-1].result_size == len(result.reduced)

    def test_unchanged_result_proof_covers_every_element(self) -> None:
        result = ddmin_steps(list(range(8)), _requires_2_and_5)
        assert len(result.proof) == len(result.reduced)
        for element in result.reduced:
            assert any(str(element) in line for line in result.proof)
        assert all("does not reproduce" in line for line in result.proof)

    def test_passing_input_raises_honestly(self) -> None:
        with pytest.raises(ValueError, match="does not reproduce"):
            ddmin_steps([1, 2, 3], lambda items: False)

    def test_empty_failing_input_is_already_minimal(self) -> None:
        result = ddmin_steps([], lambda items: len(items) == 0)
        assert result.minimized
        assert result.reduced == ()
        assert result.tests_run == 1
        assert "empty" in result.proof[0]

    def test_budget_stop_is_honest(self) -> None:
        def fails_when_long(items: Any) -> bool:
            return len(items) >= 10

        result = ddmin_steps(list(range(20)), fails_when_long, max_tests=4)
        assert result.budget_exhausted
        assert not result.minimized
        assert result.tests_run == 4
        assert result.proof == ()
        assert result.reduced
        assert result.iterations[-1].action == "budget_stop"

    def test_zero_budget_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="max_tests"):
            ddmin_steps([1], lambda items: True, max_tests=0)


class TestReduceList:
    def test_reduce_list_is_ddmin_alias(self) -> None:
        result: MinimizeResult[tuple[int, ...]] = reduce_list(
            list(range(8)), _requires_2_and_5
        )
        assert result.minimized
        assert result.reduced == (2, 5)


class TestReduceSet:
    def test_reduce_set_shrinks_to_required_members(self) -> None:
        result = reduce_set({0, 1, 2, 3, 4, 5, 6, 7}, lambda subset: {2, 5} <= subset)
        assert result.minimized
        assert set(result.reduced) == {2, 5}
        assert not result.budget_exhausted


class TestReduceSubstring:
    def test_reduce_substring_keeps_bug_trigger_only(self) -> None:
        def bug(text: str) -> bool:
            return "foo" in text and "bar" in text

        result: MinimizeResult[str] = reduce_substring("prefixfooMIDDLEbarSuffix", bug)
        assert result.minimized
        assert result.reduced == "foobar"
        assert not result.budget_exhausted
        assert len(result.proof) == len(result.reduced)
        assert all("does not reproduce" in line for line in result.proof)

    def test_substring_passing_input_raises(self) -> None:
        with pytest.raises(ValueError, match="does not reproduce"):
            reduce_substring("plain text", lambda text: "foo" in text and "bar" in text)


class TestDefaults:
    def test_default_budget_is_generous(self) -> None:
        assert DEFAULT_MINIMIZE_BUDGET >= 100
