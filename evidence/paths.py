"""Artifact path resolution — one owner for capsules and the eval report.

Both surfaces that serve evidence artifacts — the HTTP SPA
(``api/routes/web.py``) and the MCP tool layer (``mcp/tools.py``) — must
agree on where the capsule ``*.zip`` files and the persisted evaluation
summary live. Two answers to "where is the capsule for this job?" is how a
browser downloads a file an external agent disagrees is the same one.

Precedence:
  * ``capsule_dirs()``     — ``SPECPROOF_CAPSULE_DIR`` (if set) first,
                             then ``<repo>/capsules/``, then ``<cwd>/capsules/``.
  * ``eval_report_path()`` — ``SPECPROOF_EVAL_REPORT_PATH`` (if set),
                             else ``<repo>/docs/eval/eval-report.results.json``.
"""

from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def capsule_dirs() -> list[Path]:
    """Directories searched for capsule zip/artifact files, in precedence order."""
    dirs: list[Path] = []
    env_dir = os.getenv("SPECPROOF_CAPSULE_DIR", "").strip()
    if env_dir:
        dirs.append(Path(env_dir).resolve())
    dirs.append((_PROJECT_ROOT / "capsules").resolve())
    dirs.append((Path.cwd() / "capsules").resolve())
    return dirs


def eval_report_path() -> Path:
    """Where the persisted evaluation summary lives (env override wins)."""
    env_path = os.getenv("SPECPROOF_EVAL_REPORT_PATH", "").strip()
    if env_path:
        return Path(env_path).resolve()
    return (_PROJECT_ROOT / "docs" / "eval" / "eval-report.results.json").resolve()
