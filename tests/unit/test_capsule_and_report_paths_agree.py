"""#493 — the API and the MCP tool must find the same capsules and report.

``api/routes/web.py`` and ``mcp/tools.py`` each carry their own
``_capsule_dirs()`` and ``_eval_report_path()``. The bodies are identical today
— but each resolves them against **its own** ``_PROJECT_ROOT``, computed from a
different directory depth (``parents[2]`` from ``api/routes/``, ``parents[1]``
from ``mcp/``). They agree only because both depths happen to land on the
repository root; move either file one level and the two silently search
different directories.

That failure mode is invisible: the MCP tool would list a capsule the web UI
cannot open, or vice versa, and both would look self-consistent. This file pins
the agreement — the default, the env override, and the precedence order — so a
divergence turns red instead.

``_reports_dir()`` has no MCP twin, so there is nothing to compare for it.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from api.routes.web import _capsule_dirs as api_capsule_dirs
from api.routes.web import _eval_report_path as api_eval_report_path
from mcp.tools import _capsule_dirs as mcp_capsule_dirs
from mcp.tools import _eval_report_path as mcp_eval_report_path


@pytest.fixture(autouse=True)
def _clean_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("SPECPROOF_CAPSULE_DIR", "SPECPROOF_EVAL_REPORT_PATH"):
        monkeypatch.delenv(name, raising=False)


def test_the_two_layers_search_the_same_capsule_dirs() -> None:
    assert api_capsule_dirs() == mcp_capsule_dirs()


def test_the_two_layers_honour_the_capsule_dir_override(tmp_path: Path) -> None:
    os.environ["SPECPROOF_CAPSULE_DIR"] = str(tmp_path)
    try:
        api = api_capsule_dirs()
        mcp = mcp_capsule_dirs()
        assert api == mcp
        # the override comes first: order is precedence.
        assert api[0] == tmp_path.resolve()
    finally:
        os.environ.pop("SPECPROOF_CAPSULE_DIR", None)


def test_the_capsule_dirs_end_at_the_repository_then_the_cwd() -> None:
    dirs = api_capsule_dirs()
    assert len(dirs) >= 2
    # repository capsules before the cwd's, so a stale cwd copy cannot shadow it.
    assert dirs[-2].name == "capsules" and dirs[-2].parent == Path(__file__).resolve().parents[2]
    assert dirs[-1] == (Path.cwd() / "capsules").resolve()


def test_the_two_layers_resolve_the_same_eval_report_path() -> None:
    assert api_eval_report_path() == mcp_eval_report_path()


def test_the_two_layers_honour_the_eval_report_path_override(tmp_path: Path) -> None:
    target = tmp_path / "custom-report.json"
    os.environ["SPECPROOF_EVAL_REPORT_PATH"] = str(target)
    try:
        assert api_eval_report_path() == mcp_eval_report_path() == target.resolve()
    finally:
        os.environ.pop("SPECPROOF_EVAL_REPORT_PATH", None)


def test_both_layers_point_at_the_same_repository_root() -> None:
    # The root is the reason the two copies agree; pin it directly so a moved
    # file (which changes the parents[N] depth) fails here, not in production.
    from api.routes.web import _PROJECT_ROOT as API_ROOT
    from mcp.tools import _PROJECT_ROOT as MCP_ROOT

    assert API_ROOT == MCP_ROOT == Path(__file__).resolve().parents[2]
