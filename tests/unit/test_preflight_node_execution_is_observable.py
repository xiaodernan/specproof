"""Preflight node execution tests (#190) — honest counters at the node
boundary, written WITH the landing (not backfilled).

The node's single execution seam (``run_preflight``) is stubbed with preset
results; everything else runs for real (the upstream-error short-circuit,
the env escape hatch, the fail-open wrapper, the outcome fork, the
``Preflight:`` error injection). One case per outcome word in
PREFLIGHT_OUTCOMES:

- clean: a real probe ran and reported no blocking problems;
- blocked: a real probe ran and reported blocking problems — the injected
  Preflight: errors are what graph._abort_on_preflight turns into an early
  report;
- upstream_errors: intake errors present — the probe is not attempted
  (seam 0 calls);
- disabled: the SPECPROOF_PREFLIGHT escape hatch — probe not attempted;
- probe_error: the runner raised — fail-open (passed=True, a warning, no
  errors key);

plus preflight_runs_total on every path and a drift gate binding the parity
family's regex words to PREFLIGHT_OUTCOMES and to the source literals.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from agent import preflight as pf
from agent.nodes.preflight import (
    ENV_DISABLE,
    ERROR_PREFIX,
    PREFLIGHT_OUTCOMES,
    preflight_node,
)
from observability.metrics import snapshot

ROOT = Path(__file__).resolve().parents[2]

# Derived from the declaration — a new word extends the delta table with it.
_COUNTERS = ("preflight_runs_total",) + tuple(
    f"preflight_outcomes_{word}_total" for word in sorted(PREFLIGHT_OUTCOMES)
)


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


def _before() -> dict[str, float]:
    return {name: _counter(name) for name in _COUNTERS}


def _deltas(before: dict[str, float]) -> dict[str, float]:
    return {name: _counter(name) - start for name, start in before.items()}


def _only(*words: str) -> dict[str, float]:
    """Expected deltas: runs+1 and exactly the named outcome words +1."""
    deltas = dict.fromkeys(_COUNTERS, 0.0)
    deltas["preflight_runs_total"] = 1.0
    for word in words:
        deltas[f"preflight_outcomes_{word}_total"] = 1.0
    return deltas


def _stub_runner(
    monkeypatch: pytest.MonkeyPatch, preset: Any
) -> list[str | None]:
    """Replace the node's execution seam; return the call log."""
    calls: list[str | None] = []

    def fake(workspace: str | None, language: str | None = None) -> Any:  # noqa: ARG001
        calls.append(workspace)
        if isinstance(preset, Exception):
            raise preset
        return preset

    monkeypatch.setattr("agent.nodes.preflight.run_preflight", fake)
    monkeypatch.delenv(ENV_DISABLE, raising=False)
    return calls


def _state(
    tmp_path: Path, errors: list[str] | None = None
) -> dict[str, Any]:
    return {
        "repo_path": str(tmp_path),
        "app_dir": "",
        "errors": list(errors or []),
    }


# ── the outcome family: one case per word ──────────────────────────────────


def test_clean_probe_counts_runs_and_clean(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preset = pf.PreflightResult(language=pf.LANGUAGE_NODE)
    calls = _stub_runner(monkeypatch, preset)

    before = _before()
    out = preflight_node(_state(tmp_path))

    assert _deltas(before) == _only("clean")
    assert len(calls) == 1
    assert out["preflight"]["passed"] is True
    assert out["errors"] == []


def test_blocked_probe_counts_blocked_and_injects_prefixed_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    preset = pf.PreflightResult(
        language=pf.LANGUAGE_JAVA, errors=["Java not found."]
    )
    preset.passed = False
    calls = _stub_runner(monkeypatch, preset)

    before = _before()
    out = preflight_node(_state(tmp_path))

    assert _deltas(before) == _only("blocked")
    assert len(calls) == 1
    assert out["preflight"]["passed"] is False
    # The guard (graph._abort_on_preflight) aborts the job on these errors.
    assert out["errors"] == [f"{ERROR_PREFIX}Java not found."]


def test_upstream_errors_skip_the_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _stub_runner(monkeypatch, pf.PreflightResult())

    before = _before()
    out = preflight_node(
        _state(tmp_path, errors=["Repository path does not exist: x"])
    )

    assert _deltas(before) == _only("upstream_errors")
    assert calls == []
    assert out["preflight"]["not_run"] == "upstream_errors"
    assert "errors" not in out


def test_disabled_env_counts_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _stub_runner(monkeypatch, pf.PreflightResult())
    monkeypatch.setenv(ENV_DISABLE, "0")

    before = _before()
    out = preflight_node(_state(tmp_path))

    assert _deltas(before) == _only("disabled")
    assert calls == []
    assert out["preflight"]["not_run"] == f"disabled_by_{ENV_DISABLE}"
    assert "errors" not in out


def test_probe_error_fails_open_and_counts_probe_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = _stub_runner(
        monkeypatch, RuntimeError("probe infrastructure is broken")
    )

    before = _before()
    out = preflight_node(_state(tmp_path))

    assert _deltas(before) == _only("probe_error")
    assert len(calls) == 1
    # Fail-open: passed stays True, so the outcome word is the only place
    # this fate is visible to the dashboard reader.
    assert out["preflight"]["passed"] is True
    assert out["preflight"]["not_run"] == "probe_error"
    assert out["preflight"]["warnings"] == [
        "Preflight could not run: probe infrastructure is broken"
    ]
    assert "errors" not in out


# ── vocabulary drift gate ──────────────────────────────────────────────────


def test_outcome_vocabulary_matches_parity_and_source() -> None:
    """PREFLIGHT_OUTCOMES == parity regex words == emission literals."""
    from tests.unit.test_observability_metric_parity import (
        CONCATENATED_FAMILIES,
    )

    pattern, _doc = CONCATENATED_FAMILIES["preflight"]
    match = re.search(r"\(([^()]+)\)", pattern.pattern)
    assert match is not None, "pattern must have an alternation group"
    pattern_words = set(match.group(1).split("|"))

    source = (ROOT / "agent" / "nodes" / "preflight.py").read_text(
        encoding="utf-8"
    )
    literals = {
        f"preflight_outcomes_{word}_total"
        for word in re.findall(
            r'incr\("preflight_outcomes_([a-z_]+)_total"\)', source
        )
    }
    assert 'incr("preflight_runs_total")' in source
    declared = {f"preflight_outcomes_{word}_total" for word in PREFLIGHT_OUTCOMES}

    assert literals == declared, (
        f"emission literals {sorted(literals)} must equal the declared "
        f"vocabulary {sorted(declared)}"
    )
    assert pattern_words == set(PREFLIGHT_OUTCOMES), (
        f"parity regex words {sorted(pattern_words)} must equal "
        f"PREFLIGHT_OUTCOMES {sorted(PREFLIGHT_OUTCOMES)}"
    )
