"""LangGraph verification graph for SpecProof Phase 0.

Builds a StateGraph with the Phase 0 verification pipeline:
  intake → compile_contracts → prepare_base → prepare_head
  → collect_diff → run_static_checks → generate_counterexamples
  → run_differential → review_court → build_matrix
  → create_capsule → publish_report → END
"""

from langgraph.graph import END, StateGraph

from agent.nodes.build_matrix import build_matrix_node
from agent.nodes.collect_diff import collect_diff_node
from agent.nodes.compile_contracts import compile_contracts_node
from agent.nodes.create_capsule import create_capsule_node
from agent.nodes.generate_counterexamples import generate_counterexamples_node
from agent.nodes.intake import intake_node
from agent.nodes.prepare_base import prepare_base_node
from agent.nodes.prepare_head import prepare_head_node
from agent.nodes.publish_report import publish_report_node
from agent.nodes.review_court import review_court_node
from agent.nodes.run_differential import run_differential_node
from agent.nodes.run_static_checks import run_static_checks_node
from agent.state import Phase0State, initial_state


def build_phase0_graph() -> StateGraph:
    """Build and compile the Phase 0 verification graph.

    Returns a compiled graph ready for invoke().
    """
    builder = StateGraph(Phase0State)

    # ── Add nodes ──
    builder.add_node("intake", intake_node)
    builder.add_node("compile_contracts", compile_contracts_node)
    builder.add_node("prepare_base", prepare_base_node)
    builder.add_node("prepare_head", prepare_head_node)
    builder.add_node("collect_diff", collect_diff_node)
    builder.add_node("run_static_checks", run_static_checks_node)
    builder.add_node("generate_counterexamples", generate_counterexamples_node)
    builder.add_node("run_differential", run_differential_node)
    builder.add_node("review_court", review_court_node)
    builder.add_node("build_matrix", build_matrix_node)
    builder.add_node("create_capsule", create_capsule_node)
    builder.add_node("publish_report", publish_report_node)

    # ── Add edges ──
    builder.set_entry_point("intake")
    builder.add_edge("intake", "compile_contracts")
    builder.add_edge("compile_contracts", "prepare_base")
    builder.add_edge("prepare_base", "prepare_head")
    builder.add_edge("prepare_head", "collect_diff")
    builder.add_edge("collect_diff", "run_static_checks")
    builder.add_edge("run_static_checks", "generate_counterexamples")
    builder.add_edge("generate_counterexamples", "run_differential")
    builder.add_edge("run_differential", "review_court")
    builder.add_edge("review_court", "build_matrix")
    builder.add_edge("build_matrix", "create_capsule")
    builder.add_edge("create_capsule", "publish_report")
    builder.add_edge("publish_report", END)

    return builder.compile()  # type: ignore[return-value]


__all__ = ["build_phase0_graph", "Phase0State", "initial_state"]
