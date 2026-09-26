"""#106 gate: every scope the vocabulary offers must be a scope a route honours.

`api/identity/principal.py` defines the RBAC vocabulary, and `mint_token` (post
#105) now refuses a scope that names a cell outside it. That still left one way
to mint a credential that does nothing: a cell the matrix *does* define but that
no request is ever checked against. `cases:verify` was exactly that — granted to
admin and auditor in the design table ("读+验签"), while every HTTP path lands on
`classify_request`'s other cells and the certificate endpoint
(`GET /api/v1/jobs/{job_id}/certificate`) is classified as `cases:read`. Because
scopes NARROW, an admin who followed the doc and minted `--scopes cases:verify`
got a token that grants nothing and quietly strips the read the role already had.

So the vocabulary and the route table have to be reconciled from both sides:
a cell is either reachable by a real operation or explicitly declared
unreachable with the reason and a working substitute — and a declaration cannot
survive once a route starts honouring it. Both directions are derived from the
app's own OpenAPI operations rather than hand-copied, because a hand-copied
route list would keep passing after the routes changed.
"""

from __future__ import annotations

import inspect

import pytest

from api.identity.principal import (
    CELLS_WITHOUT_A_ROUTE,
    ROLE_MATRIX,
    Principal,
    classify_request,
    mintable_cells,
    principal_denial,
    scope_cells,
)
from api.identity.tokens import ScopeVocabularyError, mint_token
from api.server import app
from storage.identity import IdentityStore, build_identity_store

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head")


def operations() -> list[str]:
    """Every `METHOD /path` the shipped app exposes.

    `app.routes` under-reports in this FastAPI version (included routers stay
    lazy), so the OpenAPI document is the enumeration that can be trusted.
    """
    paths = app.openapi()["paths"]
    return [
        f"{method.upper()} {path}"
        for path, item in sorted(paths.items())
        for method in sorted(item)
        if method in HTTP_METHODS
    ]


def reachable_cells() -> dict[str, list[str]]:
    """cell -> the operations the middleware would check against it."""
    hits: dict[str, list[str]] = {}
    paths = app.openapi()["paths"]
    for path, item in sorted(paths.items()):
        for method in sorted(item):
            if method not in HTTP_METHODS:
                continue
            cell = classify_request(method.upper(), path)
            if cell is not None:
                hits.setdefault(f"{cell.resource}:{cell.action}", []).append(
                    f"{method.upper()} {path}"
                )
    return hits


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> IdentityStore:
    monkeypatch.setenv("SPECPROOF_TOKEN_HMAC_KEY", "ab" * 32)
    monkeypatch.setenv("SPECPROOF_BCRYPT_ROUNDS", "4")
    identity = build_identity_store("")
    tenant = identity.create_tenant(name="default")
    identity.create_user(tenant_id=tenant.id, email="op@example.com", role="operator")
    return identity


def user_id(store: IdentityStore) -> str:
    tenant = store.list_tenants()[0]
    return store.list_users(tenant.id)[0].id


def mint(store: IdentityStore, scopes: str) -> None:
    mint_token(store, user_id=user_id(store), name="t", scopes=scopes)


# ── the route table is read, not asserted ────────────────────────────────────
def test_the_operation_enumeration_is_the_real_one() -> None:
    """A gate over an empty or stubbed route list would prove nothing."""
    ops = operations()
    assert len(ops) > 40, f"expected the shipped operation set, got {len(ops)}"
    assert "GET /api/v1/admin/audit" in ops
    assert "GET /api/v1/jobs/{job_id}/certificate" in ops


def test_classification_never_invents_a_cell_outside_the_matrix() -> None:
    """`classify_request` may not gate routes on a cell the vocabulary lacks.

    If it did, the middleware would refuse with a scope the operator cannot
    mint: `mint_token` rejects the only string that would satisfy it.
    """
    invented = sorted(set(reachable_cells()) - set(scope_cells()))
    assert not invented, f"routes are gated on cells the matrix has no name for: {invented}"


# ── both directions of the reconciliation ────────────────────────────────────
def test_every_vocabulary_cell_is_either_routed_or_declared() -> None:
    unmintable = sorted(
        set(scope_cells()) - set(reachable_cells()) - set(CELLS_WITHOUT_A_ROUTE)
    )
    assert not unmintable, (
        f"these cells are mintable but no request is ever checked against them: "
        f"{unmintable}. A token scoped to one of them grants nothing and narrows "
        f"away what the roles allow — either route one, or add the cell to "
        f"CELLS_WITHOUT_A_ROUTE with the reason and a working substitute."
    )


def test_the_declaration_has_no_stale_entry() -> None:
    """Once a route honours a cell, the escape hatch must shrink.

    Kept honest in this direction too: a declaration that outlives the gap is a
    permanent refusal to mint a scope that has since become useful.
    """
    stale = sorted(set(CELLS_WITHOUT_A_ROUTE) & set(reachable_cells()))
    assert not stale, (
        f"these cells are now reachable from a route, so minting them is "
        f"legitimate again: {stale} — remove them from CELLS_WITHOUT_A_ROUTE"
    )


def test_a_declared_cell_is_a_real_cell_of_the_matrix() -> None:
    unknown = sorted(set(CELLS_WITHOUT_A_ROUTE) - set(scope_cells()))
    assert not unknown, f"the declaration lists non-cells: {unknown}"


def test_every_declared_cell_names_a_substitute_that_does_work() -> None:
    """The refusal text has to end with something the operator can mint.

    'This scope grants nothing' alone sends an admin to guess; the sentence is
    only correct if the alternative it points at really is routed.
    """
    routed = set(reachable_cells())
    for cell, reason in CELLS_WITHOUT_A_ROUTE.items():
        assert reason.strip(), f"{cell} is declared without a reason"
        assert any(alt in reason for alt in routed), (
            f"{cell}'s reason must point at a routed cell: {reason}"
        )


# ── the harm, behaviourally ─────────────────────────────────────────────────
def test_a_dead_cell_cannot_be_minted_and_says_what_to_mint_instead(
    store: IdentityStore,
) -> None:
    for cell in CELLS_WITHOUT_A_ROUTE:
        with pytest.raises(ScopeVocabularyError) as exc:
            mint(store, cell)
        assert cell in str(exc.value)
        assert "cases:read" in str(exc.value)


def test_the_mint_remedy_list_offers_only_mintable_cells(
    store: IdentityStore,
) -> None:
    """'valid scopes are: ...' must not advertise the cell it just refused."""
    with pytest.raises(ScopeVocabularyError) as exc:
        mint(store, "cases:verify")
    remedy = str(exc.value).split("valid scopes are:", 1)[1]
    assert "cases:read" in remedy
    for cell in CELLS_WITHOUT_A_ROUTE:
        assert cell not in remedy, (
            f"the remedy list still advertises a dead cell: {remedy}"
        )


@pytest.mark.parametrize("cell", mintable_cells())
def test_every_cell_that_a_route_honours_is_still_mintable(
    store: IdentityStore, cell: str
) -> None:
    """The new refusal must not narrow the legitimate vocabulary by one."""
    mint(store, cell)


def test_a_multi_word_scope_list_survives_when_only_live_cells_are_named(
    store: IdentityStore,
) -> None:
    mint(store, "jobs:read, billing:read")


def test_the_resource_wildcard_still_covers_a_partly_dead_resource(
    store: IdentityStore,
) -> None:
    """`cases:*` is honest: it covers read+trigger even though verify is dead."""
    mint(store, "cases:*")


def test_a_token_scoped_to_the_dead_cell_cannot_read_the_certificate(
    store: IdentityStore,
) -> None:
    """The consequence the operator used to discover from someone else's 403.

    Same role (auditor), same route (`cases:read` for the certificate
    endpoint), two scope strings: the dead one is refused and says why in
    terms of the gate that really closed.
    """
    auditor = Principal(
        user_id="u", tenant_id="t", roles=frozenset({"auditor"}),
        scopes=frozenset({"cases:verify"}),
    )
    denial = principal_denial(auditor, "cases", "read")
    assert denial is not None
    assert "cases:verify" in denial
    assert "cases:read" in denial

    working = Principal(
        user_id="u", tenant_id="t", roles=frozenset({"auditor"}),
        scopes=frozenset({"cases:read"}),
    )
    assert principal_denial(working, "cases", "read") is None


def test_no_role_holds_only_cells_that_no_route_asks_for() -> None:
    """Every role must be able to do at least one thing on the HTTP surface.

    A role whose whole grant is dead cells is a login that opens nothing — the
    kind of account that reads as 'broken product' to the person inside it.
    """
    routed = set(reachable_cells())
    for role, grants in sorted(_role_cells().items()):
        usable = sorted(set(grants) & routed)
        assert usable, f"role {role!r} cannot perform any routed action: {grants}"
    assert _role_cells(), "no roles in the matrix, so the loop above proves nothing"


def _role_cells() -> dict[str, set[str]]:
    return {
        role: {
            f"{resource}:{action}"
            for resource, actions in grants.items()
            for action in actions
        }
        for role, grants in ROLE_MATRIX.items()
    }


# ── the guard sits on the only path that creates a token ────────────────────
def test_mint_token_advertises_only_the_cells_it_will_accept() -> None:
    source = inspect.getsource(mint_token)
    assert "mintable_cells(" in source, source
    assert "scope_cells(" not in source, (
        "the 'valid scopes are:' list must not be built from the raw vocabulary, "
        "which still contains cells nothing enforces"
    )
