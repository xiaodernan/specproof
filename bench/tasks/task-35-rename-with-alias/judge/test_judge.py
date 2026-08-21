# mypy: ignore-errors
"""Hidden judge tests for task-35: acceptance + no-regression guards."""

import warnings

import pytest
from svc import fetch, fetch_user


def test_alias_delegates_to_new_name() -> None:
    store = {"u1": 42}
    with pytest.warns(DeprecationWarning):
        assert fetch(store, "u1") == fetch_user(store, "u1") == 42


def test_new_name_emits_no_warning() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fetch_user({}, "x")
    assert not caught
