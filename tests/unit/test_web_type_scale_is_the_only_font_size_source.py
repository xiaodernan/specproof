"""Every font size in the web app comes from the type scale (#1624).

WHY. The app had **twenty** different font sizes typed straight into
six CSS files (209 declarations), spread from 8px to 34px, with sizes
that differ by a single pixel next to each other (15/16/17, 22/23/24).
That is what the eye reads as "this page was assembled rather than
designed": the hierarchy is not a hierarchy, it is a list of whatever
was typed last. A type scale turns the hierarchy into ten named steps,
so a size has to be *argued for* instead of typed in.

WHAT THIS MEASURES:

* every ``font-size`` declaration is a scale token (a ``clamp()`` is
  allowed to carry scale VALUES inside it -- the responsive hero sizes
  interpolate between two steps of the same ladder),
* every token the app uses is declared in the token file,
* the ladder has a bounded number of steps (a ratchet: it may not grow
  one step at a time),
* the steps ascend and are distinct.

The measurements are counts, and the gate prints the offending
declarations by file and line so a fix is one edit away.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web"
SRC = WEB / "src"
TOKENS = SRC / "theme" / "tokens.css"

#: The scale's steps, smallest first. The ratchet: a new step is a
#: design decision, not a side effect of one page's typography.
SCALE_STEPS = (
    "--text-2xs",
    "--text-xs",
    "--text-sm",
    "--text-md",
    "--text-lg",
    "--text-xl",
    "--text-2xl",
    "--text-3xl",
    "--text-4xl",
    "--text-display",
    "--text-hero",
)

CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT = re.compile(r"//[^\n]*")
#: A font-size declaration: either a token, a plain px, or a clamp().
FONT_SIZE = re.compile(r"(?<![-\w])font-size\s*:\s*([^;}\n]+)")
PX = re.compile(r"(?<![\w.-])(\d+(?:\.\d+)?)px\b")
TOKEN_USE = re.compile(r"var\(\s*(--text-[a-z0-9-]+)\s*\)")
TOKEN_DECL = re.compile(r"(--text-[a-z0-9-]+)\s*:\s*(\d+(?:\.\d+)?)px\s*;")

#: The ladder may not grow without a decision. Eleven steps today.
MAX_STEPS = 11


def _css_files() -> list[Path]:
    return sorted(p for p in SRC.glob("**/*.css") if "node_modules" not in p.parts)


def _strip_comments(text: str) -> str:
    return LINE_COMMENT.sub(" ", CSS_COMMENT.sub(" ", text))


def _declared_tokens() -> dict[str, float]:
    text = TOKENS.read_text(encoding="utf-8")
    return {name: float(value) for name, value in TOKEN_DECL.findall(text)}


def test_every_font_size_comes_from_the_scale() -> None:
    """No raw font size may be typed into a rule."""
    declared = _declared_tokens()
    offenders: list[str] = []
    for path in _css_files():
        text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in FONT_SIZE.finditer(line):
                value = match.group(1).strip()
                if value.startswith("var("):
                    for token in TOKEN_USE.findall(value):
                        if token not in declared:
                            offenders.append(
                                f"{path.relative_to(ROOT)}:{line_no}: {token} is not "
                                "declared in the token file"
                            )
                    continue
                # A clamp() may interpolate between two steps of the ladder --
                # but the values it names still have to be ladder values.
                if "clamp(" in value:
                    for literal in PX.findall(value):
                        if float(literal) not in declared.values():
                            offenders.append(
                                f"{path.relative_to(ROOT)}:{line_no}: clamp() names "
                                f"{literal}px, which is not a step of the scale"
                            )
                    continue
                offenders.append(
                    f"{path.relative_to(ROOT)}:{line_no}: font-size: {value} -- a raw "
                    "size; use a --text-* step"
                )
    assert not offenders, (
        f"{len(offenders)} font sizes are not on the scale:\n  "
        + "\n  ".join(offenders[:20])
    )


def test_the_scale_has_a_bounded_number_of_steps() -> None:
    """The ladder may not grow one page at a time."""
    declared = _declared_tokens()
    assert len(declared) <= MAX_STEPS, (
        f"the type scale has {len(declared)} steps ({sorted(declared)}), the ratchet "
        f"allows {MAX_STEPS} -- a new step is a design decision, and this one is "
        "not yet argued for"
    )


def test_the_steps_ascend_and_are_distinct() -> None:
    """A ladder whose steps do not ascend is not a ladder."""
    declared = _declared_tokens()
    values = [declared[name] for name in SCALE_STEPS if name in declared]
    assert values == sorted(values), f"the scale's sizes do not ascend: {values}"
    assert len(set(values)) == len(values), f"two steps share a size: {values}"


def test_every_step_of_the_ladder_is_used_somewhere() -> None:
    """A step nobody uses is a name waiting to be misused."""
    used: set[str] = set()
    for path in _css_files():
        text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        used.update(TOKEN_USE.findall(text))
    unused = [name for name in SCALE_STEPS if name not in used]
    assert not unused, (
        f"the ladder carries {len(unused)} steps nobody uses: {unused} -- either the "
        "step is dead (remove it) or a rule was typed in raw (use it)"
    )


def test_the_measurement_is_not_vacuous() -> None:
    """A gate that reads nothing is a green light with no bulb."""
    declared = _declared_tokens()
    assert len(declared) >= 8, (
        f"the token file declares only {len(declared)} type steps -- the parser "
        "stopped reading the file"
    )
    font_sizes = 0
    for path in _css_files():
        text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        font_sizes += len(FONT_SIZE.findall(text))
    assert font_sizes > 100, (
        f"the web CSS declares only {font_sizes} font sizes -- the census is too "
        "small to be the app's"
    )
