"""Fence tests for the inline ``--layer`` / ``--allow`` parsing in archreview.

``archreview_cmd`` parses ``--layer REGEX=NAME`` and ``--allow SRC>DST`` inline
in the click callback: a missing ``=`` or ``>`` must raise ``ClickException``
rather than be silently mis-split. The valid path must hand ``review`` a
``dict[str, str]`` and a ``list[tuple[str, str]]``. Driven through
``click.testing.CliRunner`` so the real click argument wiring is exercised.

``review`` is monkeypatched (it walks real Python source); the point here is the
argument contract, not the graph analysis.
"""

import tempfile

from click.testing import CliRunner

import devtools.archreview as archreview
from cli.specproof.commands.devtools import archreview_cmd


def _fake_review(captured):
    def review(root, layer_rules=None, allowed_edges=None):
        captured["root"] = root
        captured["layers"] = layer_rules
        captured["edges"] = allowed_edges
        return {"module_count": 0, "edge_count": 0, "cycles": [], "findings": []}
    return review


def test_invalid_layer_raises(monkeypatch):
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as d:
        result = runner.invoke(archreview_cmd, [d, "--layer", "no-equals"])
    assert result.exit_code != 0
    assert "invalid --layer" in result.output


def test_invalid_allow_raises(monkeypatch):
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as d:
        result = runner.invoke(archreview_cmd, [d, "--allow", "no-arrow"])
    assert result.exit_code != 0
    assert "invalid --allow" in result.output


def test_layer_and_allow_parsed(monkeypatch):
    captured = {}
    monkeypatch.setattr(archreview, "review", _fake_review(captured))
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as d:
        result = runner.invoke(
            archreview_cmd,
            [d, "--layer", "core=Core", "--layer", "ui=UI", "--allow", "Core>UI"],
        )
    assert result.exit_code == 0, result.output
    assert captured["layers"] == {"core": "Core", "ui": "UI"}
    assert captured["edges"] == [("Core", "UI")]


def test_no_rules_passes_none_and_empty(monkeypatch):
    captured = {}
    monkeypatch.setattr(archreview, "review", _fake_review(captured))
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as d:
        result = runner.invoke(archreview_cmd, [d])
    assert result.exit_code == 0, result.output
    # layer_rules or None -> None when empty; allowed_edges stays a list
    assert captured["layers"] is None
    assert captured["edges"] == []


def test_summary_line_reports_counts(monkeypatch):
    def review(root, layer_rules=None, allowed_edges=None):
        return {"module_count": 3, "edge_count": 2, "cycles": [1], "findings": [1, 2]}

    monkeypatch.setattr(archreview, "review", review)
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as d:
        result = runner.invoke(archreview_cmd, [d])
    assert result.exit_code == 0, result.output
    assert "modules=3" in result.output
    assert "edges=2" in result.output
    assert "cycles=1" in result.output
    assert "findings=2" in result.output


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
