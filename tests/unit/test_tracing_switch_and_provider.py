"""The tracing switch must actually switch, and the api must instrument in order (#236).

Two defects, both invisible until someone tries to use them:

A. ``SPECPROOF_OTEL_ENABLED`` is documented as this repo's own on/off switch in
   api/server.py and docs/operations/MIDDLEWARE.md — and nothing read it. Setting
   it to 0 turned nothing off. A switch that changes nothing is worse than no
   switch: the docs promise control that does not exist.

B. ``add_trace_middleware`` wraps the app's handlers with whatever TracerProvider
   is global *at the moment it runs*. With no provider installed it captures the
   SDK's default no-op proxy and every span is discarded silently. Only the
   worker ever called ``init_tracing``, so the api's spans died in exactly that
   way — the ``localhost:4318`` default in OBSERVABILITY.md §1 described the
   worker, not this process.

OpenTelemetry is not a test dependency, so the tests needing the "installed and
enabled" path inject a stub into ``sys.modules``: without it the answer is False
whether or not the switch is wired, and the assertion would pass for the wrong
reason.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from observability import tracing

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def fake_otel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``import opentelemetry`` succeed, as if the extra were installed."""
    monkeypatch.setitem(sys.modules, "opentelemetry", type(sys)("opentelemetry"))


def _baseline_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing set, SDK present: tracing is on. Every A-arm starts here."""
    monkeypatch.setattr(tracing, "_NOOP", False)
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.delenv("SPECPROOF_OTEL_ENABLED", raising=False)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None), ("", None), ("maybe", None), ("2", None),
        ("1", True), ("true", True), ("TRUE", True), ("  yes  ", True),
        ("on", True),
        ("0", False), ("false", False), ("off", False), ("No", False),
    ],
)
def test_the_switch_is_tri_state_and_tolerates_operator_spelling(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: bool | None
) -> None:
    """Unset and unrecognised must stay distinguishable from a deliberate off.

    If unset collapsed to False, every caller that never heard of the variable
    would lose tracing — the very failure mode #236 is undoing for the api.
    """
    if raw is None:
        monkeypatch.delenv("SPECPROOF_OTEL_ENABLED", raising=False)
    else:
        monkeypatch.setenv("SPECPROOF_OTEL_ENABLED", raw)
    assert tracing._flag("SPECPROOF_OTEL_ENABLED") is expected


def test_the_documented_switch_actually_disables_tracing(
    monkeypatch: pytest.MonkeyPatch, fake_otel: None
) -> None:
    """Defect A: ``0`` must mean off, SDK installed and nothing else set."""
    _baseline_on(monkeypatch)
    assert tracing._is_enabled() is True, (
        "baseline: with the SDK present and no switch set, tracing is on — if "
        "this is False the test cannot distinguish A from a missing extra"
    )
    monkeypatch.setenv("SPECPROOF_OTEL_ENABLED", "0")
    assert tracing._is_enabled() is False, (
        "SPECPROOF_OTEL_ENABLED=0 left tracing on; the switch is documented "
        "but unread"
    )


def test_the_switch_can_also_force_tracing_on(
    monkeypatch: pytest.MonkeyPatch, fake_otel: None
) -> None:
    """A one-way off switch cannot be verified by anyone who defaults to off."""
    _baseline_on(monkeypatch)
    monkeypatch.setenv("SPECPROOF_OTEL_ENABLED", "1")
    assert tracing._is_enabled() is True


def test_the_otel_standard_kill_switch_still_beats_an_explicit_on(
    monkeypatch: pytest.MonkeyPatch, fake_otel: None
) -> None:
    """OTEL_SDK_DISABLED is the standard; an operator who sets it means it."""
    _baseline_on(monkeypatch)
    monkeypatch.setenv("SPECPROOF_OTEL_ENABLED", "1")
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    assert tracing._is_enabled() is False


def test_the_native_otel_disable_spelling_is_still_honoured(
    monkeypatch: pytest.MonkeyPatch, fake_otel: None
) -> None:
    """#236 must not narrow the pre-existing lever while adding a repo one.

    Only ``true`` used to count. Reading it through ``_flag`` widens that to
    ``1``/``on``/``yes``; the old spelling has to keep working, and a bogus
    value must not become a deliberate off.
    """
    _baseline_on(monkeypatch)
    monkeypatch.setenv("OTEL_SDK_DISABLED", "false")
    assert tracing._is_enabled() is True, "OTEL_SDK_DISABLED=false must not disable"
    monkeypatch.setenv("OTEL_SDK_DISABLED", "1")
    assert tracing._is_enabled() is False
    monkeypatch.setenv("OTEL_SDK_DISABLED", "garbage")
    assert tracing._is_enabled() is True, (
        "an unrecognised OTEL_SDK_DISABLED value must not silently disable "
        "tracing; it reads as unset, exactly as before"
    )


def _executable_lines(source: str) -> list[str]:
    """Drop comments and blanks.

    The order asserted below is about what the process *does* at import, so a
    comment describing that order must not be able to satisfy it.
    """
    return [
        line
        for line in source.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def test_the_api_installs_a_provider_before_it_instruments_the_app() -> None:
    """Defect B: init_tracing must precede add_trace_middleware in api/server.py.

    The instrumentor captures the global TracerProvider at the moment it runs.
    In the other order it captures the SDK's default no-op proxy and every span
    is discarded with no error — which is why this ran unwired for so long.
    """
    body = _executable_lines((ROOT / "api" / "server.py").read_text(encoding="utf-8"))
    init_at = next(
        (i for i, line in enumerate(body) if "init_tracing(" in line), None
    )
    assert init_at is not None, (
        "api/server.py no longer calls init_tracing: the api process exports "
        "no spans again (only the worker ever installed a provider)"
    )
    mw_at = next(
        (i for i, line in enumerate(body) if "add_trace_middleware(" in line), None
    )
    assert mw_at is not None, "api/server.py no longer attaches the middleware"
    assert init_at < mw_at, (
        f"init_tracing (executable line {init_at}) must run BEFORE "
        f"add_trace_middleware ({mw_at}); the instrumentor captures whatever "
        f"TracerProvider is global when it runs, and with none installed it "
        f"captures a no-op proxy that discards every span silently"
    )


def test_the_api_names_itself_as_its_own_service() -> None:
    """Traces from api and worker must not both report one service name.

    The default is ``specproof-p1``; two processes reporting that name make the
    per-service SLO panels in the Grafana dashboard meaningless.
    """
    source = (ROOT / "api" / "server.py").read_text(encoding="utf-8")
    assert 'service_name="specproof-api"' in source, (
        "api/server.py must pass a distinct service_name to init_tracing, or "
        "api and worker spans are indistinguishable in the collector"
    )


def test_middleware_doc_states_the_precedence_the_code_implements() -> None:
    """MIDDLEWARE.md's env table must say what the switch can and cannot do.

    Before this, the row read ``SPECPROOF_OTEL_ENABLED | (空) | 置 1 开启`` — an
    operator could only learn that 1 enables tracing, never that 0 disables it
    (the entire reason the switch exists, and the thing that had to be fixed)
    nor that the OTel-standard kill switch outranks it. A table that documents
    the "on" half of a tri-state switch and omits the "off" half reads as if
    setting 0 is a no-op, which is precisely the bug this file is named for.

    The assertions are deliberately about the *operator-facing* consequence, not
    about prose: the row must exist, must name both values, and must say which
    wins.
    """
    doc = (ROOT / "docs" / "operations" / "MIDDLEWARE.md").read_text(encoding="utf-8")
    row = next(
        (line for line in doc.splitlines()
         if line.startswith("| SPECPROOF_OTEL_ENABLED")),
        "",
    )
    assert row, (
        "MIDDLEWARE.md's env table no longer has a SPECPROOF_OTEL_ENABLED row, "
        "so the switch api/server.py documents in its own docstring is "
        "undocumented in the operator's table"
    )
    assert "0" in row and "1" in row, (
        f"the row must name both values of a tri-state switch: {row!r} — "
        f"without 0 the table cannot tell an operator how to turn it off"
    )
    assert "关闭" in row, (
        f"the row must state that 0 disables tracing, not just that 1 enables "
        f"it: {row!r}"
    )

    disable_row = next(
        (line for line in doc.splitlines()
         if line.startswith("| OTEL_SDK_DISABLED")),
        "",
    )
    assert disable_row, (
        "MIDDLEWARE.md must document OTEL_SDK_DISABLED: it is the only lever "
        "that ever worked, and leaving it out of the table leaves an operator "
        "with a switch that appears to be the only one"
    )
    assert "高于" in disable_row, (
        f"the row must say OTEL_SDK_DISABLED outranks an explicit 1, or an "
        f"operator debugging \"why is nothing traced\" sees two switches and "
        f"no ordering between them: {disable_row!r}"
    )


def test_the_documented_off_value_is_the_one_the_code_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The doc's "0" must be the literal the switch actually compares against.

    A doc can say "置 0 关闭" while the code accepts only ``false``/``no``; the
    table would then lie in exactly the way the old switch did. This binds the
    wording the row now promises to the literal set ``_flag`` parses.
    """
    for raw, expected in (("0", False), ("1", True)):
        monkeypatch.setenv("SPECPROOF_OTEL_ENABLED", raw)
        assert tracing._flag("SPECPROOF_OTEL_ENABLED") is expected, (
            f"MIDDLEWARE.md documents {raw!r}; the switch must parse it"
        )
    monkeypatch.delenv("SPECPROOF_OTEL_ENABLED")
    assert tracing._flag("SPECPROOF_OTEL_ENABLED") is None, (
        "the row says 未设 = 沿用默认; an unset switch must stay tri-state "
        "None, not False, or every caller that never set it loses tracing"
    )


