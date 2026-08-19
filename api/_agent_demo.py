"""Bundled deterministic demo task for the Web Agent Console (W42).

POST /agent/jobs must work out-of-the-box without a real repo path: this
module materializes the calc.py double-fix fixture from
tests/unit/test_craft_verify.py (FIX_SPEC) into a fresh temp workspace and
exports the explicitly injected M1 fix rule — the same deterministic path
scripts/bench_craft.py drives via --no-llm --fix-module. No LLM, no
network, no Docker: the spec is parsed by rule templates, the plan comes
from craft/planner's deterministic engine and the fix is the exact
apply_edit the unit tests use.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from craft.editor import Editor
from craft.loop import FixFunction
from craft.planner import Step

#: Task label shown in the console meta when the bundled demo is used.
DEMO_TASK_NAME = "console-demo-calc-fix"

#: The FIX_SPEC from tests/unit/test_craft_verify.py — title + 验收 + 影响.
DEMO_SPEC_TEXT = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

#: Buggy calc.py (double() divides instead of multiplies).
CALC_BODY = (
    'def double(x):\n    return x / 2\n\n\ndef greeting(name):\n'
    '    return "hello " + name\n'
)

#: The judge test suite the loop must turn green.
TEST_CALC_BODY = (
    "from calc import double, greeting\n\n\n"
    "def test_double():\n    assert double(4) == 8\n\n\n"
    'def test_greeting():\n    assert greeting("a") == "hello a"\n'
)


def fix_double(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    """Deterministic double-fix: replace the /2 bug with *2 (M1, explicit).

    Registered under the "test" step kind, exactly like the bench tasks'
    fixes.py and tests/unit/test_craft_loop.py. ``diagnosis`` is the rule
    template's expected/actual extraction; it is not used to invent the
    edit — the edit is hard-coded by the injected rule.
    """
    editor.apply_edit("calc.py", "return x / 2", "return x * 2")
    return ["calc.py"]


#: Explicitly injected fix registry for the demo (step kind "test" -> fix).
DEMO_FIX_REGISTRY: dict[str, FixFunction] = {"test": fix_double}


def materialize_demo_workspace(parent: Path) -> Path:
    """Create a fresh demo workspace under *parent* and return its path.

    A new temp directory is created per call so concurrent demo jobs never
    share state; calc.py carries the bug and test_calc.py the judge test.
    """
    parent.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="demo-calc-", dir=parent))
    (workspace / "calc.py").write_text(CALC_BODY, encoding="utf-8")
    (workspace / "test_calc.py").write_text(TEST_CALC_BODY, encoding="utf-8")
    return workspace
