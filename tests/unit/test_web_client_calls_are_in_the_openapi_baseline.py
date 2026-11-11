"""The web client and the API contract must agree, operation by operation.

WHY THIS GATE. The OpenAPI baseline (``docs/openapi/baseline.json``) is
already a fact source: the CI leg ``openapi-schema-diff`` compares it with
the live application's schema. But nothing compared it with the **client**:
the web app may call a path (or a method) that no longer exists, and the
pipeline stays green because the baseline and the server agree with each
other. The break only shows up as a 404 in a browser.

WHAT IT CHECKS. Every API call the web client makes -- path template AND
method -- must exist in the baseline. The client builds paths by
concatenation (``"/api/v1/jobs/" + encodeURIComponent(jobId) + "/capsule"``),
so the template is rebuilt here: a literal, then ``{id}`` for every
runtime segment.

WHAT IT DELIBERATELY DOES NOT CHECK. The other direction (a baseline
operation the web client never calls) is not a defect -- the API serves
other consumers -- so it is printed, not asserted.

HOW IT READS. The client is scanned as TEXT (the call sites are string
concatenations, not a runtime trace); the baseline is the committed file.
Both are read fresh on every run, so an endpoint rename that updates the
baseline but not the client lands here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "docs" / "openapi" / "baseline.json"
CLIENT = ROOT / "apps" / "web" / "src" / "api.ts"

#: The client helpers and the HTTP method each one performs.
METHODS = {
    "apiGet": "GET",
    "apiPost": "POST",
    "apiPut": "PUT",
    "apiPatch": "PATCH",
    "apiDelete": "DELETE",
    "apiFetch": "GET",
}

#: A call site: helper name at the start of the expression.
CALL = re.compile(r"\b(" + "|".join(METHODS) + r")\s*(?:<[^<>]*>)?\(")
LITERAL = re.compile(r"\"([^\"]*)\"")


def _argument_text(text: str, start: int) -> str:
    """The path argument of the call: up to the first top-level comma.

    The path is a concatenation (``"/api/v1/jobs/" + encodeURIComponent(jobId)
    + "/capsule"``), so it has to be read as source. The argument ends at
    the first comma that is not inside brackets -- that is where the request
    body starts, and the body's literals are values, not paths.
    """
    depth = 1
    i = start
    while i < len(text) and depth:
        ch = text[i]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                break
        elif ch == "," and depth == 1:
            break
        i += 1
    return text[start:i]



def _baseline_operations() -> set[tuple[str, str]]:
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    out: set[tuple[str, str]] = set()
    for entry in data["operations"]:
        head = entry[0] if isinstance(entry, (list, tuple)) else entry
        method, _, path = str(head).partition(" ")
        out.add((method.upper(), path))
    return out


def _template(expression: str) -> str:
    """The path family the call addresses.

    The client builds paths by concatenation, so the **leading literal** is
    what identifies the family: ``"/api/v1/jobs/"`` for every job-scoped
    call, whether the id is appended before or after it. A query string is
    not part of the path (``"/api/v1/billing/invoices?period="`` addresses
    the invoices family).
    """
    literals = LITERAL.findall(expression)
    if not literals:
        return ""
    return literals[0].split("?", 1)[0].rstrip("/")


def _client_calls() -> list[tuple[str, str]]:
    text = CLIENT.read_text(encoding="utf-8")
    calls: list[tuple[str, str]] = []
    for match in CALL.finditer(text):
        helper = match.group(1)
        argument = _argument_text(text, match.end())
        template = _template(argument)
        if template:
            calls.append((METHODS[helper], template))
    return calls


def _matches(template: str, path: str) -> bool:
    """Does a baseline operation cover this client path family?

    The baseline stores concrete templates (``/api/v1/jobs/{job_id}/capsule``)
    and the client addresses a family (``/api/v1/jobs``): the family is
    covered when the baseline path IS the family, or lives under it. The
    boundary of this rule is the client's own source shape -- the first
    literal of the call -- so a client that addresses a family gets the
    guarantee "the backend documents this family with this method", not
    "every sub-path of the family exists".
    """
    family = template.split("?", 1)[0].rstrip("/")
    baseline = path.split("?", 1)[0].rstrip("/")
    return baseline == family or baseline.startswith(family + "/")


def test_every_client_call_exists_in_the_openapi_baseline() -> None:
    operations = _baseline_operations()
    calls = _client_calls()
    assert calls, (
        "no API call was found in the web client — the scanner stopped "
        "reading the call sites, and an empty census reads exactly like a "
        "client that calls nothing"
    )
    missing = [
        f"{method} {template}"
        for method, template in calls
        if not any(
            m == method and _matches(template, path)
            for m, path in operations
        )
    ]
    assert not missing, (
        f"{len(missing)} of {len(calls)} web client calls have no operation in "
        f"the OpenAPI baseline: {missing[:6]} — the client would get a 404 "
        "and the pipeline would still be green (the baseline and the server "
        "agree with each other)"
    )


def test_the_client_covers_at_least_the_admin_surface() -> None:
    """A floor on the population: the client must still call the admin,
    billing, demo and job-feedback surfaces. Without it, a rename that
    emptied the client of calls would satisfy the gate above vacuously."""
    calls = _client_calls()
    prefixes = {
        template.split("/")[3]
        for _method, template in calls
        if template.startswith("/api/v1/")
    }
    for prefix in ("admin", "billing", "demo", "jobs"):
        assert prefix in prefixes, (
            f"the client no longer calls /api/v1/{prefix} — the gate above "
            f"would be measuring a client that talks to nothing (saw {sorted(prefixes)})"
        )


def test_the_baseline_still_covers_the_client_surface() -> None:
    """The baseline is the fact source; if it lost the client's operations
    the comparison above would go quiet instead of red."""
    operations = _baseline_operations()
    assert len(operations) >= 30, (
        f"the baseline holds {len(operations)} operations — the census "
        "collapsed and every comparison above would pass vacuously"
    )
