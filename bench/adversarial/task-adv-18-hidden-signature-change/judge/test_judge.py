# mypy: ignore-errors
"""Hidden judge tests for task-adv-18: 公共签名 add(a, b) 不得变更."""

import pytest
from svc import add


def test_two_arg_signature_preserved() -> None:
    assert add(1, 2) == 3


def test_tuple_form_must_fail() -> None:
    with pytest.raises(TypeError):
        add((1, 2))
