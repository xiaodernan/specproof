"""#110 — one job-status vocabulary, three consumers, and now a gate.

The status channel had THREE hand-written copies of the same word list and they
disagreed:

1. `storage/mysql.py::_VALID_TRANSITIONS` — the authoritative state machine.
   Ten states: the keys plus every reachable target.
2. `api/routes/jobs.py` — the `?status=` filter accepted eleven words: it
   admitted `UNVERIFIED` and `INCONCLUSIVE` (matrix-row / verdict words, never a
   job status ⇒ the query matched nothing while the page reported "no results",
   which is indistinguishable from a real empty result) and it REJECTED `STALE`
   with a 422 even though `STALE` is a terminal status this system writes.
3. `apps/web/src/ui/StatusPill.tsx` — the Jobs filter dropdown is built from
   this map, so it offered those two impossible filters and never offered STALE.

Plus `apps/web/src/pages/JobDetail.tsx::STATUS_HELP` was missing `PENDING` — the
status EVERY job starts in (the insert writes 'PENDING'), so a freshly created
job fell back to the generic banner — while carrying `UNVERIFIED`, an entry no
job could ever reach. `JobDetail.test.tsx` then used that unreachable word as a
job status, which is the "dead word certified by a green gate" shape.

The fix derives the API's set from the state machine (`ALL_STATUSES`) and pins
the frontend to it. This file is the pin: every direction, so neither a new
state nor a resurrected ghost word can drift again. Text-level on purpose — it
runs in the fast loop and needs no database.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from storage.mysql import _VALID_TRANSITIONS, ALL_STATUSES, TERMINAL_STATUSES

REPO = Path(__file__).resolve().parents[2]
MYSQL = REPO / "storage" / "mysql.py"
JOBS_ROUTE = REPO / "api" / "routes" / "jobs.py"
STATUS_PILL = REPO / "apps" / "web" / "src" / "ui" / "StatusPill.tsx"
JOBS_PAGE = REPO / "apps" / "web" / "src" / "pages" / "Jobs.tsx"
JOB_DETAIL = REPO / "apps" / "web" / "src" / "pages" / "JobDetail.tsx"

#: Words that name a matrix row / verdict, not a job status. They must never
#: appear in the status channel again — this is the exact pair that used to
#: reach the filter and the pill map.
_NOT_STATUSES = ("UNVERIFIED", "INCONCLUSIVE")


def _ts_string_array(source: str, name: str) -> set[str]:
    """Read `export const NAME: readonly string[] = ["A", "B"];` from TS."""
    match = re.search(
        rf"export const {name}[^=]*=\s*\[(.*?)\]", source, re.S
    )
    assert match, f"{name} not found — the gate would pass vacuously"
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def _ts_record_keys(source: str, name: str) -> set[str]:
    """Read the keys of `const NAME: Record<string, string> = { KEY: "…" };`."""
    match = re.search(rf"const {name}[^=]*=\s*\{{(.*?)\n\}};", source, re.S)
    assert match, f"{name} not found — the gate would pass vacuously"
    return set(re.findall(r"^\s*([A-Z_][A-Z0-9_]*):", match.group(1), re.M))


def _authoritative_statuses() -> set[str]:
    """Keys ∪ every reachable target of the state machine, read from source."""
    tree = ast.parse(MYSQL.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign | ast.Assign):
            targets = (
                [node.target] if isinstance(node, ast.AnnAssign) else node.targets
            )
            if any(
                isinstance(t, ast.Name) and t.id == "_VALID_TRANSITIONS"
                for t in targets
            ):
                assert isinstance(node.value, ast.Dict)
                keys = {
                    k.value
                    for k in node.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
                targets_inner: set[str] = set()
                for value in node.value.values:
                    # Terminal states are written as `set()` (a Call), the rest
                    # as `{"A", "B"}` literals — accept both, but nothing else,
                    # so a future shape cannot slip through unread.
                    if isinstance(value, ast.Call):
                        assert (
                            isinstance(value.func, ast.Name)
                            and value.func.id == "set"
                            and not value.args
                        ), "expected set() targets"
                        continue
                    assert isinstance(value, ast.Set), "expected set() targets"
                    targets_inner |= {
                        e.value
                        for e in value.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)
                    }
                return keys | targets_inner
    raise AssertionError("_VALID_TRANSITIONS not found in storage/mysql.py")


def test_all_statuses_is_derived_from_the_state_machine() -> None:
    """The exported set is the machine's, not a second copy of it."""
    assert _authoritative_statuses() == ALL_STATUSES
    assert frozenset(_VALID_TRANSITIONS) | frozenset(
        set().union(*_VALID_TRANSITIONS.values())
    ) == ALL_STATUSES


def test_stale_is_a_status_and_the_ghosts_are_not() -> None:
    """Both halves of the reported defect, named explicitly so a future edit
    that re-adds either one fails here with the reason attached."""
    assert "STALE" in ALL_STATUSES, "STALE is a real terminal status"
    assert "STALE" in TERMINAL_STATUSES
    for ghost in _NOT_STATUSES:
        assert ghost not in ALL_STATUSES, (
            f"{ghost} is a verdict/matrix word — RUNNING never transitions to it"
        )


def test_the_route_derives_its_filter_set_instead_of_re_typing_it() -> None:
    """The route must consume ALL_STATUSES; a literal list here is the drift."""
    source = JOBS_ROUTE.read_text(encoding="utf-8")
    assert "ALL_STATUSES" in source
    for ghost in _NOT_STATUSES:
        assert f'"{ghost}"' not in source, (
            f"api/routes/jobs.py re-typed {ghost} into the status filter"
        )


def test_frontend_status_vocabulary_matches_the_state_machine() -> None:
    """JOB_STATUSES (what the filter dropdown offers) == the machine, both ways."""
    source = STATUS_PILL.read_text(encoding="utf-8")
    offered = _ts_string_array(source, "JOB_STATUSES")
    assert offered == set(ALL_STATUSES), (
        "JOB_STATUSES and storage/mysql.py::ALL_STATUSES disagree: "
        f"only in TS {sorted(offered - set(ALL_STATUSES))}, "
        f"only in Python {sorted(set(ALL_STATUSES) - offered)}"
    )


def test_every_offered_status_has_a_chinese_label() -> None:
    """No status may render as a raw English token in the dropdown."""
    source = STATUS_PILL.read_text(encoding="utf-8")
    labels = _ts_record_keys(source, "STATUS_LABELS")
    missing = set(ALL_STATUSES) - labels
    assert not missing, f"statuses with no label: {sorted(missing)}"


def test_the_pill_map_does_not_carry_verdict_words() -> None:
    """STATUS_LABELS is the status channel. The two ghost words are dead here:
    no job row can hold them, so their presence only misleads the dropdown that
    is built from this map."""
    source = STATUS_PILL.read_text(encoding="utf-8")
    labels = _ts_record_keys(source, "STATUS_LABELS")
    for ghost in _NOT_STATUSES:
        assert ghost not in labels, (
            f"{ghost} is a verdict word; it belongs to resultPill/verdictLabel"
        )


def test_jobs_dropdown_offers_only_real_statuses() -> None:
    """The dropdown must be driven by JOB_STATUSES, not by the whole pill map —
    that is exactly how the two impossible filters reached users."""
    source = JOBS_PAGE.read_text(encoding="utf-8")
    assert "JOB_STATUSES.map(" in source
    assert "Object.entries(STATUS_LABELS)" not in source


def test_job_detail_guidance_covers_every_status_including_pending() -> None:
    """STATUS_HELP == the machine, both directions.

    PENDING is the status every job is inserted with; it was missing, so a new
    job showed the generic fallback. UNVERIFIED was present and unreachable.
    """
    source = JOB_DETAIL.read_text(encoding="utf-8")
    keys = _ts_record_keys(source, "STATUS_HELP")
    assert keys == set(ALL_STATUSES), (
        "STATUS_HELP and the state machine disagree: "
        f"unreachable entries {sorted(keys - set(ALL_STATUSES))}, "
        f"statuses with no guidance {sorted(set(ALL_STATUSES) - keys)}"
    )
    assert "PENDING" in keys
    for ghost in _NOT_STATUSES:
        assert ghost not in keys
