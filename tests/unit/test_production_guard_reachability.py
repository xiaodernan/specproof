"""#79 — the production credential guard must be reachable from the deployment.

`storage/config_guard.py` refuses to boot with shipped default passwords, but
only when `SPECPROOF_ENV=production`, and `api/server.py` calls it unconditionally
on import. Measured before this file existed:

- no deployment entry point set `SPECPROOF_ENV` at all, so `is_production()` was
  false everywhere the product actually runs and the guard could never fire;
- `compose.production.yml` handed every credential a `:-specproof_pass`
  fallback, so an operator who forgot a secret got the shipped default silently
  instead of an error.

These tests read the deployment files themselves. A guard that is only proven by
its own unit test is a guard nobody can reach.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from storage.config_guard import (
    _DEFAULT_CREDENTIALS,
    ProductionConfigError,
    enforce_production_config,
    is_production,
    validate_production_config,
)

REPO = Path(__file__).resolve().parents[2]
PRODUCTION_COMPOSE = REPO / "compose.production.yml"
API_SERVER = REPO / "api" / "server.py"
LOCAL_SCRIPTS = (
    REPO / "scripts" / "start_local.ps1",
    REPO / "scripts" / "start_local_light.ps1",
)

yaml = pytest.importorskip("yaml")

GUARDED_VARS = {var for var, _default in _DEFAULT_CREDENTIALS}


def compose_services() -> dict[str, dict[str, str]]:
    """`{service: {env var: raw value}}` from the production overlay."""
    doc = yaml.safe_load(PRODUCTION_COMPOSE.read_text(encoding="utf-8"))
    services = doc["services"]
    assert isinstance(services, dict) and services, "no services parsed — probe broken"
    return {
        name: dict(spec.get("environment") or {})
        for name, spec in services.items()
    }


def app_services() -> dict[str, dict[str, str]]:
    """Services that run our code — the ones that read credentials as a client.

    Identified by the image/build of this repo, not by name spelling.
    """
    doc = yaml.safe_load(PRODUCTION_COMPOSE.read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}
    for name, spec in (doc["services"] or {}).items():
        builds_repo = "docker/" in str(spec.get("build", ""))
        runs_our_module = "python -m" in str(spec.get("command", ""))
        if builds_repo or runs_our_module:
            out[name] = dict(spec.get("environment") or {})
    assert out, "no application service found in compose.production.yml"
    return out


def test_the_api_actually_calls_the_guard() -> None:
    text = API_SERVER.read_text(encoding="utf-8")
    assert re.search(r"^enforce_production_config\(\)", text, re.M), (
        "api/server.py no longer calls enforce_production_config() at import"
    )


def test_every_app_service_declares_which_environment_it_is() -> None:
    missing = {name for name, env in app_services().items() if "SPECPROOF_ENV" not in env}
    assert not missing, f"services with an unset SPECPROOF_ENV: {sorted(missing)}"


def test_the_value_compose_sets_is_the_value_the_guard_arms_on() -> None:
    """Not 'contains production' — the guard's own predicate must say so."""
    for name, env in app_services().items():
        value = str(env.get("SPECPROOF_ENV", ""))
        previous = os.environ.get("SPECPROOF_ENV")
        os.environ["SPECPROOF_ENV"] = value
        try:
            assert is_production(), (
                f"{name} sets SPECPROOF_ENV={value!r}, which is_production() "
                "does not treat as production — the guard stays inert"
            )
        finally:
            if previous is None:
                del os.environ["SPECPROOF_ENV"]
            else:
                os.environ["SPECPROOF_ENV"] = previous


def test_no_guarded_credential_keeps_a_shipped_default_in_production() -> None:
    offenders: list[str] = []
    for name, env in app_services().items():
        for var, value in env.items():
            if var not in GUARDED_VARS:
                continue
            text = str(value)
            if ":-" in text:
                offenders.append(f"{name}.{var} falls back to a default: {text}")
    assert not offenders, "credentials an operator can silently leave unset:\n  " + "\n  ".join(
        offenders
    )


def phase0_parameterised_vars() -> set[str]:
    """Credentials the infrastructure layer reads from the operator's env.

    A deployment is `compose.phase0.yml` + `compose.production.yml`: the root
    password belongs to the MySQL container, never to the app, yet the guard
    still checks it stack-wide. So "the operator can satisfy this" is answered
    across both files — and both interpolate the SAME host variable, which is
    why requiring it in the app layer cannot desync the servers.
    """
    text = (REPO / "compose.phase0.yml").read_text(encoding="utf-8")
    return {m.group(1) for m in re.finditer(r"\$\{([A-Z_][A-Z0-9_]*)[:?]", text)}


def test_the_guard_covers_every_credential_compose_asks_for() -> None:
    """The two lists must not drift: a required var the guard ignores, or a
    guarded var the profile never asks for, both leave a hole."""
    asked: set[str] = set()
    for env in app_services().values():
        asked |= {var for var, value in env.items() if ":?" in str(value)}
    # Only credential-shaped names are the guard's business; phase0 also
    # parameterises ports and database names, which are not secrets.
    credential_shaped = {
        var for var in asked if var.endswith(("_PASSWORD", "_USER"))
    }
    unchecked = credential_shaped - GUARDED_VARS
    assert not unchecked, (
        f"compose requires credentials the guard never checks: {sorted(unchecked)}"
    )
    unasked = GUARDED_VARS - asked - phase0_parameterised_vars()
    assert not unasked, (
        f"the guard blocks boot on {sorted(unasked)} but no file a deployment "
        "loads reads them from the operator's environment"
    )


def test_production_boot_with_defaults_is_refused_for_real(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wired end-to-end behaviour, not the guard read in isolation."""
    monkeypatch.setenv("SPECPROOF_ENV", str(app_services()["api"]["SPECPROOF_ENV"]))
    for var, default in _DEFAULT_CREDENTIALS:
        monkeypatch.setenv(var, default)
    monkeypatch.setenv("SPECPROOF_API_KEY", "a-real-looking-key")
    assert validate_production_config(), "defaults must be reported as violations"
    with pytest.raises(ProductionConfigError):
        enforce_production_config()


def test_local_scripts_declare_themselves_not_production(monkeypatch: pytest.MonkeyPatch) -> None:
    for script in LOCAL_SCRIPTS:
        assert script.exists(), f"{script.name} moved — this gate no longer covers it"
        text = script.read_text(encoding="utf-8")
        match = re.search(r'\$env:SPECPROOF_ENV\s*=\s*"([^"]+)"', text)
        assert match, f"{script.name} never sets SPECPROOF_ENV; 'unset' is not a decision"
        monkeypatch.setenv("SPECPROOF_ENV", match.group(1))
        assert not is_production(), (
            f"{script.name} sets SPECPROOF_ENV={match.group(1)!r}, which the guard "
            "treats as production — a local demo start would refuse to boot"
        )
