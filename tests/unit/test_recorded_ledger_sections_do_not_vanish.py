"""Fence: a section number the ledger has ever recorded may not vanish from HEAD unsaid.

WHY THIS EXISTS. #451's code landed (7d5a669, c2aced6) and its ledger section landed with it; a
later lane's lineage then carried a ledger copy without that section, and the record was gone.
No gate went red: the ledger still parsed, still had a plausible section count, still had a
plausible id list. ``git show c2aced6:docs/operations/DEEP_OPTIMIZATION_PLAN.md`` has the
``## #451`` heading and ``8e39432:…`` does not — the disappearance is visible in two readings that
were both already in the repository, and before this file nothing compared them.

MEASURED BEFORE WRITING (probes: ``.scratch/m469_ledger_loss_feasibility.py``,
``.scratch/m469_monotone_feasibility.py``, ``.scratch/m469_ruler_agreement.py``,
``.scratch/m469_grep_ruler.py``, ``.scratch/m469_token_lens.py``, ``.scratch/m469_title_lens.py``,
``.scratch/m469_reword.log``):

  354 revisions of the ledger are reachable from HEAD. Reading every one of them in full costs
  18.12s and pipes 288,972,122 bytes; ``git grep -e '^## #'`` over the same 354 revs costs 1.22s
  in 4 calls and reproduces the authoritative reading exactly (285 numbers ever recorded, 283 at
  HEAD, the same lost pair).
  charging the NUMBER or the whole ID TOKEN gives the same lost pair here; the token is charged,
  because a dropped ``## #144`` whose ``## #144b`` survives is a loss the number lens cannot see.
  294 id tokens have ever been recorded; 292 are at HEAD; the lost pair is #287 and #288, and BOTH
  are re-aims rather than losses.
  the diff/patch ruler was rejected: its ``+`` lines see only 284 of the 285 ids ever recorded, so
  a number that entered HEAD through a merge would be invisible to it — under-detection, the
  false-green direction.
  the "every ``#NNN`` in a commit subject must have a section" ruler was rejected too: 101 reachable
  subjects have no section under any heading spelling, so that charge needs a 101-row table of
  other lanes' history rather than a fence.
  the TITLE-level ratchet ("every title ever written must still be at HEAD") was rejected by its
  own measurement: 293 titles have ever been recorded against 292 at HEAD, and the one title absent
  from HEAD belongs to ``## #444``, which is at HEAD with a reworded title — a lane fixing the prose
  of a living section would have been charged for losing it.

WHY THE EXEMPTION IS DERIVED, AND WHY IT IS "AT LEAST ONE". A lost id is excused when a HEAD
heading carries one of the titles that id was recorded with — that is what makes a renumbering
legible without a table. "At least one", not "exactly one", because the ledger really did carry two
sections under one id in the same revision: ``8e1bded`` shows ``## #288`` twice, with the 账本
duplicate-gate title and with the ``github_checks`` key-passthrough title, and at HEAD those two
titles are ``## #289`` and ``## #290``. That is a split — two records survived, one number was
abandoned — and a fence that demanded a single survivor would call it a loss.

THE JUDGMENT, and the direction of its errors: a recorded id absent from HEAD is refused unless one
HEAD heading carries the same title text under a different id. A lane that both renumbers and
rewords a section is refused (the title is what makes the match checkable); a lane that gutts a
section's BODY while keeping its heading line is not caught here, and a lane that deletes a section
and edits this file's words is not caught by anything — that is true of every gate here.

  L1 both readings must be populated, and every id HEAD shows must be a recorded id too — the two
     lenses (``git grep`` over history, my own regex over HEAD's blob) are graded on one file.
  L2 a recorded id missing from HEAD whose titles ALL vanished is refused, naming the revision that
     last carried it.
  L3 the exemption is only as good as its referent: each surviving title must name exactly one HEAD
     id, and HEAD's titles and ids must stand one-to-one.
  L4 the fence charges a deletion of a real heading from real bytes, does NOT charge the same bytes
     when the heading is only renumbered (the #287/#288 shape), and charges it again when the
     heading is renumbered AND reworded.
  L5 a collapsed reading must refuse, not certify: an empty history (shallow clone, a plane without
     ``.git``, the ledger renamed) is named as such.
  L6 #292's uniqueness parser is the ledger's other reader; this fence is blind exactly where it is
     not — the headings whose id is glued to its title (``## #167：…``) — measured from the same
     bytes, so the two lenses move together instead of pinning a count.
  L7 those glued headings are inside this fence's reach: deleting one from real bytes goes red, and
     #292's parser cannot see the same deletion at all. Without this leg a narrowing of ``ID`` back
     to the whitespace-anchored shape would go unmentioned — measured, an anchored lens does not see
     zero glued headings but 286 of them, because its match ends after the separator and a title's
     first character then reads as glue; the leg refuses that witness through the clause that asks
     whether the id it picked is really invisible to #292 (the first is ``#130``, which parses).

THE GLUED HEADINGS, measured: HEAD carries 292 id tokens and #292's whitespace-requiring parser sees
286 of them. The six it cannot see are ``## #163``–``## #168``, each glued to its title with a
full-width colon (``## #163：Worker 崩溃恢复的两个可测时钟…``). Those six are why this file keeps
its own lens instead of importing #292's parser, so they are compared as sets (L6) and deleted as
witnesses (L7) rather than pinned as a count a lane could repair.
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
LEDGER_REL = "docs/operations/DEEP_OPTIMIZATION_PLAN.md"
GATE_292 = ROOT / "tests" / "unit" / "test_ledger_section_ids_are_unique.py"

#: What this fence charges: the id token of a ``## #<id>`` heading, digits plus an optional suffix,
#: and deliberately NOT requiring whitespace after it — the ledger ships glued titles
#: (``## #167：stage 族定制梯度…``), which a whitespace-anchored parser cannot see (L6/L7).
ID = re.compile(r"^## #([0-9]+[A-Za-z0-9\-]*)", re.M)
#: The id and whatever separator the lane used. Stripped to get the title that L2-L4 compare.
LEAD = re.compile(r"^## #[0-9]+[A-Za-z0-9\-]*[ \t]*")

#: Floors, set far below the measurements above so they cannot rot with the ledger, but high
#: enough that a collapsed reading cannot read as "clean" (L1/L5).
MIN_REVS = 100
MIN_IDS = 200
#: Revs per ``git grep`` call. 354 revs in one argv is 14 KB of argument and works on this
#: machine; the chunk keeps the door alive as the ledger's history grows.
REV_CHUNK = 120

#: ``id token -> the revisions that carried it`` / ``id token -> heading lines it carried``
_Map = dict[str, tuple[str, ...]]
#: ``(revisions, ids->revisions, ids->lines, HEAD bytes, where those bytes came from)``
_Readings = tuple[tuple[str, ...], _Map, _Map, str, str]


class UnreadableLedgerError(RuntimeError):
    """A reading collapsed: the fence declines to judge rather than certify."""


def _num_key(kv: tuple[str, tuple[str, ...]]) -> tuple[int, str]:
    """Order id tokens by their number, then by token, so a refusal reads like the ledger."""
    return int(re.match(r"\d+", kv[0]).group(0)), kv[0]


def _git(*args: str) -> bytes:
    proc = subprocess.run(args, cwd=ROOT, capture_output=True)
    # git grep exits 1 on "no match", which is a legitimate (alarming) reading, not a crash.
    detail = f"{' '.join(args)} -> rc={proc.returncode} {proc.stderr[:160]!r}"
    assert proc.returncode in (0, 1), detail
    return proc.stdout


def _head_text() -> tuple[str, str]:
    """The bytes this fence grades as HEAD, and a label naming where they came from.

    ``SPECPROOF_LEDGER_HEAD_PATH`` exists for the mutation arms: L4 and L7 have to delete one real
    heading and renumber another, and the only honest way to do that is to grade a COPY of HEAD's
    own bytes — the ledger is a shared work tree other lanes are appending to. #292 ships the same
    convention for the same reason (its ``SPECPROOF_LEDGER_PATH``); nothing outside the arms
    sets it.
    """
    override = os.environ.get("SPECPROOF_LEDGER_HEAD_PATH", "")
    if override:
        path = Path(override)
        assert path.is_file(), f"ledger override names no file: {path}"
        return path.read_text(encoding="utf-8"), f"copy:{path.name}"
    blob = _git("git", "show", f"HEAD:{LEDGER_REL}")
    return blob.decode("utf-8", errors="replace"), "HEAD blob"


def _title(line: str) -> str:
    return LEAD.sub("", line.rstrip("\r\n")).strip()


@functools.lru_cache(maxsize=1)
def _revs() -> tuple[str, ...]:
    raw = _git("git", "log", "--format=%H%x00", "--", LEDGER_REL)
    text = raw.decode("utf-8", errors="replace")
    return tuple(s.strip() for s in text.split("\x00") if s.strip())


@functools.lru_cache(maxsize=1)
def _recorded() -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    """``ids → revisions`` and ``ids → heading lines``, over every reachable ledger revision.

    One ``git grep`` per chunk of revisions: it reads each revision's own blob, so no diff
    simplification can hide a heading from it (the patch ruler's blind spot, measured above).
    """
    revs = _revs()
    carriers: dict[str, set[str]] = {}
    lines: dict[str, set[str]] = {}
    for start in range(0, len(revs), REV_CHUNK):
        batch = list(revs[start : start + REV_CHUNK])
        out = _git("git", "grep", "-e", "^## #", *batch, "--", LEDGER_REL)
        for row in out.decode("utf-8", errors="replace").splitlines():
            _sha, _, rest = row.partition(":")
            _path, _, body = rest.partition(":")
            m = ID.match(body)
            if m:
                carriers.setdefault(m.group(1), set()).add(_sha)
                lines.setdefault(m.group(1), set()).add(body.rstrip("\r\n"))
    ids_by_rev = {k: tuple(sorted(v)) for k, v in carriers.items()}
    lines_by_id = {k: tuple(sorted(v)) for k, v in lines.items()}
    return ids_by_rev, lines_by_id


def _head_index(text: str) -> tuple[set[str], dict[str, list[str]]]:
    """HEAD's ids, and ``title → ids`` — the table L2/L3 match a lost id against."""
    ids = set(ID.findall(text))
    by_title: dict[str, list[str]] = {}
    for line in text.splitlines():
        m = ID.match(line)
        if m:
            by_title.setdefault(_title(line), []).append(m.group(1))
    return ids, by_title


class Row:
    """One recorded id that HEAD does not show, and what (if anything) explains it."""

    __slots__ = ("carriers", "gone", "ident", "survivors", "titles")

    def __init__(
        self,
        ident: str,
        carriers: tuple[str, ...],
        titles: tuple[str, ...],
        survivors: list[str],
        gone: list[str],
    ) -> None:
        self.ident = ident
        self.carriers = carriers
        self.titles = titles
        self.survivors = survivors
        #: Titles this id was recorded with that no HEAD heading carries.
        self.gone = gone

    @property
    def last(self) -> str:
        """The newest revision that still carried this id (``git log`` order is newest first)."""
        order = {sha: i for i, sha in enumerate(_revs())}
        return min(self.carriers, key=lambda s: order.get(s, len(order)))

    def explain(self) -> str:
        if not self.gone:
            return (
                f"#{self.ident} -> #{'/'.join(self.survivors)}: all {len(self.titles)} recorded "
                f"title(s) still head a section — «{self.titles[0][:56]}»"
            )
        return (
            f"#{self.ident} recorded in {len(self.carriers)} revision(s), last in {self.last[:7]}, "
            f"absent from HEAD and no heading carries its title: «{self.gone[0][:64]}»"
        )

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"Row(#{self.ident}, survivors={self.survivors}, gone={len(self.gone)})"


def _rows(carriers: _Map, lines: _Map, text: str) -> list[Row]:
    """Every recorded id HEAD does not show, with its title survivors attached when they exist."""
    head_ids, by_title = _head_index(text)
    out: list[Row] = []
    for ident, revs in sorted(carriers.items(), key=_num_key):
        if ident in head_ids:
            continue
        titles = {_title(line) for line in lines.get(ident, ())}
        out.append(
            Row(
                ident,
                revs,
                tuple(sorted(titles)),
                sorted({hid for title in titles for hid in by_title.get(title, [])}),
                sorted(title for title in titles if title not in by_title),
            )
        )
    return out


def _require_population(revs: tuple[str, ...], carriers: _Map, head_ids: set[str]) -> None:
    """L1/L5: a collapsed reading is a refusal, never a clean bill."""
    if len(revs) < MIN_REVS:
        raise UnreadableLedgerError(
            f"only {len(revs)} revisions of {LEDGER_REL} are reachable — a shallow clone, a "
            f"plane without .git, or a renamed ledger. The fence needs {MIN_REVS} to judge."
        )
    if len(carriers) < MIN_IDS:
        raise UnreadableLedgerError(
            f"only {len(carriers)} ids recorded across {len(revs)} revisions (floor {MIN_IDS})"
        )
    if len(head_ids) < MIN_IDS:
        raise UnreadableLedgerError(
            f"only {len(head_ids)} ids in HEAD's copy of {LEDGER_REL} (floor {MIN_IDS})"
        )


def _readings() -> _Readings:
    text, label = _head_text()
    carriers, lines = _recorded()
    _require_population(_revs(), carriers, set(ID.findall(text)))
    return _revs(), carriers, lines, text, label


def _splice_head(text: str, ident: str, new_ident: str = "") -> str:
    """Rewrite exactly one real heading line of HEAD's bytes.

    ``new_ident=""`` drops the whole heading line (a deletion); otherwise the id token is replaced
    and the rest of the line — separator character and title — is carried over verbatim, which is
    what a lane renumbering a record actually does. Deriving the splice from the heading's own bytes
    instead of a ``f"## #{ident} "`` needle keeps it working on the glued headings (L7).

    The cut is at ``m.end(1)`` — the end of the id TOKEN — not at ``m.end()``. A lens that anchors
    its group with a trailing ``[ \\t]`` would otherwise swallow the separator and hand the legs a
    renumbered heading that is glued for reasons having nothing to do with what they claim to test
    (measured: an anchored ``ID`` turned ``## #468 Phase 4 继续…`` into ``## #4689Phase 4 继续…``).
    """
    lines = text.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if (m := ID.match(line)) and m.group(1) == ident]
    assert len(hits) == 1, f"expected exactly one heading line for #{ident}, found {len(hits)}"
    i = hits[0]
    if not new_ident:
        del lines[i]
        return "".join(lines)
    m = ID.match(lines[i])
    assert m is not None
    lines[i] = f"## #{new_ident}" + lines[i][m.end(1) :]
    return "".join(lines)


# ─────────────────────────────── L1 — the two readings ───────────────────────────────
def test_both_readings_are_populated_and_share_one_basis() -> None:
    """L1 — denominators, and: every id HEAD shows is also a recorded id.

    The subset clause is the cross-reader parity. HEAD's ids come from my regex over one blob; the
    recorded ids come from ``git grep`` over 354 blobs including that one. If either lens stopped
    seeing a spelling the other sees — or if a heading appeared at HEAD that no revision ever
    recorded — the difference is named instead of grading as "no losses".
    """
    revs, carriers, _lines, text, _label = _readings()
    head_ids, _by_title = _head_index(text)
    assert len(revs) >= MIN_REVS and len(carriers) >= MIN_IDS and len(head_ids) >= MIN_IDS
    unrecorded = sorted(head_ids - set(carriers))
    assert not unrecorded, f"HEAD shows ids no revision records — the lenses disagree: {unrecorded}"


# ─────────────────────────────── L2 — the fence ───────────────────────────────
def test_no_recorded_section_is_missing_from_head_without_a_survivor() -> None:
    """L2 — what the #451 incident would have needed to be caught."""
    _revs_, carriers, lines, text, label = _readings()
    charged = [row for row in _rows(carriers, lines, text) if row.gone]
    assert not charged, (
        f"sections recorded in the ledger's own history but lost from HEAD ({label}):\n  "
        + "\n  ".join(row.explain() for row in charged)
    )
    excused = [row for row in _rows(carriers, lines, text) if not row.gone]
    assert all(row.survivors for row in excused), [row.explain() for row in excused]


# ─────────────────────────────── L3 — the exemption's referent ───────────────────────────────
def test_the_survivor_named_by_an_excused_id_is_one_real_head_section() -> None:
    """L3 — "the title survives elsewhere" has to mean ONE section, and a real one.

    A lost id excused by a title match is only checkable while each HEAD title names a single HEAD
    id: if two sections carried the same title, the match would stop saying which one the record
    became. Measured over HEAD's own bytes, not tabulated — a lane that copies a heading line to a
    second number trips this leg.
    """
    _revs_, carriers, lines, text, _label = _readings()
    head_ids, by_title = _head_index(text)
    dup_titles = {title: ids for title, ids in by_title.items() if len(ids) > 1}
    assert not dup_titles, f"one title under {len(dup_titles)} HEAD ids: {list(dup_titles)[:3]}"
    assert len(by_title) == len(head_ids), f"{len(by_title)} titles vs {len(head_ids)} ids at HEAD"
    for row in _rows(carriers, lines, text):
        phantom = set(row.survivors) - head_ids
        assert not phantom, f"#{row.ident} is excused by an id HEAD does not show: {phantom}"
        assert row.ident not in row.survivors, f"#{row.ident} is its own survivor: {row.explain()}"
        for title in row.titles:
            if title in by_title:
                assert len(by_title[title]) == 1, f"«{title[:40]}» names {by_title[title]}"


# ─────────────────────────────── L4 — the judgment, both ways ───────────────────────────────
def test_the_fence_charges_a_deletion_and_excuses_a_renumber() -> None:
    """L4 — the same bytes, three judgments, on a real heading of a real ledger.

    Deleting a section from HEAD's own bytes must produce exactly the red the #451 incident did not
    produce. Renumbering the same heading must NOT: that is the #287/#288 shape this fence has to
    tolerate. Renumbering AND rewording it must produce the red again — the exemption is bound to
    the title, not to the number's being close.

    Each judgment is graded as a DIFFERENCE against the lost set of the unmutated bytes, so another
    lane's pending loss in the ledger cannot make this leg's arithmetic wrong: the mutation has to
    add exactly the victim and nothing else.
    """
    _revs_, carriers, lines, text, _label = _readings()
    head_ids, _by_title = _head_index(text)
    victim = max(head_ids, key=lambda i: int(re.match(r"\d+", i).group(0)))
    before = {row.ident for row in _rows(carriers, lines, text) if row.gone}
    assert victim not in before, "the victim is already lost"

    def lost_after(spliced: str) -> set[str]:
        return {row.ident for row in _rows(carriers, lines, spliced) if row.gone}

    assert lost_after(_splice_head(text, victim)) == before | {victim}, (
        f"deleting #{victim}'s heading line did not charge exactly it on top of {sorted(before)}"
    )

    renumbered = _splice_head(text, victim, f"{victim}9")
    assert lost_after(renumbered) == before, (
        f"a bare renumber was charged: {sorted(lost_after(renumbered) - before)}"
    )
    survivor = [row for row in _rows(carriers, lines, renumbered) if row.ident == victim]
    assert survivor and survivor[0].survivors == [f"{victim}9"], survivor

    reworded = renumbered.replace(f"## #{victim}9", f"## #{victim}9 本门的标题被改写：", 1)
    assert reworded != renumbered, "the id needle stopped matching"
    assert lost_after(reworded) == before | {victim}, (
        "renumber + reword still read as a re-aim — the survivor match stopped needing the title"
    )


# ─────────────────────────────── L5 — collapse refuses ───────────────────────────────
def test_a_collapsed_reading_refuses_instead_of_certifying() -> None:
    """L5 — the other plane: no .git, a shallow clone, a renamed ledger.

    Each denominator collapse is named. Without this leg an empty history reading is "zero losses"
    and the fence greenlights the plane that cannot answer it.
    """
    revs, carriers, _lines, text, _label = _readings()
    head_ids, _by_title = _head_index(text)
    with pytest.raises(UnreadableLedgerError, match=r"revisions"):
        _require_population(revs[:10], carriers, head_ids)
    with pytest.raises(UnreadableLedgerError, match=r"ids recorded"):
        _require_population(revs, {"1": ("a",)}, head_ids)
    with pytest.raises(UnreadableLedgerError, match=r"HEAD"):
        _require_population(revs, carriers, set())
    assert _rows({}, {}, text) == [], "an empty history invented losses"
    # and the shipped plane is NOT collapsed: the refusal above is reachable only by lying
    assert len(carriers) >= MIN_IDS and len(head_ids) >= MIN_IDS


# ─────────────────────────── L6/L7 — the other reader, and reach ───────────────────────────
@functools.lru_cache(maxsize=1)
def _gate_292() -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("sp_gate292", GATE_292)
    assert spec is not None and spec.loader is not None, f"cannot load {GATE_292}"
    module = importlib.util.module_from_spec(spec)
    sys.modules["sp_gate292"] = module
    spec.loader.exec_module(module)
    return module


def _glued(text: str) -> set[str]:
    """HEAD's ids whose heading has no whitespace between the id and its title."""
    return {
        m.group(1)
        for m in ID.finditer(text)
        if text[m.end() : m.end() + 1] not in {" ", "\t", "\n", ""}
    }


def test_the_two_ledger_readers_differ_only_where_the_ledger_spells_headings_glued() -> None:
    """L6 — #292 owns the ledger's id TOKENS; this fence owns their survival.

    Its parser requires whitespace between the id and the title, so it does not see
    ``## #167：stage 族定制梯度…`` at all. Measured from the same bytes: the ids this fence sees and
    #292 does not are exactly the headings whose next character is neither space nor tab. Nothing
    pins a count, so when a lane repairs a glued heading both readers move together.
    """
    _revs_, _carriers, _lines, text, _label = _readings()
    owner = _gate_292()
    theirs = {s.ident for s in owner.parse_sections(text)}
    mine = set(ID.findall(text))
    assert theirs <= mine, f"#292 shows ids this fence does not: {sorted(theirs - mine)}"
    glued = _glued(text)
    assert mine - theirs == glued, f"lens drift: {sorted(mine - theirs)} vs glued {sorted(glued)}"
    assert len(theirs) >= MIN_IDS, f"#292's parser collapsed to {len(theirs)} ids on HEAD's bytes"


def test_a_glued_heading_is_inside_this_fences_reach() -> None:
    """L7 — the reach claim, tested as behavior instead of as a regex's shape.

    The whole reason this fence keeps its own lens is the glued headings, so the witness has to be a
    glued heading: deleting one from HEAD's own bytes must go red here and stay invisible to #292's
    parser. The charge is graded as a DIFFERENCE against this reading's own lost set, exactly as in
    L4 — an arm that already deleted one heading must not be read as making this witness charge two.

    A narrowing of ``ID`` back to the whitespace-anchored shape does NOT empty the derived
    population, which is what this leg's first clause would name. Measured (``.scratch/
    m469_a6_replay.py``): an anchored group ends after the separator, so ``_glued`` then reads each
    title's first character as glue and returns 286 ids instead of 6. The leg still goes red,
    through the clause that asks whether the witness it chose is really invisible to #292's parser
    — the first id an anchored lens calls "glued" is ``#130``, which #292 parses — and L6's drift
    clause (``∅`` vs those 286) goes red beside it.
    """
    _revs_, carriers, lines, text, _label = _readings()
    glued = sorted(_glued(text), key=lambda i: int(re.match(r"\d+", i).group(0)))
    assert glued, "no glued heading in HEAD's ledger — the lens that exists to see them went blind"
    owner = _gate_292()
    theirs = {s.ident for s in owner.parse_sections(text)}
    victim = glued[0]
    assert victim not in theirs, f"#{victim} is not glued after all — wrong witness shape"
    before = {row.ident for row in _rows(carriers, lines, text) if row.gone}
    assert victim not in before, f"#{victim} was already lost before this leg deleted anything"
    after = {row.ident for row in _rows(carriers, lines, _splice_head(text, victim)) if row.gone}
    assert after == before | {victim}, (
        f"deleting the glued heading #{victim} charged {sorted(after - before)} "
        f"on top of {sorted(before)}"
    )


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
