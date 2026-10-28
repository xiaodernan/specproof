"""#517 — one Retry-After producer, tabled; the census hole's second catch.

#516 opened `providers` for the first time and found
`_wait_retry_after_or_exponential` in `providers/openai_compatible.py` and
`retrieval/embeddings.py` as two byte-identical bodies — one decision, "a 429 waits
for Retry-After, otherwise capped exponential", written twice. The outer copies
matched; the helper each one called did **not**: providers guarded the response
object twice (`getattr(response, "headers", None)`, then `hasattr(headers, "get")`),
while retrieval indexed `response.headers.get(...)` straight through. Over sixteen
response shapes the two agreed on every header *value* a gateway can send and
disagreed on exactly three malformed *response* shapes, where providers answered
None and retrieval raised `AttributeError`.

This file is what that table looks like **after** the merge: the same sixteen cells,
answered by one producer, with the three former crash shapes now returning None.
What changed is not the numbers, it is who owns them — so the legs below moved from
"do the two copies agree" to three claims that survive a single implementation:

* the header spelling has exactly one home in product code (a re-inlined copy goes
  red here, the same reverse control #516 uses for the timestamp format);
* both call sites *delegate* — pinned on the bound object's identity, so an
  import-less local copy under the same name cannot pass;
* the parser is total: nothing in the table raises, because it runs inside
  tenacity's `wait=`, where an exception spends the remaining attempts instead of
  scheduling one. #516 measured that cost as 3 attempts versus 1.

The reachability legs at the bottom keep the honesty of the original claim: the
crash shape is **not** reachable from a live gateway. Every `httpx.Response` carries
a `Headers` mapping, and the openai SDK dereferences `response.headers` in its own
constructor, so an SDK error over a headerless response dies before tenacity runs.
What can hand the parser a stripped response is a transport double or an adapter
that builds its own error — `httpx.HTTPStatusError` stores whatever response it gets.
So #517 closed a latent divergence with a misleading failure mode, not an incident,
and this file says which is which.
"""
from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import RateLimitError
from tenacity import Retrying, retry_if_exception, stop_after_attempt

import contracts.retry_after as shared
import providers.openai_compatible as providers_module
import retrieval.embeddings as retrieval_module
from contracts.retry_after import retry_after_seconds, wait_retry_after_or_exponential
from providers.openai_compatible import _RETRYABLE_EXCEPTIONS
from tests.unit.test_structural_clone_ratchet import PACKAGES

REPO = Path(__file__).resolve().parents[2]

Parser = Callable[[BaseException], "float | None"]
Outcome = tuple[str, Any]

#: Stands for "attach nothing at all", so the table can name an exception that
#: carries no `response` attribute rather than one carrying None.
NO_RESPONSE = object()

#: The header name, spelled once. The census leg below reads it from here so the
#: gate and the probe cannot drift apart.
HEADER = "retry-after"

ANSWER_NONE: Outcome = ("value", None)


class GatewayError(Exception):
    """An exception shaped like the SDK's: it carries a `.response`."""

    def __init__(self, response: object) -> None:
        self.response = response
        super().__init__("429 from the gateway")


def _exception_for(response: object) -> BaseException:
    if response is NO_RESPONSE:
        return RuntimeError("gateway error that carries no response at all")
    return GatewayError(response)


def _outcome(parser: Parser, exc: BaseException) -> Outcome:
    """("value", x) or ("raise", ExceptionTypeName) — the type name is the datum."""
    try:
        return ("value", parser(exc))
    except Exception as exc_out:  # noqa: BLE001
        return ("raise", type(exc_out).__name__)


def _headers(raw: object) -> SimpleNamespace:
    return SimpleNamespace(headers={HEADER: raw})


#: The three response shapes a real httpx response never produces — and the whole
#: reason the two copies used to diverge. Kept named, because a merge that silently
#: drops them would also drop the arms that prove the guard is load-bearing.
NO_HEADERS_ATTR = SimpleNamespace()
NULL_HEADERS = SimpleNamespace(headers=None)
HEADERS_WITHOUT_GET = SimpleNamespace(headers=object())
DIVERGENT_RESPONSES: tuple[tuple[str, SimpleNamespace], ...] = (
    ("response without headers", NO_HEADERS_ATTR),
    ("headers is None", NULL_HEADERS),
    ("headers has no get()", HEADERS_WITHOUT_GET),
)

#: (label, the `response` an exception carries, the answer) — every cell inherited
#: from #516's run of **both** parsers; the three former `retrieval` crashes now read
#: as the exponential fallback they always should have been.
SHAPES: list[tuple[str, object, Outcome]] = [
    ("no response attribute", NO_RESPONSE, ANSWER_NONE),
    ("response is None", None, ANSWER_NONE),
    ("response without headers", NO_HEADERS_ATTR, ANSWER_NONE),
    ("headers is None", NULL_HEADERS, ANSWER_NONE),
    ("headers has no get()", HEADERS_WITHOUT_GET, ANSWER_NONE),
    ("headers empty", SimpleNamespace(headers={}), ANSWER_NONE),
    ("no retry-after key", SimpleNamespace(headers={"date": "x"}), ANSWER_NONE),
    ("retry-after '7'", _headers("7"), ("value", 7.0)),
    ("retry-after '7.5'", _headers("7.5"), ("value", 7.5)),
    ("retry-after '0'", _headers("0"), ("value", 0.0)),
    ("retry-after '-3'", _headers("-3"), ("value", 0.0)),
    ("retry-after ''", _headers(""), ANSWER_NONE),
    ("retry-after None", _headers(None), ANSWER_NONE),
    ("retry-after int", _headers(7), ("value", 7.0)),
    ("retry-after list", _headers(["7", "8"]), ANSWER_NONE),
    (
        "retry-after HTTP-date",
        _headers("Wed, 21 Oct 2015 07:28:00 GMT"),
        ANSWER_NONE,
    ),
]

#: The two shipped modules that used to own a copy of this decision.
CONSUMERS = ("providers/openai_compatible.py", "retrieval/embeddings.py")


@pytest.mark.parametrize("label,response,expected", SHAPES)
def test_the_producer_answers_the_shape_the_table_says(
    label: str, response: object, expected: Outcome
) -> None:
    assert _outcome(retry_after_seconds, _exception_for(response)) == expected, label


@pytest.mark.parametrize("label,response", DIVERGENT_RESPONSES)
def test_the_three_shapes_that_used_to_split_the_copies_now_answer_none(
    label: str, response: object
) -> None:
    """The merge's actual behaviour change, named shape by shape.

    Before #517 these three raised `AttributeError` out of `retrieval`'s parser.
    Asserting the None here (rather than only "it does not raise") keeps the
    *fallback* semantics pinned: absent-but-malformed means exponential backoff,
    not a zero wait.
    """
    assert _outcome(retry_after_seconds, GatewayError(response)) == ANSWER_NONE, label


def test_the_parser_raises_for_nothing_in_the_table() -> None:
    """Totality is the contract, and it is the reason the merge picked this copy.

    A parser that can raise inside `wait=` does not report a bad header: it ends the
    retry loop. #516 measured that as 3 attempts versus 1 for the same exception.
    """
    raised = [
        label
        for label, response, _expected in SHAPES
        if _outcome(retry_after_seconds, _exception_for(response))[0] == "raise"
    ]
    assert raised == [], raised


def _spells_header(node: ast.AST) -> bool:
    """Whether this subtree names the header — decoded, and ignoring case.

    Comparing the *spelling* is the point of the leg, and a text comparison is only
    as good as the quote style it guesses: `ast.unparse` renders string constants
    with single quotes, so the first version of this test looked for a double-quoted
    literal inside unparsed text and could not fire for any code. A1 measured that —
    it predicted two reds and produced one. Matching the decoded constant closes the
    vacuous leg, and comparing case-insensitively matches what a copy must be:
    `httpx.Headers` lookup ignores case, so `"Retry-After"` is the same header read
    again, not a different one. Bare string statements are skipped so a docstring
    *about* the header is not mistaken for a module that reads it — #517's measure
    says three product modules mention it in prose and exactly one spells it as code.
    """
    prose = {
        id(child.value)
        for child in ast.walk(node)
        if isinstance(child, ast.Expr) and isinstance(child.value, ast.Constant)
    }
    return any(
        isinstance(child, ast.Constant)
        and isinstance(child.value, str)
        and id(child) not in prose
        and HEADER in child.value.lower()
        for child in ast.walk(node)
    )


def _product_modules_naming_the_header() -> list[str]:
    """Shipped modules whose own source spells the `retry-after` header.

    Walked over the ratchet's own `PACKAGES`, so the two gates cannot cover
    different trees — the same reason #516 gave for tying the timestamp census to it.
    """
    hits: list[str] = []
    for package in PACKAGES:
        for path in (REPO / package).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if _spells_header(ast.parse(path.read_text(encoding="utf-8"))):
                hits.append(path.relative_to(REPO).as_posix())
    return sorted(hits)


def test_the_header_is_read_in_exactly_one_product_module() -> None:
    """Reverse control for the merge: a re-inlined parse must go red here.

    The clone ratchet compares same-named bodies, so a copy written under another
    name — or a copy that reads the header inline without a helper — is invisible to
    it. This leg compares the *spelling*.
    """
    assert _product_modules_naming_the_header() == ["contracts/retry_after.py"]


def _runtime_import_roots(tree: ast.Module) -> set[str]:
    """Top-level packages the module imports at runtime, TYPE_CHECKING excluded.

    `contracts/retry_after.py` keeps tenacity behind `if TYPE_CHECKING:` so the
    producer stays importable from a stdlib-only environment; a leg that counted
    that annotation as a dependency would forbid the very thing it wants. Walked
    by hand rather than with `ast.walk`, which descends into the guarded block.
    """
    roots: set[str] = set()

    def visit(node: ast.AST, guarded: bool) -> None:
        if isinstance(node, ast.If):
            guarded = guarded or ast.unparse(node.test) == "TYPE_CHECKING"
        if not guarded:
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
        for child in ast.iter_child_nodes(node):
            visit(child, guarded)

    visit(tree, False)
    return roots


def test_the_producer_stays_reachable_without_a_dependency_edge() -> None:
    """`contracts` is the home because neither consumer can own this for the other.

    #517 measured that `retrieval/` imports nothing from `providers/` and
    vice-versa, so merging into either package would add a cross-layer edge to the
    live call path. Pinned on imports rather than prose: the day the producer needs
    httpx or one of its consumers, the reason for the home dies and the merge has
    to move — not accumulate an edge nobody chose.
    """
    tree = ast.parse((REPO / "contracts/retry_after.py").read_text(encoding="utf-8"))
    third_party = _runtime_import_roots(tree) - {"__future__", "typing"}
    assert third_party == set(), sorted(third_party)


@pytest.mark.parametrize("rel", CONSUMERS)
def test_the_former_owners_now_delegate_to_the_one_producer(rel: str) -> None:
    """Checked on the AST: the module imports the shared pair and keeps no parser.

    `providers` and `retrieval` each carried both functions until #517; a merge that
    left one of them reading the header locally would still pass a behaviour test,
    because the two answers agree on every shape a gateway can send.
    """
    tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "contracts.retry_after"
        for alias in node.names
    }
    assert "wait_retry_after_or_exponential" in imported, (
        f"{rel} no longer imports the shared wait: {sorted(imported)}"
    )
    own_parsers = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and _spells_header(node)
    ]
    assert not own_parsers, f"{rel} parses {HEADER} again itself: {own_parsers}"


@pytest.mark.parametrize(
    "module", [providers_module, retrieval_module], ids=["providers", "retrieval"]
)
def test_the_retry_loops_are_wired_to_the_shared_wait_by_identity(
    module: object,
) -> None:
    """The bound name must *be* the shared function, not a look-alike.

    An import is easy to replace with a local def of the same name; identity is what
    makes the tenacity `wait=` on each live path the one this table measured.
    """
    assert module.wait_retry_after_or_exponential is shared.wait_retry_after_or_exponential


@pytest.mark.parametrize(
    ("attempt", "header", "expected"),
    [
        (1, None, 1.0),
        (2, None, 2.0),
        (3, None, 4.0),
        (7, None, 60.0),
        (1, "9", 9.0),
        (7, "9", 9.0),
        (7, "90", 90.0),
        (3, "0", 0.0),
    ],
    ids=[
        "a1",
        "a2",
        "a3",
        "a7-capped",
        "a1-header",
        "a7-header-beats-cap",
        "a7-header-over-cap",
        "a3-zero",
    ],
)
def test_the_shared_wait_answers_the_seconds_both_clients_used_to_agree_on(
    attempt: int, header: str | None, expected: float
) -> None:
    """The numbers from #516's two-copy comparison, now owned once.

    A merge into one home must not move the 60s cap or let the exponential curve
    beat the gateway's own header — the header wins at every attempt number, and
    `a7-header-over-cap` is the cell that says the cap bounds the *curve*, never
    the header. Round 1's arm A4 (rewrite the tail as `min(retry_after, curve)`)
    predicted two reds and measured one: every header value the table carried was
    already under the curve at its own attempt number, so nothing distinguished
    "the header wins" from "the smaller of the two". A4 going red twice is this
    row's job.
    """
    response = None if header is None else _headers(header)
    state = SimpleNamespace(
        outcome=SimpleNamespace(exception=lambda: GatewayError(response)),
        attempt_number=attempt,
    )
    assert wait_retry_after_or_exponential(state) == expected, (attempt, header)


def test_the_exponential_cap_is_the_number_the_table_scores_against() -> None:
    """`a7-capped` above is 60.0 only if the constant is 60.0; pin it, not a copy."""
    assert shared.MAX_EXPONENTIAL_WAIT_SECONDS == 60.0


def test_a_malformed_response_shape_no_longer_costs_the_retry_budget() -> None:
    """The fix's teeth, measured inside a tenacity loop shaped like embeddings runs.

    #516 ran the same exception through both copies: the guarding one spent all
    three attempts, the indexing one raised from `wait=` and gave up after one — and
    `retrieval/embeddings.py` reports that as "embedding endpoint unreachable", a
    header-shape bug surfacing as an outage. One producer, three attempts.
    """
    exc_to_raise = GatewayError(NULL_HEADERS)
    attempts: list[int] = []

    def attempt() -> None:
        attempts.append(1)
        raise exc_to_raise

    retryer = Retrying(
        retry=retry_if_exception(lambda _exc: True),
        wait=wait_retry_after_or_exponential,
        stop=stop_after_attempt(3),
        reraise=True,
    )
    with pytest.raises(GatewayError):
        retryer(attempt)
    assert len(attempts) == 3, f"spent {len(attempts)} of 3 attempts"


@pytest.mark.parametrize("exc_type", _RETRYABLE_EXCEPTIONS, ids=lambda t: t.__name__)
def test_no_retryable_error_on_the_provider_path_can_reach_a_crash_shape(
    exc_type: type,
) -> None:
    """The boundary of the claim above, per exception type the retryer accepts.

    Each of these is built the way the SDK builds it, so `.response` is a real
    `httpx.Response` — which always carries a `Headers` mapping. That is why the
    divergence #516 measured stayed latent: the live path cannot hand the parser a
    stripped response, only a double or a hand-built error can.
    """
    response = httpx.Response(429, request=httpx.Request("POST", "http://gateway.test"))
    exc = (
        exc_type(request=response.request)
        if "Timeout" in exc_type.__name__ or "Connection" in exc_type.__name__
        else exc_type("rate limited", response=response, body=None)
    )
    assert _outcome(retry_after_seconds, exc)[0] == "value", exc_type.__name__


def test_the_openai_sdk_refuses_a_response_with_no_headers() -> None:
    """Why the SDK path could never have crashed in our parser: it crashes first.

    `RateLimitError.__init__` dereferences `response.headers.get("x-request-id")`,
    so a headerless response is rejected at construction — before tenacity is even
    handed the exception. Measured, not assumed, and it is the reason #517 is
    prospective hardening rather than an incident fix.
    """

    class Stripped:
        request = httpx.Request("POST", "http://gateway.test")
        status_code = 429
        headers = None

    with pytest.raises(AttributeError):
        RateLimitError("rate limited", response=Stripped(), body=None)
