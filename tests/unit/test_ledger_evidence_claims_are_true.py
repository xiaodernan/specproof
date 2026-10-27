"""The ledger's file lists must be TRUE, and a plan must say that it is a plan.

WHY THIS EXISTS.  The ledger is this project's audit trail: every unit writes a
section, and the section's ``**证据文件**`` block is a factual claim — "these are
the files that are the evidence for what this section did".  Measured on the
ledger before this gate was written (``.scratch/probe476_evidence_blocks2.py``,
``.scratch/probe476_record_vs_plan.py``, ``.scratch/probe476_control_chars.py``):

  * 19 sections carry a file list; 12 of them name a path that is NOT in the
    tree — 49 distinct paths, and ``git log --all -- <path>`` returns **0
    commits for every one of them**: they never existed, in any revision.
  * nine of those sections (#461-#468, #473) are PLANS — each has an
    ``**执行计划**`` block, and the commit that carried the section changed
    nothing but the ledger itself.  Yet each ended with a ``**质量门**`` block
    reading "ruff + mypy 全绿" and an ``**证据文件**`` block reading
    "（新增）" for files that were never created.
  * three sections (#455, #456, #473) carry a path whose first letter was eaten
    by a TAB: the ledger says ``\\tests/unit/test_adapter_protocol.py`` where the
    file is ``tests/unit/test_adapter_protocol.py``.  That is a non-raw Python
    string literal — ``"\\tests/..."`` — and ``\\t`` became a tab.  The whole
    ledger holds exactly 5 TAB characters and every one of them is one of these
    five lines; there is no legitimate tab anywhere to exempt.
  * #473 also calls ``craft/adapters/python_adapter.py`` "现有" (existing).  It
    never existed.

So a reader — the operator, the next lane, an auditor — reading #468 would
believe the product has a multi-tenant quota system, a Rust adapter, a plugin
market and a distributed scheduler.  It has none of them.  The multi-tenancy
that DOES exist lives somewhere else (``storage/billing.py``,
``storage/tenant_scope.py``, migrations 0005/0007/0014), which is a separate
finding and is recorded as such; what this gate closes is the **shape** of the
record, not the gap it describes.

THE RULERS, each one sentence:

  L1  every path in an ``**证据文件**`` or ``**现状文件**`` block must exist in
      the tree.  A record's evidence must be real.
  L2  a ``**拟新增文件**`` block may only appear in a section that carries the
      plan marker ``**状态**：计划（未落地）``.  A plan that does not declare
      itself a plan is a record wearing a plan's file list.
  L3  a plan-marked section may not carry a ``**质量门**`` block (a gate that
      passed); it says ``**计划质量门**`` instead.  A plan has no passed gate.
  L4  no path may be broken by a control character.  This is the TAB class:
      one letter of one path is replaced, and the path stops resolving.

WHAT IS DELIBERATELY OUT OF SCOPE.  The ledger names 805 distinct path-shaped
tokens and 154 of them do not exist — that is the whole ledger, prose included,
and a gate over that set is a false-positive machine (the #475 lesson: measure
the ruler before choosing it).  This gate reads only the FILE LISTS, which is
where a claim about the product's files is made.  It also does not check that a
``**拟新增文件**`` path is still absent: a plan's wish list may quietly become
true, and that is a bookkeeping question, not a false claim.  A path inside
struck-through text (``~~...~~``) is a RETRACTED claim and is not charged —
without that, the ledger could not write down the very corrections this unit
made.

The ledger is a shared work tree that other lanes append to, so the gate reads
a COPY when ``SPECPROOF_LEDGER_PATH`` is set; the mutation arms use that.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: The ledger this gate reads. Overridable so the mutation arms can grade a
#: COPY: the live ledger is shared, and an arm that mutated it would risk
#: clobbering another lane's section. #292 and #475 ship the same convention.
LEDGER = Path(
    os.environ.get(
        "SPECPROOF_LEDGER_PATH",
        ROOT / "docs" / "operations" / "DEEP_OPTIMIZATION_PLAN.md",
    )
)

#: A numbered section heading. The ledger also ships GLUED headings
#: (``## #163：Worker ...``), so whitespace after the id is NOT required.
SECTION = re.compile(r"^## #([0-9]+[A-Za-z0-9\-]*)")

#: The marker a section carries when it records work that was NOT done.
PLAN_MARK = "**状态**：计划（未落地）"

#: The quality-gate heading, and the one a plan uses instead.
QUALITY_GATE = "**质量门**"
PLAN_QUALITY_GATE = "**计划质量门**"

#: The file-list headings, and what kind of claim each one makes.
FILE_LISTS = {
    "**证据文件**": "evidence",
    "**现状文件**": "current",
    "**拟新增文件**": "planned",
}

#: A path with an extension. The character class is ASCII-only on purpose: a
#: Unicode ``\w`` would match CJK, and the ledger's prose is full of things
#: like "取消/超时有界" that are not paths.
FILE_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_./\-])((?:[A-Za-z0-9_.\-]+/)+[A-Za-z0-9_.\-]*\.[A-Za-z0-9]+)"
)
#: A directory path (trailing slash). The trailing lookahead keeps it from
#: matching the prefix of a longer name: in ``a/b/c/d.py`` no directory token
#: may swallow ``a/b/``.
DIR_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_./\-])((?:[A-Za-z0-9_.\-]+/)+[A-Za-z0-9_.\-]+/)(?![A-Za-z0-9_.\-])"
)

#: A line that opens a file list.
LIST_HEAD = re.compile(r"^\*\*(证据文件|现状文件|拟新增文件)\*\*")


@dataclass(frozen=True)
class Section:
    """One numbered section of the ledger."""

    ident: str
    start: int
    end: int
    body: str


@dataclass(frozen=True)
class Block:
    """One file-list block, with the paths it names."""

    kind: str
    section: str
    line: int
    paths: tuple[tuple[str, int], ...]
    #: the raw list lines, with their line numbers — the control-character
    #: ruler needs the ORIGINAL text (the struck-through copy has had its
    #: columns shifted by the blanking).
    items: tuple[tuple[int, str], ...]


def sections(text: str) -> list[Section]:
    """Every numbered section, in document order."""
    lines = text.splitlines()
    heads = [
        (m.group(1), n)
        for n, line in enumerate(lines, start=1)
        if (m := SECTION.match(line))
    ]
    out: list[Section] = []
    for i, (ident, start) in enumerate(heads):
        end = heads[i + 1][1] - 1 if i + 1 < len(heads) else len(lines) + 1
        out.append(Section(ident, start, end, "\n".join(lines[start - 1:end])))
    return out


def _is_list_item(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(("- ", "* ", "+ ", "| "))


def _without_struck_text(line: str) -> str:
    """The line with its retracted (``~~...~~``) spans blanked out.

    An odd number of ``~~`` means the span runs to the end of the line, which
    is how a half-written retraction reads.
    """
    if line.count("~~") < 2:
        if line.count("~~") == 1:
            head, _, _ = line.partition("~~")
            return head
        return line
    out = re.sub(r"~~.*?~~", " ", line)
    if out.count("~~") == 1:
        head, _, _ = out.partition("~~")
        return head
    return out


def paths_in(line: str) -> list[tuple[str, int, int]]:
    """Every path token in the line, with the span it starts and ends at."""
    found = [(m.group(1), m.start(), m.end()) for m in FILE_TOKEN.finditer(line)]
    found += [(m.group(1), m.start(), m.end()) for m in DIR_TOKEN.finditer(line)]
    return sorted(found, key=lambda triple: triple[1])


def file_blocks(text: str) -> list[Block]:
    """Every file-list block, with the paths it names.

    A block runs from its heading line through the list lines under it and
    stops at the first line that is neither blank nor a list item.  A heading
    line is not a list item, so a block never swallows the block after it.
    """
    lines = text.splitlines()
    owners = sections(text)
    out: list[Block] = []
    for n, line in enumerate(lines, start=1):
        m = LIST_HEAD.match(line.strip())
        if not m:
            continue
        kind = FILE_LISTS[f"**{m.group(1)}**"]
        section = ""
        for sec in owners:
            if sec.start <= n <= sec.end:
                section = sec.ident
                break
        paths: list[tuple[str, int]] = []
        items: list[tuple[int, str]] = []
        for k in range(n, len(lines)):
            nxt = lines[k]
            if not nxt.strip():
                continue
            if not _is_list_item(nxt):
                break
            items.append((k + 1, nxt))
            paths.extend(
                (path, item_line)
                for path, _start, _end in paths_in(_without_struck_text(nxt))
                for item_line in (k + 1,)
            )
        out.append(Block(kind, section, n, tuple(paths), tuple(items)))
    return out


def is_plan(section: Section) -> bool:
    """Whether the section declares itself a plan."""
    return PLAN_MARK in section.body


def has_quality_gate(section: Section) -> bool:
    """Whether the section carries a gate that reads as PASSED."""
    return any(line.strip().startswith(QUALITY_GATE) for line in section.body.splitlines())


def missing_paths(text: str, root: Path) -> list[tuple[str, str, int]]:
    """Every path an evidence/current block names that is not in the tree."""
    out: list[tuple[str, str, int]] = []
    for block in file_blocks(text):
        if block.kind == "planned":
            continue
        for path, _col in block.paths:
            if not (root / path).exists():
                out.append((block.section, path, block.line))
    return out


def unmarked_planned_blocks(text: str) -> list[tuple[str, int]]:
    """Planned-file blocks that live in a section that does not declare a plan."""
    plans = {s.ident for s in sections(text) if is_plan(s)}
    return [
        (block.section, block.line)
        for block in file_blocks(text)
        if block.kind == "planned" and block.section not in plans
    ]


def plans_carrying_a_passed_gate(text: str) -> list[str]:
    """Plan-marked sections that still carry a ``**质量门**`` block."""
    return [
        s.ident
        for s in sections(text)
        if is_plan(s) and has_quality_gate(s)
    ]


def control_broken_paths(text: str) -> list[tuple[str, int]]:
    """Paths in a file list whose first character was eaten by a control character.

    Scoped to the FILE LISTS on purpose: that is where the ledger makes a
    claim about a file.  A tab-indented code block in prose is not a claim
    about a path, and charging it would make this ruler wider than the thing
    it measures.
    """
    out: list[tuple[str, int]] = []
    for block in file_blocks(text):
        for item_line, raw in block.items:
            for path, start, _end in paths_in(raw):
                if start > 0 and ord(raw[start - 1]) < 32:
                    out.append((path, item_line))
    return out


# ---------------------------------------------------------------------------
# the ledger
# ---------------------------------------------------------------------------

LEDGER_TEXT = LEDGER.read_text(encoding="utf-8")
BLOCKS = file_blocks(LEDGER_TEXT)
SECTIONS = sections(LEDGER_TEXT)


# ---------------------------------------------------------------------------
# L0  the lens itself must still see
# ---------------------------------------------------------------------------


def test_the_file_lists_were_found_and_parsed() -> None:
    """A collapsed parse must not read as "no violations".

    The parser is the ruler; if it stops finding the blocks, every rule below
    would pass vacuously.  The counts are floors well under the measurement
    (19 file lists, 119 paths) so they cannot rot with the ledger.
    """
    assert len(SECTIONS) >= 290, f"only {len(SECTIONS)} sections parsed"
    kinds = {block.kind for block in BLOCKS}
    assert "evidence" in kinds, f"no evidence block found: {kinds}"
    assert len(BLOCKS) >= 15, f"only {len(BLOCKS)} file lists found"
    assert sum(len(block.paths) for block in BLOCKS) >= 80, (
        f"only {sum(len(block.paths) for block in BLOCKS)} paths parsed"
    )


# ---------------------------------------------------------------------------
# L1  a record's evidence must be real
# ---------------------------------------------------------------------------


def test_every_evidence_file_exists() -> None:
    """The red this unit closes: 49 paths that never existed in any revision."""
    bad = missing_paths(LEDGER_TEXT, ROOT)
    assert not bad, (
        "these sections name files that are not in the tree, so their evidence "
        "claim is false:\n  "
        + "\n  ".join(f"#{sec}: {path} (block at line {line})" for sec, path, line in bad)
    )


def test_a_phantom_evidence_file_is_refused() -> None:
    """Reverse control: the ruler must be able to say no."""
    fragment = (
        "## #900 落地的某节\n\n"
        "**证据文件**：\n"
        "- craft/adapters/not_a_real_adapter.py（新增）\n"
    )
    bad = missing_paths(fragment, ROOT)
    assert bad == [("900", "craft/adapters/not_a_real_adapter.py", 3)], bad


def test_a_struck_through_path_is_not_a_claim() -> None:
    """A retracted path is not a claim — the ledger must be able to write
    down "that file never existed", which is exactly the correction #476
    had to make."""
    fragment = (
        "## #900 落地的某节\n\n"
        "**证据文件**：\n"
        "- ~~`agent/never_existed.py` 从未存在~~\n"
        "- `craft/adapters/protocol.py`\n"
    )
    assert missing_paths(fragment, ROOT) == []


# ---------------------------------------------------------------------------
# L2  a plan must declare itself
# ---------------------------------------------------------------------------


def test_a_planned_file_list_only_lives_in_a_marked_plan_section() -> None:
    """A plan that does not say it is a plan is a record in disguise."""
    bad = unmarked_planned_blocks(LEDGER_TEXT)
    assert not bad, (
        "these sections list files they plan to create but do not declare "
        "themselves plans:\n  "
        + "\n  ".join(f"#{sec} (block at line {line})" for sec, line in bad)
    )


def test_an_unmarked_planned_file_list_is_refused() -> None:
    """Reverse control."""
    fragment = (
        "## #900 落地的某节\n\n"
        "**拟新增文件**：\n"
        "- craft/adapters/not_a_real_adapter.py\n"
    )
    assert unmarked_planned_blocks(fragment) == [("900", 3)]


def test_a_marked_plan_section_may_carry_a_planned_file_list() -> None:
    """The exemption itself, exercised: a marked plan is allowed."""
    fragment = (
        "## #900 计划中的某节\n"
        f"{PLAN_MARK}\n\n"
        "**拟新增文件**：\n"
        "- craft/adapters/not_a_real_adapter.py\n"
    )
    assert unmarked_planned_blocks(fragment) == []


# ---------------------------------------------------------------------------
# L3  a plan has no passed gate
# ---------------------------------------------------------------------------


def test_a_plan_section_does_not_carry_a_passing_quality_gate() -> None:
    """"ruff + mypy 全绿" is a claim about work that ran. A plan has none."""
    bad = plans_carrying_a_passed_gate(LEDGER_TEXT)
    assert not bad, (
        f"these plan sections still carry a {QUALITY_GATE} block, which reads "
        f"as a gate that passed: {bad}"
    )


def test_a_plan_section_with_a_quality_gate_is_refused() -> None:
    """Reverse control."""
    fragment = (
        "## #900 计划中的某节\n"
        f"{PLAN_MARK}\n\n"
        f"{QUALITY_GATE}\n"
        "- ruff + mypy 全绿\n"
    )
    assert plans_carrying_a_passed_gate(fragment) == ["900"]


# ---------------------------------------------------------------------------
# L4  a path may not be broken by a control character
# ---------------------------------------------------------------------------


def test_no_path_is_broken_by_a_control_character() -> None:
    """The TAB class: one letter of one path replaced, and the path stops
    resolving.  The whole ledger holds 5 TAB characters and every one of them
    is one of these lines."""
    bad = control_broken_paths(LEDGER_TEXT)
    assert not bad, (
        "these paths are preceded by a control character (a TAB ate the first "
        "letter):\n  " + "\n  ".join(f"{path} (line {line})" for path, line in bad)
    )


def test_a_tab_broken_path_is_refused() -> None:
    """Reverse control, with the exact shape the ledger shipped."""
    fragment = (
        "## #900\n\n"
        "**证据文件**：\n"
        "- \tests/unit/test_adapter_protocol.py（协议测试持续通过）\n"
    )
    bad = control_broken_paths(fragment)
    # the path is reported AS PARSED: the TAB already ate the 't', so the
    # token the ruler sees is the broken one, not the intended one.
    assert bad == [("ests/unit/test_adapter_protocol.py", 4)], bad


def test_the_plan_marker_is_one_exact_string() -> None:
    """The marker is load-bearing, so it may not be a family of spellings.

    A gate that accepted "计划" / "（未落地）" / "PLAN" would be a gate that
    accepts a plan's ADJECTIVE instead of its DECLARATION.
    """
    fragment = "## #900\n\n**状态**：计划\n\n**拟新增文件**：\n- a/b.py\n"
    assert unmarked_planned_blocks(fragment) == [("900", 5)], (
        "a near-miss spelling of the plan marker was accepted as a plan"
    )
