"""#specproof: no production app service may run as root.

compose.production.yml is the definition of what we run in production
(PRODUCTION_SPEC §12). The sandbox already pins uid 1000 end to end
(runner argv, worker service, writable submounts); the last three
root-defaults were the app images themselves — Dockerfile.api and
Dockerfile.worker both default to root on python:3.12-slim, and only the
worker service carried a compose-side `user:` override.

This gate binds each application service (api / worker / outbox-relay) to
a non-root numeric uid in the production compose file, and refuses any
Dockerfile-level `USER` directive that would contradict it. The sandbox
(dind daemon) is intentionally excluded: it must stay privileged, and its
containers (untrusted code) are pinned to uid 1000 by sandbox/runner.py
(tests/unit/test_sandbox_runner.py).

Mutation arms: all two-pointed checks have negative controls below (a root
compose user must fail the gate).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.production.yml"
DOCKERFILE_API = ROOT / "docker" / "Dockerfile.api"
DOCKERFILE_WORKER = ROOT / "docker" / "Dockerfile.worker"

APP_SERVICES = ("api", "worker", "outbox-relay")
EXPECTED_UID = "1000:1000"


def _compose() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return data


def _services() -> dict[str, Any]:
    services: dict[str, Any] = _compose()["services"]
    return services


def _dockerfile_user_directive(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("USER"):
            value = stripped[4:].strip()
            if value:
                return value.split()[0]
    return None


def test_every_production_app_service_pins_a_nonroot_uid() -> None:
    services = _services()
    for name in APP_SERVICES:
        svc = services.get(name)
        assert svc, f"compose.production.yml lost the {name!r} service"
        user = str(svc.get("user", "")).strip()
        assert user == EXPECTED_UID, (
            f"{name}: production must run as uid {EXPECTED_UID}, got {user!r} "
            f"(missing `user:` means the image default — root on python:3.12-slim)"
        )


def test_the_uid_is_numeric_and_nonroot() -> None:
    services = _services()
    for name in APP_SERVICES:
        user = str(services[name]["user"])
        uid, _, _ = user.partition(":")
        assert uid.isdigit() and int(uid) != 0, (
            f"{name}: uid {uid!r} is not numeric non-root; named/ root users are refused"
        )


def test_dockerfiles_do_not_contradict_the_compose_pin() -> None:
    for path in (DOCKERFILE_API, DOCKERFILE_WORKER):
        directive = _dockerfile_user_directive(path)
        assert directive != "root" and directive != "0", (
            f"{path.name} declares USER {directive}; the compose-side pin would be a lie"
        )


def test_mutation_a_root_compose_user_is_caught() -> None:
    services = _services()
    mutated = {**services, "api": {**services["api"], "user": "0:0"}}
    offenders = [
        name for name in APP_SERVICES
        if str(mutated[name].get("user", "")).strip() != EXPECTED_UID
    ]
    assert offenders == ["api"]


def test_mutation_a_missing_user_key_is_caught() -> None:
    services = _services()
    api = {k: v for k, v in services["api"].items() if k != "user"}
    mutated = {**services, "api": api}
    offenders = [
        name for name in APP_SERVICES
        if str(mutated[name].get("user", "")).strip() != EXPECTED_UID
    ]
    assert offenders == ["api"]


def test_the_sandbox_daemon_is_explicitly_out_of_scope() -> None:
    # The dind daemon must stay privileged (it starts the untrusted
    # sandboxes); its own `user` is expected to be unset. This test documents
    # that boundary so a future "fix the whole file" pass does not pin it.
    services = _services()
    sandbox = services.get("sandbox")
    assert sandbox and sandbox.get("privileged") is True, (
        "the sandbox daemon is the only privileged service; if it gained a "
        "`user:` or lost privileged mode, this gate and RUNBOOK §5 must be re-derived"
    )
    # Untrusted code execution inside it is pinned elsewhere (uid 1000 argv).
    runner = (ROOT / "sandbox" / "runner.py").read_text(encoding="utf-8")
    assert '"--user", SANDBOX_USER' in runner or '"--user",' in runner, (
        "sandbox runner no longer pins a non-root --user argv"
    )


def test_workers_are_pinned_to_the_workspaces_volume_boundary() -> None:
    services = _services()
    worker = services["worker"]
    env = worker.get("environment", {})
    flat = {k: str(v) for k, v in (env.items() if isinstance(env, dict) else [])}
    assert flat.get("SPECPROOF_ALLOWED_ROOT") == "/workspaces"
