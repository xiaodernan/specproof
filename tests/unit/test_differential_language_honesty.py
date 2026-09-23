"""run_differential honest fallback for non-Java repositories (roadmap Phase 2).

The counterexample generator emits Java/JUnit tests only. When no generated
test exists, a non-Java repository must NOT get a vague "nothing to run" —
it should be told plainly that executable differential is unsupported for its
language and reported UNVERIFIED, never as a pass.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.nodes.run_differential import run_differential_node


def _mk_repo(root: Path, markers: dict[str, str]) -> str:
    d = root
    d.mkdir(parents=True, exist_ok=True)
    for name, body in markers.items():
        (d / name).write_text(body, encoding="utf-8")
    return str(d)


def _state(base: str, head: str) -> dict[str, Any]:
    return {
        "base_workspace": base,
        "head_workspace": head,
        "app_dir": "",
        "changed_symbols": [],
        "generation_record": {},
        "contracts": [],
        # No generated test -> exercises the not-test_class branch.
        "generated_tests_path": "",
        "job_id": None,
    }


def test_non_java_repo_gets_language_honest_unverified(tmp_path: Path) -> None:
    base = _mk_repo(tmp_path / "base", {"package.json": "{}"})
    head = _mk_repo(tmp_path / "head", {"package.json": "{}"})

    out = run_differential_node(_state(base, head))  # type: ignore[arg-type]
    diff = out["diff_results"]
    entry = next(d for d in diff if d.get("contract_id") == "DIFF-01")

    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert entry.get("language") == "node"
    assert "counterexample generator emits" in entry["detail"]
    assert "UNVERIFIED" in entry["detail"]
    # Honest: differential must never be reported as a pass here.
    assert out.get("contract_results", []) == []


def test_java_repo_keeps_generic_no_test_detail(tmp_path: Path) -> None:
    base = _mk_repo(tmp_path / "base", {"pom.xml": "<project/>"})
    head = _mk_repo(tmp_path / "head", {"pom.xml": "<project/>"})

    out = run_differential_node(_state(base, head))  # type: ignore[arg-type]
    entry = next(
        d for d in out["diff_results"] if d.get("contract_id") == "DIFF-01"
    )
    assert entry["verdict"] == "NON_REPRODUCIBLE"
    assert "language" not in entry  # java path is the generic one
    assert entry["detail"].startswith("No generated counterexample")


def test_python_repo_names_python_not_node(tmp_path: Path) -> None:
    base = _mk_repo(tmp_path / "base", {"requirements.txt": "pytest\n"})
    head = _mk_repo(tmp_path / "head", {"requirements.txt": "pytest\n"})

    out = run_differential_node(_state(base, head))  # type: ignore[arg-type]
    entry = next(
        d for d in out["diff_results"] if d.get("contract_id") == "DIFF-01"
    )
    assert entry.get("language") == "python"
    assert "python project" in entry["detail"]
