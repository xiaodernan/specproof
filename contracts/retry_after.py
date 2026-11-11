"""The Retry-After contract — one parser, one wait policy (#517).

Two live call paths each carried their own copy of this decision:
``providers/openai_compatible.py`` (chat + responses, via the openai SDK) and
``retrieval/embeddings.py`` (embeddings, via httpx). #516 measured that the two
**wait** wrappers were byte-identical while the two **parsers** they called were
not: the providers copy guards the response object, the retrieval copy indexes
``response.headers.get(...)`` straight through. A byte-identical outer copy is
how a drifted inner decision stays invisible to a clone lens.

The merged semantics are the defensive ones, for a reason that is measured
rather than stylistic: an exception raised inside tenacity's ``wait=`` is not
retried. #517 ran both copies against the same malformed response and counted
attempts — 3 with the guarding parser, 1 with the indexing one — and
``retrieval/embeddings.py`` wraps its retryer in ``except Exception``, so the
crash was reported as "embedding endpoint unreachable". A header-shape bug
would have arrived as an unreachable endpoint, with two of three attempts
already spent.

Reachability, also measured (#517): today the crashing shape cannot arrive from
the gateway. All five retryable SDK errors answer identically in both copies,
the openai SDK refuses to construct an error over a response with no headers
(``response.headers.get("x-request-id")`` runs in its ``__init__``, so the
AttributeError lands before tenacity is ever called), and every
``httpx.Response`` carries a ``Headers`` mapping. What *is* reachable is any
non-httpx response object — a transport double, an adapter that builds its own
error — because ``httpx.HTTPStatusError`` stores whatever response it is handed.
So this is a latent divergence with a misleading failure mode, not an
incident: worth one producer precisely because nothing on the path would have
noticed the two drifting further.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tenacity import RetryCallState

#: Cap on the exponential fallback, in seconds. A gateway that sends no
#: Retry-After must not make a job wait out a minute and a half between probes.
MAX_EXPONENTIAL_WAIT_SECONDS = 60.0

#: The randomness source for the jitter. Module-level so a test can seed it
#: (``_JITTER.seed(...)``) and get a reproducible schedule.
_JITTER = random.Random()


def jittered_wait_seconds(cap: float, *, rng: random.Random | None = None) -> float:
    """Spread a backoff over ``[cap/2, cap]`` (equal jitter).

    WHY JITTER AT ALL. A pure exponential backoff is a **synchronization
    point**: every client that was refused in the same second computes the
    same wait and returns in the same second, so the retry storm arrives as
    a spike instead of a ramp — the provider sees exactly the burst it was
    trying to shed, and the recovery takes longer than it should. The AWS
    "Exponential Backoff and Jitter" note measures the difference; this is
    the "equal jitter" variant (half of the cap fixed, half random), which
    keeps a guaranteed minimum wait -- important here, because the cap may
    BE the server's own ``Retry-After`` hint in spirit -- while still
    spreading the herd.

    The cap itself is unchanged: this only decides WHERE INSIDE the cap the
    wait lands. Passing ``cap`` (rather than the attempt number) keeps the
    cap policy with the caller that owns it (the LLM path and the notify
    relay have different bases) and puts the jitter policy in one place.
    """
    source = rng if rng is not None else _JITTER
    bounded = max(0.0, float(cap))
    half = bounded / 2.0
    return half + source.uniform(0.0, half)



def retry_after_seconds(exc: BaseException) -> float | None:
    """Parse the ``Retry-After`` header of a rate-limited response.

    Seconds form only. Returns None when the header is absent, unparseable
    (an HTTP-date), or reached through a response object that does not carry a
    header mapping — callers then fall back to exponential backoff. This
    function never raises: it runs inside tenacity's ``wait=``, where an
    exception costs the remaining attempts instead of triggering a retry.
    """
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("retry-after") if hasattr(headers, "get") else None
    if raw is None:
        return None
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return None
    return max(0.0, seconds)


def wait_retry_after_or_exponential(retry_state: RetryCallState) -> float:
    """429 → honor Retry-After when present; otherwise capped exponential.

    The server's own ``Retry-After`` is honored **exactly** -- it is an
    instruction, not a hint, and jittering it would retry earlier than the
    server asked. Only the exponential fallback is jittered (#1615): the
    fallback is our own guess, and a guess every client makes identically
    is how a rate-limited provider gets a synchronized retry spike.
    """
    outcome = retry_state.outcome
    exception = outcome.exception() if outcome is not None else None
    retry_after = retry_after_seconds(exception) if exception is not None else None
    if retry_after is not None:
        return retry_after
    cap = min(
        MAX_EXPONENTIAL_WAIT_SECONDS,
        float(2 ** max(0, retry_state.attempt_number - 1)),
    )
    return jittered_wait_seconds(cap)


__all__ = [
    "MAX_EXPONENTIAL_WAIT_SECONDS",
    "jittered_wait_seconds",
    "retry_after_seconds",
    "wait_retry_after_or_exponential",
]
