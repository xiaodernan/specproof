"""Redis round-trip observability (#212) — sibling of the #169 ES ladder.

storage/redis.py wraps every ``self.client.<op>`` call in
``_timed_redis("<op>")``, so each round trip lands in the concatenated
family ``redis_request_seconds_<op>``. These cases pin:

- behavioral: driving every store method through a fake client moves the
  per-op histogram by exactly the call counts, and the fake's ledger
  agrees with the histogram deltas;
- ladder: bounds == _REDIS_BUCKETS (sorted, positive) and the top covers
  the client's own socket_timeout literal (a timed-out request stays in a
  finite bucket);
- finally semantics: a raising round trip still observes;
- failure partition: a swallowed xread/xlen/ping failure still counts
  (the failed round trip is a real request);
- rollback path: the budget incrby rollback is timed too;
- source census: every self.client.<op> call site sits directly inside a
  ``with _timed_redis("<same op>")`` — vocabulary and wrapper words cannot
  drift, and no client call can be added untimed.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import redis as redis_pkg

from observability import metrics as metrics_module
from storage.redis import _REDIS_BUCKETS, RedisConfig, RedisStore

ROOT = Path(__file__).resolve().parents[2]
REDIS_SOURCE = ROOT / "storage" / "redis.py"

#: The 13-op vocabulary shipped by the module (mirrors the parity gate's
#: derived family; here it also floors the AST census's reach).
ALL_OPS = {
    "decrby", "eval", "exists", "expire", "get", "incr", "incrby",
    "ping", "set", "setex", "xadd", "xlen", "xread",
}


class _FakeRedis:
    """Records every op; canned responses / injected failures per op."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.failures: dict[str, Exception] = {}
        self.responses: dict[str, Any] = {}
        self.defaults: dict[str, Any] = {
            "set": True, "exists": 1, "incr": 1, "xadd": "1-1",
            "xread": [], "xlen": 0, "ping": True, "decrby": 100,
            "get": None, "eval": 1, "setex": True, "incrby": 0,
        }

    def _record(self, op: str) -> Any:
        self.calls.append(op)
        failure = self.failures.get(op)
        if failure is not None:
            raise failure
        if op in self.responses:
            return self.responses[op]
        return self.defaults.get(op)

    def set(self, *args: Any, **kwargs: Any) -> Any:
        return self._record("set")

    def get(self, *args: Any, **kwargs: Any) -> Any:
        return self._record("get")

    def setex(self, *args: Any, **kwargs: Any) -> Any:
        return self._record("setex")

    def incr(self, *args: Any, **kwargs: Any) -> Any:
        return self._record("incr")

    def incrby(self, *args: Any, **kwargs: Any) -> Any:
        return self._record("incrby")

    def decrby(self, *args: Any, **kwargs: Any) -> Any:
        return self._record("decrby")

    def exists(self, *args: Any, **kwargs: Any) -> Any:
        return self._record("exists")

    def expire(self, *args: Any, **kwargs: Any) -> Any:
        return self._record("expire")

    def xadd(self, *args: Any, **kwargs: Any) -> Any:
        return self._record("xadd")

    def xread(self, *args: Any, **kwargs: Any) -> Any:
        return self._record("xread")

    def xlen(self, *args: Any, **kwargs: Any) -> Any:
        return self._record("xlen")

    def eval(self, *args: Any, **kwargs: Any) -> Any:
        return self._record("eval")

    def ping(self, *args: Any, **kwargs: Any) -> Any:
        return self._record("ping")


@pytest.fixture()
def store(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[RedisStore, _FakeRedis]:
    fake = _FakeRedis()
    monkeypatch.setattr(
        RedisStore, "client", property(lambda self: fake)  # type: ignore[arg-type]
    )
    return RedisStore(config=RedisConfig()), fake


def _count(op: str) -> float:
    hists = metrics_module.snapshot()["histograms"]
    return hists.get(f"redis_request_seconds_{op}", {}).get("count", 0.0)


def test_driving_every_method_moves_each_op_histogram(store) -> None:
    s, fake = store
    before = {op: _count(op) for op in ALL_OPS}

    s.set_progress("j", {"p": 1})
    s.get_progress("j")
    s.xadd_progress("j", "n", "running")
    s.xread_progress("j")
    s.stream_length("j")
    assert s.acquire_lease("j", "w", max_hold_seconds=60) is True
    fake.responses["get"] = "w"  # the lease reads back as ours
    assert s.renew_lease("j", "w") is True
    fake.responses["get"] = None
    s.release_lease("j", "w")
    s.get_lease_owner("j")
    s.init_budget("j", 100)
    assert s.consume_budget("j", 10) is True
    s.check_budget("j")
    assert s.acquire_scope_lock("scope") is not None
    s.release_scope_lock("scope", "tok")
    s.cache_llm_response("k", {})
    s.get_cached_llm_response("k")
    s.cache_provider_capability("h", {})
    s.get_cached_provider_capability("h")
    s.set_idempotent("e")
    s.is_idempotent("e")
    assert s.is_ready() is True

    expected = {
        "setex": 3, "get": 6, "incr": 1, "expire": 3, "xadd": 1,
        "xread": 1, "xlen": 1, "set": 6, "exists": 3, "eval": 2,
        "decrby": 1, "ping": 1,
    }
    for op, times in expected.items():
        delta = _count(op) - before[op]
        assert delta == times, (op, delta)

    # the untouched rollback arm: incrby has no histogram yet
    assert "incrby" not in Counter(fake.calls)

    # the fake's ledger agrees with the histogram deltas (mechanism side):
    # every real call is observed exactly once, none is double-counted.
    ledger = dict(Counter(fake.calls))
    assert ledger == expected


def test_bucket_ladder_matches_the_constant_and_covers_socket_timeout(store) -> None:
    s, _ = store
    s.get_progress("j")
    bounds = metrics_module.snapshot()["histograms"][
        "redis_request_seconds_get"
    ]["bounds"]
    assert bounds == list(_REDIS_BUCKETS)
    assert list(_REDIS_BUCKETS) == sorted(_REDIS_BUCKETS)
    assert all(b > 0 for b in _REDIS_BUCKETS)
    # The top must sit ABOVE the timed-out worst case: a request cut off at
    # socket_timeout measures slightly over it, so an exactly-equal top would
    # dump timed-out samples into +Inf. The bound comes from the source,
    # not copied here.
    text = REDIS_SOURCE.read_text(encoding="utf-8")
    match = re.search(r"socket_timeout=(\d+(?:\.\d+)?)", text)
    assert match is not None, "client socket_timeout literal not found"
    assert _REDIS_BUCKETS[-1] > float(match.group(1))


def test_raising_round_trip_still_observes(store) -> None:
    s, fake = store
    fake.failures["get"] = RuntimeError("wire down")
    before = _count("get")
    with pytest.raises(RuntimeError):
        s.get_progress("j")
    assert _count("get") - before == 1.0


def test_swallowed_failures_still_count(store) -> None:
    s, fake = store
    fake.failures["xread"] = redis_pkg.ResponseError("WRONGTYPE")
    fake.failures["xlen"] = redis_pkg.ResponseError("WRONGTYPE")
    fake.failures["ping"] = redis_pkg.ConnectionError("down")
    cases = [
        ("xread", lambda: s.xread_progress("j") == []),
        ("xlen", lambda: s.stream_length("j") == 0),
        ("ping", lambda: s.is_ready() is False),
    ]
    for op, drive in cases:
        before = _count(op)
        assert drive(), op
        assert _count(op) - before == 1.0, op


def test_budget_rollback_times_the_incrby(store) -> None:
    s, fake = store
    fake.responses["decrby"] = -5
    before_d, before_i = _count("decrby"), _count("incrby")
    assert s.consume_budget("j", 10) is False
    assert _count("decrby") - before_d == 1.0
    assert _count("incrby") - before_i == 1.0
    assert fake.calls == ["decrby", "incrby"]


def _client_calls(tree: ast.Module) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "client"
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "self"
        ):
            calls.append(node)
    return calls


def _timed_withs(tree: ast.Module) -> list[tuple[ast.With, str]]:
    out: list[tuple[ast.With, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.With) and len(node.items) == 1:
            ctx = node.items[0].context_expr
            if (
                isinstance(ctx, ast.Call)
                and isinstance(ctx.func, ast.Name)
                and ctx.func.id == "_timed_redis"
                and len(ctx.args) == 1
                and isinstance(ctx.args[0], ast.Constant)
                and isinstance(ctx.args[0].value, str)
            ):
                out.append((node, ctx.args[0].value))
    return out


def test_every_client_call_is_timed_with_its_own_word() -> None:
    tree = ast.parse(REDIS_SOURCE.read_text(encoding="utf-8"))
    calls = _client_calls(tree)
    wrappers = _timed_withs(tree)

    covered: set[int] = set()
    seen_ops: list[str] = []
    for wrapper, word in wrappers:
        inner = [
            node
            for node in ast.walk(wrapper)
            if isinstance(node, ast.Call) and node in calls
        ]
        assert len(inner) == 1, (
            f"wrapper _timed_redis({word!r}) must wrap exactly one client "
            f"call, found {len(inner)}"
        )
        (call,) = inner
        assert call.func.attr == word, (word, call.func.attr)
        covered.add(id(call))
        seen_ops.append(word)

    # bidirectional coverage: no call outside a wrapper, no wrapper without
    # a call; both counts come from this same walk (the two scans cannot
    # narrow independently of each other)
    assert len(wrappers) == len(calls)
    assert len(covered) == len(calls)
    # floors from the same scan: the vocabulary the scanner actually saw
    # must be the shipped 13-op set — a scanner that stops matching (e.g.
    # a refactor to a local alias) collapses to a subset and fails here
    ops = {call.func.attr for call in calls}
    assert ops == ALL_OPS
    assert set(seen_ops) == ALL_OPS
