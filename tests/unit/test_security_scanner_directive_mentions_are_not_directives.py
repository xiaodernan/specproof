"""A line that MENTIONS the directive must not silence anything.

#453's boundary ⑤ was explicit: the mechanism's regex finds the marker at
end of line, so a whole-line comment or a document that quotes the directive
form was parsed as a suppression, and only the ledger's own heading had been
reworded by hand. This batch measured that on planted shapes: a mention in a
code
span, a mention with trailing prose — each hid a real CRITICAL finding,
exactly like a line that *uses* the directive.

The fix is in the mechanism: a directive names WHOLE pattern names, and a tail
that is anything else is malformed, and a malformed directive silences
nothing. This file pins that behaviour on planted shapes, pins the one case
the mechanism provably cannot tell apart, and censuses the tree so that a
mention written into a scannable file cannot hide there either.

**The irreducible case.** A line whose prose mentions the form and then ends
with a whole pattern name is the same shape as a line that uses the directive:
the mechanism has no way to read intent from the prose in front of the marker.
`test_the_boundary_a_prose_mention_with_a_whole_name_still_silences` pins that
boundary so it cannot change by accident — a future fix has to update it.

This module's name contains ``security_scanner`` on purpose: the no-leak gates
(``tests/security/test_no_key_leak.py``, ``tests/security/test_no_secrets.py``)
skip files whose path contains that string, because a file that talks about
secret patterns legitimately contains secret-shaped strings.
"""
from __future__ import annotations

from pathlib import Path

from agent.security_scanner import (
    _NOSEC_RE,
    _directive_names,
    _should_exclude,
    _walk_scannable,
    scan_directory,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: Runtime-built, so this file does not itself hold a secret-shaped literal.
_FAKE_KEY = "sk-" + "a" * 40

#: A line that fires exactly one pattern ("OpenAI/LLM API Key").
_ONE_PATTERN_LINE = f'token = "{_FAKE_KEY}"'

#: A line that fires two patterns ("OpenAI/LLM API Key" and "API Key Assignment").
_TWO_PATTERN_LINE = f'api_key = "{_FAKE_KEY}"'

#: The marker text, without the leading ``#`` the mechanism requires — so the
#: prose of this file is never itself a directive.
_MARKER = "specproof-nosec"


def _old_suppressed(line: str, pattern_name: str) -> bool:
    """The rule the mechanism used before this change: the name appears in the tail.

    Kept here as the control that says the planted shapes really were
    dangerous: under this rule a mention that quoted the form silenced the
    finding just like a use did.
    """
    m = _NOSEC_RE.search(line)
    return m is not None and pattern_name in m.group("names")


def _plant(directory: Path, body: str) -> list[str]:
    """Scan a directory holding one file and return the reported pattern names."""
    (directory / "planted.yml").write_text(body, encoding="utf-8")
    result = scan_directory(str(directory))
    return [f.pattern_name for f in result.findings]


#: Every planted mention, with whether the pre-change rule silenced it.
#:
#: "True" — the old rule hid the finding, so the shape is what the fix is for.
#: "False" — the old rule left it standing too; the shape is here so that the
#:          rule keeps its behaviour on the tails that were always inert.
_MENTIONS: tuple[tuple[str, str, bool], ...] = (
    (
        "codespan_at_eol",
        f'{_ONE_PATTERN_LINE}  // see `# {_MARKER} OpenAI/LLM API Key`\n',
        True,
    ),
    (
        "codespan_midline",
        f'{_ONE_PATTERN_LINE}  // see `# {_MARKER} OpenAI/LLM API Key` for details\n',
        True,
    ),
    (
        "trailing_prose",
        f"{_ONE_PATTERN_LINE}  // fixture # {_MARKER} OpenAI/LLM API Key (a test value)\n",
        True,
    ),
    (
        "placeholder",
        f"{_ONE_PATTERN_LINE}  // the form is # {_MARKER} <pattern name>\n",
        False,
    ),
)


def test_a_mention_of_the_directive_leaves_the_finding_standing(tmp_path: Path) -> None:
    """A line that only mentions the mechanism must not silence the finding."""
    for label, body, _silenced_before in _MENTIONS:
        target = tmp_path / label
        target.mkdir()
        assert _plant(target, body) == ["OpenAI/LLM API Key"], (
            f"the {label} shape silenced a CRITICAL finding"
        )


def test_the_old_rule_silenced_the_planted_mentions_that_now_do_not() -> None:
    """The control: the shapes the fix acts on really were dangerous.

    Without this, the leg above could be green for the wrong reason — e.g. if
    the planted secret stopped firing and the scan reported nothing at all.
    """
    for label, body, silenced_before in _MENTIONS:
        line = body.rstrip("\n")
        assert _old_suppressed(line, "OpenAI/LLM API Key") is silenced_before, (
            f"the {label} shape does not behave as this file claims it did "
            "under the pre-change rule"
        )


def test_a_use_that_names_the_whole_pattern_still_silences(tmp_path: Path) -> None:
    """The control: the real thing keeps working."""
    body = f"{_ONE_PATTERN_LINE}  // test fixture value # {_MARKER} OpenAI/LLM API Key\n"
    assert _plant(tmp_path, body) == []


def test_a_directive_naming_one_of_two_firing_patterns_silences_only_that_one(
    tmp_path: Path,
) -> None:
    """Naming is scoped to the named pattern — the other one still reports."""
    body = f"{_TWO_PATTERN_LINE}  // test fixture value # {_MARKER} OpenAI/LLM API Key\n"
    assert _plant(tmp_path, body) == ["API Key Assignment"]


def test_a_directive_naming_two_whole_patterns_silences_both(tmp_path: Path) -> None:
    """Two whole names, space-separated — the contract the scoped gate pins."""
    body = (
        f"{_TWO_PATTERN_LINE}  // test fixture value # {_MARKER} "
        "OpenAI/LLM API Key API Key Assignment\n"
    )
    assert _plant(tmp_path, body) == []


def test_a_malformed_directive_silences_nothing(tmp_path: Path) -> None:
    """A bare directive, and one whose tail is not a whole name, hide nothing."""
    for label, body in (
        ("bare", f"{_ONE_PATTERN_LINE}  // # {_MARKER}\n"),
        ("trailing_prose", f"{_ONE_PATTERN_LINE}  // # {_MARKER} OpenAI/LLM API Key (x)\n"),
        ("unknown_name", f"{_ONE_PATTERN_LINE}  // # {_MARKER} No Such Pattern\n"),
        ("chinese_tail", f"{_ONE_PATTERN_LINE}  // # {_MARKER} 这是测试夹具不是真密钥\n"),
    ):
        target = tmp_path / label
        target.mkdir()
        assert _plant(target, body) == ["OpenAI/LLM API Key"], (
            f"the {label} directive silenced a finding it did not earn"
        )


def test_the_boundary_a_prose_mention_with_a_whole_name_still_silences(
    tmp_path: Path,
) -> None:
    """The irreducible case, pinned.

    This line is a *mention* — its prose is about the mechanism — but it ends
    with a whole pattern name, which is the same shape a real directive has.
    The mechanism reads the tail, not the intent, so it silences. Nothing in
    the line-level contract can separate the two; a future fix has to change
    the shape of the directive itself, and must update this leg when it does.
    """
    body = f"{_ONE_PATTERN_LINE}  // the form is # {_MARKER} OpenAI/LLM API Key\n"
    assert _plant(tmp_path, body) == []


def test_the_parser_accepts_only_whole_pattern_names() -> None:
    """The rule, stated on the parser rather than on a scan."""
    assert _directive_names(f"x # {_MARKER} OpenAI/LLM API Key") == ("OpenAI/LLM API Key",)
    assert _directive_names(f"x # {_MARKER} API Key Assignment") == ("API Key Assignment",)
    assert _directive_names(
        f"x # {_MARKER} OpenAI/LLM API Key, Bearer Token"
    ) == ("OpenAI/LLM API Key", "Bearer Token")
    assert _directive_names(
        f"x # {_MARKER} OpenAI/LLM API Key Bearer Token"
    ) == ("OpenAI/LLM API Key", "Bearer Token")
    # longest match wins: "GitHub Classic Token" is not "GitHub PAT" plus text
    assert _directive_names(f"x # {_MARKER} GitHub Classic Token") == (
        "GitHub Classic Token",
    )
    # anything that is not a whole name makes the whole directive malformed
    for tail in (
        "",
        "   ",
        "<pattern name>",
        "OpenAI/LLM API Key (a fixture)",
        "OpenAI/LLM API Key`",
        "No Such Pattern",
        "OpenAI/LLM API Key, No Such Pattern",
    ):
        assert _directive_names(f"x # {_MARKER} {tail}") == (), (
            f"the tail {tail!r} was accepted as a directive"
        )


# ── the tree census ──────────────────────────────────────────────────────────


def _marker_lines() -> list[tuple[str, int, str]]:
    """Every line in a file the scanner reads that carries the marker text."""
    found: list[tuple[str, int, str]] = []
    for rel, path in _walk_scannable(PROJECT_ROOT):
        if _should_exclude(rel):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError, OSError):
            continue
        for lineno, line in enumerate(content.splitlines(), 1):
            if _MARKER in line:
                found.append((rel, lineno, line))
    return found


def _malformed(lines: list[tuple[str, int, str]]) -> list[tuple[str, int, str]]:
    """The lines the mechanism would read as a directive but cannot parse."""
    return [
        (rel, lineno, line)
        for rel, lineno, line in lines
        if _NOSEC_RE.search(line) and not _directive_names(line)
    ]


_MARKER_LINES = _marker_lines()


def test_the_census_sees_the_tree() -> None:
    """Non-vacuity: the walk found the marker, in files the scanner reads."""
    assert _MARKER_LINES, (
        f"no line carrying {_MARKER} found under {PROJECT_ROOT}; the walk is "
        "over-pruning, so a clean census would mean nothing"
    )
    assert any(_NOSEC_RE.search(line) for _rel, _n, line in _MARKER_LINES), (
        "no located directive in the tree — the census has nothing to judge"
    )


def test_the_census_can_still_see_the_shape_it_forbids() -> None:
    """Anti-vacuity: the census must flag a malformed located marker line."""
    planted_bad = [
        ("planted.md", 1, f'{_ONE_PATTERN_LINE}  // see `# {_MARKER} OpenAI/LLM API Key`'),
    ]
    planted_good = [
        ("planted.md", 1, f"{_ONE_PATTERN_LINE}  // fixture # {_MARKER} OpenAI/LLM API Key"),
    ]
    assert _malformed(planted_bad) == planted_bad
    assert _malformed(planted_good) == []


def test_no_located_marker_line_in_the_tree_is_malformed() -> None:
    """A mention written into a scannable file must not read as a directive.

    The mechanism now ignores a malformed directive, so a mention in the tree
    is harmless — but it is still a line that looks like a suppression, which
    is how a reviewer is misled. This census says: in this repo the marker
    only ever appears in a shape the mechanism can parse.
    """
    malformed = _malformed(_MARKER_LINES)
    assert malformed == [], "\n".join(
        f"  {rel}:{lineno} — {line.strip()[:120]}" for rel, lineno, line in malformed
    )
