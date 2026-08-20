"""Offline regression tests for the v10 real-run fixes (W163) — no network.

Real eval evidence (docs/eval/swebench-llm-results-v10.json, real
deepseek-v4-pro runs):

- pallets__flask-4045 FAILED s5 with 'LLM unavailable: LLM 调用失败:
  APITimeoutError: Request timed out.' — a TRANSIENT gateway timeout on a
  diagnose chat call killed the step. A transient timeout must be retried
  (with backoff) before surfacing as LLMUnavailableError.
- pallets__flask-4992 STUCK: the model re-proposed the SAME edit
  repeatedly (W156 catches it as [LLM_PROPOSAL_REPEATED] at 3x). The
  repair instruction on a repeat must demand a DIFFERENT approach.

Covers:

- (a) a transient APITimeoutError on the first chat call retries exactly
  twice with the configured backoff, then succeeds — retries recorded;
- (b) two timeouts then a third timeout -> LLMUnavailableError honest
  FAILED with the retry count on record (report.llm_usage.timeout_retries
  + report.llm_timeout_retries);
- (c) a repeated proposal arms exactly ONE diversified instruction
  (contains 'DIFFERENT' and the canonical summary of the previous
  proposal), and a different proposal then converges DONE;
- (d) a diversified retry that returns the identical proposal again falls
  back to the M1 3x counting ([LLM_PROPOSAL_REPEATED] ->
  同类错误连续 3 次 -> STUCK) — W158/W161 semantics preserved;
- (e) non-timeout failures keep the immediate LLMUnavailableError (no
  retries, no backoff).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from craft.llm import LLMClient, LLMUnavailableError, _is_transient_timeout
from craft.loop import CraftLoop
from craft.planner import compile_plan
from craft.spec import parse_spec_text
from providers.base import LLMMessage, LLMResponse

FIX_SPEC_NO_REF = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

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

DIFFERENT_PROPOSAL = json.dumps(
    {
        "diagnosis": "换成真正的乘法修复",
        "edits": [
            {
                "action": "apply_edit",
                "path": "calc.py",
                "old": "return x / 3",
                "new": "return x * 2",
            }
        ],
    },
    ensure_ascii=False,
)


class APITimeoutError(TimeoutError):
    """Offline stand-in for openai.APITimeoutError (type-name detected)."""


class _FaultyProvider:
    """Offline provider stub: chat() raises exc for the first failures
    calls, then replies with canned content. No network, no API key."""

    def __init__(self, failures: int, exc: BaseException, reply: str = "") -> None:
        self.failures = failures
        self.exc = exc
        self.reply = reply
        self.calls = 0

    async def chat(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        del messages
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc
        usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        return LLMResponse(content=self.reply, usage=usage, model="fake-w163")


class _ScriptedClient(LLMClient):
    """chat_sync override replaying canned replies; captures every prompt."""

    def __init__(self, replies: list[str], *, job_id: str = "job-w163") -> None:
        super().__init__(provider=None, token_budget=100_000, job_id=job_id)
        self._replies = list(replies)
        self.call_count = 0
        self.prompts: list[str] = []

    def chat_sync(self, messages: list[LLMMessage], **kwargs: Any) -> LLMResponse:
        self.call_count += 1
        prompt = "".join(
            str(message.content) for message in messages if message.role == "user"
        )
        self.prompts.append(prompt)
        reply = self._replies[min(self.call_count - 1, len(self._replies) - 1)]
        usage = {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
        label = str(kwargs.get("label") or "diagnose")
        self.budget.record(usage, label=label)
        return LLMResponse(content=reply, usage=usage, model="fake-w163")


def _write_fixture_repo(tmp_path: Path) -> None:
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
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['.']\n", encoding="utf-8"
    )


def _make_llm_loop(
    tmp_path: Path,
    client: LLMClient,
    *,
    job_id: str,
) -> CraftLoop:
    spec = parse_spec_text(FIX_SPEC_NO_REF)
    plan = compile_plan(spec)
    return CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id=job_id,
        exec_mode="local",
        client=client,
    )


# -- (a) transient timeout retries twice, then succeeds ----------------------


def test_transient_timeout_retries_twice_then_succeeds() -> None:
    """(a) A transient APITimeoutError on the first chat call is retried
    exactly twice with the configured backoff, then the call succeeds —
    and every retry is recorded."""
    provider = _FaultyProvider(
        failures=2,
        exc=APITimeoutError("Request timed out."),
        reply='{"ok": true}',
    )
    client = LLMClient(
        provider=provider,  # type: ignore[arg-type]  # duck-typed offline stub
        token_budget=100_000,
        timeout_retry_backoffs=(0.0, 0.0),
    )
    try:
        response = client.chat_sync(
            [LLMMessage(role="user", content="hi")], label="diagnose"
        )
    finally:
        client.close()
    assert response.content == '{"ok": true}'
    assert provider.calls == 3  # first attempt + 2 retries
    assert client.timeout_retries == 2
    assert client.stats_report()["timeout_retries"] == 2


def test_transient_timeout_classification_by_type_and_text() -> None:
    """The transient-timeout classifier covers APITimeoutError, the
    builtin TimeoutError and 'Request timed out' text — other failures
    are not transient."""
    assert _is_transient_timeout(APITimeoutError("Request timed out.")) is True
    assert _is_transient_timeout(TimeoutError("read timed out")) is True
    assert _is_transient_timeout(RuntimeError("Request timed out.")) is True
    assert _is_transient_timeout(ValueError("boom")) is False
    assert _is_transient_timeout(LLMUnavailableError("LLM_API_KEY 未设置")) is False


# -- (b) exhausted timeouts -> honest FAILED with retry count ----------------



def test_exhausted_timeouts_fail_honestly_with_retry_count(tmp_path: Path) -> None:
    """(b) Two retries then a third timeout: the step fails honestly as
    LLMUnavailableError (FAILED, never faked) and the retry count is
    auditable in report.llm_usage.timeout_retries and
    report.llm_timeout_retries."""
    _write_fixture_repo(tmp_path)
    provider = _FaultyProvider(
        failures=3,
        exc=TimeoutError("Request timed out."),
    )
    client = LLMClient(
        provider=provider,  # type: ignore[arg-type]  # duck-typed offline stub
        token_budget=100_000,
        timeout_retry_backoffs=(0.0, 0.0),
    )
    try:
        loop = _make_llm_loop(tmp_path, client, job_id="job-b")
        report = loop.run()
    finally:
        client.close()
    assert report["result"] == "FAILED"
    steps = {step["id"]: step for step in report["steps"]}
    assert steps["s3"]["status"] == "failed"
    reason = steps["s3"]["evidence"]["reason"]
    assert "LLM unavailable" in reason
    assert "LLM 调用失败" in reason
    assert "TimeoutError" in reason
    assert "Request timed out" in reason
    assert "迭代预算超限" not in reason
    assert report["budget_used"]["iterations"] == 1
    assert provider.calls == 3  # first attempt + 2 retries
    assert report["llm_usage"]["timeout_retries"] == 2
    assert report["llm_timeout_retries"] == 2


# -- (c) repeat arms ONE diversified instruction, then converges --------------


def test_repeat_arms_one_diversified_instruction_then_different_converges(
    tmp_path: Path,
) -> None:
    """(c) An exact repeat of an already-attempted proposal is rejected
    (never executed), arms exactly ONE diversified instruction for the
    next diagnose call — it lists the previous canonical proposal and
    demands a DIFFERENT fix path — and a different proposal then
    converges DONE."""
    _write_fixture_repo(tmp_path)
    client = _ScriptedClient(
        [BAD_PROPOSAL, BAD_PROPOSAL, DIFFERENT_PROPOSAL], job_id="job-c"
    )
    loop = _make_llm_loop(tmp_path, client, job_id="job-c")
    report = loop.run()
    assert report["result"] == "DONE"
    assert client.call_count == 3  # no extra LLM call for the retry
    assert client.prompts[0].count("DIFFERENT") == 0
    assert client.prompts[1].count("DIFFERENT") == 0
    instruction_prompt = client.prompts[2]
    assert instruction_prompt.count("DIFFERENT") == 1
    assert "identical to an earlier attempt" in instruction_prompt
    assert "do NOT repeat any previous edit" in instruction_prompt
    assert "apply_edit calc.py" in instruction_prompt
    assert "return x / 2" in instruction_prompt  # previous proposal summary
    assert "return x / 3" in instruction_prompt  # previous proposal summary
    assert "return x * 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")


# -- (d) diversified retry identical again -> M1 3x STUCK --------------------


def test_diversified_retry_returning_identical_falls_back_to_m1_3x_stuck(
    tmp_path: Path,
) -> None:
    """(d) The diversified retry returns the identical proposal again: the
    W158 M1 counting takes over — the 3rd consecutive repeat trips the
    documented 同类错误连续 3 次 -> STUCK rule with the
    [LLM_PROPOSAL_REPEATED] signature, and the repeat is never executed."""
    _write_fixture_repo(tmp_path)
    client = _ScriptedClient([BAD_PROPOSAL], job_id="job-d")
    loop = _make_llm_loop(tmp_path, client, job_id="job-d")
    report = loop.run()
    steps = {step["id"]: step for step in report["steps"]}
    assert report["result"] == "STUCK"
    assert steps["s3"]["status"] == "stuck"
    reason = steps["s3"]["evidence"]["reason"]
    assert "[LLM_PROPOSAL_REPEATED]" in reason
    assert "第 1 次迭代" in reason
    assert "同类错误连续 3 次" in reason
    assert "迭代预算超限" not in reason
    assert client.call_count == 4  # identical to the W156/W158 no-retry shape
    assert sum(1 for prompt in client.prompts if "DIFFERENT" in prompt) == 1
    assert report["budget_used"]["iterations"] == 4
    file_text = (tmp_path / "calc.py").read_text(encoding="utf-8")
    assert "return x / 3" in file_text  # the repeat was never executed
    assert "return x * 2" not in file_text


# -- (e) non-timeout failures keep the immediate behavior --------------------


def test_non_timeout_failure_keeps_immediate_behavior() -> None:
    """(e) A non-timeout provider failure is NOT retried: it surfaces as
    LLMUnavailableError on the first hit with zero recorded retries."""
    provider = _FaultyProvider(failures=5, exc=ValueError("boom"))
    client = LLMClient(
        provider=provider,  # type: ignore[arg-type]  # duck-typed offline stub
        token_budget=100_000,
        timeout_retry_backoffs=(0.0, 0.0),
    )
    try:
        with pytest.raises(LLMUnavailableError) as excinfo:
            client.chat_sync(
                [LLMMessage(role="user", content="hi")], label="diagnose"
            )
    finally:
        client.close()
    assert "ValueError" in str(excinfo.value)
    assert "boom" in str(excinfo.value)
    assert provider.calls == 1
    assert client.timeout_retries == 0
    assert client.stats_report()["timeout_retries"] == 0

