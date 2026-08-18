"""Graph-level tests for state channels that nodes write but the
schema previously did not declare.

Regression guard: LangGraph drops node outputs that are not schema
channels. collect_diff writes diff_by_file and generate_counterexamples
writes generation_record; without the channels the worker's Inline
Finding path saw an empty diff map and differential evidence recorded
generation_source "unknown". These tests lock the channels into the
graph wiring itself (not just the node return values).
"""

from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from agent.nodes.collect_diff import collect_diff_node
from agent.state import Phase0State, initial_state

REPO_ROOT = Path(__file__).resolve().parents[2]


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


def test_diff_by_file_survives_graph_invoke():
    graph = StateGraph(Phase0State)
    graph.add_node("collect_diff", collect_diff_node)
    graph.add_edge(START, "collect_diff")
    graph.add_edge("collect_diff", END)
    app = graph.compile()

    state = initial_state(
        repo_path=str(REPO_ROOT),
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
