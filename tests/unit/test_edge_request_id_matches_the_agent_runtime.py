"""The edge and the agent runtime must speak ONE request-id language.

Both planes mint a request id when the caller did not supply one, and both
put it in the same header — otherwise the id an operator reads off an edge
error is not the id they can grep the upstream logs for. That is the whole
point of the edge minting one (#1558), and it is exactly the kind of claim
that rots silently when one side renames a constant.

This gate reads BOTH sides and compares them:

  * ``api/middleware.py`` — the agent runtime: the header name it reads
    (``REQUEST_ID_HEADER``) and the shape of the id it generates
    (``uuid.uuid4().hex[:16]`` — 16 lowercase hex characters);
  * ``services/gateway/.../EdgeRequestIdGlobalFilter.java`` — the edge: the
    header name it mints and forwards, and the length of the id it generates.

If either side changes its name or its length alone, this gate reds. It does
not start a JVM and does not call the gateway: it compares the two
declarations, which is the part that can drift without a test noticing.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT_MIDDLEWARE = ROOT / "api" / "middleware.py"
EDGE_FILTER = (ROOT / "services" / "gateway" / "src" / "main" / "java"
               / "dev" / "specproof" / "gateway" / "filter"
               / "EdgeRequestIdGlobalFilter.java")

#: The header both planes use.
HEADER = "X-Request-ID"

#: How many hex characters an id has when nobody supplied one.
ID_LENGTH = 16


def _agent_runtime_header() -> str:
    text = AGENT_MIDDLEWARE.read_text(encoding="utf-8")
    match = re.search(r'REQUEST_ID_HEADER\s*=\s*"([^"]+)"', text)
    assert match, (
        f"{AGENT_MIDDLEWARE} no longer declares REQUEST_ID_HEADER as a string "
        "literal — the edge and the agent runtime would then disagree about "
        "the header name without this gate noticing"
    )
    return match.group(1)


def _agent_runtime_id_shape() -> str:
    text = AGENT_MIDDLEWARE.read_text(encoding="utf-8")
    match = re.search(r"uuid\.uuid4\(\)\.hex\[:(\d+)\]", text)
    assert match, (
        f"{AGENT_MIDDLEWARE} no longer generates its request id as "
        "uuid4().hex[:N] — the edge's shape must be re-derived from here"
    )
    return match.group(1)


def _edge_header() -> str:
    text = EDGE_FILTER.read_text(encoding="utf-8")
    match = re.search(r'HEADER\s*=\s*"([^"]+)"', text)
    assert match, (
        f"{EDGE_FILTER} no longer declares its header name as a string literal"
    )
    return match.group(1)


def _edge_id_length() -> str:
    text = EDGE_FILTER.read_text(encoding="utf-8")
    match = re.search(r"ID_LENGTH\s*=\s*(\d+)", text)
    assert match, (
        f"{EDGE_FILTER} no longer declares the id length as a number"
    )
    return match.group(1)


def test_both_planes_use_the_same_request_id_header() -> None:
    agent = _agent_runtime_header()
    edge = _edge_header()
    assert agent == edge, (
        f"the agent runtime reads {agent!r} but the edge mints {edge!r} — a "
        "request id the operator reads off an edge error would not be the id "
        "the upstream logs carry"
    )
    assert agent == HEADER, (
        f"the request-id header moved to {agent!r}; the operator runbooks and "
        f"the dashboards that quote {HEADER!r} would be quoting a header "
        "nobody sends"
    )


def test_both_planes_generate_the_same_id_shape() -> None:
    agent = _agent_runtime_id_shape()
    edge = _edge_id_length()
    assert agent == edge, (
        f"the agent runtime generates {agent} hex characters and the edge "
        f"{edge} — two id shapes in one hop make the operator's grep "
        "path-dependent"
    )
    assert int(agent) == ID_LENGTH, (
        f"the request-id length moved to {agent}; this gate pins {ID_LENGTH} "
        "because the operator-facing shape (16 hex characters) is what the "
        "runbooks document"
    )


def test_the_edge_never_rewrites_an_id_it_was_given() -> None:
    """An inbound id is kept as-is — the caller is correlating its own logs."""
    text = EDGE_FILTER.read_text(encoding="utf-8")
    assert "inbound" in text and "newRequestId()" in text, (
        f"{EDGE_FILTER} no longer reads an inbound id and falls back to a "
        "generated one — the edge must not rewrite a caller's id"
    )
    assert re.search(
        r"inbound\s*==\s*null\s*\|\|\s*inbound\.isBlank\(\)",
        text,
    ), (
        f"{EDGE_FILTER} no longer treats a missing/blank inbound id as "
        "\"generate one\" — a blank header would otherwise be forwarded "
        "upstream as an empty id"
    )
