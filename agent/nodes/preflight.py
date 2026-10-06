"""preflight node — check the toolchain *before* spending minutes on a build.

Roadmap Phase 1.4. `agent/preflight.py` has existed since Phase 0.5 but was
never called, so a missing JDK surfaced several minutes later as raw Maven
stderr. This node runs the language-appropriate checks right after intake and
short-circuits the pipeline when the environment physically cannot produce
evidence.

Guarantees:
  * Never blocks a non-Java repository for a missing JDK (language-aware).
  * Never masks an upstream error (missing repo / spec) with its own result.
  * Fail-open on unknown language: only the universal checks run.
  * Never raises — a probe failure is data, not an exception.

Counters (#190): preflight_runs_total counts every invocation and the
``preflight_outcomes_<word>_total`` family records how the run ended. The
result dict's ``passed=True`` is true for FOUR of the five outcomes (clean
probe, fail-open probe error, disabled escape hatch, upstream short-circuit)
— only the outcome word separates them, so never read ``passed`` alone.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from agent.preflight import LANGUAGE_UNKNOWN, detect_language, run_preflight
from agent.state import Phase0State
from observability.metrics import incr

# Escape hatch for air-gapped CI or unit tests that must not spawn subprocesses.
ENV_DISABLE = "SPECPROOF_PREFLIGHT"
_DISABLED_VALUES = {"0", "false", "off", "no", "disabled"}

ERROR_PREFIX = "Preflight: "

#: The closed set of ways a preflight run can end (#190). Mirrored by the
#: parity family's regex and the behavior tests — a new word must move all
#: three together.
PREFLIGHT_OUTCOMES = frozenset({
    "blocked",          # real probe ran, blocking problems recorded
    "clean",            # real probe ran, no blocking problems
    "disabled",         # ENV_DISABLE escape hatch
    "probe_error",      # runner raised — fail-open
    "upstream_errors",  # intake errors present — probe not attempted
})


def _disabled() -> bool:
    return os.environ.get(ENV_DISABLE, "").strip().lower() in _DISABLED_VALUES


def _workspace(repo_path: str, app_dir: str) -> str | None:
    """Directory holding the build file; None when it is not on disk."""
    if not repo_path:
        return None
    root = Path(repo_path)
    if app_dir:
        candidate = Path(app_dir)
        root = candidate if candidate.is_absolute() else root / candidate
    try:
        return str(root) if root.is_dir() else None
    except OSError:
        return None


def preflight_node(state: Phase0State) -> dict[str, Any]:
    """Probe the toolchain and record the result in ``state["preflight"]``.

    Blocking problems are appended to ``state["errors"]`` with a stable
    ``Preflight:`` prefix so the web layer can map them to action cards.
    #190: emits preflight_runs_total plus exactly one
    ``preflight_outcomes_<word>_total`` per invocation (PREFLIGHT_OUTCOMES
    is the closed vocabulary).
    """
    raw = cast(dict[str, Any], state)
    existing_errors = list(raw.get("errors", []) or [])

    # #190: count every preflight execution that reaches this node
    incr("preflight_runs_total")

    # An upstream intake error (repo/spec missing) is the real cause; do not
    # pile environment noise on top of it.
    if existing_errors:
        # #190: the probe is not attempted — the run's fate is upstream
        incr("preflight_outcomes_upstream_errors_total")
        return {
            "preflight": {
                "passed": True,
                "language": LANGUAGE_UNKNOWN,
                "checks": [],
                "errors": [],
                "warnings": [],
                "skipped": [],
                "not_run": "upstream_errors",
            }
        }

    if _disabled():
        # #190: escape hatch — no probe, no evidence about the environment
        incr("preflight_outcomes_disabled_total")
        return {
            "preflight": {
                "passed": True,
                "language": LANGUAGE_UNKNOWN,
                "checks": [],
                "errors": [],
                "warnings": [],
                "skipped": [],
                "not_run": f"disabled_by_{ENV_DISABLE}",
            }
        }

    repo_path = raw.get("repo_path", "") or ""
    app_dir = raw.get("app_dir", "") or ""
    workspace = _workspace(repo_path, app_dir)

    language = detect_language(repo_path, app_dir)
    try:
        result = run_preflight(workspace, language=language)
    except Exception as exc:  # noqa: BLE001 - preflight must never kill a job
        # A broken probe is not a broken repository: warn and carry on.
        # #190: fail-open — passed=True below, so the outcome word is the
        # only place this fate is visible.
        incr("preflight_outcomes_probe_error_total")
        return {
            "preflight": {
                "passed": True,
                "language": language,
                "checks": [],
                "errors": [],
                "warnings": [f"Preflight could not run: {exc}"],
                "skipped": [],
                "not_run": "probe_error",
            }
        }

    # #190: the fork the guard acts on — blocked appends Preflight: errors
    # that graph._abort_on_preflight turns into an early report.
    if result.passed:
        incr("preflight_outcomes_clean_total")
    else:
        incr("preflight_outcomes_blocked_total")

    errors = existing_errors + [f"{ERROR_PREFIX}{msg}" for msg in result.errors]
    return {"preflight": result.to_dict(), "errors": errors}


__all__ = ["ENV_DISABLE", "ERROR_PREFIX", "PREFLIGHT_OUTCOMES", "preflight_node"]
