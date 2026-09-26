"""#105 gate: a scope string must name a cell the RBAC matrix actually has.

Scopes narrow. Once a token carries any scope at all, a request has to be
covered by it (api/identity/principal.py::principal_denial), so "job:read" —
one missing 's' — does not merely fail to grant job reads: it strips every
permission the credential would otherwise have had. Before this milestone the
operator learned that later, from the holder's 403, which named the scopes
truthfully and the typo not at all.

Two-sided like the rest of this lane: the refusals are behaviour, the accepted
vocabulary is generated from the matrix instead of retyped here, and the last
tests prove the guard sits on the only path that can create a token.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from api.identity import cli
from api.identity.principal import ALL_ACTIONS, RESOURCES, scope_cells
from api.identity.tokens import ScopeVocabularyError, mint_token
from storage.identity import IdentityStore, build_identity_store

REPO = Path(__file__).resolve().parents[2]
ADMIN_SOURCE = REPO / "api" / "routes" / "admin.py"
TOKENS_SOURCE = REPO / "api" / "identity" / "tokens.py"


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


def mint(store: IdentityStore, scopes: str) -> str:
    _row, token = mint_token(store, user_id=user_id(store), name="t", scopes=scopes)
    return token


# ── refusals name the gate and the remedy ───────────────────────────────────
def test_a_typoed_resource_is_refused_and_lists_the_real_resources(store) -> None:
    with pytest.raises(ScopeVocabularyError) as exc:
        mint(store, "job:read")
    message = str(exc.value)
    assert "'job:read'" in message
    assert "unknown resource" in message
    for resource in RESOURCES:
        assert resource in message, f"the remedy must list resources: {message}"
    assert "jobs:read" in message, "the operator should see the cell they meant"


def test_a_typoed_action_is_refused_and_lists_that_resources_actions(store) -> None:
    with pytest.raises(ScopeVocabularyError) as exc:
        mint(store, "cases:reed")
    message = str(exc.value)
    assert "unknown action 'reed'" in message
    for action in sorted(ALL_ACTIONS["cases"]):
        assert action in message, f"cases actions must be listed: {message}"


def test_a_string_that_is_not_a_pair_is_refused_with_the_format(store) -> None:
    with pytest.raises(ScopeVocabularyError) as exc:
        mint(store, "jobs")
    message = str(exc.value)
    assert "is not a scope" in message
    assert "<resource>:<action>" in message


def test_every_bad_item_in_one_request_is_reported(store) -> None:
    with pytest.raises(ScopeVocabularyError) as exc:
        mint(store, "job:read, cases:reed, admin:delete")
    assert str(exc.value).count("names unknown") == 3, str(exc.value)


def test_a_refused_scope_stores_no_token_row(store) -> None:
    tenant = store.list_tenants()[0]
    owner = user_id(store)
    with pytest.raises(ScopeVocabularyError):
        mint(store, "billing:write")  # billing has one action: read
    assert store.list_users(tenant.id)[0].id == owner
    # Nothing half-exists: the same operator can still mint the real cell.
    assert mint(store, "billing:read").startswith("sp_")


# ── the accepted vocabulary is read from the matrix, not retyped ────────────
@pytest.mark.parametrize("scope", scope_cells())
def test_every_matrix_cell_can_be_minted(store, scope: str) -> None:
    assert mint(store, scope).startswith("sp_")


@pytest.mark.parametrize(
    "raw",
    ["", "*", "jobs:*", "admin:*", "jobs:read,billing:*", " jobs:read , * "],
)
def test_the_wildcard_and_empty_forms_stay_valid(store, raw: str) -> None:
    assert mint(store, raw).startswith("sp_")


# ── the guard is armed at the entry points, not only in the helper ──────────
def test_the_cli_refuses_and_prints_no_token(store, capsys, monkeypatch) -> None:
    monkeypatch.setattr(cli, "get_identity_store", lambda: store)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["mint-token", user_id(store), "--scopes", "job:read"])
    assert exit_info.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == "", f"a refused token must never reach stdout: {captured.out!r}"
    assert "refusing to mint" in captured.err
    assert "unknown resource" in captured.err


def test_the_cli_still_mints_a_valid_scope(store, capsys, monkeypatch) -> None:
    monkeypatch.setattr(cli, "get_identity_store", lambda: store)
    assert cli.main(["mint-token", user_id(store), "--scopes", "jobs:read"]) == 0
    assert "sp_" in capsys.readouterr().out


def test_mint_token_validates_before_anything_is_written() -> None:
    source = TOKENS_SOURCE.read_text(encoding="utf-8")
    body = source[source.index("def mint_token(") :]
    assert "scope_problems(" in body, (
        "mint_token no longer checks the scope vocabulary, so a narrowed, "
        "silently useless credential can be created again"
    )
    assert body.index("scope_problems(") < body.index("store.create_api_token("), (
        "validation runs after the row is written: the token would exist even "
        "though the request was refused"
    )


def test_the_admin_route_reports_a_caller_mistake_not_a_provider_failure() -> None:
    source = ADMIN_SOURCE.read_text(encoding="utf-8")
    assert "except ScopeVocabularyError as exc:" in source, (
        "POST /api/v1/admin/tokens no longer distinguishes a bad scope string "
        "from an unconfigured provider"
    )
    start = source.index("except ScopeVocabularyError as exc:")
    block = source[start : start + source[start:].index("\n    except ")]
    assert "VALIDATION_FAILED" in block, block
    assert "PROVIDER_UNAVAILABLE" not in block, (
        "a caller typo surfaced as 503 sends the operator to debug the server"
    )
    assert "status_code=503" in source[source.index("except TokenConfigError") :], (
        "the missing-HMAC-key case must still be a provider failure, otherwise "
        "the assertion above proves nothing"
    )


def test_nothing_outside_the_choke_point_writes_a_token_row() -> None:
    """The scope guard protects mint_token; a second write path would bypass it."""
    lanes = ("api", "storage", "ops", "scripts", "integrations", "cli")
    writers = {
        str(path.relative_to(REPO))
        for lane in lanes
        if (REPO / lane).is_dir()
        for path in (REPO / lane).rglob("*.py")
        if "create_api_token(" in path.read_text(encoding="utf-8")
    }
    assert writers == {
        "api" + os.sep + "identity" + os.sep + "tokens.py",
        "storage" + os.sep + "identity.py",
    }, f"a token can be created without the vocabulary check: {sorted(writers)}"
