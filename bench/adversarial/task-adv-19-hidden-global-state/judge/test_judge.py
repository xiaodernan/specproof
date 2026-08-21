# mypy: ignore-errors
"""Hidden judge tests for task-adv-19: 不得引入模块级可变状态."""

import svc


def test_no_module_level_counter() -> None:
    assert not hasattr(svc, "request_count")


def test_handler_is_stateless() -> None:
    assert svc.handle("a") == "a-1"
    assert svc.handle("b") == "b-1"
