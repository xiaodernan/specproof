# mypy: ignore-errors
"""Hidden judge tests for task-05: acceptance + no-regression guards."""

import edge_cases
from svc import upper_first


def test_more_edges_hold() -> None:
    assert upper_first("ABC") == "ABC"
    assert upper_first("a\nb") == "A\nb"


def test_edge_case_module_present_and_usable() -> None:
    assert callable(edge_cases.run_edge_cases)
    assert edge_cases.run_edge_cases(upper_first) is True
