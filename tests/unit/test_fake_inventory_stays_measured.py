"""The fake inventory must keep saying what it says.

The queue item "replace the remaining hand-written fakes with an
evaluator" was re-framed by MEASURING what those fakes actually are
(docs/architecture/FAKE_INVENTORY.md): of 252 hand-written fakes, only
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
    assert buckets["store-duck-type"] == 42
    assert sum(buckets.values()) == 252


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
