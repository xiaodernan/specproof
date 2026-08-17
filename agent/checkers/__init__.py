"""Contract checker registry — deterministic Java source-diff analyzers.

Each checker compares Base and Head sources and reports violations of one
contract family. Findings are labelled "java_source_diff" evidence and are
capped at MAJOR by the Review Court (static analysis can never produce
BLOCKER on its own — only real execution can).
"""

from agent.checkers.java_source import contract_results_for, run_contract_checks

__all__ = ["run_contract_checks", "contract_results_for"]
