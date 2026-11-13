"""The prefix/suffix trim on the text-diff path — and the identical-output proof.

`_text_diff` feeds Java (and every non-Python suffix) through
`difflib.SequenceMatcher`; without trimming, a localized change inside a big
file pays the matcher's superlinear cost over the whole file, equal ends
included. This file pins:

  * hunks for the common cases are exactly what the stock algorithm emits —
    verified by replaying the stock algorithm inline on randomized fixtures,
    not by re-deriving expectations by hand;
  * edge boundaries (all-equal, empty inner span, prefix-only trim);
  * the mode label stays "text" for Java sources.
"""

from __future__ import annotations

import difflib
import random

from craft.structured_diff import _trim_common_ends, compute_structured_diff


def _stock_text_diff(path: str, before_text: str, after_text: str) -> list[dict]:
    """The pre-trim algorithm, inline — the reference the trim must match."""
    before_lines = before_text.split("\n")
    after_lines = after_text.split("\n")
    matcher = difflib.SequenceMatcher(a=before_lines, b=after_lines)
    hunks = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        kind = {"delete": "delete_lines", "insert": "insert_lines",
                 "replace": "replace_lines"}[tag]
        hunks.append({"kind": kind,
                      "before": "\n".join(before_lines[i1:i2]),
                      "after": "\n".join(after_lines[j1:j2]),
                      "symbols": []})
    return hunks


def _text_hunks(result: dict) -> list[dict]:
    assert result["mode"] == "text"
    return result["hunks"]


def _java_body(n: int) -> list[str]:
    lines = []
    for i in range(n):
        lines.append(f"class Widget{i:04d} {{")
        lines.append(f"    int field{i:04d};")
        lines.append(f"}}")
    return lines


def test_all_equal_produces_no_hunks() -> None:
    result = compute_structured_diff("a\nb\nc\n", "a\nb\nc\n", "Widget.java")
    assert _text_hunks(result) == []


def test_prefix_and_suffix_are_trimmed() -> None:
    before = _java_body(200)
    after = before.copy()
    after[300] = "    int CHANGED;"
    b_lo, b_hi, a_lo, a_hi = _trim_common_ends(before, after)
    assert b_lo == a_lo == 300
    assert b_hi == a_hi == 301


def test_trimmed_matches_stock_on_randomized_localized_edits() -> None:
    rng = random.Random(20261113)
    base = _java_body(120)  # 360 lines
    for _ in range(30):
        after = list(base)
        start = rng.randrange(0, len(after) - 20)
        window = rng.randrange(1, 8)
        op = rng.choice(["insert", "modify", "delete"])
        if op == "insert":
            after[start:start] = [f"    // new-{start}-{k}" for k in range(window)]
        elif op == "modify":
            for k in range(window):
                after[start + k] = f"    int edited{k};"
        else:
            del after[start:start + window]
        btext, atext = "\n".join(base), "\n".join(after)
        assert _text_hunks(compute_structured_diff(btext, atext, "Widget.java")) == \
            _stock_text_diff("Widget.java", btext, atext)


def test_prefix_only_and_suffix_only_boundaries() -> None:
    before = _java_body(50)
    # head differs, the rest aligns: only the head span needs the matcher
    after = ["class NewHead {}"] + before[1:]
    assert _trim_common_ends(before, after) == (0, 1, 0, 1)
    # the tail differs: head trim reaches the final line
    after = before[:-1] + ["class NewTail {}"]
    b_lo, b_hi, a_lo, a_hi = _trim_common_ends(before, after)
    assert a_lo == b_lo == len(before) - 1
    assert b_hi == a_hi == len(before)


def test_empty_inputs_are_handled() -> None:
    assert compute_structured_diff("", "", "Widget.java")["hunks"] == []
    diff = compute_structured_diff("", "package demo;\n", "Widget.java")
    assert any(h["kind"] == "insert_lines" for h in _text_hunks(diff))
    diff = compute_structured_diff("package demo;\n", "", "Widget.java")
    assert any(h["kind"] == "delete_lines" for h in _text_hunks(diff))
