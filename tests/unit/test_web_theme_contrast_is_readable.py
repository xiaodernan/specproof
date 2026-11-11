"""The design system's text must be readable in BOTH themes (WCAG 2.1).

Beauty that nobody can read is not beauty: this gate measures the contrast
of the token pairs the UI actually paints -- body text on the page, text on
a card, muted text, links, text on an accent button -- in the dark (default)
theme and in the light theme, and fails when a pair is below the WCAG
minimum (4.5:1 for body text, 3:1 for muted meta text and other non-text
elements).

It reads the token file as CSS: the base ``:root`` block is the DARK theme
(the file is dark-first), and every ``:root[data-theme="light"]`` block
overrides it for the light theme. A token that only exists in the light
theme therefore counts for the light theme only -- which is exactly what the
browser does.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web" / "src"
#: The cascade the product pages actually get (main.tsx imports them in this
#: order): the token file first, then the base stylesheet, then the PRODUCT
#: stylesheet -- which re-declares the accent ramp and the surfaces in the
#: product's green palette. Grading tokens.css alone would grade a palette
#: the product pages do not paint.
LAYERS = (
    WEB / "theme" / "tokens.css",
    WEB / "styles" / "base.css",
    WEB / "styles" / "product.css",
)

DECL = re.compile(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;")
LIGHT_SELECTOR = ":root[data-theme=\"light\"]"

#: (foreground, background, minimum ratio, what it is)
PAIRS = [
    ("--color-text", "--color-bg", 4.5, "body text on the page"),
    ("--color-text", "--color-surface", 4.5, "text on a card"),
    ("--color-text", "--color-surface-2", 4.5, "text on a raised card"),
    ("--color-text-2", "--color-surface", 4.5, "secondary text on a card"),
    ("--color-text-3", "--color-surface", 3.0, "muted/meta text on a card"),
    ("--color-link", "--color-bg", 4.5, "a link on the page"),
    # the accent button paints --color-on-accent (white) on --accent-600,
    # and on --accent-700 while hovered; --color-text-inverse is NOT what
    # the buttons use (it is a token no rule paints -- measuring it would
    # grade a combination the user never sees)
    ("--color-on-accent", "--accent-600", 4.5, "text on an accent button"),
    ("--color-on-accent", "--accent-700", 4.5, "text on a hovered accent button"),
]


def _blocks(text: str) -> list[tuple[str, str]]:
    """(selector, body) for every top-level block in the token file."""
    out: list[tuple[str, str]] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                selector = text[start:i].strip().splitlines()[-1].strip()
                start = i + 1
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                out.append((selector, text[start:i]))
    return out


def _theme_values(paths: tuple[Path, ...]) -> dict[str, dict[str, str]]:
    """The effective palette per theme, with the real cascade applied.

    The layers are read in import order and the later ones win, exactly as
    the browser resolves them. The light theme starts from the dark one and
    then takes every light override.
    """
    dark: dict[str, str] = {}
    light: dict[str, str] = {}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for selector, body in _blocks(text):
            declared = {m.group(1): m.group(2) for m in DECL.finditer(body)}
            if not declared:
                continue
            if LIGHT_SELECTOR in selector:
                light.update(declared)
            else:
                dark.update(declared)
    effective_light = dict(dark)
    effective_light.update(light)
    return {"dark": dark, "light": effective_light}


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))


def _luminance(rgb: tuple[int, int, int]) -> float:
    channels = []
    for value in rgb:
        c = value / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg: tuple[int, int, int], bg: tuple[int, int, int]) -> float:
    l1 = _luminance(fg)
    l2 = _luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


def test_both_themes_keep_the_text_readable() -> None:
    themes = _theme_values(LAYERS)
    assert set(themes) == {"dark", "light"}, f"the token file parsed into {set(themes)}"
    problems: list[str] = []
    measured: list[str] = []
    for theme, values in themes.items():
        for fg, bg, minimum, label in PAIRS:
            if fg not in values or bg not in values:
                problems.append(f"{theme}: {label} — {fg} or {bg} is not defined")
                continue
            ratio = _contrast(_rgb(values[fg]), _rgb(values[bg]))
            measured.append(f"{theme:5s} {ratio:5.2f} {label}")
            if ratio < minimum:
                problems.append(
                    f"{theme}: {label} is {ratio:.2f}:1, WCAG wants {minimum}:1 "
                    f"({fg} on {bg})"
                )
    assert not problems, (
        "the design system paints text that cannot be read:\n  "
        + "\n  ".join(problems)
        + "\nmeasured:\n  "
        + "\n  ".join(measured)
    )


def test_the_gate_measured_something() -> None:
    """A contrast gate that reads nothing is a green light with no bulb."""
    themes = _theme_values(LAYERS)
    for theme, values in themes.items():
        assert len(values) > 20, (
            f"the {theme} theme resolved only {len(values)} tokens — the parser "
            "stopped reading the file"
        )
