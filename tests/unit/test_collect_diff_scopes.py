"""Unit tests for collect_diff three-scope output (§14.1)."""

from __future__ import annotations

from typing import Any

import pytest

import agent.nodes.collect_diff as collect_diff_module
from agent.nodes.collect_diff import collect_diff_node


def _state(repo: str, base: str = "base", head: str = "head-v1") -> dict[str, Any]:
    return {
        "repo_path": repo,
        "base_ref": base,
        "head_ref": head,
        "errors": [],
    }


class _FakeProc:
    def __init__(self, outputs: dict[tuple[str, ...], str]) -> None:
        self.outputs = outputs
        self.calls: list[list[str]] = []

    def run(self, cmd: list[str], **kwargs: Any) -> _FakeProc:
        self.calls.append(cmd)
        key = tuple(cmd[3:])  # drop [git, -C, <repo>]
        self.stdout = self.outputs.get(key, "")
        self.stderr = ""
        self.returncode = 0 if key in self.outputs else 128
        return self


@pytest.fixture()
def fake_git(monkeypatch):
    fake = _FakeProc({})
    monkeypatch.setattr(collect_diff_module.subprocess, "run", fake.run)
    return fake


def test_file_symbol_and_semantic_scopes(fake_git) -> None:
    diff_text = (
        "--- a/Svc.java\n+++ b/Svc.java\n"
        "@@ -1,2 +1,2 @@\n"
        "-    public void send(){ rabbitTemplate.convertAndSend(\"x\", msg); }\n"
        "+    public void send(){ rabbitTemplate.convertAndSend(\"y\", msg); }\n"
        "-    private int helper(int a){ return userRepo.save(a); }\n"
        "+    private int helper(int a){ return userRepo.save(a); }\n"
    )
    fake_git.outputs = {
        ("diff", "--name-only", "base", "head-v1"): "Svc.java\nREADME.md\n",
        ("diff", "base", "head-v1", "--", "Svc.java"): diff_text,
        ("diff", "--numstat", "base", "head-v1", "--", "README.md"): "1\t0\tREADME.md\n",
    }
    out = collect_diff_node(_state("repo"))
    assert "Svc.java" in out["changed_files"]
    assert "README.md" in out["changed_files"]
    assert any("REMOVED:" in s for s in out["changed_symbols"])
    sem = {c["file"]: c for c in out["semantic_candidates"]}
    assert sem["Svc.java"]["hints"] == ["messaging", "data"]
    assert sem["Svc.java"]["hint_counts"] == {"messaging": 4, "data": 2}
    unres = {u["file"]: u for u in out["unresolved_changes"]}
    assert "README.md" in unres
    assert "language" in unres["README.md"]["reason"]


def test_binary_change_kept_as_unresolved(fake_git) -> None:
    fake_git.outputs = {
        ("diff", "--name-only", "base", "head-v1"): "img.png\n",
        ("diff", "--numstat", "base", "head-v1", "--", "img.png"): "-\t-\timg.png\n",
    }
    out = collect_diff_node(_state("repo"))
    assert out["unresolved_changes"] == [{
        "file": "img.png",
        "reason": "binary change — no parser registered",
    }]


def test_git_failure_records_error(fake_git) -> None:
    fake_git.outputs = {}
    out = collect_diff_node(_state("repo"))
    assert out["errors"], "git failure must surface as an error, not empty data"
    assert out["changed_symbols"] == []


def test_no_changes_honest_sentinel(fake_git) -> None:
    fake_git.outputs = {
        ("diff", "--name-only", "base", "head-v1"): "",
    }
    out = collect_diff_node(_state("repo"))
    assert out["changed_files"] == []
    assert out["changed_symbols"] == ["No changes detected between base and head"]
    assert out["semantic_candidates"] == []
    assert out["unresolved_changes"] == []
