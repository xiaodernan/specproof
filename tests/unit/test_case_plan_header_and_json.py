"""Fence: ``CasePlan.header_lines`` / ``as_json`` say exactly what they promise.

``header_lines`` is the human-readable case-set banner printed before a run:
it must announce the mode, the excluded count, the ``--include-holdout``
caveat (only when isolation was skipped), the declared-but-absent cases, and
the manifest note — each only when it applies. ``as_json`` is the machine
sidecar: same facts, sorted so two runs compare byte-stably.

Neither had a direct test.
"""

from pathlib import Path

from cli.specproof.case_set import CASE_SET_ALL, CASE_SET_HOLDOUT, CasePlan


def _plan(**kw) -> CasePlan:
    base = {
        "kept": [],
        "mode": CASE_SET_HOLDOUT,
        "excluded": [],
        "unknown_declared": [],
        "manifest_path": "",
        "note": "",
    }
    base.update(kw)
    return CasePlan(**base)


# --- header_lines -----------------------------------------------------------

def test_header_reports_mode_and_kept_count():
    lines = _plan(kept=[Path("a"), Path("b"), Path("c")]).header_lines()
    assert len(lines) == 1
    assert CASE_SET_HOLDOUT in lines[0]
    assert "3 个案例参与本轮评测" in lines[0]
    # no excluded -> the "，排除 N 个" clause must not appear
    assert "排除" not in lines[0]


def test_header_reports_excluded_count():
    line = _plan(kept=[Path("a")], excluded=["x", "y"]).header_lines()[0]
    assert "，排除 2 个" in line


def test_header_warns_only_when_isolation_skipped():
    all_mode = _plan(mode=CASE_SET_ALL).header_lines()
    assert any("未做 holdout 隔离" in line and "--include-holdout" in line for line in all_mode)

    isolated = _plan(mode=CASE_SET_HOLDOUT).header_lines()
    assert not any("未做 holdout 隔离" in line for line in isolated)


def test_header_reports_declared_but_absent_sorted():
    lines = _plan(unknown_declared=["zeta", "alpha"]).header_lines()
    joined = "\n".join(lines)
    assert "不在本" in joined
    assert "alpha" in joined and "zeta" in joined
    # sorted: alpha before zeta
    assert joined.index("alpha") < joined.index("zeta")


def test_header_reports_manifest_note():
    lines = _plan(note="holdout manifest v3").header_lines()
    assert any("manifest note: holdout manifest v3" in line for line in lines)


def test_header_omits_optional_lines_when_empty():
    lines = _plan().header_lines()
    assert len(lines) == 1


# --- as_json ----------------------------------------------------------------

def test_as_json_shape_and_sorting():
    payload = _plan(
        kept=[Path("a")],
        mode=CASE_SET_HOLDOUT,
        excluded=["b", "a"],
        unknown_declared=["z", "y"],
        manifest_path="m.json",
        note="n",
    ).as_json()
    assert payload == {
        "mode": CASE_SET_HOLDOUT,
        "manifest_path": "m.json",
        "excluded_holdout_cases": ["a", "b"],
        "declared_but_absent": ["y", "z"],
        "manifest_note": "n",
    }


def test_as_json_empty_lists():
    payload = _plan().as_json()
    assert payload["excluded_holdout_cases"] == []
    assert payload["declared_but_absent"] == []


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
