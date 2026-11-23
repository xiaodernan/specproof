"""Every number the project names must exist as a structural record.

WHAT THIS CLOSES. Two lanes in one week produced the same shape of lie:

  * #2071 (`3f332e9`) shipped with a commit subject naming `#2071` while the
    ledger held no `## #2071` section — the number was unresolvable in the
    repository's own chronicle, and the published fact pack
    (`docs/latest.json`, re-struck at `7e9f98e`) went out saying
    `latest_strike: "#2071"`. A reader following the published number found
    prose about other units, never a record of this one.
  * the ledger's 「下一号队列」 blocks name gate files by path. Two of them were
    never written (`tests/unit/test_mutation_engine.py`, named 10 times;
    `tests/unit/test_ci_nightly_full_eval_job.py`, twice). Nothing anywhere read
    those paths back — this repository holds no red-gate roster at all, so a
    promised gate stayed green by being unrunnable, and the only way to notice
    was to go look for the file, which nobody did.

Both are the defect class #2071 recorded from the other side ("a leg nobody
runs does not speak") and the same one #287 closed for duplicated section ids.

WHAT COUNTS AS A RECORD. A `## #<id>` HEADING in the ledger. Not prose: this
file's own first draft wrote "见 #2071" three times while #2071 had no section,
which is the whole bug in miniature. Prose is measured (it says where the debt
lives) but never satisfies a leg — the synthetic witness below pins that, and
`tests/unit/test_recorded_ledger_sections_do_not_vanish.py` records why the
project rejected the substring ruler.

MEASURED BEFORE WRITING (2026-11-23, baseline `7e9f98e`; artifacts
`.scratch/const2072.json`, `.scratch/census2072b.json`,
`.scratch/gatefiles2072narrow.py`, predictions in `.scratch/predict_fence2072.md`):

    commits reachable from HEAD            2926
    distinct numbers cited in subjects      1073   (1468 mentions)
    「衔接 #N」 pointer lines in the ledger   156   (154 distinct: 1914, 1919,
                                                    1964 point at nothing)
    `## #<id>` headings, this file's ruler  1888   (1888 distinct — #2029's
                                                    duplicate was split into
                                                    `#2029` / `#2029b` here)
    the same ruler in #287's gate           1882   — it requires a space or tab
                                                    after the id, so 163–168
                                                    (`## #163：`, full-width
                                                    colon) are invisible to it
    build_latest.py's chronicle ruler       1867   — the published
                                                    `chronicle_entries` is 21
                                                    short of the truth
    named, no section, id < 130               80   (the ledger starts at #130)
    named, no section, id >= 130              51   (the register below)
    frontier window: subjects citing a number  51 of the newest 100
    frontier window: violations                0   (this is what makes the
                                                    zero-tolerance leg payable)
    gate files named by the ledger           412   (measured across 779 mentions;
                                                    the 413rd backticked path is
                                                    `test_the_payload...py`, an
                                                    ellipsis, not a commitment.
                                                    3 absent when this was counted
                                                    — the third was this file,
                                                    which the same commit wrote)

WHY NO 131-ROW TABLE. The prior lane refused this fence on cost
("补 101 个编号成本过高，不做"). The affordable shape is a floor plus a
one-way ratchet plus a window that cannot be deferred: history keeps its
register as a ceiling, the newest 100 commits get zero tolerance, and every
constant above is a measured number with the leg that releases it downward.

ARMS. Every leg above has a mutation arm (`.scratch/arms_fence2072.py`, P1–P10
predicted before any of them ran), including the two that prove the lens is
structural rather than textual: P3 (a substring ruler goes green on P1's
deleted heading and only the synthetic witness notices) and P5 (a ref-poor
checkout empties the window and the population leg, not the zero-tolerance
leg, is what refuses).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Overridable so the mutation arms run against a COPY of the shared ledger
#: (house convention, see `test_ledger_section_ids_are_unique.py`): other lanes
#: append to that file, and an arm that touched it could clobber their section.
LEDGER = Path(
    os.environ.get(
        "SPECPROOF_LEDGER_PATH",
        str(ROOT / "docs" / "operations" / "DEEP_OPTIMIZATION_PLAN.md"),
    )
)
LATEST = Path(
    os.environ.get("SPECPROOF_LATEST_JSON_PATH", str(ROOT / "docs" / "latest.json"))
)
BUILD_LATEST = ROOT / "scripts" / "build_latest.py"

#: How many of the newest commit subjects get zero tolerance.
FRONTIER_WINDOW = int(os.environ.get("SPECPROOF_FRONTIER_WINDOW", "100"))
#: Test-only knob for the ref-poor-checkout arm (P5); 0 means "every commit".
LOG_LIMIT = int(os.environ.get("SPECPROOF_CITATION_LOG_LIMIT", "0"))

#: The ledger's own first section. Numbers below this predate it, so a missing
#: section for them is a citation to history, not a debt against the chronicle.
ERA_START = 130
#: Measured 2026-11-23 (see the docstring table). One-way: paying debt down may
#: lower it, adding to it may not.
DEBT_CEILING = 51
RULER_GAP_CEILING = 21
#: Measured 412 distinct paths named, 2 of them absent. It was 3 until this file
#: landed: the ledger named `test_every_number_a_commit_cites_has_a_ledger_section.py`
#: in the same commit that wrote it, so the promise became a file and the ceiling
#: came down with it. That is what a one-way ratchet is for.
GATE_FILE_CEILING = 2

#: Numbers named by a commit subject or a 「衔接」 pointer with no section.
#: Every entry is a debt the project chose to carry; a NEW number is not.
UNRECORDED: frozenset[str] = frozenset(
    {
        "131", "133", "138", "148", "149", "151", "152", "153", "154", "155",
        "156", "157", "158", "160", "161", "162", "169", "171", "172", "173",
        "186", "187", "188", "189", "190", "191", "192", "193", "194", "195",
        "196", "197", "198", "199", "200", "201", "224", "225", "226", "227",
        "228", "229", "233", "270", "274", "287", "1581", "1914", "1919",
        "1964", "1979",
    }
)

#: Gate files the ledger names in backticks that do not exist in the tree.
#: 1914/1919/1964's siblings in kind: a promise written as a path.
NAMED_BUT_ABSENT: frozenset[str] = frozenset(
    {
        "tests/unit/test_mutation_engine.py",
        "tests/unit/test_ci_nightly_full_eval_job.py",
    }
)

#: `#1234` — a bare number token, the citation shape both lenses share.
CITE = re.compile(r"#(\d{2,4})\b")
#: 「衔接 #1234」 — the ledger's forward pointer to the unit it continues.
POINTER = re.compile(r"衔接\s*#(\d{2,4})")
#: The record. Id token = digits + optional suffix, ending at the first
#: character that cannot be part of an id, so `## #163：` and `## #144b` are
#: both read (#287's ruler requires a space or tab and therefore misses 163–168).
HEADING = re.compile(r"^## #([0-9]+[A-Za-z0-9\-]*)", re.M)
#: A gate file named by path inside the ledger.
GATE_FILE = re.compile(
    r"`(tests/(?:unit|integration|e2e|security|fault|contract|scenario|perf)"
    r"/test_[A-Za-z0-9_.\-]+\.py)`"
)


def _git_subjects() -> list[str]:
    """Commit subjects, newest first. A failure is a red, never a skip: a leg
    that skips because `git` misbehaved is a leg that goes green on nothing."""
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "log", "--format=%s"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, f"`git log` failed ({proc.returncode}): {proc.stderr}"
    subjects = proc.stdout.splitlines()
    assert subjects, "`git log` returned no subjects at all"
    if LOG_LIMIT:
        subjects = subjects[:LOG_LIMIT]
    return subjects


def _ledger_text() -> str:
    text = LEDGER.read_text(encoding="utf-8", errors="replace")
    assert len(text) > 100_000, (
        f"{LEDGER} is {len(text)} bytes — that is not the ledger; the gate is "
        "reading an empty or truncated file and every leg below is vacuous"
    )
    return text


def _records(text: str) -> set[str]:
    return set(HEADING.findall(text))


def _cited(subjects: list[str]) -> set[str]:
    return {tok for line in subjects for tok in CITE.findall(line)}


def _pointed(text: str) -> set[str]:
    return set(POINTER.findall(text))


def _debt(named: set[str], records: set[str]) -> set[str]:
    """Named since the ledger's own era began, with no section to resolve to."""
    return {n for n in named if n not in records and int(n) >= ERA_START}


def _build_latest_ruler() -> re.Pattern[str]:
    """The regex literal `build_latest.py` counts chronicle entries with.

    Read out of the script rather than retyped: a leg that hard-codes the ruler
    keeps passing the day the published count starts coming from somewhere else.
    """
    src = BUILD_LATEST.read_text(encoding="utf-8")
    for lit in re.finditer(r'r?"((?:[^"\\]|\\.)*)"', src):
        if "^## " in lit.group(1):
            return re.compile(lit.group(1), re.M)
    raise AssertionError(
        f"{BUILD_LATEST.name} no longer contains a `^## ` ruler — the published "
        "chronicle count is derived from something this gate has not looked at"
    )


# --------------------------------------------------------------------------
# the population, so a collapsed lens cannot read as "no violations"
# --------------------------------------------------------------------------


def test_the_census_actually_ran() -> None:
    subjects = _git_subjects()
    text = _ledger_text()
    records = _records(text)
    named = _cited(subjects) | _pointed(text)
    assert len(subjects) >= 2000, f"only {len(subjects)} commits — shallow checkout?"
    assert len(named) >= 1000, f"only {len(named)} numbers named — the lens collapsed"
    assert len(records) >= 1800, f"only {len(records)} sections parsed"
    assert len(HEADING.findall(text)) == len(records), (
        "two sections share an id — a reference to it cannot be resolved "
        "(this is what #287 closed and #2029 re-opened)"
    )


def test_a_heading_is_a_record_and_prose_is_not() -> None:
    """The lens is structural. Synthetic witnesses, no ledger involved.

    Without this leg the whole file could be resting on a substring search,
    which is the ruler the project already rejected
    (`test_recorded_ledger_sections_do_not_vanish.py`).
    """
    fragment = "## #9001 a unit with a section\n\n- 见 #9001，另有一处正文提到 9001\n"
    assert "9001" in _records(fragment)
    prose_only = "- 见 #9002\n\n本号衔接 #9003。\n"
    assert _records(prose_only) == set(), "prose was counted as a record"
    # `## #144b` is its own id; `## #163：` is id 163 with a full-width colon.
    assert _records("## #144b landing\n\n## #163：配方\n") == {"144b", "163"}


# --------------------------------------------------------------------------
# the frontier: no new debt, and proof the window was actually fed
# --------------------------------------------------------------------------


def test_the_frontier_window_carries_no_new_debt() -> None:
    subjects = _git_subjects()[:FRONTIER_WINDOW]
    records = _records(_ledger_text())
    gaps = sorted(n for n in _cited(subjects) if n not in records)
    assert not gaps, (
        f"{len(gaps)} number(s) cited by the newest {FRONTIER_WINDOW} commits "
        f"have no `## #<id>` section: {gaps} — this is how #2071 shipped"
    )


def test_the_frontier_window_is_populated() -> None:
    """A window nobody fed is a zero-tolerance leg that tolerates everything."""
    subjects = _git_subjects()[:FRONTIER_WINDOW]
    carrying = [line for line in subjects if CITE.search(line)]
    assert len(subjects) >= FRONTIER_WINDOW, (
        f"the window asked for {FRONTIER_WINDOW} commits and got "
        f"{len(subjects)} — a ref-poor checkout turns the leg above green by "
        "leaving it nothing to read"
    )
    assert len(carrying) >= 20, (
        f"only {len(carrying)} of {len(subjects)} subjects cite a number — the "
        "citation convention stopped being the convention"
    )


def test_a_planted_dangling_citation_is_detected() -> None:
    """Synthetic counterpart of the window leg: the detector fires on demand."""
    records = {"1", "2"}
    planted = ["fix(x): #9001 does the thing", "chore(y): #2 continues"]
    assert _cited(planted) - records == {"9001"}


# --------------------------------------------------------------------------
# the historical debt: registered, capped, and only allowed to shrink
# --------------------------------------------------------------------------


def test_the_unrecorded_register_covers_every_gap() -> None:
    debt = _debt(_cited(_git_subjects()) | _pointed(_ledger_text()), _records(_ledger_text()))
    outside = sorted(debt - UNRECORDED, key=int)
    assert not outside, (
        f"numbers named with no section and no register entry: {outside} — "
        "either write the section or say so here in a commit that explains it"
    )


def test_the_debt_ceiling_does_not_rise() -> None:
    debt = _debt(_cited(_git_subjects()) | _pointed(_ledger_text()), _records(_ledger_text()))
    assert len(debt) <= DEBT_CEILING, (
        f"{len(debt)} numbers named since #{ERA_START} with no section; the "
        f"ceiling is {DEBT_CEILING} (measured 2026-11-23) and it moves down only"
    )
    assert len(UNRECORDED) == DEBT_CEILING, (
        f"the register holds {len(UNRECORDED)} ids against a ceiling of "
        f"{DEBT_CEILING} — when a debt is paid, delete its id and lower the "
        "ceiling in the same commit"
    )


# --------------------------------------------------------------------------
# the published numbers, which are the claims a reader actually sees
# --------------------------------------------------------------------------


def test_the_published_fact_pack_names_a_recorded_unit() -> None:
    pack = json.loads(LATEST.read_text(encoding="utf-8"))
    strike = str(pack.get("latest_strike") or "")
    assert strike.startswith("#"), f"latest_strike is {strike!r}, not a number"
    ident = strike.lstrip("#")
    assert ident in _records(_ledger_text()), (
        f"the published fact pack advertises {strike} as the newest strike and "
        "the ledger has no section by that id — exactly what #2071 shipped as"
    )


def test_the_published_chronicle_count_stays_between_the_floors() -> None:
    pack = json.loads(LATEST.read_text(encoding="utf-8"))
    published = int(pack.get("chronicle_entries") or 0)
    truth = len(_records(_ledger_text()))
    assert published >= 1000, (
        f"chronicle_entries {published} is below the floor build_latest.py "
        "refuses to emit under — a shallow run leaked a fact pack"
    )
    assert published <= truth, (
        f"the pack publishes {published} chronicle entries; the ledger holds "
        f"{truth} sections. A published count above the truth is not drift, it "
        "is a fabricated number"
    )


def test_the_ruler_that_counts_the_chronicle_drifts_no_further() -> None:
    """`build_latest.py`'s ruler vs this file's, over the same bytes.

    Measured 2026-11-23: 1867 against 1888, a gap of 21. Every one of those 21
    is a section the public chronicle count does not see (`## #163：` and its
    five siblings, the `b`-suffixed halves). The gap is registered, not
    celebrated: it may shrink when the ruler is widened, and may not widen.
    """
    text = _ledger_text()
    gap = len(_records(text)) - len(_build_latest_ruler().findall(text))
    assert gap >= 0, (
        f"build_latest.py counts {gap} MORE sections than the structural ruler "
        "— the two lenses are no longer comparable; re-read both"
    )
    assert gap <= RULER_GAP_CEILING, (
        f"the published chronicle count is {gap} sections short of the ledger "
        f"(ceiling {RULER_GAP_CEILING}, measured 2026-11-23)"
    )


# --------------------------------------------------------------------------
# promised gates: a path in a queue block is a commitment
# --------------------------------------------------------------------------


def _named_gate_files(text: str) -> set[str]:
    return {
        p for p in GATE_FILE.findall(text) if "..." not in p and "…" not in p
    }


def test_every_gate_file_the_ledger_names_exists() -> None:
    absent = sorted(p for p in _named_gate_files(_ledger_text()) if not (ROOT / p).exists())
    outside = sorted(set(absent) - NAMED_BUT_ABSENT)
    assert not outside, (
        f"the ledger names gate files that were never written: {outside} — a "
        "promised gate that does not exist cannot appear in any red roster, so "
        "it stays green by being unrunnable"
    )
    assert len(absent) <= GATE_FILE_CEILING, (
        f"{len(absent)} named gate files are absent (ceiling "
        f"{GATE_FILE_CEILING}); write them or amend the ledger text"
    )


def test_a_planted_absent_gate_file_is_detected() -> None:
    """Synthetic counterpart: the lens fires on a name with no file."""
    planted = "见 `tests/unit/test_a_file_that_does_not_exist_2072.py`。\n"
    found = _named_gate_files(planted)
    assert found == {"tests/unit/test_a_file_that_does_not_exist_2072.py"}, found
    assert not all((ROOT / p).exists() for p in found)
    # A path with an ellipsis is prose shorthand, not a commitment.
    assert _named_gate_files("`tests/unit/test_the_payload...py`") == set()
