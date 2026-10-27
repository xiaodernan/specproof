"""#459 — one truthy/falsy vocabulary for every boolean env switch.

``MINIO_SECURE`` used to be read as ``os.getenv(...).lower() == "true"``, so
``MINIO_SECURE=1`` (the spelling every other switch in this repo accepts)
silently meant **TLS off** — a security-relevant misread, and exactly the
hand-copied-vocabulary drift class (#404).

The vocabulary still lives at each read site (the env-knob census in
``test_env_template_binds_the_compose_knobs.py`` recognises only the literal
``os.getenv(NAME, DEFAULT)`` carriers, so folding them behind a helper would
make the knobs invisible to it). What this file locks instead is the property
that actually matters: **every shipped switch agrees on the vocabulary**,
behaviourally, whatever its implementation.

A switch may legitimately be *tri-state* (``observability.tracing._flag``
returns ``None`` for unset/unknown so an absent switch is not mistaken for a
deliberate "off"), so the cross-switch assertion covers the truthy/falsy
vocabulary, and the tri-state difference is pinned separately.
"""
from __future__ import annotations

import pytest

from agent.self_test_diff import ALLOW_LOCAL_TEST_EXEC_ENV, self_test_execution_allowed
from observability.tracing import _flag as tracing_flag
from storage.minio import MinIOConfig
from storage.notify_relay import NOTIFY_OUTBOX_ENV, notify_outbox_lane_enabled

TRUTHY_SPELLINGS = ["1", "true", "TRUE", "True", "yes", "YES", "on", "ON", " 1 ", " true "]
FALSY_SPELLINGS = ["0", "false", "FALSE", "no", "NO", "off", "OFF", " 0 ", " false "]
UNSET_OR_JUNK = ["", "   ", "maybe", "2", "enabled"]


@pytest.fixture(autouse=True)
def _clean_minio_port(monkeypatch: pytest.MonkeyPatch) -> None:
    # from_env() also reads MINIO_PORT; keep it out of the way.
    monkeypatch.delenv("MINIO_PORT", raising=False)


def _switches() -> list[tuple[str, str, object]]:
    return [
        ("minio.secure", "MINIO_SECURE", lambda: MinIOConfig.from_env().secure),
        ("notify_outbox", NOTIFY_OUTBOX_ENV, notify_outbox_lane_enabled),
        ("self_test_exec", ALLOW_LOCAL_TEST_EXEC_ENV, self_test_execution_allowed),
    ]


# ── The bug: MINIO_SECURE=1 must mean TLS ON ───────────────────────────


def test_minio_secure_treats_the_standard_truthy_set_as_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The regression: "1" used to compare unequal to "true" and leave TLS off.
    for raw in TRUTHY_SPELLINGS:
        monkeypatch.setenv("MINIO_SECURE", raw)
        assert MinIOConfig.from_env().secure is True, f"MINIO_SECURE={raw!r} did not turn TLS on"


def test_minio_secure_is_off_for_everything_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for raw in [*FALSY_SPELLINGS, *UNSET_OR_JUNK]:
        monkeypatch.setenv("MINIO_SECURE", raw)
        assert MinIOConfig.from_env().secure is False, f"MINIO_SECURE={raw!r} turned TLS on"
    monkeypatch.delenv("MINIO_SECURE")
    assert MinIOConfig.from_env().secure is False


# ── Every shipped switch agrees on the vocabulary ──────────────────────


@pytest.mark.parametrize("raw", TRUTHY_SPELLINGS)
def test_every_switch_treats_truthy_spellings_as_on(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    for label, env_name, reader in _switches():
        monkeypatch.setenv(env_name, raw)
        assert reader() is True, f"{label} did not treat {raw!r} as on"


@pytest.mark.parametrize("raw", FALSY_SPELLINGS)
def test_every_switch_treats_falsy_spellings_as_off(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    for label, env_name, reader in _switches():
        monkeypatch.setenv(env_name, raw)
        assert reader() is False, f"{label} did not treat {raw!r} as off"


@pytest.mark.parametrize("raw", UNSET_OR_JUNK)
def test_every_switch_is_off_for_junk_or_blank(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    for label, env_name, reader in _switches():
        monkeypatch.setenv(env_name, raw)
        assert reader() is False, f"{label} treated junk {raw!r} as on"


# ── The tri-state switch's documented difference ───────────────────────


@pytest.mark.parametrize("raw", TRUTHY_SPELLINGS)
def test_tracing_flag_agrees_on_truthy(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("SPECPROOF_OTEL_ENABLED", raw)
    assert tracing_flag("SPECPROOF_OTEL_ENABLED") is True


@pytest.mark.parametrize("raw", FALSY_SPELLINGS)
def test_tracing_flag_agrees_on_falsy(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("SPECPROOF_OTEL_ENABLED", raw)
    assert tracing_flag("SPECPROOF_OTEL_ENABLED") is False


@pytest.mark.parametrize("raw", [*UNSET_OR_JUNK, "  "])
def test_tracing_flag_is_none_when_unset_or_unrecognised(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    # The tri-state difference is deliberate: an absent switch is not a
    # deliberate "off", so it reports None rather than False.
    monkeypatch.setenv("SPECPROOF_OTEL_ENABLED", raw)
    assert tracing_flag("SPECPROOF_OTEL_ENABLED") is None
    monkeypatch.delenv("SPECPROOF_OTEL_ENABLED")
    assert tracing_flag("SPECPROOF_OTEL_ENABLED") is None
