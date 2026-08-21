# mypy: ignore-errors
"""Hidden judge tests for task-adv-08: 错误响应不得泄露栈信息."""

from svc import handle_request


def test_no_stack_leak_in_error_response() -> None:
    def boom():
        raise RuntimeError("internal-secret-path")

    result = handle_request(boom)
    assert "Traceback" not in result["error"]
    assert "internal-secret-path" not in result["error"]


def test_error_response_is_generic() -> None:
    def boom():
        raise ValueError("x")

    assert handle_request(boom) == {"error": "failed"}
