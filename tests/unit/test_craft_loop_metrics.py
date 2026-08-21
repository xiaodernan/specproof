"""W44 craft-loop metrics wiring tests — no live LLM, no network.

The loop's LLM diagnosis path is exercised with fakes: a recording client
plays canned model outputs (JSON edit proposals or JSON Action Envelopes),
a fake router/cache feed the routing/caching bookkeeping, and the real
ToolCallSelfCheck validates envelopes with the model round-trip injected
as the producer callable. Covers: success-rate math, checker counters,
router fallback counting, cache-hit skipping, the judge-persona flag and
the zero-filled gains block of an unconfigured loop.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from craft.editor import Editor
from craft.llm import LLMUnavailableError
from craft.loop import CraftLoop, CraftLoopError
from craft.planner import Step, compile_plan
from craft.spec import parse_spec_text
from craft.tools import ToolRegistry
from providers.router import ProviderRoute
from providers.toolcheck import ToolCallSelfCheck

FIX_SPEC = "修复 double 函数的逻辑错误\n验收: test_double 测试通过\n影响: calc.py"

_VALID_PROPOSAL = json.dumps({
    "diagnosis": "double 除错了, 应改为乘 2",
    "edits": [
        {
            "action": "apply_edit",
            "path": "calc.py",
            "old": "return x / 2",
            "new": "return x * 2",
        }
    ],
})

_CACHED_OPS = [
    {
        "action": "apply_edit",
        "path": "calc.py",
        "old": "return x / 2",
        "new": "return x * 2",
    }
]

_VALID_ENVELOPE = json.dumps({
    "action": "apply_patch",
    "version": 1,
    "params": {"path": "calc.py", "old": "return x / 2", "new": "return x * 2"},
})

_BAD_VERSION_ENVELOPE = json.dumps({
    "action": "apply_patch",
    "version": 99,
    "params": {"path": "calc.py", "old": "return x / 2", "new": "return x * 2"},
})


class FakeResponse:
    """LLMResponse stand-in: the loop only reads .content."""

    def __init__(self, content: str) -> None:
        self.content = content


class FakeBudget:
    used = 0.0


class FakeClient:
    """Recording chat_sync: pops one canned outcome per call (str content
    or an exception to raise). No network, no live LLM."""

    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.call_count = 0
        self.prompts: list[str] = []
        self.budget = FakeBudget()

    def chat_sync(self, messages: list[Any], **kwargs: object) -> FakeResponse:
        self.call_count += 1
        prompt = "".join(
            str(message.content) for message in messages if message.role == "user"
        )
        self.prompts.append(prompt)
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return FakeResponse(str(item))

    def stats_report(self) -> dict[str, int]:
        return {"calls": self.call_count}


class FakeRouter:
    """Records route() calls; counts on_failure() like the real router."""

    def __init__(self, tier: str = "strong") -> None:
        self.tier = tier
        self.route_calls: list[str] = []
        self.fallback_count = 0

    def route(self, task_kind: str) -> ProviderRoute:
        self.route_calls.append(task_kind)
        return ProviderRoute(tier=self.tier, base_url="", model="fake-model")

    def on_failure(self, route: ProviderRoute) -> ProviderRoute:
        self.fallback_count += 1
        return ProviderRoute(
            tier="strong", base_url="", model="fake-model", is_fallback=True
        )


class FakeCache:
    """Duck-typed SemanticCache: optional canned hit, put recording."""

    def __init__(
        self, hit: dict[str, Any] | None = None, *, miss: bool = False
    ) -> None:
        self._value = hit
        self._miss = miss
        self.hits = 0
        self.misses = 0
        self.puts: list[tuple[str, object]] = []

    def get(self, key: str) -> Any:
        if self._miss or self._value is None:
            self.misses += 1
            return None
        self.hits += 1
        return self._value

    def put(self, key: str, value: object, *, kind: str) -> None:
        self.puts.append((key, value))


def write_fixture_repo(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(
        "def double(x):\n    return x / 2\n\n\ndef greeting(name):\n"
        '    return "hello " + name\n',
        encoding="utf-8",
    )
    (tmp_path / "test_calc.py").write_text(
        "from calc import double, greeting\n\n\n"
        "def test_double():\n    assert double(4) == 8\n\n\n"
        'def test_greeting():\n    assert greeting("a") == "hello a"\n',
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['.']\n", encoding="utf-8"
    )


def fix_double(editor: Editor, step: Step, diagnosis: str) -> list[str]:
    editor.apply_edit("calc.py", "return x / 2", "return x * 2")
    return ["calc.py"]


def make_llm_loop(
    tmp_path: Path,
    client: FakeClient,
    *,
    tool_registry: ToolRegistry | None = None,
    self_check: ToolCallSelfCheck | None = None,
    router: FakeRouter | None = None,
    cache: FakeCache | None = None,
    judge_persona: bool = False,
) -> CraftLoop:
    write_fixture_repo(tmp_path)
    spec = parse_spec_text(FIX_SPEC)
    plan = dataclasses.replace(compile_plan(spec), mode="llm")
    return CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-w44",
        exec_mode="local",
        client=client,
        tool_registry=tool_registry,
        tool_call_self_check=self_check,
        router=router,
        semantic_cache=cache,
        judge_persona=judge_persona,
    )


def make_envelope_loop(tmp_path: Path, client: FakeClient) -> CraftLoop:
    registry = ToolRegistry(tmp_path)
    return make_llm_loop(
        tmp_path,
        client,
        tool_registry=registry,
        self_check=ToolCallSelfCheck.from_registry(registry),
    )


def fixed(tmp_path: Path) -> bool:
    return "return x * 2" in (tmp_path / "calc.py").read_text(encoding="utf-8")


# -- unconfigured -> zero-filled gains ---------------------------------------


def test_unconfigured_loop_reports_zero_gains(tmp_path: Path) -> None:
    """No W44 knobs at all: the deterministic M1 path still writes a
    stable gains block with every field present and zero."""
    write_fixture_repo(tmp_path)
    spec = parse_spec_text(FIX_SPEC)
    plan = compile_plan(spec)
    loop = CraftLoop(
        spec,
        plan,
        tmp_path,
        job_id="job-plain",
        exec_mode="local",
        fix_registry={"test": fix_double},
    )
    report = loop.run()
    assert report["result"] == "DONE"
    assert report["gains"] == {
        "tool_call_attempts": 0,
        "tool_call_valid": 0,
        "tool_call_retried": 0,
        "tool_call_success_rate": 0.0,
        "router_fallback_count": 0,
        "cache_hits": 0,
        "judge_persona_applied": 0,
    }


def test_self_check_without_registry_raises_at_construction(tmp_path: Path) -> None:
    """The envelope path executes through the registry; without one the
    wiring refuses to build instead of failing mid-run."""
    write_fixture_repo(tmp_path)
    spec = parse_spec_text(FIX_SPEC)
    plan = dataclasses.replace(compile_plan(spec), mode="llm")
    registry = ToolRegistry(tmp_path)
    try:
        CraftLoop(
            spec,
            plan,
            tmp_path,
            job_id="job-bad",
            exec_mode="local",
            tool_call_self_check=ToolCallSelfCheck.from_registry(registry),
        )
    except CraftLoopError as exc:
        assert "tool_registry" in str(exc)
    else:
        raise AssertionError("self-check without registry must refuse to build")


# -- self-check counters and success-rate math --------------------------------


def test_valid_envelope_counters_and_success_rate(tmp_path: Path) -> None:
    client = FakeClient([_VALID_ENVELOPE])
    loop = make_envelope_loop(tmp_path, client)
    report = loop.run()
    assert report["result"] == "DONE"
    assert fixed(tmp_path)
    gains = report["gains"]
    assert gains["tool_call_attempts"] == 1
    assert gains["tool_call_valid"] == 1
    assert gains["tool_call_retried"] == 0
    assert gains["tool_call_success_rate"] == 1.0
    assert client.call_count == 1
    assert report["tool_registry"]["dispatches"] == 1


def test_retried_envelope_success_rate_math(tmp_path: Path) -> None:
    """One invalid envelope arms exactly one retry; 2 attempts, 1 valid ->
    success rate 0.5, and the retry instruction reached the model."""
    client = FakeClient([_BAD_VERSION_ENVELOPE, _VALID_ENVELOPE])
    loop = make_envelope_loop(tmp_path, client)
    report = loop.run()
    assert report["result"] == "DONE"
    assert fixed(tmp_path)
    gains = report["gains"]
    assert gains["tool_call_attempts"] == 2
    assert gains["tool_call_valid"] == 1
    assert gains["tool_call_retried"] == 1
    assert gains["tool_call_success_rate"] == 0.5
    assert client.call_count == 2
    assert "TOOL CALL SELF-CHECK" in client.prompts[1]


def test_unparseable_envelope_arms_the_checker_retry(tmp_path: Path) -> None:
    """Non-JSON model output goes through the checker as 'not a JSON
    object' and consumes the single retry before the valid envelope."""
    client = FakeClient(["no json here at all", _VALID_ENVELOPE])
    loop = make_envelope_loop(tmp_path, client)
    report = loop.run()
    assert report["result"] == "DONE"
    assert fixed(tmp_path)
    gains = report["gains"]
    assert gains["tool_call_attempts"] == 2
    assert gains["tool_call_valid"] == 1
    assert gains["tool_call_retried"] == 1
    assert gains["tool_call_success_rate"] == 0.5


def test_give_up_after_second_invalid_envelope_fails_honestly(
    tmp_path: Path,
) -> None:
    """Two invalid envelopes: give_up with the stable registry error code,
    the step FAILED with M1 semantics and the gains carry the counters."""
    client = FakeClient([_BAD_VERSION_ENVELOPE, _BAD_VERSION_ENVELOPE])
    loop = make_envelope_loop(tmp_path, client)
    report = loop.run()
    assert report["result"] == "FAILED"
    assert not fixed(tmp_path)
    gains = report["gains"]
    assert gains["tool_call_attempts"] == 2
    assert gains["tool_call_valid"] == 0
    assert gains["tool_call_retried"] == 1
    assert gains["tool_call_success_rate"] == 0.0
    steps = {step["id"]: step for step in report["steps"]}
    reason = steps["s3"]["evidence"]["reason"]
    assert "信封自检未通过" in reason
    assert "TOOL_VERSION_MISMATCH" in reason


# -- router wiring ------------------------------------------------------------


def test_router_routes_diagnose_and_counts_cheap_fallback(tmp_path: Path) -> None:
    """router.route('diagnose') runs for the LLM diagnosis path; a cheap-tier
    failure falls back to one strong retry and the fallback is counted."""
    router = FakeRouter(tier="cheap")
    client = FakeClient([LLMUnavailableError("cheap gateway down"), _VALID_PROPOSAL])
    loop = make_llm_loop(tmp_path, client, router=router)
    report = loop.run()
    assert report["result"] == "DONE"
    assert fixed(tmp_path)
    assert router.route_calls == ["diagnose"]
    assert router.fallback_count == 1
    assert client.call_count == 2
    assert report["gains"]["router_fallback_count"] == 1
    assert "JUDGE INTEGRITY PERSONA" not in client.prompts[0]


def test_strong_tier_never_falls_back(tmp_path: Path) -> None:
    """A strong route failing is a plain honest LLM-unavailable FAILED —
    no fallback bookkeeping, no retry."""
    router = FakeRouter(tier="strong")
    client = FakeClient([LLMUnavailableError("strong gateway down")])
    loop = make_llm_loop(tmp_path, client, router=router)
    report = loop.run()
    assert report["result"] == "FAILED"
    assert router.fallback_count == 0
    assert client.call_count == 1
    assert report["gains"]["router_fallback_count"] == 0
    steps = {step["id"]: step for step in report["steps"]}
    assert "LLM unavailable" in steps["s3"]["evidence"]["reason"]


# -- semantic cache wiring -----------------------------------------------------


def test_cache_hit_skips_the_llm_round_trip(tmp_path: Path) -> None:
    """A cached diagnose result applies without any model call and the
    cache's own hits counter flows into the gains block."""
    cache = FakeCache(hit={"explanation": "缓存命中", "ops": _CACHED_OPS})
    client = FakeClient([])
    loop = make_llm_loop(tmp_path, client, cache=cache)
    report = loop.run()
    assert report["result"] == "DONE"
    assert fixed(tmp_path)
    assert client.call_count == 0
    assert cache.hits == 1
    assert report["gains"]["cache_hits"] == 1


def test_cache_miss_fills_the_cache_and_reports_zero_hits(tmp_path: Path) -> None:
    """A miss computes through the LLM, stores the parsed ops, and the
    gains block still reports the cache's hits counter (zero)."""
    cache = FakeCache(miss=True)
    client = FakeClient([_VALID_PROPOSAL])
    loop = make_llm_loop(tmp_path, client, cache=cache)
    report = loop.run()
    assert report["result"] == "DONE"
    assert fixed(tmp_path)
    assert client.call_count == 1
    assert cache.misses == 1
    assert len(cache.puts) == 1
    assert cache.puts[0][1] == {
        "explanation": "double 除错了, 应改为乘 2",
        "ops": _CACHED_OPS,
    }
    assert report["gains"]["cache_hits"] == 0


# -- judge persona flag ---------------------------------------------------------


def test_judge_persona_applied_to_the_diagnose_prompt(tmp_path: Path) -> None:
    client = FakeClient([_VALID_PROPOSAL])
    loop = make_llm_loop(tmp_path, client, judge_persona=True)
    report = loop.run()
    assert report["result"] == "DONE"
    assert "JUDGE INTEGRITY PERSONA" in client.prompts[0]
    assert report["gains"]["judge_persona_applied"] == 1
