"""The relaxed anchor must find the same spans, and must not re-normalize
the file for every window.

#1616 changed the scan in ``craft/editor.py::_relaxed_ws_anchor`` from
"normalize every window's lines" to "normalize the file's lines once, then
compare windows". The behaviour has to be identical -- the anchor decides
WHERE an edit lands, so a different answer is a different edit.

Two legs:
  * equivalence against a reference implementation of the old shape, over
    the cases that matter (exact, whitespace drift, several matches, the
    anchor at the end of the file, an anchor wider than the file, empty);
  * the cost shape: the number of normalizations is O(lines), not
    O(lines x width). That is asserted by COUNTING the calls (a timing
    assertion would be flaky and would say less).
"""

from __future__ import annotations

from typing import Any

import pytest

from craft import editor as editor_module
from craft.editor import _relaxed_ws_anchor


def _reference(text: str, old: str) -> tuple[int, int, int] | None:
    """The pre-#1616 shape: normalize every window, compare, count."""
    file_text = text.replace("\r\n", "\n")
    file_lines = file_text.split("\n")
    old_text = old.replace("\r\n", "\n")
    old_lines = old_text.split("\n")
    if old_lines and old_lines[-1] == "":
        old_lines.pop()
    if not old_lines:
        return None
    needle = [editor_module._normalize_ws_line(line) for line in old_lines]
    width = len(needle)
    occurrences = 0
    first_start = 0
    for start_index in range(len(file_lines) - width + 1):
        window = file_lines[start_index: start_index + width]
        if [editor_module._normalize_ws_line(line) for line in window] != needle:
            continue
        if occurrences == 0:
            first_start = start_index
        occurrences += 1
    if occurrences == 0:
        return None
    start_offset = len("\n".join(file_lines[:first_start]))
    if first_start > 0:
        start_offset += 1
    end_index = first_start + width
    end_offset = len("\n".join(file_lines[:end_index]))
    return start_offset, end_offset, occurrences


FILE = "\n".join(
    [
        "class Demo {",
        "    void run() {",
        "\t\tint value = 1;",
        "        int other = 2;",
        "    }",
        "}",
    ]
) + "\n"

CASES: list[tuple[str, str, str]] = [
    ("exact match", FILE, "        int other = 2;"),
    ("tab drift", FILE, "    \tint other = 2;"),
    ("trailing-space drift", FILE, "        int other = 2;   "),
    ("multi-line anchor", FILE, "    void run() {\n\t\tint value = 1;"),
    ("no match", FILE, "        int nowhere = 9;"),
    ("anchor at the end", FILE, "    }\n}"),
    ("wider than the file", FILE, "a\nb\nc\nd\ne\nf\ng\nh"),
    ("empty old", FILE, ""),
    ("single blank line", FILE, "\n"),
]


@pytest.mark.parametrize(("label", "text", "old"), CASES, ids=[c[0] for c in CASES])
def test_the_scan_finds_exactly_what_the_old_shape_found(
    label: str, text: str, old: str
) -> None:
    assert _relaxed_ws_anchor(text, old) == _reference(text, old), label


def test_several_matches_are_still_counted() -> None:
    text = "x = 1\nx = 1\nx = 1\n"
    # the span is the FIRST match ("x = 1" = 5 characters), the count is every
    # normalized match in the file
    assert _relaxed_ws_anchor(text, "x = 1") == (0, 5, 3)
    assert _relaxed_ws_anchor(text, "x = 1") == _reference(text, "x = 1")


def test_the_file_is_normalized_once_per_scan_not_once_per_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cost shape: O(lines) normalizations, not O(lines x width).

    Counted, not timed: a timing assertion is flaky on a shared box, and
    the call count IS the property (#1616).
    """
    lines = 400
    width = 20
    text = "\n".join(f"    int v_{i} = 1;" for i in range(lines)) + "\n"
    old = "\n".join(f"    int v_{i} = 1;" for i in range(lines - width, lines)) + "\n"

    calls = {"n": 0}
    original: Any = editor_module._normalize_ws_line

    def counting(line: str) -> str:
        calls["n"] += 1
        return original(line)

    monkeypatch.setattr(editor_module, "_normalize_ws_line", counting)
    result = _relaxed_ws_anchor(text, old)

    assert result is not None, "the anchor should have matched"
    # the old lines + the file's lines, and nothing per window
    assert calls["n"] <= lines + width + 2, (
        f"the scan normalized {calls['n']} times for {lines} lines and a "
        f"{width}-line anchor -- that is the O(lines x width) shape again"
    )
