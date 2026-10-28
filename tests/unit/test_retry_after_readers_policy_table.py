"""#516 — the two 429 wait-policy readers, tabled: the first catch of the census hole.

The clone ratchet compares shipped packages, and until #516 it never opened
`providers`: the package list was a hand-typed tuple and `providers` (18 modules,
imported by `retrieval/`) was not in it. Opening it revealed
`_wait_retry_after_or_exponential` in `providers/openai_compatible.py` and
`retrieval/embeddings.py` as two byte-identical bodies — one decision, "a 429 waits
for Retry-After, otherwise capped exponential", written twice.

The outer copies match. The helper each one calls does **not**, and that is why this
file exists instead of a merge: `providers._retry_after_seconds` guards the response
twice (`getattr(response, "headers", None)`, then `hasattr(headers, "get")`), while
`retrieval._retry_after_seconds` indexes `response.headers.get(...)`. #516 probed
both over sixteen response shapes: they agree on every shape a gateway can actually
send — every header *value*, including the HTTP-date and unparseable forms — and
disagree on exactly three malformed *response* shapes, where providers answers None
(fall back to exponential) and retrieval raises AttributeError.

The coverage asymmetry is how it survived: the providers copy has six direct shape
assertions in `test_providers_dsv4.py`; the retrieval copy had none, and one
end-to-end 429 case in `test_retrieval_hybrid.py`. A copy nobody tested drifted from
a copy somebody did, inside a module the door never opened.

Merging is queued as #517 — it changes behaviour on a live call path, so it needs
its own arms. This table pins the wait seconds the two clients must keep agreeing on
and names the divergence, so #517 cannot silently pick one policy without a claim
going red.
"""
from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from tenacity import Retrying, retry_if_exception, stop_after_attempt

from providers.openai_compatible import _retry_after_seconds as providers_parse
from providers.openai_compatible import _wait_retry_after_or_exponential as providers_wait
from retrieval.embeddings import _retry_after_seconds as retrieval_parse
from retrieval.embeddings import _wait_retry_after_or_exponential as retrieval_wait

Parser = Callable[[BaseException], "float | None"]
Outcome = tuple[str, Any]

#: Stands for "attach nothing at all", so the table can name an exception that
#: carries no `response` attribute rather than one carrying None.
NO_RESPONSE = object()


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
    return SimpleNamespace(headers={"retry-after": raw})


#: The three response shapes a real httpx response never produces, and the whole
#: reason the two parsers currently diverge.
NO_HEADERS_ATTR = SimpleNamespace()
NULL_HEADERS = SimpleNamespace(headers=None)
HEADERS_WITHOUT_GET = SimpleNamespace(headers=object())
DIVERGENT_RESPONSES: tuple[tuple[str, SimpleNamespace], ...] = (
    ("response without headers", NO_HEADERS_ATTR),
    ("headers is None", NULL_HEADERS),
    ("headers has no get()", HEADERS_WITHOUT_GET),
)


#: (label, the `response` an exception carries, providers, retrieval) — every cell
#: was read off a run of both parsers over these sixteen shapes, not off the source.
ANSWER_NONE: Outcome = ("value", None)
SHAPES: list[tuple[str, object, Outcome, Outcome]] = [
    ("no response attribute", NO_RESPONSE, ANSWER_NONE, ANSWER_NONE),
    ("response is None", None, ANSWER_NONE, ANSWER_NONE),
    ("response without headers", NO_HEADERS_ATTR, ANSWER_NONE, ("raise", "AttributeError")),
    ("headers is None", NULL_HEADERS, ANSWER_NONE, ("raise", "AttributeError")),
    ("headers has no get()", HEADERS_WITHOUT_GET, ANSWER_NONE, ("raise", "AttributeError")),
    ("headers empty", SimpleNamespace(headers={}), ANSWER_NONE, ANSWER_NONE),
    ("no retry-after key", SimpleNamespace(headers={"date": "x"}), ANSWER_NONE, ANSWER_NONE),
    ("retry-after '7'", _headers("7"), ("value", 7.0), ("value", 7.0)),
    ("retry-after '7.5'", _headers("7.5"), ("value", 7.5), ("value", 7.5)),
    ("retry-after '0'", _headers("0"), ("value", 0.0), ("value", 0.0)),
    ("retry-after '-3'", _headers("-3"), ("value", 0.0), ("value", 0.0)),
    ("retry-after ''", _headers(""), ANSWER_NONE, ANSWER_NONE),
    ("retry-after None", _headers(None), ANSWER_NONE, ANSWER_NONE),
    ("retry-after int", _headers(7), ("value", 7.0), ("value", 7.0)),
    ("retry-after list", _headers(["7", "8"]), ANSWER_NONE, ANSWER_NONE),
    ("retry-after HTTP-date", _headers("Wed, 21 Oct 2015 07:28:00 GMT"), ANSWER_NONE, ANSWER_NONE),
]

#: The three malformed-response shapes, named once (above) so a merge has to delete
#: them from the same place the table reads them.
DIVERGENT_SHAPES = [label for label, _response in DIVERGENT_RESPONSES]


@pytest.mark.parametrize("label,response,expected_p,expected_r", SHAPES)
def test_each_reader_answers_the_shape_the_table_says(
    label: str, response: object, expected_p: Outcome, expected_r: Outcome
) -> None:
    exc = _exception_for(response)
    assert _outcome(providers_parse, exc) == expected_p, label
    assert _outcome(retrieval_parse, exc) == expected_r, label


def test_the_two_readers_differ_on_exactly_the_measured_three_shapes() -> None:
    """Computed by running both parsers, not by reading the table above.

    Every header *value* has to answer the same way in both: a different wait for
    the same 429 would mean the embeddings client and the chat client honour the
    gateway's rate limit differently, and no test today compares the two numbers.
    If #517 merges the parsers, this goes red and the roster entry for the pair is
    removed with it — a merge is progress, and the gate makes it get recorded.
    """
    disagreed = [
        label
        for label, response, _p, _r in SHAPES
        if _outcome(providers_parse, _exception_for(response))
        != _outcome(retrieval_parse, _exception_for(response))
    ]
    assert disagreed == DIVERGENT_SHAPES, disagreed


def test_the_providers_copy_is_the_defensive_one() -> None:
    """Which copy tolerates a malformed response is itself a claim, not a habit."""
    for _label, response in DIVERGENT_RESPONSES:
        exc = GatewayError(response)
        assert providers_parse(exc) is None
        with pytest.raises(AttributeError):
            retrieval_parse(exc)


@pytest.mark.parametrize(
    ("attempt", "header", "expected"),
    [
        (1, None, 1.0),
        (2, None, 2.0),
        (3, None, 4.0),
        (7, None, 60.0),
        (1, "9", 9.0),
        (7, "9", 9.0),
        (3, "0", 0.0),
    ],
    ids=["a1", "a2", "a3", "a7-capped", "a1-header", "a7-header-beats-cap", "a3-zero"],
)
def test_both_copies_of_the_wait_policy_answer_the_same_seconds(
    attempt: int, header: str | None, expected: float
) -> None:
    """The byte-identical outer pair, measured as numbers rather than as AST.

    The ratchet pins that the two bodies are the same; this pins what they answer,
    so a merge into one home cannot quietly move the 60s cap or let the exponential
    curve beat the gateway's own header.
    """
    response = None if header is None else _headers(header)
    exc = GatewayError(response)
    state = SimpleNamespace(
        outcome=SimpleNamespace(exception=lambda: exc), attempt_number=attempt
    )
    assert providers_wait(state) == expected
    assert retrieval_wait(state) == expected, (attempt, header)


def test_a_header_shape_bug_costs_the_two_clients_different_retry_budgets() -> None:
    """What the measured divergence costs, inside a tenacity loop shaped like the
    one embeddings runs.

    Same exception, two copies of the wait function: the providers copy falls
    through to exponential and spends all three attempts; the retrieval copy raises
    from inside `wait=`, tenacity does not retry a wait-callback failure, and the
    client gives up after one attempt. `retrieval/embeddings.py` then reports it as
    "embedding endpoint unreachable" — a header-shape bug surfacing as an outage.
    """
    exc_to_raise = GatewayError(NULL_HEADERS)

    def run(wait: Callable[[object], float]) -> int:
        attempts: list[int] = []

        def attempt() -> None:
            attempts.append(1)
            raise exc_to_raise

        retryer = Retrying(
            retry=retry_if_exception(lambda _exc: True),
            wait=wait,
            stop=stop_after_attempt(3),
            reraise=True,
        )
        with pytest.raises((GatewayError, AttributeError)):
            retryer(attempt)
        return len(attempts)

    assert run(providers_wait) == 3
    assert run(retrieval_wait) == 1
