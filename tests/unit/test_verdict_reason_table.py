"""The reason table: which reason means "something is wrong" (Phase 3).

`evidence/verdict.py` files every reason it produces under one of two
kinds:

* **REASON_BLOCKING** — the run produced something self-contradictory,
  or it found a defect. A reader told BLOCKED goes looking for a defect.
* **REASON_GAP** — the run could not obtain, attribute or decide the
  evidence. Nothing is proven wrong; a reader told NEEDS_REVIEW goes
  looking for the missing evidence.

Both are fail-closed. The line between them is the whole point of the
split, and it is a TABLE — so this file pins it row by row. If a reason
moves from one column to the other, a reader's next action changes
with it, and that must be a deliberate edit here.

The scenarios below are the shapes a real run produces. Each names the
reason it triggers and the word the policy must answer with.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from evidence.verdict import (
    REASON_BLOCKING,
    REASON_GAP,
    REASON_TABLE,
    evaluate_verification,
)

PASSING_ROW: dict[str, Any] = {
    "contract_id": "C-1",
    "result": "PASS",
    "experiment": "STATIC-01",
    "evidence": "ev-1",
}


def _row(**changes: Any) -> dict[str, Any]:
    return {**PASSING_ROW, **changes}


#: (name, matrix, contracts, the reason it triggers, the KIND of that
#: reason, the word the policy must answer with)
#:
#: The KIND column and the WORD column are separate claims, and the
#: difference matters: a GAP reason can COEXIST with a BLOCKING one
#: (a broken contract set is both "no valid contract" and "a row for a
#: contract that does not exist"), and then the word is BLOCKED. The
#: table classifies each REASON; the verdict follows from the kinds
#: present.
SCENARIOS: list[
    tuple[str, dict[str, Any], list[dict[str, Any]] | None, str, str, str]
] = [
    (
        "no checks at all", {}, None, "零检查", REASON_GAP, "NEEDS_REVIEW",
    ),
    (
        "a row that is not even a mapping",
        {"rows": [None]}, None, "格式无效", REASON_BLOCKING, "BLOCKED",
    ),
    (
        "a contract that FAILED",
        {"rows": [_row(result="FAIL")]}, None, "检查失败", REASON_BLOCKING,
        "BLOCKED",
    ),
    (
        "a contract with no decidable result",
        {"rows": [_row(result="UNVERIFIED")]}, None, "没有任何实验产出结果",
        REASON_GAP, "NEEDS_REVIEW",
    ),
    (
        "a PASS with no evidence behind it",
        {"rows": [_row(evidence="")]}, None, "缺少证据引用", REASON_GAP,
        "NEEDS_REVIEW",
    ),
    (
        "a PASS with no experiment behind it",
        {"rows": [_row(experiment="")]}, None, "缺少实验记录", REASON_GAP,
        "NEEDS_REVIEW",
    ),
    (
        "a row with no contract id",
        {"rows": [_row(contract_id="")]}, None, "缺少契约标识", REASON_GAP,
        "NEEDS_REVIEW",
    ),
    (
        "two rows for one contract",
        {"rows": [_row(), _row()]}, None, "存在重复检查行", REASON_BLOCKING,
        "BLOCKED",
    ),
    (
        "a row for a contract that does not exist",
        {"rows": [_row(contract_id="OTHER")]},
        [{"id": "C-1"}], "没有对应验收契约", REASON_BLOCKING, "BLOCKED",
    ),
    (
        "a contract with no row",
        {"rows": [_row()]}, [{"id": "C-1"}, {"id": "C-2"}],
        "缺少契约检查结果", REASON_GAP, "NEEDS_REVIEW",
    ),
    (
        "a contract set with a duplicate id",
        {"rows": [_row()]}, [{"id": "C-1"}, {"id": "C-1"}],
        "标识缺失或重复", REASON_BLOCKING, "BLOCKED",
    ),
    (
        "no valid contract at all",
        {"rows": [_row()]}, [{"id": ""}], "没有有效的验收契约", REASON_GAP,
        "BLOCKED",
    ),
    (
        "a summary that disagrees with its rows",
        {"rows": [_row()], "passed": 0}, None, "与实际检查记录不一致",
        REASON_BLOCKING, "BLOCKED",
    ),
    (
        "a contract total that cannot be right",
        {"rows": [_row()], "total_contracts": 5}, None, "契约总数与检查覆盖不一致",
        REASON_BLOCKING, "BLOCKED",
    ),
]


@pytest.mark.parametrize(
    "name,matrix,contracts,reason_fragment,kind,expected",
    SCENARIOS,
    ids=[case[0] for case in SCENARIOS],
)
def test_each_reason_sits_on_its_side_of_the_table(
    name: str,
    matrix: dict[str, Any],
    contracts: list[dict[str, Any]] | None,
    reason_fragment: str,
    kind: str,
    expected: str,
) -> None:
    decision = evaluate_verification(
        matrix, contracts=contracts,
    )
    # The reason this scenario triggers is really among the reasons.
    matching = [
        reason for reason in decision.reasons if reason_fragment in reason
    ]
    assert matching, (
        f"{name}: no reason mentions {reason_fragment!r}: {decision.reasons}"
    )
    # And it sits on the side of the table the table claims — THIS
    # reason, not the decision as a whole (a GAP reason can coexist
    # with a BLOCKING one).
    for reason in matching:
        is_blocking = reason in decision.blocking
        assert is_blocking == (kind == REASON_BLOCKING), (
            f"{name}: {reason!r} is "
            f"{'blocking' if is_blocking else 'a gap'}, the table says {kind}"
        )
    assert decision.status == expected, (
        f"{name}: the policy said {decision.status}, the table says {expected}; "
        f"reasons: {decision.reasons}"
    )


class TestTheTableIsConsistent:
    def test_a_blocking_verdict_carries_its_blocking_reasons(self) -> None:
        decision = evaluate_verification({"rows": [_row(result="FAIL")]})
        assert decision.status == "BLOCKED"
        assert decision.blocking
        assert set(decision.blocking) <= set(decision.reasons)

    def test_a_gap_verdict_carries_no_blocking_reason(self) -> None:
        decision = evaluate_verification({"rows": [_row(evidence="")]})
        assert decision.status == "NEEDS_REVIEW"
        assert not decision.blocking

    def test_the_two_kinds_are_distinct_and_named(self) -> None:
        assert REASON_BLOCKING != REASON_GAP
        assert REASON_BLOCKING == "blocking"
        assert REASON_GAP == "gap"

    def test_no_scenario_is_simultaneously_both_kinds(self) -> None:
        """A reason that is in both columns would make the word arbitrary."""
        for name, matrix, contracts, _fragment, _kind, _expected in SCENARIOS:
            decision = evaluate_verification(matrix, contracts=contracts)
            assert not (decision.blocking and len(decision.blocking) == len(decision.reasons)
                        and decision.status == "NEEDS_REVIEW"), name


class TestTheReasonTable:
    """The table is the authority: one place says every reason and its side.

    Three failure modes, one gate each:

    * a declared reason nobody produces is a DEAD WORD — it would be
      quoted as coverage of a case that cannot happen;
    * a reason produced without being declared would escape the table
      entirely — the table would be a partial picture, and the next
      reader would trust it;
    * a reason filed with a kind outside the two would make the verdict
      word arbitrary.
    """

    def test_every_declared_reason_is_actually_produced(self) -> None:
        import inspect

        import evidence.verdict as verdict_module

        source = inspect.getsource(verdict_module.evaluate_verification)
        produced = set(re.findall(r'file_reason\(\s*"([^"]+)"', source))
        declared = set(REASON_TABLE)
        assert declared == produced, (
            "the declared reasons and the produced reasons differ: "
            f"declared-only={sorted(declared - produced)}, "
            f"produced-only={sorted(produced - declared)}"
        )

    def test_every_kind_is_one_of_the_two(self) -> None:
        for key, (_text, kind) in REASON_TABLE.items():
            assert kind in (REASON_BLOCKING, REASON_GAP), (key, kind)

    def test_a_reason_can_only_enter_through_the_table(self) -> None:
        """The table is the ONLY way in — otherwise it is a partial picture."""
        import inspect

        import evidence.verdict as verdict_module

        source = inspect.getsource(verdict_module.evaluate_verification)
        appends = [
            line.strip() for line in source.splitlines()
            if "filed.append" in line
        ]
        assert len(appends) == 1, appends
        # The single append must live inside the file_reason helper, which
        # is the only thing that consults the table.
        helper = source.split("def file_reason", 1)[1].split("\n    passed", 1)[0]
        assert "filed.append" in helper
        assert "reason_text(" in helper
        # …and the helper is the ONLY place that consults the table.
        assert source.count("reason_text(") == 1, (
            "a reason must reach the table through the helper only"
        )

    def test_an_undeclared_reason_raises(self) -> None:
        from evidence.verdict import reason_text

        with pytest.raises(KeyError, match="not a declared reason"):
            reason_text("no_such_reason")

    def test_a_gap_reason_can_coexist_with_a_blocking_one(self) -> None:
        """The table classifies REASONS; the verdict follows from the kinds.

        A broken contract set is both "no valid contract" (a gap) and
        "a row for a contract that does not exist" (a contradiction) —
        and the word is BLOCKED, because a contradiction is present.
        """
        decision = evaluate_verification(
            {"rows": [_row()]}, contracts=[{"id": ""}],
        )
        assert decision.status == "BLOCKED"
        assert any("没有有效的验收契约" in reason for reason in decision.reasons)
        assert not any(
            "没有有效的验收契约" in reason for reason in decision.blocking
        ), "that reason is a gap, and it must stay filed as one"
        assert decision.blocking, "…but the contradiction beside it is blocking"
