"""The web UI stays on its design system: 4px grid, no theme-blind colors.

WHAT THIS MEASURES (and why it is a gate rather than a chore):

* **off-grid spacing** -- pixel literals used as spacing (padding / margin /
  gap / inset) that are neither on the 4px grid nor one of the hairlines the
  system allows (1/2/3px). Those are the pixels the eye reads as "this UI is
  not aligned"; measured at **307** across the web sources before #1612, and
  the change snapped every one of them (plus the twelve repeated inline
  ``.kv-label`` margins, which became one class rule).
* **theme-blind colors** -- a color literal painted directly in a rule
  instead of being a token. Such a literal cannot flip with
  ``[data-theme="light"]``, so the light theme paints the wrong color
  there. Measured at **20** real literals before #1612 (the rest of the
  naive count were issue numbers in comments -- ``#245``, ``#122`` -- which
  is why this gate strips comments before counting).

Floors, not zeroes-by-luck: both numbers are asserted at 0 so a later
change cannot quietly double them, and the measurement is printed so a
future owner can see what the change was worth.

Excluded on purpose:
  * ``src/theme/tokens.css`` -- the tokens themselves are literals;
  * ``src/ui-kit/UiKit.tsx`` -- the palette catalogue displays the tokens;
  * test files -- a fixture's hex is data, not a painted surface.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web"
SRC = WEB / "src"

#: The token file: literals there are declarations, not painted surfaces.
TOKEN_FILE = "tokens.css"
#: The palette catalogue: it renders the tokens on purpose.
CATALOGUE = "src/ui-kit/UiKit.tsx"

COLOR = re.compile(
    r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b"
    r"|\brgba?\(\s*[\d.]+[^)]*\)|\bhsla?\(\s*[\d.]+[^)]*\)"
)
PX = re.compile(r"(?<![\w.-])(\d+(?:\.\d+)?)px\b")
HAIRLINE = {1, 2, 3}

#: The properties the eye reads as rhythm (CSS spelling + React camelCase).
SPACING_PROPS = (
    "padding", "padding-top", "padding-right", "padding-bottom", "padding-left",
    "margin", "margin-top", "margin-right", "margin-bottom", "margin-left",
    "gap", "row-gap", "column-gap", "inset", "top", "right", "bottom", "left",
    "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
    "marginTop", "marginRight", "marginBottom", "marginLeft",
    "rowGap", "columnGap",
)
DECL_SELECTOR = re.compile(r":root|\[data-theme")
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT = re.compile(r"//[^\n]*")


def _strip_comments(text: str) -> str:
    """Drop comments so an issue number (``#245``) is not read as a color."""
    text = CSS_COMMENT.sub(" ", text)
    return LINE_COMMENT.sub(" ", text)


def _token_blocks(text: str) -> list[tuple[int, int]]:
    """Spans of the token-declaration blocks (``:root`` / ``[data-theme``)."""
    spans: list[tuple[int, int]] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                head = text[max(0, start - 300):start]
                if DECL_SELECTOR.search(head):
                    spans.append((start, i))
    return spans


def _property_of(text: str, index: int) -> str:
    """The property name of the declaration containing this offset."""
    brace = text.rfind("{", 0, index)
    semi = text.rfind(";", 0, index)
    return text[max(brace, semi) + 1:index].strip().split(":")[0].strip()


def _sources() -> list[Path]:
    files = [p for p in sorted(SRC.rglob("*.css")) if p.name != TOKEN_FILE]
    files += [p for p in sorted(SRC.rglob("*.tsx")) if ".test." not in p.name]
    return files


def measure() -> tuple[list[str], list[str]]:
    """(off-grid spacing hits, theme-blind color hits) as readable lines."""
    off_grid: list[str] = []
    blind: list[str] = []
    for path in _sources():
        rel = path.relative_to(WEB).as_posix()
        if rel == CATALOGUE:
            continue
        raw = path.read_text(encoding="utf-8")
        text = _strip_comments(raw)
        for match in PX.finditer(text):
            value = float(match.group(1))
            if value.is_integer() and int(value) in HAIRLINE:
                continue
            if value % 4 == 0:
                continue
            if _property_of(text, match.start()) not in SPACING_PROPS:
                continue
            line = raw.count("\n", 0, match.start()) + 1
            off_grid.append(f"{rel}:{line} {match.group(0)}")
        spans = _token_blocks(text)
        for match in COLOR.finditer(text):
            if any(start <= match.start() <= end for start, end in spans):
                continue
            line = raw.count("\n", 0, match.start()) + 1
            blind.append(f"{rel}:{line} {match.group(0)}")
    return off_grid, blind


def test_the_web_ui_stays_on_the_4px_grid() -> None:
    off_grid, _ = measure()
    assert not off_grid, (
        f"{len(off_grid)} spacing literals are off the 4px grid (the rhythm the eye "
        f"reads): {off_grid[:8]}"
    )


def test_no_painted_color_bypasses_the_theme_tokens() -> None:
    _, blind = measure()
    assert not blind, (
        f"{len(blind)} colors are painted as literals, so they cannot follow the "
        f"light theme: {blind[:8]}"
    )


def test_the_measurement_still_sees_the_web_sources() -> None:
    """A broken ruler would read a clean repository as clean.

    The gate is worth nothing if its scan stops finding anything, so the
    population it walks is asserted: the web sources exist, the stylesheets
    are non-trivial, and the token file is still the place where the palette
    is declared.
    """
    files = _sources()
    assert len(files) >= 15, f"the scan walks only {len(files)} files"
    css = [p for p in files if p.suffix == ".css"]
    assert len(css) >= 5, f"only {len(css)} stylesheets are scanned"
    total_lines = sum(
        len(p.read_text(encoding="utf-8").splitlines()) for p in css
    )
    assert total_lines >= 1000, (
        f"the scanned stylesheets hold {total_lines} lines -- the ruler would be "
        "reading a fragment"
    )
    tokens = (WEB / "src" / "theme" / "tokens.css")
    assert tokens.is_file(), "the token file moved; the exclusion above is stale"
