"""Offline regression tests for the v9 real-run fixes (W156) — no network/LLM.

Real eval evidence (docs/eval/swebench-llm-results-v9.json, real
deepseek-v4-pro runs):

- pallets__flask-4045 STUCK at s3: the craft loop's TEST step ran pytest
  over the WHOLE repo suite, and the old flask commit's tests/test_cli.py
  fails collection under the modern venv pytest ("Interrupted: 1 error
  during collection").
- pallets__flask-4992 FAILED s6 (迭代预算超限): the diagnose/edit loop
  iterated all 12 budgeted rounds re-proposing the same edits.

Covers:

- (a) the LLM-path test_green pytest command always carries
  --continue-on-collection-errors; the deterministic command stays
  byte-identical;
- (b) the command scopes to the spec-referenced real test file when one is
  referenced, and the scoped run really skips an unrelated
  collection-error file (real pytest in a tmp fixture);
- (c) an exact repeat of an already-attempted edit proposal fails the step
  with the stable code [LLM_PROPOSAL_REPEATED] and stops calling the model;
- (d) a genuinely different proposal still gets a new iteration.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from craft.executor import Executor
from craft.llm import LLMClient
from craft.loop import CraftLoop
from craft.planner import compile_plan
from craft.spec import parse_spec_text
from providers.base import LLMMessage, LLMResponse

FIX_SPEC_NO_REF = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

SPEC_WITH_REF = (
    "修复 double 函数的逻辑错误\n"
    "参考 tests/test_calc.py::test_double 的失败断言\n"
    "验收: test_double 测试通过\n"
    "影响: calc.py"
)

GOOD_PROPOSAL = json.dumps(
    {
        "diagnosis": "double() 把乘法写成了除法, 应改为乘 2",
        "edits": [
            {
                "action": "apply_edit",
                "path": "calc.py",
                "old": "return x / 2",
                "new": "return x * 2",
            }
        ],
    },
    ensure_ascii=False,
)

BAD_PROPOSAL = json.dumps(
    {
        "diagnosis": "把除数改成 3 试试",
        "edits": [
            {
                "action": "apply_edit",
                "path": "calc.py",
                "old": "return x / 2",
                "new": "return x / 3",
            }
        ],
    },
    ensure_ascii=False,
)

BAD_PROPOSAL_B = json.dumps(
    {
        "diagnosis": "改成减一试试",
        "edits": [
            {
                "action": "apply_edit",
                "path": "calc.py",
                "old": "return x / 3",
                "new": "return x - 1",
            }
        ],
    },
    ensure_ascii=False,
)

GOOD_PROPOSAL_LAST = json.dumps(
    {
        "diagnosis": "回到乘法修复",
        "edits": [
            {
                "action": "apply_edit",
                "path": "calc.py",
                "old": "return x - 1",
                "new": "return x * 2",
            }
        ],
    },
    ensure_ascii=False,
)


class _ScriptedClient(LLMClient):
    """chat_sync override replaying canned replies; counts every call."""

    def __init__(self, replies: list[str], *, job_id: str = "job-w156") -> None:
        super().__init__(provider=None, token_budget=100_000, job_id=job_id)
        self._replies = list(replies)
        self.call_count = 0

    def chat_sync(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        del messages
        self.call_count += 1
        reply = self._replies[min(self.call_count - 1, len(self._replies) - 1)]
        usage = {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
        label = str(kwargs.get("label") or "diagnose")
        self.budget.record(usage, label=label)
        return LLMResponse(content=reply, usage=usage, model="fake-w156")


def _write_fixture_repo(tmp_path: Path, *, broken_test: bool = False) -> None:
    (tmp_path / "calc.py").write_text(
        "def double(x):\n    return x / 2\n\n\ndef greeting(name):\n"
        '    return "hello " + name\n',
        encoding="utf-8",
    )
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_calc.py").write_text(
        "from calc import double, greeting\n\n\n"
        "def test_double():\n    assert double(4) == 8\n\n\n"
        'def test_greeting():\n    assert greeting("a") == "hello a"\n',
        encoding="utf-8",
    )
    if broken_test:
        (tests_dir / "test_unrelated_broken.py").write_text(
            "import no_such_module_for_sure_xyz\n", encoding="utf-8"
        )
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['.']\n", encoding="utf-8"
    )


def _make_loop(
    tmp_path: Path,
    spec_text: str,
    *,
    job_id: str,
    client: _ScriptedClient | None = None,
) -> CraftLoop:
    spec = parse_spec_text(spec_text)
    plan = compile_plan(spec)
    return CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id=job_id,
        exec_mode="local",
        client=client,
    )


# -- (a) collection-error tolerance on the LLM-path test command -------------


def test_llm_test_command_always_tolerates_collection_errors(tmp_path: Path) -> None:
    """(a) The LLM-path test_green pytest command always carries
    --continue-on-collection-errors; with no referenced test file the whole
    suite still runs instead of aborting."""
    _write_fixture_repo(tmp_path)
    loop = _make_loop(tmp_path, FIX_SPEC_NO_REF, client=_ScriptedClient([]), job_id="job-a")
    assert loop._build_test_step_command() == [
        "python",
        "-m",
        "pytest",
        "-q",
        "--continue-on-collection-errors",
    ]


def test_deterministic_test_command_stays_byte_identical(tmp_path: Path) -> None:
    """The deterministic path keeps the pre-W156 pytest command verbatim —
    even when the spec references a test file, scoping never touches it."""
    _write_fixture_repo(tmp_path)
    loop = _make_loop(tmp_path, SPEC_WITH_REF, job_id="job-det")
    assert loop._build_test_step_command() == ["python", "-m", "pytest", "-q"]


# -- (b) scoping to the referenced test file ---------------------------------


def test_llm_test_command_scopes_to_the_spec_referenced_test_file(
    tmp_path: Path,
) -> None:
    """(b) A test file referenced by the problem statement scopes the
    LLM-path pytest run to that file (resolved to a real workspace file)."""
    _write_fixture_repo(tmp_path)
    loop = _make_loop(tmp_path, SPEC_WITH_REF, client=_ScriptedClient([]), job_id="job-b")
    assert loop._build_test_step_command() == [
        "python",
        "-m",
        "pytest",
        "-q",
        "--continue-on-collection-errors",
        "tests/test_calc.py",
    ]


def test_scoped_test_step_skips_unrelated_collection_errors(tmp_path: Path) -> None:
    """End-to-end with real pytest: on a fixture whose unrelated test file
    fails collection, the OLD whole-suite command aborts with exit 2
    ("Interrupted: 1 error during collection") while the scoped LLM-path
    run converges DONE without ever collecting the broken file."""
    _write_fixture_repo(tmp_path, broken_test=True)
    before = Executor(tmp_path, mode="local").run(["python", "-m", "pytest", "-q"])
    assert before.exit_code == 2
    assert "error during collection" in before.output_tail

    client = _ScriptedClient([GOOD_PROPOSAL])
    loop = _make_loop(tmp_path, SPEC_WITH_REF, client=client, job_id="job-llm-e2e")
    report = loop.run()
    steps = {step["id"]: step for step in report["steps"]}
    assert report["result"] == "DONE"
    assert steps["s3"]["status"] == "green"
    assert steps["s3"]["evidence"]["exit_code"] == 0
    assert client.call_count == 1
    assert "return x * 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")


# -- (c) repeated identical proposal -> [LLM_PROPOSAL_REPEATED] --------------


def test_repeated_identical_proposal_fails_with_stable_code(tmp_path: Path) -> None:
    """(c) An exact repeat of an already-attempted proposal fails the step
    with [LLM_PROPOSAL_REPEATED] naming the first iteration, executes
    nothing and makes no further LLM call — the budget is preserved."""
    _write_fixture_repo(tmp_path)
    client = _ScriptedClient([BAD_PROPOSAL, BAD_PROPOSAL, BAD_PROPOSAL])
    loop = _make_loop(tmp_path, FIX_SPEC_NO_REF, client=client, job_id="job-c")
    report = loop.run()
    steps = {step["id"]: step for step in report["steps"]}
    assert report["result"] == "FAILED"
    assert steps["s3"]["status"] == "failed"
    reason = steps["s3"]["evidence"]["reason"]
    assert "[LLM_PROPOSAL_REPEATED]" in reason
    assert "第 1 次迭代" in reason
    assert "迭代预算超限" not in reason
    assert client.call_count == 2
    assert report["budget_used"]["iterations"] == 2
    assert "return x / 3" in (tmp_path / "calc.py").read_text(encoding="utf-8")


# -- (d) a genuinely different proposal still iterates -----------------------


def test_genuinely_different_proposal_gets_a_new_iteration(tmp_path: Path) -> None:
    """(d) Proposals that differ (action/path/old/new) keep iterating: three
    distinct proposals converge DONE without any false-positive repeat."""
    _write_fixture_repo(tmp_path)
    client = _ScriptedClient([BAD_PROPOSAL, BAD_PROPOSAL_B, GOOD_PROPOSAL_LAST])
    loop = _make_loop(tmp_path, FIX_SPEC_NO_REF, client=client, job_id="job-d")
    report = loop.run()
    assert report["result"] == "DONE"
    assert client.call_count == 3
    assert "return x * 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")
