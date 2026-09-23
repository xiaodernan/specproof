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
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

from agent.preflight import LANGUAGE_UNKNOWN, detect_language, run_preflight
from agent.state import Phase0State

# Escape hatch for air-gapped CI or unit tests that must not spawn subprocesses.
ENV_DISABLE = "SPECPROOF_PREFLIGHT"
_DISABLED_VALUES = {"0", "false", "off", "no", "disabled"}

ERROR_PREFIX = "Preflight: "


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
    """
    raw = cast(dict[str, Any], state)
    existing_errors = list(raw.get("errors", []) or [])

    # An upstream intake error (repo/spec missing) is the real cause; do not
    # pile environment noise on top of it.
    if existing_errors:
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

    errors = existing_errors + [f"{ERROR_PREFIX}{msg}" for msg in result.errors]
    return {"preflight": result.to_dict(), "errors": errors}


__all__ = ["ENV_DISABLE", "ERROR_PREFIX", "preflight_node"]
