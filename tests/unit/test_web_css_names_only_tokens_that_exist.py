"""Every ``var(--x)`` in the web app must name something that exists.

WHY THIS IS A GATE.

A custom property that is not declared is not a colour -- it is a hole.
The browser resolves ``var(--muted, #8b93a1)`` to the fallback and
carries on; but ``var(--color-text-1)`` with no fallback makes the whole
declaration invalid at computed-value time, so the browser drops it and
the element keeps whatever it inherited. That is invisible in review and
visible on screen: a label in the wrong colour, a border that is simply
not there.

The three sibling gates cannot see any of this. ``#1612`` counts colour
*literals*, ``#1625`` counts radii, ``#1628`` counts shadow colours --
a missing token is none of those, so a page could be perfectly clean by
their standards and still lose declarations at runtime. Before this gate
the web sources carried **26** holes (25 of them with no fallback at
all), and one page's gold was invisible for exactly that reason: it asked
for ``--archive-gold-light``, which no theme ever declared.

WHAT THIS MEASURES.

A reference is legal when the name resolves to one of two things:

* **declared** -- a custom property the browser is actually told about:
  the palette in ``theme/tokens.css`` *and* the product surfaces' own
  theme override in ``styles/product.css`` (a second ``:root`` block
  that re-declares the palette in jade; it is a declaration too, and a
  rule that only looked at ``tokens.css`` would call its tokens
  missing), or
* **provided** -- a property a component injects on the element itself,
  the way ``DonutMeter`` injects ``--arc`` with the arc's own fraction.
  Those are per-element values, not palette entries, and they are legal
  even though no theme declares them.

Everything else is a hole, and the gate prints every one of them.

Both sets are *derived*, not typed: no name is written down in this
file, so renaming or moving a token cannot put this gate back into its
own ruler.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web"
SRC = WEB / "src"
TOKENS = SRC / "theme" / "tokens.css"

CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT = re.compile(r"//[^\n]*")

#: ``var(--name)`` or ``var(--name, fallback)`` -- the name only.
VAR_USE = re.compile(r"var\(\s*(--[a-z0-9][a-z0-9-]*)\s*(?:,|\))")
#: a custom-property *assignment* in CSS: ``--name: value;``
CSS_ASSIGN = re.compile(r"(?<![\w-])(--[a-z0-9][a-z0-9-]*)\s*:")
#: an inline injection: ``{"--name": v}`` / ``["--name" as string]: v``
INLINE_ASSIGN = re.compile(
    r"[\"'](--[a-z0-9][a-z0-9-]*)[\"']\s*(?:as\s+string\s*\])?\s*:"
)


def _strip_comments(text: str) -> str:
    return LINE_COMMENT.sub(" ", CSS_COMMENT.sub(" ", text))


def _sources() -> list[Path]:
    """The web sources the app actually ships (tests excluded)."""
    files = [p for p in sorted(SRC.rglob("*.css")) if p.name != "tokens.css"]
    files += [p for p in sorted(SRC.rglob("*.tsx")) if ".test." not in p.name]
    files += [p for p in sorted(SRC.rglob("*.ts")) if ".test." not in p.name]
    return files


def _declared() -> set[str]:
    """Custom properties the browser is told about, by any declaration."""
    names: set[str] = set()
    for path in [TOKENS, *sorted(SRC.rglob("*.css"))]:
        text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        names.update(CSS_ASSIGN.findall(text))
    return names


def _provided() -> set[str]:
    """Custom properties a component injects on the element itself."""
    names: set[str] = set()
    for path in sorted(SRC.rglob("*.tsx")) + sorted(SRC.rglob("*.ts")):
        if ".test." in path.name:
            continue
        text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        names.update(INLINE_ASSIGN.findall(text))
    return names


def _holes(text: str, known: set[str]) -> list[str]:
    """The names in ``text`` that resolve to nothing."""
    return [name for name in VAR_USE.findall(text) if name not in known]


def measure() -> list[str]:
    """Every unresolvable reference, as readable lines."""
    known = _declared() | _provided()
    holes: list[str] = []
    for path in _sources():
        rel = path.relative_to(WEB).as_posix()
        raw = path.read_text(encoding="utf-8", errors="replace")
        text = _strip_comments(raw)
        for name in _holes(text, known):
            holes.append(f"{rel}: {name}")
    return holes


def test_every_custom_property_reference_resolves() -> None:
    holes = measure()
    assert not holes, (
        f"{len(holes)} var() references name a custom property that nothing "
        f"declares or provides, so the browser drops the whole declaration: "
        f"{holes[:10]}"
    )


def test_the_ruler_would_catch_a_name_that_does_not_exist() -> None:
    """A ruler that cannot see a hole is a green light with no bulb.

    The detector is exercised directly on text that names a property
    nothing declares -- if it came back empty, the gate above would be
    measuring nothing and would pass on any repository.
    """
    known = {"--color-text", "--color-surface"}
    assert _holes("color: var(--color-text);", known) == []
    assert _holes("color: var(--not-a-token);", known) == ["--not-a-token"]
    assert _holes(
        "background: var(--color-surface, var(--also-missing));", known
    ) == ["--also-missing"]


def test_the_measurement_is_not_vacuous() -> None:
    """The scan must really read the app."""
    files = _sources()
    assert len(files) >= 40, f"the scan walks only {len(files)} files"
    css = [p for p in files if p.suffix == ".css"]
    assert len(css) >= 30, f"only {len(css)} stylesheets are scanned"
    declared = _declared()
    assert len(declared) >= 500, (
        f"only {len(declared)} custom properties are declared -- the parser "
        "stopped reading the files"
    )
    provided = _provided()
    assert provided, "no inline-injected property was found -- the reader is blind"
    references = 0
    for path in files:
        text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        references += len(VAR_USE.findall(text))
    assert references >= 300, (
        f"the web sources hold only {references} var() references -- the "
        "census is too small to be the app's"
    )


def test_the_palette_is_still_where_the_palette_lives() -> None:
    """The token file is the palette's home; if it moves, the scan must know."""
    assert TOKENS.is_file(), "the token file moved; the readers above are stale"
    text = TOKENS.read_text(encoding="utf-8")
    assert ":root" in text, "the token file declares no :root block"
