"""Every corner radius in the web app comes from the radius ladder (#1625).

WHY. The app typed **fifteen** different corner radii straight into its
CSS (2/3/4/5/6/7/8/9/10/11/12/14/16/19/20px, plus 999px for pills),
while the token file declared five steps. Corners are what the eye
reads as "this is a card" versus "this is a button" versus "this is a
chip": a corner language with fifteen radii is not a language. The
ladder has eight steps now, and every corner comes from it.

WHAT THIS MEASURES:

* every radius declaration is a ladder step (a percentage, ``inherit``
  and ``0`` are not radii -- they are shapes that do not use the
  ladder),
* every step the app uses is declared in the token file,
* the ladder has a bounded number of steps (a ratchet),
* and the measurement is not vacuous (the token file declares the steps,
  the CSS really does declare radii).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "apps" / "web" / "src"
TOKENS = SRC / "theme" / "tokens.css"

#: The ladder, smallest first. The ratchet: a new step is a design
#: decision, not a side effect of one component's corner.
LADDER = (
    "--radius-2xs",
    "--radius-xs",
    "--radius-sm",
    "--radius-md",
    "--radius-lg",
    "--radius-xl",
    "--radius-2xl",
    "--radius-full",
)
MAX_STEPS = 8

CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
LINE_COMMENT = re.compile(r"//[^\n]*")
RADIUS = re.compile(
    r"(?<![-\w])(border-radius|border-top-left-radius|border-top-right-radius"
    r"|border-bottom-left-radius|border-bottom-right-radius)\s*:\s*([^;}\n]+)"
)
PX = re.compile(r"(?<![\w.-])(\d+(?:\.\d+)?)px\b")
TOKEN_USE = re.compile(r"var\(\s*(--radius-[a-z0-9-]+)\s*\)")
TOKEN_DECL = re.compile(r"(--radius-[a-z0-9-]+)\s*:\s*(\d+(?:\.\d+)?)px\s*;")

#: Values that are not radii and do not use the ladder.
NOT_A_RADIUS = ("inherit", "0", "50%", "initial", "unset")


def _css_files() -> list[Path]:
    return sorted(p for p in SRC.glob("**/*.css") if "node_modules" not in p.relative_to(SRC).parts)


def _strip_comments(text: str) -> str:
    return LINE_COMMENT.sub(" ", CSS_COMMENT.sub(" ", text))


def _declared() -> dict[str, float]:
    return {
        name: float(value)
        for name, value in TOKEN_DECL.findall(TOKENS.read_text(encoding="utf-8"))
    }


def test_every_radius_comes_from_the_ladder() -> None:
    declared = _declared()
    offenders: list[str] = []
    for path in _css_files():
        text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        for line_no, line in enumerate(text.splitlines(), start=1):
            for match in RADIUS.finditer(line):
                value = match.group(2).strip()
                if value in NOT_A_RADIUS:
                    continue
                if value.startswith("var("):
                    for token in TOKEN_USE.findall(value):
                        if token not in declared:
                            offenders.append(
                                f"{path.relative_to(ROOT)}:{line_no}: {token} is not "
                                "declared in the token file"
                            )
                    continue
                # A shorthand may mix steps and zeros ("0 0 var(--radius-md)
                # var(--radius-md)" rounds two corners only). Every component
                # has to be a zero or a step of the ladder.
                for part in value.split():
                    if part == "0" or part.startswith("var("):
                        continue
                    literal = PX.fullmatch(part)
                    if literal is None:
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{line_no}: {part} -- a raw radius"
                        )
                        continue
                    if float(literal.group(1)) not in declared.values():
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{line_no}: {part} is not a "
                            f"step of the ladder ({sorted(declared.values())})"
                        )
    assert not offenders, (
        f"{len(offenders)} radii are not on the ladder:\n  "
        + "\n  ".join(offenders[:20])
    )


def test_the_ladder_has_a_bounded_number_of_steps() -> None:
    declared = _declared()
    assert len(declared) <= MAX_STEPS, (
        f"the radius ladder has {len(declared)} steps ({sorted(declared)}), the "
        f"ratchet allows {MAX_STEPS}"
    )


def test_every_step_is_used_somewhere() -> None:
    used: set[str] = set()
    for path in _css_files():
        text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        used.update(TOKEN_USE.findall(text))
    unused = [name for name in LADDER if name not in used]
    assert not unused, (
        f"the ladder carries {len(unused)} steps nobody uses: {unused} -- either the "
        "step is dead (remove it) or a rule was typed in raw (use it)"
    )


def test_the_measurement_is_not_vacuous() -> None:
    declared = _declared()
    assert len(declared) >= 6, (
        f"the token file declares only {len(declared)} radius steps -- the parser "
        "stopped reading the file"
    )
    radii = 0
    for path in _css_files():
        text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        radii += len(RADIUS.findall(text))
    assert radii > 30, (
        f"the web CSS declares only {radii} radii -- the census is too small to be "
        "the app's"
    )
