"""Gate: every metric name the ops docs show a reader must exist (#305).

OBSERVABILITY.md and RUNBOOK.md are the documents an on-call reader follows
into Grafana, a scrape or an alert. They name metrics in prose, in table cells
and in code spans — 123 mentions / 95 unique names measured before this test
existed. Nothing checked those names. #161 (repaired by #296) accounts the
names CODE reads; #217 accounts section 8.10's FILE inventory. The names in the
rest of the same two docs were still free text: a reader told to plot
``specproof_findings_attribution_compared`` waits for a series that never
appears, because the emitter writes
``incr("findings_attribution_compared_total")``
(agent/nodes/review_court.py:392).

Measured at #305, of those 123 mentions: 62 counter / 23 gauge / 11 histogram /
5 concatenated-family / 11 family stems named by their prefix (10 unique stems)
— and 11 that accounted to nothing. Ten of those eleven are not metrics at all
(a Grafana 口令 and MySQL database names, which share the ``specproof_``
shape); the eleventh is the real defect, and it is a doc bug this commit also
fixes: OBSERVABILITY.md:142 compressed three sibling counters into
``specproof_findings_attribution_compared/kept/rejected_total``, so only the
first name is even a token, and it is a dead one.

The floors below are read off the SAME census AFTER that repair, not off the
pre-fix numbers: 126 mentions / 98 unique names, 12 placeholder mentions over
11 stems, 10 exempted non-metric mentions, and 83 documented names that
account only after the prefix strip.

Two design decisions the legs below pin down:

* The docs name metrics the way ``/metrics`` renders them, with the
  ``specproof_`` prefix that observability/metrics.py:120-138 adds at
  exposition time; the emission calls carry no prefix. Comparing the two
  planes therefore means stripping exactly that prefix — leg
  ``test_the_two_planes_differ_by_the_prefix_alone`` witnesses that this is the
  only difference, so the strip cannot silently become wrong.
* The population is every ``specproof_*`` token, unconditionally. Narrowing it
  by name shape would have dropped the defect above (it has no ``_total``
  suffix). So the non-metric spellings go through an exemption table keyed on
  identity — (document, name) plus a proof token that must sit on the very
  line making the claim — never on the name alone.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import TypedDict

from tests.unit.test_observability_metric_parity import (
    CONCATENATED_FAMILIES,
    ROOT,
    _emitted_names,
    account_name,
    concatenated_prefix_types,
)

DOC_DIR = ROOT / "docs" / "operations"
DOCS = ("OBSERVABILITY.md", "RUNBOOK.md")

#: What observability/metrics.py prepends when it renders the exposition.
PREFIX = "specproof_"

#: A reader-facing metric name in these documents.
DOC_NAME = re.compile(r"specproof_([a-z0-9_]+)")

#: ``specproof_a_total/b_total`` — the compression a table cell falls into when
#: sibling names share a suffix. The tails carry no prefix, so DOC_NAME never
#: sees them and a half-dead name would read as fine; this clause refuses the
#: spelling itself.
COMPRESSED = re.compile(r"specproof_[a-z0-9_]*(?:/[a-z0-9_]+)+")

#: Spellings that share the ``specproof_`` shape but are not metrics: a Grafana
#: admin口令 and MySQL database names. Each entry is keyed on identity AND
#: carries proof tokens — at least one must appear on every line that uses the
#: spelling, so the exemption cannot be inherited by a new, unrelated mention.
NOT_METRICS: dict[tuple[str, str], tuple[str, ...]] = {
    ("OBSERVABILITY.md", "admin"): ("ADMIN_PASSWORD",),
    ("RUNBOOK.md", "pass"): ("compose.production.yml",),
    ("RUNBOOK.md", "phase0"): ("MYSQL_DATABASE", "mysqldump", "conftest"),
    ("RUNBOOK.md", "test"): ("MYSQL_DATABASE", "CREATE/GRANT"),
}


class Mention(TypedDict):
    doc: str
    line: int
    name: str
    account: str
    clause: str


@lru_cache(maxsize=1)
def _mentions() -> tuple[Mention, ...]:
    found: list[Mention] = []
    for doc in DOCS:
        path = DOC_DIR / doc
        assert path.is_file(), f"{doc} moved — the census population is broken"
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for name in DOC_NAME.findall(line):
                found.append(
                    Mention(
                        doc=doc,
                        line=no,
                        name=name,
                        account=account_name(name),
                        clause=line.strip(),
                    )
                )
    return tuple(found)


def _exemption_proof(m: Mention) -> str | None:
    """The proof token that witnesses this mention as a non-metric spelling."""
    proofs = NOT_METRICS.get((m["doc"], m["name"]))
    if proofs is None:
        return None
    return next((proof for proof in proofs if proof in m["clause"]), None)


#: First character that stops a regex from naming a fixed literal prefix.
_REGEX_BREAK = re.compile(r"[\(\[\?\+\*\{\}\\]")


def _spelled_names() -> frozenset[str]:
    """Every spelling an emission site can produce, names *and* family stems.

    ``_emitted_names()`` deliberately excludes runtime-concatenated names, so it
    cannot answer "does this family exist" — six of the docs' stems
    (``es_request_seconds_``, ``redis_request_seconds_``, ``tool_run_seconds_``,
    ``jobs_duration_seconds_``, ``capsule_replay_verdict_``,
    ``mcp_tool_errors_``) open families whose members are unlistable, and a leg
    reading only the literal census reports them as gone. The stems are taken
    from the parity gate's own two records of those families: the literal the
    concat call starts with, and the fixed prefix of each registered family
    regex — derived from its source, never hand-copied, so renaming a family
    moves this set with it.
    """
    from_call_sites = set(concatenated_prefix_types())
    from_patterns = {
        _REGEX_BREAK.split(pattern.pattern.lstrip("^"), 1)[0]
        for pattern, _ in CONCATENATED_FAMILIES.values()
    }
    return frozenset(_emitted_names() | from_call_sites | from_patterns)


def test_the_census_is_the_whole_document_pair() -> None:
    """A collapsed parse must not read as "nothing left to check"."""
    mentions = _mentions()
    assert len(mentions) >= 100, (
        f"only {len(mentions)} specproof_* mentions found across {DOCS}; "
        "the #305 measurement is 126 — if the token shape or a document moved, "
        "fix the census, do not let a short parse certify the docs"
    )
    assert len({m["name"] for m in mentions}) >= 80, (
        f"only {len({m['name'] for m in mentions})} unique names; the #305 "
        "measurement is 98"
    )


def test_every_documented_metric_name_traces_to_an_emission_site() -> None:
    """Each name is one the code can actually put on /metrics."""
    dead = [m for m in _mentions() if m["account"] == "unaccounted" and _exemption_proof(m) is None]
    assert not dead, (
        "the ops docs name metric(s) no emission site produces — a reader "
        "following them gets an empty panel; fix the name, or wire the meter: "
        + ", ".join(f"{m['doc']}:{m['line']} {PREFIX}{m['name']}" for m in dead)
    )


def test_no_metric_name_is_written_by_dropping_a_sibling() -> None:
    """``a/b_total`` compression is a doc defect, not a shorthand to allow."""
    hits = [
        (m["doc"], m["line"], match)
        for m in _mentions()
        for match in COMPRESSED.findall(m["clause"])
    ]
    assert not hits, (
        "a slash-compressed name hides every sibling behind the first token, "
        "which is the one shape this gate cannot vouch for; write each full "
        f"name: {hits}"
    )


def test_family_stems_named_in_the_docs_prefix_a_real_emission() -> None:
    """A stem ending in ``_`` is legal only as the prefix of names that exist.

    account_name() calls these "placeholder" — the same class the code plane
    uses for an unwritten constant. In prose they are a family ("判定族"), so
    the honest reading is: some spelling the code can produce must start with
    the stem.
    """
    spelled = _spelled_names()
    stems = [m for m in _mentions() if m["account"] == "placeholder"]
    assert len(stems) >= 8, (
        f"only {len(stems)} family-stem mentions in the docs; the #305 "
        "measurement is 12 — the clause below is vacuous if this population "
        "collapsed"
    )
    unsupported = sorted(
        {m["name"] for m in stems if not any(name.startswith(m["name"]) for name in spelled)}
    )
    assert not unsupported, (
        "a family stem in the docs prefixes no emitted name or registered "
        f"family — the family is gone or the stem is a typo: {unsupported}"
    )


def test_the_two_planes_differ_by_the_prefix_alone() -> None:
    """The strip is the comparison, and it is the only difference.

    Reverse control for the one design decision that could quietly invert: the
    docs quote the exposition plane, the emission calls carry no prefix
    (observability/metrics.py:118-138 adds ``specproof_`` only when rendering),
    so accounting a documented name means stripping exactly that prefix. Both
    halves are pinned: the strip must be NECESSARY (documented names account
    bare) and SUFFICIENT (nothing in the code plane is written with the prefix,
    so keeping it could never match).
    """
    names = {m["name"] for m in _mentions() if m["account"] != "placeholder"}
    bare_only = sorted(
        n
        for n in names
        if account_name(n) != "unaccounted" and account_name(PREFIX + n) == "unaccounted"
    )
    assert len(bare_only) >= 75, (
        f"only {len(bare_only)} documented names account to an emission site "
        "after the prefix strip; the #305 measurement is 83 — either the docs "
        "or metrics.py changed its naming plane"
    )
    prefixed = sorted(n for n in names if account_name(PREFIX + n) != "unaccounted")
    assert not prefixed, (
        "a documented name accounts WITH the prefix kept, i.e. the emission "
        f"itself is written as specproof_*: {prefixed}"
    )
    double = sorted(n for n in _spelled_names() if n.startswith(PREFIX))
    assert not double, (
        "an emission site spells a metric name with the exposition prefix in "
        "the source, so /metrics would render specproof_specproof_* and this "
        f"gate's strip would be wrong: {double}"
    )


def test_the_non_metric_exemptions_stay_narrow_and_used() -> None:
    """Three ways an exemption table rots, each refused here."""
    mentions = _mentions()
    spelled = _spelled_names()

    covers_a_real_metric = sorted(
        f"{doc}/{name}"
        for (doc, name) in NOT_METRICS
        if account_name(name) != "unaccounted" or any(s.startswith(name) for s in spelled)
    )
    assert not covers_a_real_metric, (
        "an exemption entry now names a metric the code emits — delete the "
        f"entry, it is no longer a non-metric spelling: {covers_a_real_metric}"
    )

    unproven = sorted(
        {f"{m['doc']}:{m['line']} {PREFIX}{m['name']}"
         for m in mentions
         if (m["doc"], m["name"]) in NOT_METRICS and _exemption_proof(m) is None}
    )
    assert not unproven, (
        "a line uses an exempted spelling without the proof token that makes it "
        "a credential or database name — the exemption did not travel with the "
        f"claim: {unproven}"
    )

    used = {(m["doc"], m["name"]) for m in mentions if _exemption_proof(m)}
    dead_entries = sorted(str(key) for key in NOT_METRICS if key not in used)
    assert not dead_entries, (
        "exemption entries no document still uses — an unearned skip list is a "
        f"hiding place: {dead_entries}"
    )
