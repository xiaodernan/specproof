"""Fence tests for ``commands/devtools.py`` path gate and report emitter.

``_resolve`` is the single existence gate every devtools subcommand passes
through; ``_emit`` is the one place a report becomes either a file or stdout.
A regression in either silently changes where output lands (or whether a
missing path is rejected), with no other test in the repo reading them.

All filesystem activity uses repo-external temp dirs (not pytest's tmp_path,
which this machine's safe-delete guard can hang on).
"""

import json
import tempfile
from pathlib import Path

import click
import pytest

from cli.specproof.commands.devtools import _emit, _resolve

# --- _resolve ---------------------------------------------------------------

def test_resolve_existing_path():
    with tempfile.TemporaryDirectory() as d:
        assert _resolve(d) == Path(d)


def test_resolve_missing_path_raises():
    with tempfile.TemporaryDirectory() as d, pytest.raises(click.ClickException):
        _resolve(str(Path(d) / "absent"))


# --- _emit ------------------------------------------------------------------

def _report():
    return {"summary": {"file_count": 2, "note": "中文说明"}, "items": [1, 2]}


def test_emit_to_file_writes_payload_and_creates_parents():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "deep" / "nested" / "report.json"
        _emit(_report(), str(out), as_json=False)
        assert out.is_file()
        expected = json.dumps(_report(), ensure_ascii=False, indent=2) + "\n"
        assert out.read_text(encoding="utf-8") == expected


def test_emit_to_file_echoes_path(capsys):
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "r.json"
        _emit(_report(), str(out), as_json=False)
        assert f"report written to: {out}" in capsys.readouterr().out


def test_emit_as_json_to_stdout(capsys):
    _emit(_report(), None, as_json=True)
    captured = capsys.readouterr().out
    assert captured == json.dumps(_report(), ensure_ascii=False, indent=2) + "\n"


def test_emit_plain_to_stdout(capsys):
    _emit(_report(), None, as_json=False)
    captured = capsys.readouterr().out
    assert captured == json.dumps(_report(), ensure_ascii=False, indent=2) + "\n"


def test_emit_keeps_non_ascii_unescaped(capsys):
    _emit(_report(), None, as_json=True)
    captured = capsys.readouterr().out
    assert "中文说明" in captured
    assert "\\u4e2d" not in captured


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
