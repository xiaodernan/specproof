"""The print stylesheet — the product's evidence goes to review boards on A4.

SpecProof's entire reason to exist is that a delivery verdict can be
carried into a review and examined there. An in-app counterexample list is
fragile evidence; the printed page is not. ``apps/web/src/styles/print.css``
exists for that moment, and this gate keeps it honest:

* the sheet loads from main.tsx (an unloaded print stylesheet is just a file);
* a stable A4 @page rule is declared;
* every interactive chrome class (navigation, command surfaces, toasts) is
  gone in print — a report that renders the shortcut overlay is not a report;
* every class that paints gradient ink (``background-clip: text`` — the
  design's signature move) is neutralized to solid ink in print. This arm is
  DERIVED from the source: add a new gradient-text utility without a print
  override and this gate fails, which is the only honest way to keep 36 such
  classes from drifting apart;
* panels avoid page breaks and table headers repeat across pages.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "apps" / "web" / "src"
PRINT = WEB / "styles" / "print.css"
MAIN = WEB / "main.tsx"

#: Every rule in these sheets that paints gradient text is fatal to A4 ink.
GRADIENT_SHEETS = ("styles/aurora.css", "styles/base.css")

_CHROME_CLASSES = (
    "sidebar",
    "workspace-topbar",
    "workspace-footer",
    "nav-backdrop",
    "ui-palette-root",
    "ui-shortcuts-root",
    "ui-toast-viewport",
    "skip-link",
    "ui-btn",
)


def _strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _gradient_text_classes() -> set[str]:
    classes: set[str] = set()
    for rel in GRADIENT_SHEETS:
        css = _strip_comments((WEB / rel).read_text(encoding="utf-8"))
        for chunk in css.split("}"):
            if "background-clip: text" not in chunk or "{" not in chunk:
                continue
            selectors = chunk.split("{")[0]
            classes.update(c.lstrip(".") for c in re.findall(r"\.[a-zA-Z_][\w-]*", selectors))
    return classes


def test_print_stylesheet_exists_and_is_loaded() -> None:
    assert PRINT.exists(), "apps/web/src/styles/print.css is missing"
    main = MAIN.read_text(encoding="utf-8")
    assert 'import "./styles/print.css";' in main, (
        "main.tsx does not import print.css — the evidence cannot print"
    )


def test_the_page_rule_is_a4_with_margins() -> None:
    css = _strip_comments(PRINT.read_text(encoding="utf-8"))
    match = re.search(r"@page\s*\{[^}]*\}", css, flags=re.S)
    assert match is not None, "no @page rule — paper output has no geometry"
    body = match.group(0)
    assert "A4" in body or "210mm" in body, f"@page does not declare A4: {body}"
    assert re.search(r"margin:\s*\d+mm", body), f"@page declares no printable margin: {body}"


def test_interactive_chrome_is_hidden_in_print() -> None:
    css = _strip_comments(PRINT.read_text(encoding="utf-8"))
    assert "@media print" in css
    for klass in _CHROME_CLASSES:
        assert re.search(r"[.]" + re.escape(klass) + r"\b[^{]*\{\s*display:\s*none", css), (
            f"interactive chrome class .{klass} is not hidden in print"
        )


def test_every_gradient_text_utility_has_a_print_ink_override() -> None:
    source_classes = _gradient_text_classes()
    assert "stat-value" in source_classes, (
        "the gradient-text scan collapsed — the parser lost the plot"
    )
    css = PRINT.read_text(encoding="utf-8")
    missing = sorted(c for c in source_classes if c not in css)
    assert not missing, (
        "gradient-text utilities without a print override (invisible ink on "
        f"paper): {missing}"
    )


def test_panels_avoid_page_breaks_and_table_headers_repeat() -> None:
    css = _strip_comments(PRINT.read_text(encoding="utf-8"))
    assert re.search(r"break-inside:\s*avoid", css), "no panel break-inside rule"
    assert re.search(r"thead\s*\{\s*display:\s*table-header-group", css), (
        "tables do not repeat their header across page breaks"
    )
