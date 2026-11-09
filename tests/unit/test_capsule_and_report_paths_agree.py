"""#493 · the API and the MCP tool find the same capsules and report.

Originally the two layers carried byte-identical copies of ``_capsule_dirs()``
and ``_eval_report_path()``, each resolving against their own module-local
``_PROJECT_ROOT`` — they agreed only because ``parents[2]`` from ``api/routes/``
and ``parents[1]`` from ``mcp/`` both land on the repository root.

They share an owner now — ``evidence.paths`` (see the module's docstring for
the precedence order) — and both layers re-export it, keeping the monkeypatch
seam healthy for the layers' own tests. This file keeps the behavioral claims:
same defaults, same env overrides, same — never divergent — answer; and now
that there is exactly one implementation, that the two layers import the same
object is pinned too.

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


def test_both_layers_import_the_same_capsule_dirs() -> None:
    assert api_capsule_dirs is mcp_capsule_dirs


def test_both_layers_import_the_same_eval_report_path() -> None:
    assert api_eval_report_path is mcp_eval_report_path


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


def test_both_layers_import_from_one_owner_not_equal_twice() -> None:
    import evidence.paths as shared

    assert api_capsule_dirs is shared.capsule_dirs
    assert mcp_capsule_dirs is shared.capsule_dirs
    assert api_eval_report_path is shared.eval_report_path
    assert mcp_eval_report_path is shared.eval_report_path
