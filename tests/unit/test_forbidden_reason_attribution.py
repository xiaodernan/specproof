"""#101 — a 403 must name the gate that actually closed.

Found by the #100 live pass: an admin token minted with ``--scopes
admin:audit,jobs:read`` landed on the dashboard and was told
``role ['admin'] may not read on cases``. The role DOES allow
``cases:read`` (ROLE_MATRIX); the token's scope list is what refused. The one
action that fixes a scope refusal — mint a wider token — is a different action
from the one a role refusal calls for, so naming the wrong gate sends an
operator to edit roles on a correct diagnosis.
"""

from __future__ import annotations

from pathlib import Path

from api.identity.principal import Principal, principal_allowed, principal_denial

REPO = Path(__file__).resolve().parents[2]
MIDDLEWARE = REPO / "api" / "middleware.py"
PRINCIPAL = REPO / "api" / "identity" / "principal.py"


def _principal(roles: set[str], scopes: set[str]) -> Principal:
    return Principal(
        user_id="u-1",
        tenant_id="t-1",
        roles=frozenset(roles),
        scopes=frozenset(scopes),
    )


def test_a_scope_refusal_names_the_scope_and_the_remedy() -> None:
    admin = _principal({"admin"}, {"admin:audit", "jobs:read"})
    denial = principal_denial(admin, "cases", "read")
    assert denial is not None
    assert "do not cover cases:read" in denial, denial
    assert "mint a token with --scopes cases:read" in denial, denial
    assert not denial.startswith("role "), (
        f"a scope refusal is worded as a role refusal: {denial!r} — the role "
        "here allows the action, so the operator would change roles instead"
    )
    assert principal_allowed(admin, "cases", "read") is False


def test_a_role_refusal_still_names_the_role() -> None:
    viewer = _principal({"viewer"}, set())
    denial = principal_denial(viewer, "admin", "audit")
    assert denial is not None
    assert denial.startswith("role ['viewer'] may not audit on admin"), denial
    assert "token scopes" not in denial, (
        f"an unscoped viewer is refused for its role, not for scopes: {denial!r}"
    )


def test_a_role_refusal_with_scopes_blames_never_the_scopes() -> None:
    # Viewer holding an explicit scope list: the role gate closes FIRST, so the
    # message must not advertise --scopes as the remedy for a role it lacks.
    viewer = _principal({"viewer"}, {"jobs:read"})
    denial = principal_denial(viewer, "admin", "audit")
    assert denial is not None
    assert denial.startswith("role ['viewer']"), denial


def test_an_allowed_call_is_not_refused_by_either_gate() -> None:
    auditor = _principal({"auditor"}, {"cases:*"})
    assert principal_denial(auditor, "cases", "verify") is None
    assert principal_allowed(auditor, "cases", "verify") is True
    # Empty scopes mean "roles decide", not "nothing is allowed".
    assert principal_denial(_principal({"auditor"}, set()), "cases", "verify") is None


def test_the_middleware_reports_the_denial_it_was_given() -> None:
    middleware = MIDDLEWARE.read_text(encoding="utf-8")
    assert "principal_denial(" in middleware, (
        "api/middleware.py no longer routes the 403 through principal_denial — "
        "re-point this gate, do not delete it"
    )
    assert "may not " not in middleware, (
        "api/middleware.py writes its own 403 sentence again; the reason must "
        "come from the gate that closed"
    )
    assert "may not " in PRINCIPAL.read_text(encoding="utf-8"), (
        "the role-arm wording disappeared from principal.py, which makes the "
        "assertion above vacuous"
    )
