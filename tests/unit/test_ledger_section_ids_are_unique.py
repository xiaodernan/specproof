"""The ledger's section ids must be unique: a number naming two units makes
every reference to it undecidable.

This is the project's own long-standing queue item. #275 measured it and
queued it; #276, #277, #278, #280, #281, #282, #284, #285 and #286 each
carried the item forward in their "下一号队列" block, and the ledger text
repeats the defect seven times. This unit closes it.

MEASURED BEFORE WRITING (probes: .scratch/probe287b_corrected_ledger_measurement.py
and .scratch/probe287_classify_references.py; the numbers below are theirs, not
estimates):

  112 `## #` sections, 109 distinct id tokens
  3 id tokens used twice: #144, #145, #246
  4 ids already carry an explicit suffix — the legal pattern the ledger
  already uses:
      #173-1, #173-2   one unit, two sub-units
      #241,  #241b     one unit, backend half / frontend half
      #254,  #254b     one unit, capture half / verdict half
  80 prose lines name one of the three reused numbers
  #246's references carry THREE different referents, which is why a cheap
  renumber was not possible:
      the eval-tolerance unit  — 9 lines, including #247's
        "另一车道已修容错（#246，提交 fed32e0）"
      the case-17 reading unit  — 4 lines, all inside its own section
      the roadmap queue reservations ("roadmap 2.6 / 3.1") — 4 lines
  so "见 #246" could mean three different things, and the ledger's own rule
  ("禁止一个新节复用另一单元已经用过的号（配方/落地同号要显式带后缀）") was
  already broken by three units.

The rule this gate enforces, and the rule the ledger states for itself:

  L1  every `## #<id>` id token is unique;
  L2  a numeric family carries AT MOST ONE bare id — so a bare number always
      resolves to exactly one unit. This is the condition that makes a
      reference decidable; the suffix form already in the ledger satisfies it
      because the bare id stays with the first half;
  L3  a family's suffixes are distinct;
  L4  every section carries a non-empty title — the registry needs a name, and
      a header without one cannot be resolved to a unit;
  L5  document order follows the numbering: a suffixed id comes AFTER its
      family's bare id, so a reader meets "#241" before "#241b".

(A first draft of L5 read "the highest number belongs to exactly one
section". It was wrong: it fired on the ledger's own legal "#241" / "#241b"
shape, and the synthetic control caught it before the ledger did. The rule
was replaced, not weakened — a gate that rejects the project's own
precedent is a gate with a bug in it.)

The fix, in the ledger (six lines, each anchored on an exact string):
  #144 recipe keeps `## #144`; its landing becomes `## #144b`
  #145 recipe keeps `## #145`; its landing becomes `## #145b`
  #246 eval-tolerance keeps `## #246`; the case-17 reading becomes `## #246b`
Bare-id choice is measured, not guessed: every prose reference to #144/#145
means the RECIPE (its landing's own text says "§#144 配方里那句…"), and #246's
largest referent cluster is the tolerance unit ("另一车道已修容错（#246，
提交 fed32e0）"). So in each family the bare id goes to the unit the prose
means, and the other half takes the ledger's own `b` suffix shape.

A gate nobody has seen red is not a gate, so the arms are in
.scratch/arm287_ledger_id_arms.py, and the synthetic reverse controls below
pin the parser itself (an id token is digits + suffix up to the first
whitespace: `## #241b` is the id "241b", NOT the id "241" with a title
starting "b").
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
#: The ledger the gate reads. Overridable so the mutation arms can run
#: against a COPY: this ledger is a shared work tree that other lanes append
#: to, and an arm that mutated the live file would risk clobbering their
#: section (or being clobbered by it). The arms therefore copy the bytes,
#: mutate the copy, and point the gate at it — the same bytes, one mutation.
LEDGER = Path(
    os.environ.get(
        "SPECPROOF_LEDGER_PATH",
        ROOT / "docs" / "operations" / "DEEP_OPTIMIZATION_PLAN.md",
    )
)

#: `## #<id><whitespace><title>` — the id token is digits plus an optional
#: letter/dash suffix, and it ends at the first whitespace. `## #241b 网页…`
#: is therefore the id "241b" and not the id "241" with the title "b 网页…".
HEAD = re.compile(r"^## #([0-9]+[A-Za-z0-9\-]*)[ \t]+(.*)$", re.M)
#: A suffix may be a letter run or a dash-number, never a dash alone.
SUFFIX = re.compile(r"^([0-9]+)([A-Za-z][A-Za-z0-9]*|-[0-9]+)?$")


class Section:
    """One `## #<id>` heading of the ledger."""

    __slots__ = ("ident", "title", "line")

    def __init__(self, ident: str, title: str, line: int) -> None:
        self.ident = ident
        self.title = title
        self.line = line

    @property
    def number(self) -> str:
        return SUFFIX.match(self.ident).group(1)  # type: ignore[union-attr]

    @property
    def suffix(self) -> str:
        return SUFFIX.match(self.ident).group(2) or ""  # type: ignore[union-attr]

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"Section(#{self.ident}, line {self.line}, {self.title[:40]!r})"


def parse_sections(text: str) -> list[Section]:
    """Every `## #<id>` heading, in document order."""
    out: list[Section] = []
    for m in HEAD.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        out.append(Section(m.group(1), m.group(2).strip(), line))
    return out


def find_violations(sections: list[Section]) -> list[str]:
    """Every rule violation, as a human-readable line. Empty means clean."""
    problems: list[str] = []

    # L1 — the id token itself is unique.
    by_ident: dict[str, list[Section]] = defaultdict(list)
    for s in sections:
        by_ident[s.ident].append(s)
    for ident, group in sorted(
        by_ident.items(),
        key=lambda kv: (int(re.match(r"[0-9]+", kv[0]).group(0)), kv[0]),
    ):
        if len(group) > 1:
            where = ", ".join(f"line {s.line} «{s.title[:40]}»" for s in group)
            problems.append(
                f"L1: id #{ident} is used {len(group)}x — a reference to it "
                f"cannot be resolved: {where}"
            )

    # L2/L3 — one bare id per family, distinct suffixes.
    families: dict[str, list[Section]] = defaultdict(list)
    for s in sections:
        families[s.number].append(s)
    for number, group in sorted(families.items(), key=lambda kv: int(kv[0])):
        bare = [s for s in group if not s.suffix]
        if len(bare) > 1:
            where = ", ".join(f"line {s.line} «{s.title[:40]}»" for s in bare)
            problems.append(
                f"L2: number #{number} has {len(bare)} bare sections — a bare "
                f"number must name exactly one unit: {where}"
            )
        suffixes = [s.suffix for s in group if s.suffix]
        if len(suffixes) != len(set(suffixes)):
            problems.append(
                f"L3: number #{number} repeats a suffix among {sorted(suffixes)}"
            )

    # L4 — a section needs a name to be resolvable to.
    for s in sections:
        if not s.title:
            problems.append(
                f"L4: section #{s.ident} at line {s.line} has no title — "
                "the registry cannot name the unit"
            )

    # L5 — document order follows the numbering: a suffixed id comes AFTER
    # its family's bare id, so a reader meets "#241" before "#241b". A family
    # with no bare id (the ledger's own "#173-1" / "#173-2") is unconstrained
    # by this rule — there is no bare id to precede.
    for number, group in sorted(families.items(), key=lambda kv: int(kv[0])):
        bare = [s for s in group if not s.suffix]
        suffixed = [s for s in group if s.suffix]
        if not bare or not suffixed:
            continue
        first_bare = min(s.line for s in bare)
        for s in suffixed:
            if s.line < first_bare:
                problems.append(
                    f"L5: #{s.ident} (line {s.line}) precedes its family's "
                    f"bare #{number} (line {first_bare}) — the document order "
                    "must follow the numbering"
                )

    return problems


# --------------------------------------------------------------------------
# the real ledger
# --------------------------------------------------------------------------

LEDGER_TEXT = LEDGER.read_text(encoding="utf-8")
SECTIONS = parse_sections(LEDGER_TEXT)


def test_the_ledger_was_actually_parsed() -> None:
    """A collapsed parse must not read as "no violations"."""
    assert len(SECTIONS) >= 100, (
        f"only {len(SECTIONS)} sections parsed — the lens changed shape "
        f"({len(LEDGER_TEXT)} bytes of ledger)"
    )
    # The id token runs to the first whitespace: a bare number plus an
    # optional suffix, never a title glued to the digits.
    assert any(s.ident.endswith("b") for s in SECTIONS), (
        "no '#<n>b' id parsed — the suffix form stopped being recognised"
    )
    assert all(SUFFIX.match(s.ident) for s in SECTIONS), (
        "an id token did not match digits+[suffix] — the parser drifted"
    )


def test_no_section_id_is_used_twice() -> None:
    """L1 — the defect this unit exists to close."""
    problems = find_violations(SECTIONS)
    assert not problems, (
        "the ledger's section ids are not unique:\n  " + "\n  ".join(problems)
    )


def test_a_bare_number_always_names_exactly_one_unit() -> None:
    """L2 — what makes "见 #246" decidable."""
    families: dict[str, list[Section]] = defaultdict(list)
    for s in SECTIONS:
        families[s.number].append(s)
    for number, group in sorted(families.items(), key=lambda kv: int(kv[0])):
        bare = [s for s in group if not s.suffix]
        assert len(bare) <= 1, (
            f"#{number} has {len(bare)} bare sections — a bare number must "
            f"name one unit: "
            + ", ".join(f"line {s.line} «{s.title[:40]}»" for s in bare)
        )


def test_every_section_can_be_named() -> None:
    """L4 — the registry needs a title for each unit."""
    unnamed = [s for s in SECTIONS if not s.title]
    assert not unnamed, (
        "sections without a title: "
        + ", ".join(f"#{s.ident} (line {s.line})" for s in unnamed)
    )


def test_the_next_unit_number_is_max_plus_one() -> None:
    """L5 — the document order must follow the numbering.

    The ledger's own shapes are the witnesses: #241 precedes #241b, #254
    precedes #254b, #144 precedes #144b. A reader who meets "#144b" before
    "#144" has no anchor for the family.
    """
    families: dict[str, list[Section]] = defaultdict(list)
    for s in SECTIONS:
        families[s.number].append(s)
    for number, group in sorted(families.items(), key=lambda kv: int(kv[0])):
        bare = [s for s in group if not s.suffix]
        suffixed = [s for s in group if s.suffix]
        if not bare or not suffixed:
            continue
        first_bare = min(s.line for s in bare)
        for s in suffixed:
            assert s.line > first_bare, (
                f"#{s.ident} (line {s.line}) precedes its family's bare "
                f"#{number} (line {first_bare})"
            )


# --------------------------------------------------------------------------
# reverse controls on synthetic input — the parser, not just the ledger
# --------------------------------------------------------------------------


def test_a_duplicated_id_is_detected() -> None:
    fragment = "## #12 first unit\nbody\n\n## #12 second unit\n"
    problems = find_violations(parse_sections(fragment))
    assert any("L1" in p for p in problems), problems
    assert any("L2" in p for p in problems), problems


def test_a_suffixed_id_is_its_own_id_not_a_prefix_match() -> None:
    """`## #241b` is the id "241b" — not "241" with a title starting "b"."""
    fragment = "## #241 backend half\n\n## #241b frontend half\n"
    sections = parse_sections(fragment)
    assert [s.ident for s in sections] == ["241", "241b"], [s.ident for s in sections]
    assert [s.number for s in sections] == ["241", "241"]
    assert [s.suffix for s in sections] == ["", "b"]
    # one bare id in the family: the legal shape, so no violation
    assert not find_violations(sections)


def test_a_family_with_two_bare_sections_is_rejected_even_with_a_suffixed_one() -> None:
    fragment = "## #7 one\n\n## #7 two\n\n## #7b three\n"
    problems = find_violations(parse_sections(fragment))
    assert any("L2" in p for p in problems), problems


def test_a_section_without_a_title_is_rejected() -> None:
    problems = find_violations(parse_sections("## #9 \n"))
    assert any("L4" in p for p in problems), problems


def test_a_suffixed_id_before_its_bare_id_is_rejected() -> None:
    """Document order must follow the numbering."""
    fragment = "## #241b frontend half\n\n## #241 backend half\n"
    problems = find_violations(parse_sections(fragment))
    assert any("L5" in p for p in problems), problems


def test_a_family_with_no_bare_id_is_unconstrained_by_the_ordering_rule() -> None:
    """The ledger's own #173-1 / #173-2 shape: no bare id to precede."""
    fragment = "## #173-2 second\n\n## #173-1 first\n"
    assert find_violations(parse_sections(fragment)) == []


def test_a_clean_ledger_fragment_produces_no_violation() -> None:
    fragment = (
        "## #1 alpha\n\n## #2 beta\n\n## #3 gamma\n\n"
        "## #3-1 gamma first half\n\n## #3-2 gamma second half\n"
    )
    assert find_violations(parse_sections(fragment)) == []
