"""#96/#97 — the Web audit view must not invent its own copy of the vocabulary.

`storage/mysql.py` stamps every `list_audit_logs` row with a
``job_disposition`` (#95), and `apps/web/src/pages/Audit.tsx` is now the first
place in the product that shows it to a human. That is exactly the seam where
#81's disease returns: a frontend that hand-types the backend's enum values
drifts the moment the backend grows one, and the reader sees a confident,
wrong label.

Both sides are parsed from their sources — the TS map and the route
handler's own `_assert_role(..., frozenset({...}))` — because a hand-copied
expectation would only re-assert what the author already believed.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LABELS = REPO / "apps" / "web" / "src" / "ui" / "auditLabels.ts"
ADMIN_ROUTE = REPO / "api" / "routes" / "admin.py"

from storage.mysql import (  # noqa: E402 — after path setup for symmetry
    AUDIT_ACTIONS,
    AUDIT_JOB_PRESENT,
    AUDIT_JOB_PURGED,
    AUDIT_JOB_SYSTEM_LEVEL,
    AUDIT_JOB_UNEXPLAINED,
)

_DISPOSITION_KEY_RE = re.compile(r"^  ([a-z_]+): \{$", re.MULTILINE)
_ROLES_RE = re.compile(r"AUDIT_ROLES: string\[\] = \[([^\]]*)\]")
_HANDLER_ROLES_RE = re.compile(
    r'@admin_router\.get\("/audit"\).*?_assert_role\(\s*principal,\s*frozenset\(\{([^}]*)\}\)',
    re.DOTALL,
)


def _labels_text() -> str:
    return LABELS.read_text(encoding="utf-8")


def fe_dispositions() -> set[str]:
    """Keys of the TS ``AUDIT_DISPOSITIONS`` map, in its own block only."""
    text = _labels_text()
    _, _, rest = text.partition("AUDIT_DISPOSITIONS: Record<string, AuditDispositionSpec> = {")
    body, _, _ = rest.partition("\n};")
    assert body, "AUDIT_DISPOSITIONS block not parsed — the probe is broken"
    return set(_DISPOSITION_KEY_RE.findall(body))


def fe_roles() -> set[str]:
    match = _ROLES_RE.search(_labels_text())
    assert match, "AUDIT_ROLES not found in auditLabels.ts"
    return {s.strip().strip('"') for s in match.group(1).split(",") if s.strip()}


def server_roles_for_audit() -> set[str]:
    match = _HANDLER_ROLES_RE.search(ADMIN_ROUTE.read_text(encoding="utf-8"))
    assert match, (
        "GET /api/v1/admin/audit no longer asserts a frozenset of roles — "
        "either the handler changed shape or the route moved; the UI gate "
        "cannot be trusted without it"
    )
    return {s.strip().strip('"') for s in match.group(1).split(",") if s.strip()}


def test_the_backend_dispositions_are_all_glossed() -> None:
    declared = {
        AUDIT_JOB_PRESENT,
        AUDIT_JOB_PURGED,
        AUDIT_JOB_SYSTEM_LEVEL,
        AUDIT_JOB_UNEXPLAINED,
    }
    assert fe_dispositions() == declared, (
        f"web-only={sorted(fe_dispositions() - declared)} "
        f"backend-only={sorted(declared - fe_dispositions())} — an auditor "
        "would see a label the store never writes, or a raw token it does"
    )


def test_every_gloss_explains_itself() -> None:
    """A label without a reason is a badge, not an audit aid."""
    text = _labels_text()
    for key in fe_dispositions():
        block = re.search(rf"^  {key}: \{{(.*?)\n  \}},", text, re.DOTALL | re.MULTILINE)
        assert block, f"{key} disappeared from the map"
        body = block.group(1)
        for field in ("label:", "hint:", "cls:"):
            assert field in body, f"AUDIT_DISPOSITIONS.{key} has no {field[:-1]}"
        assert len(re.search(r'hint: "(.*)"', body).group(1)) > 12, (
            f"{key}'s hint is too short to explain the judgement"
        )


def test_the_web_page_does_not_start_a_second_action_vocabulary() -> None:
    """Actions stay backend-declared; the page renders the token verbatim.

    A TS copy of ``AUDIT_ACTIONS`` is how #87 shipped five dead words: the
    audit *action* is the operator's own evidence, so it must not be renamed
    — and a page that renamed it would have to be kept in step forever.
    """
    text = _labels_text()
    keys = set(re.findall(r'^\s{2}"?([a-z_]+)"?:', text, re.MULTILINE))
    invented = keys & set(AUDIT_ACTIONS)
    assert not invented, (
        f"auditLabels.ts enumerates audit actions {sorted(invented)}; the "
        "declaration lives in storage/mysql.py and the page shows the token"
    )


def test_the_nav_gate_matches_the_handler() -> None:
    assert fe_roles() == server_roles_for_audit(), (
        f"UI allows {sorted(fe_roles())} but GET /admin/audit allows "
        f"{sorted(server_roles_for_audit())} — the sidebar would advertise a "
        "page that answers 403"
    )


def test_the_role_gate_is_narrower_than_billing_on_purpose() -> None:
    """The one asymmetry worth locking: operator can bill, not audit.

    If someone "harmonises" the two role sets, this test is where they learn
    the difference was measured from the handler, not copied by mistake.
    """
    roles = server_roles_for_audit()
    assert "operator" not in roles, (
        f"the audit handler now accepts operator {sorted(roles)}; update "
        "auditLabels.ts and DATA_DICTIONARY §1.8 together, not one alone"
    )
    assert roles == {"admin", "auditor"}


# ── #97: the search contract has one owner per fact ────────────

AUDIT_PAGE = REPO / "apps" / "web" / "src" / "pages" / "Audit.tsx"

_RESPONSE_KEYS_RE = re.compile(
    r'return \{\s*\n\s+"audit":.*?\n    \}', re.DOTALL
)
_INTERFACE_RE = re.compile(r"interface AuditResponse \{(.*?)\n\}", re.DOTALL)
_FIELD_RE = re.compile(r"^\s*(\w+):", re.MULTILINE)


def handler_response_keys() -> set[str]:
    text = ADMIN_ROUTE.read_text(encoding="utf-8")
    match = _RESPONSE_KEYS_RE.search(text)
    assert match, (
        "GET /admin/audit no longer returns the literal dict this gate "
        "parses — re-point the probe instead of deleting it"
    )
    return set(re.findall(r'"(\w+)":', match.group(0)))


def page_response_keys() -> set[str]:
    text = AUDIT_PAGE.read_text(encoding="utf-8")
    match = _INTERFACE_RE.search(text)
    assert match, "AuditResponse interface not found in Audit.tsx"
    return set(_FIELD_RE.findall(match.group(1)))


def test_the_page_reads_exactly_the_shape_the_handler_returns() -> None:
    """`total` and `job_present` were added together; a later field must be too.

    The mirror is how the page types its fetch. A key the handler stops
    sending becomes a permanently `null` column the reader trusts; a key the
    handler adds is invisible until someone notices it in the JSON.
    """
    served, read = handler_response_keys(), page_response_keys()
    assert served == read, (
        f"page-only={sorted(read - served)} handler-only={sorted(served - read)}"
    )


def test_the_job_id_shape_is_declared_once() -> None:
    """The pattern lives on the query; the page must not re-derive it.

    A client-side copy would let the two disagree about which ids are legal —
    the page refusing a search the server would have answered, or sending one
    it 422s on. Either way the reader learns about it from a failed click.
    """
    pattern = re.search(
        r'AUDIT_JOB_ID_PATTERN = \(\s*r"([^"]+)"', ADMIN_ROUTE.read_text(encoding="utf-8")
    )
    assert pattern, "AUDIT_JOB_ID_PATTERN not found in admin.py"
    assert "[0-9a-fA-F]" in pattern.group(1), (
        "the id shape no longer accepts the case the reader may paste; the "
        "column's collation is not case sensitive, so refusing one case is a "
        "422 for a search that would have worked"
    )
    page = AUDIT_PAGE.read_text(encoding="utf-8")
    invented = re.findall(r"\[0-9a-fA-F\]|\{8\}|\{12\}", page)
    assert not invented, f"Audit.tsx re-declares the job id shape: {invented}"


#: The first draft of this pattern said `(?:[0-9a-f]{3}-){3}` — three groups of
#: three, not four — and every assertion written against a typed example still
#: passed, because the example was typed from the same wrong idea. The only
#: proof a shape accepts the platform's own ids is to hand it generated ones.
@pytest.mark.parametrize("job_id", [str(uuid.uuid4()) for _ in range(8)] + [
    str(uuid.UUID(int=0)),
    "11111111-2222-3333-4444-555555555555".upper(),
])
def test_the_declared_shape_accepts_the_ids_the_platform_writes(job_id: str) -> None:
    declared = _handler_job_id_pattern()
    assert re.fullmatch(declared, job_id), (
        f"{job_id} is a real job id the audit filter would 422 away"
    )


@pytest.mark.parametrize(
    "job_id",
    [
        "",
        "not-a-uuid",
        "1111111-2222-3333-4444-555555555555",  # one hex short
        "11111111-2222-3333-4444-5555555555555",  # one hex over
        "11111111222233334444555555555555",  # right bytes, no dashes
        "11111111-2222-3333-4444-55555555555g",  # not hex
        "'; DROP TABLE audit_logs; --",
        "%27%3B%20DROP",
    ],
)
def test_the_declared_shape_refuses_everything_the_column_cannot_hold(job_id: str) -> None:
    assert not re.fullmatch(_handler_job_id_pattern(), job_id), (
        f"{job_id!r} would reach the store as a filter that can never match"
    )


def _handler_job_id_pattern() -> str:
    match = re.search(
        r'AUDIT_JOB_ID_PATTERN = \(\s*r"([^"]+)"', ADMIN_ROUTE.read_text(encoding="utf-8")
    )
    assert match, "AUDIT_JOB_ID_PATTERN not found in admin.py"
    return match.group(1)


def test_the_page_asks_for_the_parameter_the_handler_accepts() -> None:
    server_param = re.search(
        r"(?m)^\s+(\w+): str \| None = Query\(default=None, pattern=",
        ADMIN_ROUTE.read_text(encoding="utf-8"),
    )
    assert server_param, "no pattern-validated optional query param on /admin/audit"
    page = AUDIT_PAGE.read_text(encoding="utf-8")
    assert f'"{server_param.group(1)}=' in page or f'&{server_param.group(1)}=' in page, (
        f"the page never sends {server_param.group(1)} — the filter is cosmetic"
    )


def test_the_offered_windows_all_fit_the_handlers_declared_range() -> None:
    limits = re.search(r"const LIMITS = \[([^\]]*)\]", AUDIT_PAGE.read_text(encoding="utf-8"))
    window = re.search(
        r"limit: int = Query\(default=\d+, ge=(\d+), le=(\d+)\)",
        ADMIN_ROUTE.read_text(encoding="utf-8"),
    )
    assert limits and window, "LIMITS or the limit window declaration moved"
    offered = {int(v) for v in limits.group(1).split(",") if v.strip()}
    low, high = int(window.group(1)), int(window.group(2))
    outside = sorted(v for v in offered if not low <= v <= high)
    assert not outside, f"{outside} would only produce a 422 (handler allows {low}..{high})"


def test_the_handler_gate_matches_the_matrix_cell_the_middleware_checks() -> None:
    """Three copies of "who may read the audit trail" must be one rule.

    ``test_the_nav_gate_matches_the_handler`` reconciles the UI with the
    handler's hand-written ``frozenset({...})``. Nothing reconciled *that* set
    with ``ROLE_MATRIX`` — the cell ``TenantAuthMiddleware`` actually enforces,
    since classify_request maps /api/v1/admin/audit onto admin:audit. Two
    hand-written encodings of one §2 rule drift without anyone noticing: the
    middleware would admit a role into a handler that 403s it, or the sidebar
    would advertise a page the matrix refuses.

    The expected set is derived from the matrix, never typed here, and the last
    assertion pins the cell this test is about — otherwise the parity below
    would compare the handler against a rule nobody enforces.
    """
    from api.identity.principal import ROLE_MATRIX, classify_request

    matrix_granted = {
        role
        for role, resources in ROLE_MATRIX.items()
        if "audit" in resources.get("admin", frozenset())
    }
    handler = server_roles_for_audit()
    assert matrix_granted == handler, (
        f"ROLE_MATRIX grants admin:audit to {sorted(matrix_granted)} but "
        f"GET /admin/audit asserts {sorted(handler)} — one of the two gates "
        "will refuse a caller the other admitted"
    )
    assert fe_roles() == matrix_granted, (
        f"the sidebar lists {sorted(fe_roles())} for a matrix cell held by "
        f"{sorted(matrix_granted)}"
    )
    assert matrix_granted, (
        "nobody holds admin:audit in the matrix, so the parity above is "
        "vacuous and the endpoint is unreachable by design"
    )
    cell = classify_request("GET", "/api/v1/admin/audit")
    assert cell is not None and (cell.resource, cell.action) == ("admin", "audit"), (
        "classify_request no longer maps the audit route onto the cell this "
        "test reconciles — the comparison below proves nothing"
    )
