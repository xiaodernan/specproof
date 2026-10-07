"""#210: the provider boundary is metred — every logical LLM call is visible.

chat()/chat_stream() are the only entry points every LLM lane shares (agent
nodes, craft/llm.py and the responses-protocol probe all ride them). #210
wraps their request region in OpenAICompatibleProvider._metered():

- llm_requests_total — one tick per logical call. Tenacity retries and
  Retry-After waits happen INSIDE the region, so a 429-retried call is one
  request, not three (witnessed below against the wire-attempt count).
- llm_request_errors_total — Exception-class endings only. A cancelled or
  generator-closed call is not a provider failure: BaseException passes
  through the meter untouched (the census pins the handler type).
- llm_request_seconds — caller-visible latency with finally semantics:
  failures, cancellations and abandoned streams stay in the sequence.

Honest boundaries: the chat-protocol capability probe (CapabilityProbe)
builds its own clients and stays outside the meter; the responses-protocol
probe rides chat_stream and IS counted. Token accounting for the agent
lanes stays out of scope (providers/budget.py counts the craft lane only).

The census at the bottom parses providers/base.py (the ABC declares the
verbs) and providers/openai_compatible.py (structure): every request-entry
call inside a verb body must sit lexically inside an `async with
self._metered():` block, the raw SDK .create sites are pinned to three
helpers, and the _metered trio is pinned by name, handler type and the
shared bucket constant — none of these can be deleted without a red.
"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from openai import RateLimitError

from observability.metrics import render_text, snapshot
from providers.base import LLMMessage
from providers.openai_compatible import LLM_REQUEST_BUCKETS, OpenAICompatibleProvider
from providers.probe_result import ProbeResult

TRIO = ("llm_requests_total", "llm_request_errors_total", "llm_request_seconds")

# -- transport stubs (wire-level; mirror tests/unit/test_providers_dsv4.py) ----


class _RecordingResponder:
    """Stub chat.completions.create: replays canned outcomes, counts attempts."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = outcomes
        self.attempts = 0

    async def __call__(self, **kwargs: Any) -> Any:
        self.attempts += 1
        outcome = self.outcomes[min(self.attempts - 1, len(self.outcomes) - 1)]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _FakeCompletions:
    def __init__(self, responder: _RecordingResponder) -> None:
        self._responder = responder

    async def create(self, **kwargs: Any) -> Any:
        return await self._responder(**kwargs)


class _FakeClient:
    def __init__(self, responder: _RecordingResponder) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(responder))

    async def close(self) -> None:
        pass


class _ChunkStream:
    """Async iterator of stream chunks; a BaseException item raises mid-stream."""

    def __init__(self, items: list[Any]) -> None:
        self._items = list(items)
        self._index = 0

    def __aiter__(self) -> _ChunkStream:
        return self

    async def __anext__(self) -> Any:
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        if isinstance(item, BaseException):
            raise item
        return item


class _EventStream:
    """Responses-protocol event stream (consumed fully in these tests)."""

    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = list(events)
        self.closed = False

    def __aiter__(self) -> _EventStream:
        return self

    async def __anext__(self) -> dict[str, Any]:
        if not self._events:
            raise StopAsyncIteration
        return self._events.pop(0)

    async def close(self) -> None:
        self.closed = True


def _chunk(content: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                delta=SimpleNamespace(content=content, tool_calls=None),
                finish_reason=None,
            )
        ],
        model="deepseek-v4-pro",
    )


def _fake_response(content: str | None = "ok") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content=content, reasoning_content=None, tool_calls=[]
                ),
            )
        ],
        usage=None,
        model="deepseek-v4-pro",
    )


def _rate_limit_error(retry_after: str) -> RateLimitError:
    response = SimpleNamespace(
        headers={"retry-after": retry_after},
        status_code=429,
        request=SimpleNamespace(
            method="POST", url="http://llm.test/v1/chat/completions"
        ),
    )
    return RateLimitError("rate limited", response=response, body=None)


def _mock_api_key() -> str:
    """Fake key assembled from parts (mirror test_providers_dsv4._mock_api_key)."""
    return "sk-" + "test-" + "1234567890abcdef"


_DEFAULT_CAPS = {
    "chat": True,
    "streaming": True,
    "json_output": True,
    "tool_calls": True,
    "strict_tool_calls": False,
    "thinking": True,
    "thinking_with_tools": True,
    "reasoning_content": True,
    "usage_reporting": True,
    "error_codes": True,
    "rate_limit_headers": True,
}


def _make_provider(
    responder: _RecordingResponder, max_retries: int = 2
) -> OpenAICompatibleProvider:
    provider = OpenAICompatibleProvider(
        base_url="http://llm.test",
        api_key=_mock_api_key(),
        model="deepseek-v4-pro",
        probe_on_init=False,
        max_retries=max_retries,
    )
    provider._probe_result = ProbeResult(
        provider="openai_compatible",
        base_url=provider.base_url,
        model=provider.model,
        capabilities=dict(_DEFAULT_CAPS),
    )
    provider._client = _FakeClient(responder)
    return provider


def _completed(text: str = "SPEC_OK") -> dict[str, Any]:
    return {
        "status": "completed",
        "model": "gpt-6-astra",
        "output": [
            {"type": "message", "content": [{"type": "output_text", "text": text}]}
        ],
        "usage": {
            "input_tokens": 10, "output_tokens": 4, "total_tokens": 14,
            "input_tokens_details": {"cached_tokens": 3},
            "output_tokens_details": {"reasoning_tokens": 2},
        },
    }


def _responses_provider(outcome: Any) -> OpenAICompatibleProvider:
    provider = OpenAICompatibleProvider(
        base_url="https://gateway.test", api_key=_mock_api_key(),
        model="gpt-6-astra", reasoning_effort="max", protocol="responses",
        max_retries=0,
    )
    calls: list[dict[str, Any]] = []

    async def create(**kwargs: Any) -> Any:
        calls.append(kwargs)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    provider._client = SimpleNamespace(responses=SimpleNamespace(create=create))
    return provider


# -- delta reads over the process-global registry ------------------------------


def _delta(after: dict[str, Any], before: dict[str, Any], name: str) -> float:
    return after["counters"].get(name, 0.0) - before["counters"].get(name, 0.0)


def _hist_field(snap: dict[str, Any], field: str) -> float:
    hist = snap["histograms"].get(TRIO[2])
    if hist is None:
        return 0.0
    if field == "first_bucket":
        return hist["buckets"][0]
    return hist[field]


def _hist_delta(after: dict[str, Any], before: dict[str, Any], field: str) -> float:
    return _hist_field(after, field) - _hist_field(before, field)


# -- chat(): one logical call per call site -----------------------------------


async def test_chat_success_counts_one_request_and_observes_latency() -> None:
    responder = _RecordingResponder([_fake_response(content="ok")])
    provider = _make_provider(responder)
    before = snapshot()
    result = await provider.chat(messages=[LLMMessage(role="user", content="hi")])
    after = snapshot()
    assert result.content == "ok"
    assert _delta(after, before, TRIO[0]) == 1.0
    assert _delta(after, before, TRIO[1]) == 0.0
    assert _hist_delta(after, before, "count") == 1.0
    # A stubbed call is microseconds long: it must land in the first finite bucket.
    assert _hist_delta(after, before, "first_bucket") == 1.0


async def test_chat_permanent_error_counts_one_request_and_one_error() -> None:
    """A non-retryable failure ticks the error counter exactly once and
    propagates — the meter counts the logical call, not the wire attempts
    (a RuntimeError is not retryable, so attempts stays 1)."""
    responder = _RecordingResponder([RuntimeError("boom")])
    provider = _make_provider(responder)
    before = snapshot()
    with pytest.raises(RuntimeError, match="boom"):
        await provider.chat(messages=[LLMMessage(role="user", content="hi")])
    after = snapshot()
    assert responder.attempts == 1
    assert _delta(after, before, TRIO[0]) == 1.0
    assert _delta(after, before, TRIO[1]) == 1.0
    assert _hist_delta(after, before, "count") == 1.0


async def test_429_retry_attempts_stay_inside_one_logical_request() -> None:
    """Three wire attempts (two 429s, then success) are ONE logical request:
    tenacity retries and Retry-After waits ride inside the meter region."""
    responder = _RecordingResponder(
        [
            _rate_limit_error("0.001"),
            _rate_limit_error("0.001"),
            _fake_response(content="ok"),
        ]
    )
    provider = _make_provider(responder, max_retries=2)
    before = snapshot()
    result = await provider.chat(messages=[LLMMessage(role="user", content="hi")])
    after = snapshot()
    assert result.content == "ok"
    assert responder.attempts == 3
    assert _delta(after, before, TRIO[0]) == 1.0
    assert _delta(after, before, TRIO[1]) == 0.0
    assert _hist_delta(after, before, "count") == 1.0


async def test_cancelled_call_is_not_a_provider_failure() -> None:
    """CancelledError is a BaseException: the meter's error boundary is
    Exception-typed, so the call is counted (it happened) but NOT as a
    provider failure — and the latency observation still lands (finally)."""
    responder = _RecordingResponder([asyncio.CancelledError()])
    provider = _make_provider(responder, max_retries=0)
    before = snapshot()
    with pytest.raises(asyncio.CancelledError):
        await provider.chat(messages=[LLMMessage(role="user", content="hi")])
    after = snapshot()
    assert responder.attempts == 1
    assert _delta(after, before, TRIO[0]) == 1.0
    assert _delta(after, before, TRIO[1]) == 0.0
    assert _hist_delta(after, before, "count") == 1.0


# -- chat_stream(): the meter covers creation AND consumption ------------------


async def test_chat_stream_full_consumption_counts_one_request() -> None:
    responder = _RecordingResponder([_ChunkStream([_chunk("a"), _chunk("b")])])
    provider = _make_provider(responder)
    before = snapshot()
    pieces = [
        piece async for piece in provider.chat_stream(
            messages=[LLMMessage(role="user", content="hi")]
        )
    ]
    after = snapshot()
    assert [piece.content for piece in pieces] == ["a", "b"]
    assert _delta(after, before, TRIO[0]) == 1.0
    assert _delta(after, before, TRIO[1]) == 0.0
    assert _hist_delta(after, before, "count") == 1.0


async def test_abandoned_stream_is_observed_but_not_an_error() -> None:
    """Closing the generator after the first chunk raises GeneratorExit at
    the inner yield: the request stays counted and observed (finally) and
    the error counter stays put (GeneratorExit is not Exception)."""
    responder = _RecordingResponder([_ChunkStream([_chunk("a"), _chunk("b")])])
    provider = _make_provider(responder)
    before = snapshot()
    stream = provider.chat_stream(messages=[LLMMessage(role="user", content="hi")])
    first = await stream.__anext__()
    assert first.content == "a"
    await stream.aclose()
    after = snapshot()
    assert _delta(after, before, TRIO[0]) == 1.0
    assert _delta(after, before, TRIO[1]) == 0.0
    assert _hist_delta(after, before, "count") == 1.0


async def test_stream_mid_error_counts_one_error() -> None:
    responder = _RecordingResponder([_ChunkStream([_chunk("a"), RuntimeError("stream broke")])])
    provider = _make_provider(responder)
    before = snapshot()
    with pytest.raises(RuntimeError, match="stream broke"):
        _ = [
            piece async for piece in provider.chat_stream(
                messages=[LLMMessage(role="user", content="hi")]
            )
        ]
    after = snapshot()
    assert _delta(after, before, TRIO[0]) == 1.0
    assert _delta(after, before, TRIO[1]) == 1.0
    assert _hist_delta(after, before, "count") == 1.0


# -- responses protocol rides the same meter -----------------------------------


async def test_responses_chat_counts_one_request() -> None:
    provider = _responses_provider(_completed())
    before = snapshot()
    result = await provider.chat(messages=[LLMMessage(role="user", content="hi")])
    after = snapshot()
    assert result.content == "SPEC_OK"
    assert _delta(after, before, TRIO[0]) == 1.0
    assert _delta(after, before, TRIO[1]) == 0.0
    assert _hist_delta(after, before, "count") == 1.0


async def test_responses_stream_counts_one_request() -> None:
    stream = _EventStream(
        [
            {"type": "response.output_text.delta", "delta": "SPEC_"},
            {"type": "response.completed", "response": _completed()},
        ]
    )
    provider = _responses_provider(stream)
    before = snapshot()
    pieces = [
        piece async for piece in provider.chat_stream(
            messages=[LLMMessage(role="user", content="hi")]
        )
    ]
    after = snapshot()
    assert [piece.content for piece in pieces] == ["SPEC_", None]
    assert stream.closed
    assert _delta(after, before, TRIO[0]) == 1.0
    assert _delta(after, before, TRIO[1]) == 0.0
    assert _hist_delta(after, before, "count") == 1.0


# -- exposition -----------------------------------------------------------------


async def test_render_text_exposes_the_trio_and_the_declared_ladder() -> None:
    responder = _RecordingResponder([_fake_response(content="ok")])
    provider = _make_provider(responder)
    await provider.chat(messages=[LLMMessage(role="user", content="hi")])

    hist = snapshot()["histograms"]["llm_request_seconds"]
    assert hist["bounds"] == list(LLM_REQUEST_BUCKETS), (
        "the recorded ladder must be the provider's declared constant"
    )
    text = render_text()
    assert "# TYPE specproof_llm_requests_total counter" in text
    assert "# TYPE specproof_llm_request_errors_total counter" in text
    assert "# TYPE specproof_llm_request_seconds histogram" in text
    for bound in LLM_REQUEST_BUCKETS:
        label = f'specproof_llm_request_seconds_bucket{{le="{bound:g}"}}'
        assert label in text, label
    assert 'specproof_llm_request_seconds_bucket{le="+Inf"}' in text


# -- census: the ABC declares the verbs, the source must metre them -------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BASE_PATH = _REPO_ROOT / "providers" / "base.py"
_PROVIDER_PATH = _REPO_ROOT / "providers" / "openai_compatible.py"

#: Helpers that reach the raw SDK client. Call sites of these inside the two
#: verb bodies are the request-entry points the meter must cover; the floors
#: below were measured at #210 and come from the same walk they guard.
_ENTRY_HELPERS = frozenset(
    {"_create_response", "_create_chat_completion", "_policy_chat", "_responses_stream"}
)
_ENTRY_FLOORS = {"chat": 3, "chat_stream": 2}


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _abc_async_verbs() -> list[str]:
    """Async method names declared on ModelProvider — the LLM-lane surface
    every provider must expose. Derived from the ABC, never hand-listed."""
    tree = _parse(_BASE_PATH)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ModelProvider":
            return sorted(
                child.name
                for child in node.body
                if isinstance(child, ast.AsyncFunctionDef)
            )
    raise AssertionError("ModelProvider class not found in providers/base.py")


def _abc_timeout_defaults() -> set[float]:
    """Default timeout values declared on the ABC verb signatures."""
    found: set[float] = set()
    for node in ast.walk(_parse(_BASE_PATH)):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        args = node.args
        paired = (
            list(zip(args.args[-len(args.defaults):], args.defaults, strict=False))
            if args.defaults
            else []
        )
        paired += list(zip(args.kwonlyargs, args.kw_defaults, strict=False))
        for arg, default in paired:
            if arg.arg == "timeout" and isinstance(default, ast.Constant):
                found.add(float(default.value))
    return found


def _is_metered_with(item: ast.withitem) -> bool:
    expr = item.context_expr
    return (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Attribute)
        and expr.func.attr == "_metered"
    )


def _call_sites(tree: ast.Module) -> list[tuple[str, ast.Call, int]]:
    """(enclosing function, Call node, meter depth) for every Call node.

    A nested def (the retry `attempt()` wrappers) is attributed to its
    OUTERMOST enclosing method: its body is part of that method's execution
    structure, and that is where the call's reachability is decided."""
    sites: list[tuple[str, ast.Call, int]] = []
    stack: list[tuple[str, int]] = []

    class _Visitor(ast.NodeVisitor):
        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            name = stack[0][0] if stack else node.name
            stack.append((name, 0))
            self.generic_visit(node)
            stack.pop()

        visit_FunctionDef = visit_AsyncFunctionDef  # noqa: N815 (ast dispatch name)

        def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
            fn, depth = stack[-1] if stack else ("<module>", 0)
            metered = any(_is_metered_with(item) for item in node.items)
            stack.append((fn, depth + 1 if metered else depth))
            self.generic_visit(node)
            stack.pop()

        def visit_Call(self, node: ast.Call) -> None:
            fn, depth = stack[-1] if stack else ("<module>", 0)
            sites.append((fn, node, depth))
            self.generic_visit(node)

    _Visitor().visit(tree)
    return sites


def _meter_blocks(tree: ast.Module) -> dict[str, int]:
    counts: dict[str, int] = {}
    stack: list[str] = []

    class _Visitor(ast.NodeVisitor):
        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_FunctionDef = visit_AsyncFunctionDef  # noqa: N815 (ast dispatch name)

        def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
            if any(_is_metered_with(item) for item in node.items):
                fn = stack[-1] if stack else "<module>"
                counts[fn] = counts.get(fn, 0) + 1
            self.generic_visit(node)

    _Visitor().visit(tree)
    return counts


def test_abc_verbs_are_metred() -> None:
    """Every async verb of the ABC carries at least one meter block — a new
    verb cannot ship unmetered without this going red."""
    verbs = _abc_async_verbs()
    assert len(verbs) >= 2, f"ABC async surface shrank: {verbs}"
    blocks = _meter_blocks(_parse(_PROVIDER_PATH))
    missing = [verb for verb in verbs if blocks.get(verb, 0) < 1]
    assert not missing, f"ABC verbs without a meter block: {missing}"


def test_every_entry_call_in_the_verb_bodies_is_metered() -> None:
    """The containment claim, per the message of each assertion: request-entry
    calls inside the verb bodies sit lexically inside `async with
    self._metered():`, and the only entry calls outside any meter region are
    the ones in _responses_stream (a helper invoked inside chat_stream's
    meter block). The lazy probe call stays outside the metered region by
    design: probe time is not part of the caller-visible sample."""
    tree = _parse(_PROVIDER_PATH)
    sites = _call_sites(tree)
    verbs = _abc_async_verbs()
    entry = [
        (fn, node, depth)
        for fn, node, depth in sites
        if isinstance(node.func, ast.Attribute)
        and node.func.attr in _ENTRY_HELPERS
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    ]
    per_verb = {verb: {"total": 0, "inside": 0} for verb in verbs}
    outside: set[str] = set()
    for fn, _node, depth in entry:
        if fn in per_verb:
            per_verb[fn]["total"] += 1
            if depth > 0:
                per_verb[fn]["inside"] += 1
        elif depth == 0:
            outside.add(fn)
    for verb, floor in _ENTRY_FLOORS.items():
        got = per_verb.get(verb, {"total": 0, "inside": 0})
        assert got["total"] >= floor, (
            f"entry-call census read only {got['total']} sites in {verb}() "
            f"(floor {floor}) — the scan, not the code, is suspect"
        )
        assert got["inside"] == got["total"], (
            f"{verb}() has request-entry calls outside the meter region: "
            f"{got['total'] - got['inside']} of {got['total']}"
        )
    assert outside == {"_responses_stream"}, (
        "request-entry calls outside every meter region must live only in "
        "_responses_stream (invoked inside chat_stream's meter block); "
        f"found {sorted(outside)}"
    )
    blocks = _meter_blocks(tree)
    for verb in verbs:
        assert blocks.get(verb, 0) >= 2, (
            f"{verb}() lost a meter block ({blocks.get(verb, 0)} left): each "
            "protocol branch must own its region"
        )
    probes = [
        (fn, depth)
        for fn, node, depth in sites
        if isinstance(node.func, ast.Attribute) and node.func.attr == "_ensure_probed"
    ]
    assert len(probes) >= 2, probes
    assert all(depth == 0 for _, depth in probes), (
        f"the lazy capability probe must stay outside the metered region: {probes}"
    )


def test_raw_sdk_create_sites_are_the_three_helpers() -> None:
    """All raw-SDK .create calls live in the three transport helpers, and
    _raw_create (the policy callback) is only ever passed, never called —
    so every raw request ride is reachable only through a metered entry."""
    sites = _call_sites(_parse(_PROVIDER_PATH))
    create_fns = {
        fn
        for fn, node, _depth in sites
        if isinstance(node.func, ast.Attribute) and node.func.attr == "create"
    }
    assert create_fns == {
        "_create_response",
        "_create_chat_completion",
        "_raw_create",
    }, create_fns
    direct = [
        node.lineno
        for _fn, node, _depth in sites
        if isinstance(node.func, ast.Attribute) and node.func.attr == "_raw_create"
    ]
    assert not direct, f"_raw_create must only be passed, never called (lines {direct})"


def test_meter_region_counts_the_trio_with_exception_only_endings() -> None:
    """The _metered region structure: one requests tick, one errors tick
    guarded by an Exception-typed handler (not BaseException — cancellations
    are not provider failures), and one latency observation riding finally
    with the shared bucket constant. Each trio name is a string literal
    exactly once in the module: no second counting site."""
    tree = _parse(_PROVIDER_PATH)
    metered = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_metered"
    ]
    assert len(metered) == 1, "exactly one _metered region expected"
    fn = metered[0]
    sites = [
        node for fname, node, _depth in _call_sites(tree) if fname == "_metered"
    ]

    incr_names = sorted(
        node.args[0].value
        for node in sites
        if isinstance(node.func, ast.Name)
        and node.func.id == "incr"
        and node.args
        and isinstance(node.args[0], ast.Constant)
    )
    assert incr_names == ["llm_request_errors_total", "llm_requests_total"], incr_names

    observe = [
        node
        for node in sites
        if isinstance(node.func, ast.Name) and node.func.id == "observe_duration"
    ]
    assert len(observe) == 1, "exactly one latency observation expected"
    obs = observe[0]
    assert isinstance(obs.args[0], ast.Constant) and obs.args[0].value == TRIO[2]
    buckets_kw = [kw for kw in obs.keywords if kw.arg == "buckets"]
    assert (
        len(buckets_kw) == 1
        and isinstance(buckets_kw[0].value, ast.Name)
        and buckets_kw[0].value.id == "LLM_REQUEST_BUCKETS"
    ), "the observation must ride the declared bucket constant"

    trys = [node for node in ast.walk(fn) if isinstance(node, ast.Try)]
    assert len(trys) == 1, "the meter owns exactly one try region"
    region = trys[0]
    assert len(region.handlers) == 1, "exactly one error handler expected"
    handler = region.handlers[0]
    assert isinstance(handler.type, ast.Name) and handler.type.id == "Exception", (
        "the error boundary must be Exception-typed: BaseException would "
        "count cancellations as provider failures"
    )
    err_call = next(
        node
        for node in sites
        if isinstance(node.func, ast.Name)
        and node.func.id == "incr"
        and node.args
        and getattr(node.args[0], "value", None) == TRIO[1]
    )
    assert any(
        err_call is node for stmt in handler.body for node in ast.walk(stmt)
    ), "the errors tick must sit in the Exception handler"
    assert region.finalbody, (
        "the latency observation must ride finally so failures and "
        "cancellations stay in the sequence"
    )
    assert any(
        obs is node for stmt in region.finalbody for node in ast.walk(stmt)
    ), "observe_duration must ride finally"

    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    for name in TRIO:
        assert literals.count(name) == 1, (
            f"{name} appears as a string literal {literals.count(name)} times "
            "in the module — duplicated counting sites merge into one series"
        )


def test_ladder_resolves_the_declared_default_timeout() -> None:
    """The ladder is ascending, positive, and keeps a finite bucket at or
    above the ABC's declared default timeout — quantiles at the default
    deadline must never fall into +Inf."""
    bounds = list(LLM_REQUEST_BUCKETS)
    assert bounds == sorted(bounds) and len(bounds) >= 8, bounds
    assert all(bound > 0 for bound in bounds), bounds
    defaults = _abc_timeout_defaults()
    assert defaults, "no timeout default found on the ABC verbs"
    assert bounds[-1] >= max(defaults), (
        f"the ladder must cover the declared default timeout "
        f"{max(defaults)}s: {bounds}"
    )
