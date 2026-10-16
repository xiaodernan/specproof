"""Unit tests for _exit_verdict in agent.nodes.build_matrix.

Covers the exit-code -> per-side verdict mapping used by the matrix builder.
Pure function — no Maven, no Docker, no network.
"""

import pytest

from agent.nodes.build_matrix import _exit_verdict


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),  # no observation
        (True, None),  # bool is not a valid exit code
        (False, None),
        (0, "PASS"),
        (1, "FAIL"),
        (2, "FAIL"),
        ("0", "PASS"),
        ("1", "FAIL"),
        ("2", "FAIL"),
        ("abc", None),  # non-numeric string
        ("", None),  # empty string
        (3.14, None),  # float is not int/str
        ([], None),  # list is not int/str
    ],
)
def test_exit_verdict(value, expected):
    assert _exit_verdict(value) == expected
