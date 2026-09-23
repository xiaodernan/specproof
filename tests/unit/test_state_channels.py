"""Graph-level tests for state channels that nodes write but the
schema previously did not declare.

Regression guard: LangGraph drops node outputs that are not schema
channels. collect_diff writes diff_by_file and generate_counterexamples
writes generation_record; without the channels the worker's Inline
Finding path saw an empty diff map and differential evidence recorded
generation_source "unknown". These tests lock the channels into the
graph wiring itself (not just the node return values).
"""

import os
import subprocess
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from agent.nodes.collect_diff import collect_diff_node
from agent.state import Phase0State, initial_state

REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(repo: str, *args: str) -> None:
    # `-c core.hooksPath=` disables hook lookup so a developer/machine-global
    # hooksPath can't break these fixture commits (fresh-clone robustness).
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@x",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@x",
    }
    subprocess.run(
        ["git", "-C", repo, "-c", "core.hooksPath=", *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def _make_java_repo(tmp_path: Path) -> str:
    """A self-contained git repo whose base→head-v1 diff touches a .java file.

    The graph channel guard needs a NON-EMPTY diff to distinguish "channel
    preserved" from "genuinely empty"; relying on the checkout root to carry
    phantom `base`/`head-v1` tags makes the test fail on any clean clone.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(str(repo), "init", "-b", "main")
    java = repo / "Foo.java"
    java.write_text(
        "package com.demo;\n"
        "public class Foo {\n"
        "    public int bar(int x) { return x; }\n"
        "}\n",
        encoding="utf-8",
    )
    _git(str(repo), "add", "Foo.java")
    _git(str(repo), "commit", "-m", "base")
    _git(str(repo), "tag", "base")
    java.write_text(
        "package com.demo;\n"
        "public class Foo {\n"
        "    public int bar(int x) { return x * 2; }\n"
        "    public int baz(int x) { return x + 1; }\n"
        "}\n",
        encoding="utf-8",
    )
    _git(str(repo), "add", "Foo.java")
    _git(str(repo), "commit", "-m", "head")
    _git(str(repo), "tag", "head-v1")
    return str(repo)


def test_initial_state_carries_new_channels():
    state = initial_state(
        repo_path=str(REPO_ROOT),
        base_ref="base",
        head_ref="head-v1",
        spec_path="unused",
        depth="FAST",
    )
    assert state["diff_by_file"] == {}
    assert state["generation_record"] == {}


def test_diff_by_file_survives_graph_invoke(tmp_path: Path):
    repo = _make_java_repo(tmp_path)
    graph = StateGraph(Phase0State)
    graph.add_node("collect_diff", collect_diff_node)
    graph.add_edge(START, "collect_diff")
    graph.add_edge("collect_diff", END)
    app = graph.compile()

    state = initial_state(
        repo_path=repo,
        base_ref="base",
        head_ref="head-v1",
        spec_path="unused",
        depth="FAST",
    )
    final = app.invoke(state)
    diff_by_file = final["diff_by_file"]
    assert diff_by_file, "diff_by_file was dropped by the graph"
    assert any(name.endswith(".java") for name in diff_by_file)


def test_generation_record_survives_graph_invoke():
    def _dummy_record(state: dict[str, Any]) -> dict[str, Any]:
        return {"generation_record": {"source": "deterministic_template"}}

    graph = StateGraph(Phase0State)
    graph.add_node("record", _dummy_record)
    graph.add_edge(START, "record")
    graph.add_edge("record", END)
    app = graph.compile()

    state = initial_state(
        repo_path=str(REPO_ROOT),
        base_ref="base",
        head_ref="head-v1",
        spec_path="unused",
        depth="FAST",
    )
    final = app.invoke(state)
    assert final["generation_record"]["source"] == "deterministic_template"
