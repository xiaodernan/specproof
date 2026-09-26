"""#103 gate: the auth-mode default databases must not move with the cwd.

Before api/data_paths.py, api/identity/store.py and api/routes/billing.py each
defaulted to a bare relative path ("sqlite:specproof_identity.db"). SQLite
resolves that against the process working directory, so the very same
deployment had as many identity databases as it had launch directories: start
the server from anywhere but the repo root and every user and token was gone —
the API answered 401 with nothing to explain it, and `python -m api.identity.cli`
run from another directory provisioned a different file than the server reads.

The tests below are two-sided: they pin the anchored behaviour, and the last one
reads the shipped sources so the relative default cannot come back unnoticed.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from api.data_paths import REPO_ROOT, default_sqlite_url
from api.identity.store import (
    get_identity_store,
    identity_url,
    reset_identity_store,
)
from api.routes.billing import billing_url

REPO = Path(__file__).resolve().parents[2]
IDENTITY_SOURCE = REPO / "api" / "identity" / "store.py"
BILLING_SOURCE = REPO / "api" / "routes" / "billing.py"
HELPERS = {"SPECPROOF_IDENTITY_URL", "SPECPROOF_BILLING_URL", "SPECPROOF_DATA_DIR"}


@pytest.fixture(autouse=True)
def _tenant_mode_with_scratch_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Auth mode on, both URLs unset, and the anchored default kept off the repo."""
    monkeypatch.setenv("SPECPROOF_AUTH_ENABLED", "1")
    for name in HELPERS:
        monkeypatch.delenv(name, raising=False)
    data_dir = tmp_path / "data"
    monkeypatch.setenv("SPECPROOF_DATA_DIR", str(data_dir))
    reset_identity_store()
    yield data_dir
    reset_identity_store()


def sqlite_path(url: str) -> Path:
    assert url.startswith("sqlite:"), url
    return Path(url[len("sqlite:"):])


def test_the_default_identity_database_does_not_move_with_the_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "launch-a"
    second = tmp_path / "launch-b"
    first.mkdir()
    second.mkdir()

    monkeypatch.chdir(first)
    url_from_a = identity_url()
    monkeypatch.chdir(second)
    url_from_b = identity_url()

    assert url_from_a == url_from_b, (
        "the identity default resolved against the working directory again — "
        "each launch directory silently gets its own user/token database"
    )
    path = sqlite_path(url_from_a)
    assert path.is_absolute(), f"the shipped default must be absolute: {path}"
    assert path.name == "specproof_identity.db"
    assert not (first / "specproof_identity.db").exists()
    assert not (second / "specproof_identity.db").exists()


def test_a_user_created_under_one_cwd_survives_a_restart_from_another(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bug's actual user-visible symptom, reproduced through the store."""
    launch_a = tmp_path / "launch-a"
    launch_b = tmp_path / "launch-b"
    launch_a.mkdir()
    launch_b.mkdir()

    monkeypatch.chdir(launch_a)
    store = get_identity_store()
    tenant = store.create_tenant(name="default")
    store.create_user(tenant_id=tenant.id, email="admin@example.com", role="admin")

    # A restart from a different directory: fresh process, fresh cache.
    reset_identity_store()
    monkeypatch.chdir(launch_b)
    reopened = get_identity_store()
    user = reopened.get_user_by_email(tenant.id, "admin@example.com")

    assert user is not None, (
        "starting from another directory lost the admin that was provisioned "
        "before it — this is the silent-401 deployment failure #103 is about"
    )
    assert user.role == "admin"


def test_the_billing_default_is_anchored_the_same_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    billing = billing_url()
    identity = identity_url()
    assert sqlite_path(billing).name == "specproof_billing.db"
    assert sqlite_path(billing).parent == sqlite_path(identity).parent, (
        "identity and billing defaults drifted into different directories"
    )
    assert billing != identity
    assert not (elsewhere / "specproof_billing.db").exists()


def test_an_explicit_url_still_wins_verbatim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SPECPROOF_IDENTITY_URL", f"sqlite:{tmp_path / 'chosen.db'}")
    monkeypatch.setenv("SPECPROOF_BILLING_URL", "mysql://user:pass@host/db")
    assert identity_url() == f"sqlite:{tmp_path / 'chosen.db'}"
    assert billing_url() == "mysql://user:pass@host/db"


def test_legacy_mode_still_opens_no_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPECPROOF_AUTH_ENABLED", "")
    assert identity_url() == ""
    assert billing_url() == ""


def test_the_data_dir_override_is_created_and_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "not" / "created" / "yet"
    monkeypatch.setenv("SPECPROOF_DATA_DIR", str(target))
    url = default_sqlite_url("specproof_identity.db")
    assert sqlite_path(url) == (target / "specproof_identity.db").resolve()
    assert target.is_dir(), (
        "SPECPROOF_DATA_DIR pointing at a fresh directory must work instead of "
        "failing to boot with 'unable to open database file'"
    )


def test_the_anchored_default_never_resolves_to_the_repo_by_accident(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no override the default is the repo root, not wherever we stand."""
    monkeypatch.delenv("SPECPROOF_DATA_DIR", raising=False)
    url = default_sqlite_url("specproof_identity.db")
    assert sqlite_path(url) == REPO_ROOT / "specproof_identity.db"


def test_no_shipped_default_is_a_bare_relative_sqlite_path() -> None:
    """Source-side reverse gate: the relative default must not come back."""
    for source in (IDENTITY_SOURCE, BILLING_SOURCE):
        text = source.read_text(encoding="utf-8")
        assert "_DEFAULT_SQLITE_URL" not in text, (
            f"{source.name} reintroduced a module-level sqlite default instead "
            "of asking api/data_paths.py where the file lives"
        )
        assert "default_sqlite_url(" in text, (
            f"{source.name} no longer resolves its default through "
            "api/data_paths.py, which makes the assertion above vacuous"
        )

    helpers = (REPO / "api" / "data_paths.py").read_text(encoding="utf-8")
    assert 'Path(__file__).resolve().parents' in helpers, (
        "api/data_paths.py lost the source-anchored root: every 'absolute' "
        "default it hands out is relative again"
    )
