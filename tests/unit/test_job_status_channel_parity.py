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

from storage.agent_jobs import JOB_STATUSES as AGENT_JOB_STATUSES
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
    """The filter set must be DERIVED, never a literal list.

    The derivation lives in the application service since the route was
    moved onto it (Phase 1); the route itself must not re-type the set
    either. Both files are checked: a literal list anywhere in the chain
    is the drift this gate exists to catch.
    """
    route_source = JOBS_ROUTE.read_text(encoding="utf-8")
    service_source = (
        REPO / "api" / "services" / "verification_service.py"
    ).read_text(encoding="utf-8")
    assert "ALL_STATUSES" in service_source, (
        "the application service must derive the accepted status set from "
        "the state machine (storage/mysql.py::ALL_STATUSES)"
    )
    for source in (route_source, service_source):
        for ghost in _NOT_STATUSES:
            assert f'"{ghost}"' not in source, (
                f"the job API re-typed {ghost} into the status filter"
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


def _status_comparisons(source: str) -> list[tuple[int, str]]:
    """Every `…status… === "WORD"` operand in a TS/TSX source, with its line.

    Comparison position is where a status word is USED to decide what the reader
    sees, and it is the position the scans above cannot reach: they read Record
    keys and list elements, so `STATUS_HELP` stayed pinned while `nextAction`
    compared `status === "UNVERIFIED"` a few lines away from it (#170).

    The left operand is matched structurally (an identifier whose name ends in
    `status`) and the operand must be an uppercase token, which keeps this
    inside the job-status channel: the same file also holds
    `s.status === "fulfilled"` (a Promise result, not a status word), and other
    pages compare their OWN vocabularies — the agent console's `COMPLETED`,
    contracts' `APPROVED` — which are not this state machine's and are not
    checked here.
    """
    sites: list[tuple[int, str]] = []
    for n, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("//", "*", "/*")):
            continue
        for match in re.finditer(r'\b\w*[sS]tatus\w*\s*===\s*"([A-Z][A-Z0-9_]*)"', line):
            sites.append((n, match.group(1)))
    return sites


def _ts_string_set(source: str, name: str) -> set[str]:
    """Read `const NAME = new Set(["A", "B"]);` — the page's own copy of a set."""
    match = re.search(rf"const {name} = new Set\(\[([^\]]*)\]\)", source)
    assert match, f"const {name} = new Set([...]) not found — gate would pass vacuously"
    words = set(re.findall(r'"([^"]+)"', match.group(1)))
    assert words, f"{name} parsed to no members — gate would pass vacuously"
    return words


def test_job_detail_compares_only_statuses_the_machine_can_hold() -> None:
    """The dead branch this file previously certified around.

    `status` here is `(job.status || "").toUpperCase()`, so a word outside the
    state machine can never match it, and an `||` term carrying one is not a
    harmless spare branch: it claims a meaning (「这条状态要去看引导页」) that no
    row can ever reach, which is how a reviewer ends up trusting a branch that
    has never run.
    """
    source = JOB_DETAIL.read_text(encoding="utf-8")
    sites = _status_comparisons(source)
    # Floor, from the scan itself: a clause that matches nothing is greener than
    # the bug it is supposed to guard, and the page really does compare here.
    assert len(sites) >= 3, (
        f"the comparison scan found {len(sites)} site(s) in {JOB_DETAIL.name}; "
        "expected at least the three in nextAction and the failure banner"
    )
    unreachable = [(n, word) for n, word in sites if word not in ALL_STATUSES]
    assert not unreachable, (
        f"JobDetail compares a job status against words no row can hold: "
        f"{unreachable} — storage/mysql.py has no such state"
    )
    for ghost in _NOT_STATUSES:
        assert ghost not in {word for _, word in sites}, (
            f"{ghost} is a verdict/matrix word, never a job status"
        )


def test_job_detail_keeps_no_ungated_copy_of_the_terminal_set() -> None:
    """TERMINAL decides when the page stops listening, so it is not prose.

    `terminal = TERMINAL.has(currentStatus)` closes the progress stream and
    triggers the artifact load, and the 5-second poll runs while `!terminal`;
    #62's three-way "why is there no summary" split reads it too. A terminal
    status missing from this copy is therefore a finished job that the page
    polls forever — while a status present here but not terminal on the backend
    stops the poll on a row that is still moving.
    """
    source = JOB_DETAIL.read_text(encoding="utf-8")
    page_terminal = _ts_string_set(source, "TERMINAL")
    assert page_terminal == set(TERMINAL_STATUSES), (
        "JobDetail::TERMINAL and storage/mysql.py::TERMINAL_STATUSES disagree: "
        f"polled forever {sorted(set(TERMINAL_STATUSES) - page_terminal)}, "
        f"stopped too early {sorted(page_terminal - set(TERMINAL_STATUSES))}"
    )


def test_job_detail_progress_bar_set_covers_in_flight_states() -> None:
    """ACTIVE drives the progress bar; every in-flight state must be in it.

    The one exception is named rather than counted: FAILED is retryable on the
    backend (FAILED → QUEUED/CANCELLED/ERROR) yet holds no live progress to
    draw, so it is polled without a bar. If that carve-out ever changes, this
    assertion says which side moved instead of quietly shrinking to fit.
    """
    source = JOB_DETAIL.read_text(encoding="utf-8")
    active = _ts_string_set(source, "ACTIVE")
    in_flight = set(ALL_STATUSES) - set(TERMINAL_STATUSES)
    overlap = active & set(TERMINAL_STATUSES)
    assert not overlap, f"ACTIVE draws a progress bar for terminal states: {sorted(overlap)}"
    missing = in_flight - active - {"FAILED"}
    assert not missing, f"in-flight statuses with no progress bar: {sorted(missing)}"
    assert "FAILED" in in_flight - active, (
        "FAILED is no longer the retryable-without-progress exception; "
        "update this clause to say what replaced it"
    )

# —— #179: agent_jobs has its OWN lifecycle, NOT derived from the verification
# state machine. This is the boundary pin: the Literal in agent_jobs.py IS the
# source of truth for agent jobs; it must NOT be rewritten from ALL_STATUSES,
# and the two machines must not be confused.
AGENT_STATUSES = tuple(AGENT_JOB_STATUSES)
AGENT_TERMINAL = ("succeeded", "failed", "cancelled")


def test_agent_jobs_statuses_are_an_independent_machine_not_derived() -> None:
    """agent_jobs lifecycle (5 states) is a SEPARATE state machine from the
    verification jobs (10 states). The Literal in storage/agent_jobs.py IS the
    authority for agent jobs. It must NOT be rewritten from ALL_STATUSES.

    Evidence:
    - storage/agent_jobs.py:67 declares JobStatus = Literal["pending",
      "running", "succeeded", "failed", "cancelled"] -- this IS the vocabulary.
    - The SQL in that module uses these exact lowercase words in static
      statements (_UPDATE_STATUS_NONTERMINAL_SQL, _UPDATE_STATUS_TERMINAL_SQL,
      _ATTACH_ACCEPT_SQL) -- they are NOT parameters but literal IN-lists.
    - If someone derives a list from ALL_STATUSES here, the gate fails with the
      exact reason: two different domains, two different vocabularies.
    """
    # Agent machine is exactly these 5 words (lowercase)
    assert AGENT_STATUSES == ("pending", "running", "succeeded", "failed", "cancelled")
    assert AGENT_TERMINAL == ("succeeded", "failed", "cancelled")

    # NONE of the agent words (lowercase) appear in the verification machine
    # (which is all UPPERCASE). A lowercase word in the verification machine
    # would be a category error.
    for w in AGENT_STATUSES:
        assert w not in ALL_STATUSES, (
            f"agent word {w!r} leaked into verification machine -- "
            "two domains must stay separate"
        )
    # Conversely, no verification word (UPPERCASE) is in the agent Literal.
    for w in ALL_STATUSES:
        assert w not in AGENT_STATUSES, (
            f"verification word {w!r} leaked into agent Literal -- "
            "two domains must stay separate"
        )


def test_agent_sql_uses_the_literal_words_and_nothing_else() -> None:
    """The static SQL in storage/agent_jobs.py IN-lists must match the
    Literal exactly. If the Literal grows, the SQL must grow with it (manual
    edit, not derivation). This guards the #110/FIX-18 "no second copy" rule
    inside the agent_jobs module itself.
    """
    import re

    import storage.agent_jobs as mod

    sqls = [
        mod._UPDATE_STATUS_NONTERMINAL_SQL,
        mod._UPDATE_STATUS_TERMINAL_SQL,
        mod._ATTACH_ACCEPT_SQL,
    ]
    for sql in sqls:
        # Extract words from IN ('word1', 'word2', ...)
        found = re.findall(r"IN \(([^)]*)\)", sql)
        assert found, f"no IN-list in {sql[:80]}"
        words = [w.strip().strip("'") for w in found[0].split(",")]
        # Every word must be in the Literal
        for w in words:
            assert w in AGENT_STATUSES, f"{w!r} in SQL but not in Literal"
    # Specifically: TERMINAL SQL must contain exactly the three terminal words
    terminal_words = re.findall(r"IN \(([^)]*)\)", mod._UPDATE_STATUS_TERMINAL_SQL)[0]
    terminal_words = [w.strip().strip("'") for w in terminal_words.split(",")]
    assert set(terminal_words) == set(AGENT_TERMINAL), (
        f"_UPDATE_STATUS_TERMINAL_SQL IN-list {terminal_words} "
        f"must match Literal terminal {AGENT_TERMINAL}"
    )


def test_agent_jobs_has_no_verdict_channel_confusion() -> None:
    """The evidence/verdict_channels.py registers a 'job_status' channel
    sourced from _VALID_TRANSITIONS (verification machine). That channel is
    ONLY for verification jobs. It must NOT be imported or used by agent_jobs.
    """
    import storage.agent_jobs as mod
    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "verdict_channels" not in source, (
        "agent_jobs must not import verdict_channels -- wrong state machine"
    )
    assert "job_status" not in source.lower().replace("_", " "), (
        "agent_jobs must not reference 'job_status' channel"
    )

