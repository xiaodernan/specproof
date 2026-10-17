"""Fence tests for the fix/approve data contracts in ``commands/fix.py``.

``_load_findings`` / ``_load_requests`` parse and validate the JSON that the
fix and approve commands exchange; ``_write_requests_file`` / ``_write_pr_payload``
are the producers on the other side. They had zero direct tests, yet a shape
regression here silently feeds the fixer (or the PR payload) the wrong fields.

All filesystem activity uses repo-external temp dirs.
"""

import json
import tempfile
from pathlib import Path

import click
import pytest

from agent.fixes import FixProposal
from cli.specproof.commands.fix import (
    _load_findings,
    _load_requests,
    _write_pr_payload,
    _write_requests_file,
)


def _proposal(**kw) -> FixProposal:
    base = {
        "fix_id": "FIX-1",
        "finding_id": "FIND-1",
        "contract_id": "UNIQUE-01",
        "path": "src/UserService.java",
        "action": "replace_lines",
        "anchor_line": 42,
        "head_context": "if (userRepository.existsByEmail(newEmail)) {",
        "base_lines": ["old"],
        "head_lines": ["new"],
        "rationale": "restore the negated existence check",
        "patch": "--- a\n+++ b\n",
    }
    base.update(kw)
    return FixProposal(**base)


# --- _load_findings ---------------------------------------------------------

def test_load_findings_from_object():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "f.json"
        p.write_text(json.dumps({"findings": [{"id": "a"}, {"id": "b"}]}), encoding="utf-8")
        assert _load_findings(p) == [{"id": "a"}, {"id": "b"}]


def test_load_findings_from_plain_list():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "f.json"
        p.write_text(json.dumps([{"id": "a"}]), encoding="utf-8")
        assert _load_findings(p) == [{"id": "a"}]


def test_load_findings_filters_non_dict_entries():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "f.json"
        p.write_text(json.dumps([{"id": "a"}, "junk", 3, None]), encoding="utf-8")
        assert _load_findings(p) == [{"id": "a"}]


def test_load_findings_empty_object_is_empty():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "f.json"
        p.write_text(json.dumps({}), encoding="utf-8")
        assert _load_findings(p) == []


def test_load_findings_rejects_non_list_or_object():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "f.json"
        p.write_text(json.dumps("just a string"), encoding="utf-8")
        with pytest.raises(click.ClickException):
            _load_findings(p)


def test_load_findings_missing_file_raises():
    with tempfile.TemporaryDirectory() as d, pytest.raises(click.ClickException):
        _load_findings(Path(d) / "absent.json")


def test_load_findings_bad_json_raises():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "f.json"
        p.write_text("{not json", encoding="utf-8")
        with pytest.raises(click.ClickException):
            _load_findings(p)


# --- _load_requests ---------------------------------------------------------

def test_load_requests_object_ok():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "r.json"
        p.write_text(json.dumps({"proposals": []}), encoding="utf-8")
        assert _load_requests(p) == {"proposals": []}


def test_load_requests_rejects_list():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "r.json"
        p.write_text(json.dumps([]), encoding="utf-8")
        with pytest.raises(click.ClickException):
            _load_requests(p)


def test_load_requests_missing_raises():
    with tempfile.TemporaryDirectory() as d, pytest.raises(click.ClickException):
        _load_requests(Path(d) / "absent.json")


def test_load_requests_bad_json_raises():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "r.json"
        p.write_text("nope", encoding="utf-8")
        with pytest.raises(click.ClickException):
            _load_requests(p)


# --- _write_requests_file ---------------------------------------------------

def test_write_requests_file_payload_shape():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "fixes"
        repo = Path(d).resolve()
        path = _write_requests_file(out, [_proposal()], [{"reason": "skip"}], repo, "base", "HEAD")
        assert path.name == "fix-requests.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data["generated_at"], str) and data["generated_at"]
        assert data["github_context"] == {
            "repo_path": str(repo),
            "base_ref": "base",
            "head_ref": "HEAD",
        }
        assert data["proposals"][0]["fix_id"] == "FIX-1"
        assert data["skipped"] == [{"reason": "skip"}]


def test_write_requests_file_creates_output_dir():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "deep" / "nested"
        _write_requests_file(out, [], [], Path(d).resolve(), "base", "HEAD")
        assert (out / "fix-requests.json").is_file()


# --- _write_pr_payload ------------------------------------------------------

def test_write_pr_payload_shape():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "prs"
        fix = {
            "fix_id": "FIX-1",
            "finding_id": "FIND-1",
            "contract_id": "UNIQUE-01",
            "rationale": "restore the negated check",
            "patch": "--- a\n+++ b\n",
        }
        path = _write_pr_payload(out, fix, "org/repo", "main", "fix-branch")
        assert path.name == "fix-pr-fix-1.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["repo"] == "org/repo"
        assert data["base_branch"] == "main"
        assert data["head_branch"] == "fix-branch"
        assert data["title"] == "SpecProof fix FIX-1: restore the negated check"
        assert "FIND-1" in data["body"]
        assert "UNIQUE-01" in data["body"]
        assert "```diff" in data["body"]
        assert "--- a" in data["body"]


def test_write_pr_payload_creates_output_dir():
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "a" / "b"
        fix = {
            "fix_id": "FIX-2",
            "finding_id": "FIND-2",
            "contract_id": "C-2",
            "rationale": "r",
            "patch": "p",
        }
        _write_pr_payload(out, fix, "o/r", "main", "h")
        assert (out / "fix-pr-fix-2.json").is_file()


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
