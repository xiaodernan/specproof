"""The fake inventory must keep saying what it says.

The queue item "replace the remaining hand-written fakes with an
evaluator" was re-framed by MEASURING what those fakes actually are
(docs/architecture/FAKE_INVENTORY.md): of 265 hand-written fakes, only
20 speak a SQL surface — the ones an evaluator could stand in for. The
rest are store duck types and plain doubles, which an evaluator is NOT
a drop-in for.

That measurement is only worth anything if it stays true. This gate
re-runs the classifier and pins the counts, so the inventory cannot
drift away from the code without somebody noticing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "classify_test_fakes.py"
RULE_SCRIPT = REPO_ROOT / "scripts" / "find_rule_shaped_sql_fakes.py"
INVENTORY = REPO_ROOT / "docs" / "architecture" / "FAKE_INVENTORY.md"


def _classifier():
    spec = importlib.util.spec_from_file_location("classify_test_fakes", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # The module defines a dataclass, and dataclasses look their own
    # module up in sys.modules — so it has to be REGISTERED before it
    # is executed, not just loaded.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_script_runs() -> None:
    module = _classifier()
    fakes = module.collect()
    assert fakes, "the classifier found no fakes at all — it stopped working"


def test_the_counts_are_pinned() -> None:
    """The numbers the inventory quotes.

    A change here means the fakes changed shape — which is worth a
    conversation, not a silent edit of the document.
    """
    module = _classifier()
    fakes = module.collect()
    buckets: dict[str, int] = {
        "sql-fake": 0, "store-duck-type": 0, "plain-double": 0,
    }
    for fake in fakes:
        buckets[fake.kind] += 1

    assert buckets["sql-fake"] == 20, (
        "the SQL-fake count moved; the inventory must be updated with the "
        "reason (see docs/architecture/FAKE_INVENTORY.md)"
    )
    # #545: the total moved 255 -> 265 because TEN classes were added after
    # the #374 pin (git blame on each class definition line, not a guess).
    # Every one is a plain double under the new rule; under the old rule
    # exactly one of them (DummyAdapter) was counted as SQL:
    #   #431 a88fbce  test_adapter_protocol.py::DummyAdapter  (execute-only)
    #   #378 9ac5e9a  test_eval_resume_reuses_measured_cases.py::_FakeGraph
    #   #448 b5e2417  test_job_stage_declared_edges.py::FakeStore
    #   #500 7a7b66b  test_dashboard_window_contract.py::_FakeStore
    #   #505 0dad2d2  test_verify_persistence_failures_are_visible.py::
    #                 _FakeGraph / _RefusingStore / _AcceptingStore
    #   #511 9cfb458  test_verify_contract_list_shows_the_matrix_result.py::
    #                 _FakeGraph
    #   #523 3494441  test_rerank_degradation_cause_is_attributed_and_observable.py::_Store
    #   #524 74f94d8  test_vector_channel_degradation_cause_is_attributed_and_observable.py::_Store
    # The inventory is a MEASUREMENT, so it moves with them.
    assert buckets["store-duck-type"] == 43
    assert buckets["plain-double"] == 202
    assert sum(buckets.values()) == 265


def test_execute_alone_is_not_a_sql_surface() -> None:
    """The collision, pinned at the predicate — not only in the totals.

    The aggregate count can say "one class moved" but not WHY. `execute`
    means two different things in this tree: run a statement, or run a
    build tool (`DummyAdapter`). These four edges keep the exception from
    widening into "ignore execute everywhere": another SQL surface still
    makes the class a SQL fake, and a store surface still wins over a
    lone execute.
    """
    module = _classifier()
    fake = module.FakeClass

    def kind(methods: list[str]) -> str:
        return fake(path="x", line=1, name="FakeX", methods=methods).kind

    assert kind(["execute"]) == "plain-double"
    assert kind(["execute", "cursor"]) == "sql-fake"
    assert kind(["execute", "save"]) == "store-duck-type"
    assert kind(["cursor"]) == "sql-fake"


def test_the_inventory_quotes_the_measured_numbers() -> None:
    """The document and the measurement must agree."""
    module = _classifier()
    fakes = module.collect()
    sql = sum(1 for f in fakes if f.kind == "sql-fake")
    stores = sum(1 for f in fakes if f.kind == "store-duck-type")
    plain = sum(1 for f in fakes if f.kind == "plain-double")

    text = INVENTORY.read_text(encoding="utf-8")
    assert f"| **SQL 假** | **{sql}** |" in text
    assert f"| 仓储鸭子类型 | {stores} |" in text
    assert f"| 普通替身 | {plain} |" in text
    assert f"一共 {len(fakes)} 个" in text


def test_no_sql_fake_decides_by_the_statement_text() -> None:
    """A fake that DECIDES by the SQL text is a second opinion.

    That is the shape a query evaluator replaces — the fake decides what
    the statement means, and the production WHERE clause never has to
    agree with it. The measurement found exactly two, and both dispatch
    on the QUESTION ("is this a COUNT? an existence probe?"), not on a
    rule about the data — so replacing them would change what the test
    measures.

    If this gate goes red, a fake started deciding by the statement's
    meaning: either it becomes the evaluator's job, or the reason it
    genuinely needs its own rule is written down here.
    """
    spec = importlib.util.spec_from_file_location(
        "find_rule_shaped_sql_fakes", RULE_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    found = module.collect()
    assert len(found) == 2, (
        "the set of SQL fakes that decide by the statement text moved: "
        + "; ".join(f"{f.path}:{f.line} {f.name}" for f in found)
    )
    # And the two that remain are the ones the inventory names, with the
    # reason they stay.
    names = {f.name for f in found}
    assert names == {"_FakeCursor", "FakeCursor"}
    text = INVENTORY.read_text(encoding="utf-8")
    assert "test_audit_action_parity.py::_FakeCursor" in text
    assert "test_web_api.py::FakeCursor" in text
    assert "不换" in text
