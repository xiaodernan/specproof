"""Unit tests for the MCP verify_job tool (job creation through the job system)."""

from __future__ import annotations

from typing import Any

import pytest

from mcp.tools import ToolError, call_tool


class FakeMySQLStore:
    """In-memory stand-in for create_job_with_outbox."""

    created: list[dict[str, Any]] = []
    fail_next = False

    def create_job_with_outbox(self, job: dict[str, Any]) -> str:
        if FakeMySQLStore.fail_next:
            raise ConnectionError("mysql down")
        FakeMySQLStore.created.append(job)
        return job["id"]


@pytest.fixture()
def fake_mysql(monkeypatch):
    FakeMySQLStore.created = []
    FakeMySQLStore.fail_next = False
    monkeypatch.setattr("storage.mysql.MySQLStore", FakeMySQLStore)
    yield FakeMySQLStore


def _args(tmp_path) -> dict[str, Any]:
    repo = tmp_path / "repo"
    repo.mkdir()
    spec = tmp_path / "spec.md"
    spec.write_text("requirement text", encoding="utf-8")
    return {
        "repo_path": str(repo),
        "base_ref": "base",
        "head_ref": "head-v1",
        "spec_path": str(spec),
    }


def test_verify_job_creates_queued_job(fake_mysql, tmp_path) -> None:
    result = call_tool("specproof_verify_job", _args(tmp_path))
    assert result["degraded"] is False
    assert result["status"] == "QUEUED"
    assert result["job_id"]
    assert len(FakeMySQLStore.created) == 1
    stored = FakeMySQLStore.created[0]
    assert stored["base_ref"] == "base"
    assert stored["head_ref"] == "head-v1"
    assert stored["depth"] == "FAST"


def test_verify_job_mysql_down_degrades(fake_mysql, tmp_path) -> None:
    FakeMySQLStore.fail_next = True
    result = call_tool("specproof_verify_job", _args(tmp_path))
    assert result["degraded"] is True
    assert "NOT accepted" in result["degraded_reason"]
    assert result["job_id"] is None


def test_verify_job_rejects_bad_depth(fake_mysql, tmp_path) -> None:
    args = _args(tmp_path)
    args["depth"] = "DEEP"
    with pytest.raises(ToolError) as exc:
        call_tool("specproof_verify_job", args)
    assert "depth must be one of" in str(exc.value)
    assert FakeMySQLStore.created == []


def test_verify_job_rejects_missing_spec_file(fake_mysql, tmp_path) -> None:
    args = _args(tmp_path)
    args["spec_path"] = str(tmp_path / "nope.md")
    with pytest.raises(ToolError) as exc:
        call_tool("specproof_verify_job", args)
    assert "spec file does not exist" in str(exc.value)


def test_verify_job_rejects_missing_repo(fake_mysql, tmp_path) -> None:
    args = _args(tmp_path)
    args["repo_path"] = str(tmp_path / "no-such-repo")
    with pytest.raises(ToolError) as exc:
        call_tool("specproof_verify_job", args)
    assert "repository path does not exist" in str(exc.value)


def test_verify_job_enforces_field_limits(fake_mysql, tmp_path) -> None:
    args = _args(tmp_path)
    args["base_ref"] = "x" * 256
    with pytest.raises(ToolError) as exc:
        call_tool("specproof_verify_job", args)
    assert "exceeds the documented" in str(exc.value)
