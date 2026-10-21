"""Fence: ``empty_pool_message`` must say WHICH decision emptied the pool.

``0 cases`` produced by holdout isolation is a manifest outcome; ``no case
directories`` is a wrong path. Collapsing the two blames the directory for a
policy — and the caller exits 0, claiming a verdict from nothing measured.
This pins both branches and that they stay distinct.
"""

from pathlib import Path

from cli.specproof.case_set import CASE_SET_HOLDOUT, CasePlan, empty_pool_message

_CASES = Path("cases")


def _plan(mode: str = CASE_SET_HOLDOUT) -> CasePlan:
    return CasePlan(
        kept=[],
        mode=mode,
        excluded=[],
        unknown_declared=[],
        manifest_path="",
        note="",
    )


def test_isolation_explained_when_cases_were_discovered():
    msg = empty_pool_message(5, _plan(), _CASES)
    assert "5" in msg
    assert str(_CASES) in msg
    assert CASE_SET_HOLDOUT in msg
    assert "--include-holdout" in msg
    # the wrong-path sentence must NOT appear when cases really exist
    assert "No case directories found" not in msg


def test_wrong_path_blamed_when_none_were_discovered():
    msg = empty_pool_message(0, _plan(), _CASES)
    assert msg == f"No case directories found in {_CASES}"
    assert "--include-holdout" not in msg


def test_the_two_branches_never_collapse():
    isolated = empty_pool_message(3, _plan(), _CASES)
    missing = empty_pool_message(0, _plan(), _CASES)
    assert isolated != missing


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
