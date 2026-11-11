"""No shadow in the web app carries a literal colour (#1628).

WHY. The elevation ladder (``--elev-1`` … ``--elev-4``) is theme-aware:
the dark theme's shadows are deeper than the light theme's, because the
same rule reads a different background. A shadow written with a literal
colour is a shadow that **cannot** flip with the theme -- it is the
same darkness on both, which is exactly the "theme-blind colour" that
#1612 removed from the palette and #1619 measured for contrast.

So the rule this gate pins is narrow and honest:

* a shadow is ``none``, a ladder step, or a **ring/glow** whose colours
  are all tokens (``0 0 0 3px var(--accent-ring)`` is a focus ring, not
  an elevation, and it is allowed -- what is not allowed is a literal
  colour baked into it),
* and the ladder itself is declared for BOTH themes (a shadow that only
  exists in one theme is a theme-blind shadow wearing a token's name).

The measurement is a count of literals; the offenders are printed by
file and line.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "apps" / "web" / "src"
TOKENS = SRC / "theme" / "tokens.css"

CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT = re.compile(r"//[^\n]*")
SHADOW = re.compile(r"(?<![-\w])(box-shadow|text-shadow)\s*:\s*([^;}\n]+)")
#: A literal colour: hex or an rgb()/hsl() function.
LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\s*\(")
TOKEN_USE = re.compile(r"var\(\s*(--[a-z0-9-]+)\s*\)")
ELEVATION = re.compile(r"^--elev-\d$")


def _css_files() -> list[Path]:
    return sorted(p for p in SRC.glob("**/*.css") if "node_modules" not in p.parts)


def _strip_comments(text: str) -> str:
    return LINE_COMMENT.sub(" ", CSS_COMMENT.sub(" ", text))


def test_no_shadow_carries_a_literal_colour() -> None:
    offenders: list[str] = []
    for path in _css_files():
        text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in SHADOW.finditer(line):
                value = match.group(2).strip()
                if value == "none":
                    continue
                for literal in LITERAL.findall(value):
                    offenders.append(
                        f"{path.relative_to(ROOT)}:{line_no}: {value} -- the colour "
                        f"{literal} is baked in, so the shadow cannot flip with the theme"
                    )
    assert not offenders, (
        f"{len(offenders)} shadows carry a literal colour:\n  "
        + "\n  ".join(offenders[:20])
    )


def test_the_elevation_ladder_exists_for_both_themes() -> None:
    """A shadow that only exists in one theme is a theme-blind shadow
    wearing a token's name."""
    text = TOKENS.read_text(encoding="utf-8")
    dark = text[: text.find(':root[data-theme="light"]')]
    light = text[text.find(':root[data-theme="light"]') :]

    def steps(block: str) -> set[str]:
        return set(re.findall(r"(--elev-\d)\s*:", block))

    dark_steps = steps(dark)
    light_steps = steps(light)
    assert dark_steps, "the dark theme declares no elevation steps"
    assert dark_steps == light_steps, (
        f"the themes disagree about the ladder: dark {sorted(dark_steps)}, "
        f"light {sorted(light_steps)}"
    )
    assert len(dark_steps) >= 3, (
        f"the ladder has {len(dark_steps)} steps -- a ladder with one step is a "
        "constant"
    )


def test_the_measurement_is_not_vacuous() -> None:
    """A gate that reads nothing is a green light with no bulb."""
    shadows = 0
    for path in _css_files():
        text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        shadows += len(SHADOW.findall(text))
    assert shadows > 15, (
        f"the web CSS declares only {shadows} shadows -- the census is too small "
        "to be the app's"
    )
