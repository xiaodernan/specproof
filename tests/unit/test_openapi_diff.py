"""Unit tests for scripts/openapi_diff.py — the §8.1 schema-diff gate.

The gate is only as honest as its baseline. A baseline that reads as "no
changes" while the app grew thirty endpoints is a green light that means
nothing, and the reverse — a baseline nobody can refresh without committing a
70 KB generated document — is how a gate ends up frozen (this one sat at
2026-08-23 for a month while CI could not parse its own workflow file).

These tests pin: the two baseline shapes the gate must read, the pruned shape it
writes, that a blind baseline cannot look like "no changes", and — the one that
matters in review — that the committed baseline still matches the app.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "openapi_diff.py"
BASELINE_PATH = REPO_ROOT / "docs" / "openapi" / "baseline.json"


def _load_module() -> Any:
    """Load scripts/openapi_diff.py by path (scripts/ is not a package)."""
    spec = importlib.util.spec_from_file_location("openapi_diff", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate() -> Any:
    """The gate module under test."""
    return _load_module()


def _spec() -> dict[str, Any]:
    """A miniature app.openapi() with one two-method path."""
    return {
        "openapi": "3.1.0",
        "paths": {
            "/jobs/{job_id}": {
                "get": {"responses": {"200": {}, "404": {}}},
                "delete": {"responses": {"204": {}}},
                "parameters": [{"name": "job_id", "in": "path"}],
            },
            "/health": {"get": {"responses": {"200": {}}}},
        },
    }


def test_a_full_openapi_document_is_read(gate: Any) -> None:
    assert gate._operations(_spec()) == {
        "GET /jobs/{job_id}": {"200", "404"},
        "DELETE /jobs/{job_id}": {"204"},
        "GET /health": {"200"},
    }


def test_a_pruned_baseline_is_read(gate: Any) -> None:
    """The shape this script writes, so a refresh does not need the full doc."""
    assert gate._operations({"operations": {"GET /x": ["200"], "POST /y": []}}) == {
        "GET /x": {"200"},
        "POST /y": set(),
    }


def test_the_written_baseline_is_pruned_and_round_trips(gate: Any, tmp_path: Path) -> None:
    path = tmp_path / "baseline.json"
    gate._write_baseline(path, _spec())
    written = json.loads(path.read_text(encoding="utf-8"))
    assert "paths" not in written, "the full document must not be committed"
    assert written["operations"] == gate._baseline_doc(_spec())["operations"]
    assert gate._operations(written) == gate._operations(_spec())


def test_a_refresh_is_a_stable_diff(gate: Any) -> None:
    """Same app, different dict order ⇒ byte-identical baseline."""
    shuffled = {
        "paths": {
            "/health": {"get": {"responses": {"200": {}}}},
            "/jobs/{job_id}": {
                "get": {"responses": {"404": {}, "200": {}}},
                "delete": {"responses": {"204": {}}},
                "parameters": [{"name": "job_id", "in": "path"}],
            },
        },
    }
    assert gate._baseline_doc(shuffled) == gate._baseline_doc(_spec())


def test_an_added_endpoint_blocks(gate: Any) -> None:
    added, removed, changed = gate._diff(
        {"GET /a": {"200"}}, {"GET /a": {"200"}, "POST /b": {"201"}},
    )
    assert (added, removed, changed) == (["POST /b"], [], [])
    assert gate._report(added, removed, changed, set()) is True


def test_an_allow_token_exempts_that_endpoint_only(gate: Any) -> None:
    allowed = gate._parse_allow("POST /b, GET /c:409")
    added, removed, changed = gate._diff(
        {"GET /c": {"200"}},
        {"POST /b": {"201"}, "GET /c": {"200", "409"}, "POST /d": {"201"}},
    )
    assert gate._report(added, removed, changed, allowed) is True
    assert gate._report(["POST /b"], [], [], allowed) is False
    # A ":status" token is deliberately narrower than a whole-endpoint token:
    # it exempts the one response-code line, not a newly added endpoint.
    assert gate._report(["GET /c"], [], [], allowed) is True
    assert gate._report([], [], [("GET /c", [], ["409"])], allowed) is False
    assert gate._report([], [], [("POST /d", [], ["400"])], allowed) is True
    assert gate._report(["GET /c"], [], [], gate._parse_allow("GET /c")) is False


def test_a_removed_response_code_is_a_change_not_an_addition(gate: Any) -> None:
    assert gate._diff({"GET /a": {"200", "409"}}, {"GET /a": {"200"}}) == (
        [], [], [("GET /a", ["409"], [])],
    )


def test_a_blind_baseline_cannot_look_like_no_changes(gate: Any) -> None:
    """No operations stored ⇒ every live endpoint is reported, not silently none."""
    added, _, _ = gate._diff(gate._operations({}), gate._operations(_spec()))
    assert len(added) == 3
    assert gate._report(added, [], [], set()) is True


def test_the_committed_baseline_matches_the_app(gate: Any) -> None:
    """The exact comparison CI runs, so a schema change fails here first."""
    import api.server

    committed = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    live = api.server.app.openapi()
    added, removed, changed = gate._diff(
        gate._operations(committed), gate._operations(live),
    )
    assert not (added or removed or changed), (
        "docs/openapi/baseline.json is out of date — refresh it with "
        "`python scripts/openapi_diff.py docs/openapi/baseline.json --update` "
        f"and review the endpoint diff (added={added}, removed={removed}, "
        f"changed={changed})"
    )
