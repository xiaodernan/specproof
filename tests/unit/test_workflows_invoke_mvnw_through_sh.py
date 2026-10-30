"""#203 / #529 — every invocation of `mvnw` must go through `sh`, never directly.

`demo/spring-backend/mvnw` is committed as mode **100644** (the exec bit is a
property Windows drops, so it does not survive a round trip through a Windows
checkout). The Maven image runs that script as the **non-root** sandbox user, so
`./mvnw` fails with `Permission denied` and the step exits **126**.

`ci.yml` learned this in **#159** and fixed it in both of its jobs. The fix was
never carried into `nightly-eval.yml`, which kept `./mvnw`. Consequence: every
nightly run died **on that step**, before the evaluation step — so
`specproof-nightly-eval` reported failure while the evaluation itself never ran,
and the "Alert on regression" gate at the end of that file never executed. The
eval signal was dead, and only the workflow's own name said otherwise.

That is the shape this gate exists for: **one rule living in two files with
nothing reconciling them**. It does not check "nightly matches ci" — it checks
the rule itself, so the next workflow to add a Maven seed step inherits it.

**#529** applied the same reasoning one level up: the seed step itself was
copied in three places and is now `scripts/seed_maven_cache.sh`, so the rule's
last invocation lives THERE, not in a workflow. This census therefore scans the
script too. A workflow that reintroduces its own `mvnw` call is still checked
against the same rule — and the "every Maven job seeds the cache" premise now
belongs to tests/unit/test_the_maven_cache_seeding_has_one_owner.py, which
asserts it per job instead of via nightly-eval.yml's file name.

The census is line-based on purpose. The first version matched a full
`maven:<image> <how> mvnw` command shape, which **cannot see the broken form**:
in `./mvnw` the token is `./mvnw`, so the pattern looking for a word before
`mvnw` finds nothing and the offender is invisible. A probe that only recognises
the correct spelling cannot fail on the incorrect one.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"
SEEDER = REPO / "scripts" / "seed_maven_cache.sh"
MVNW = "demo/spring-backend/mvnw"

#: A command position invoking the wrapper: `mvnw`, `./mvnw`, `/work/mvnw`, …
_INVOKES_RE = re.compile(r"(?:^|\s)(?:\.?/)?(?:[\w./\-]*/)?mvnw\b")
_THROUGH_SH_RE = re.compile(r"\b(?:sh|bash)\s+mvnw\b")


def _census_files() -> list[Path]:
    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert files, f"no workflows found under {WORKFLOWS} — probe broken"
    assert SEEDER.is_file(), (
        f"{SEEDER} is missing — the seeding owner moved, so this census no "
        "longer reaches the invocation it exists to check"
    )
    return files + [SEEDER]


def mvnw_lines() -> list[tuple[str, int, str]]:
    """`(file, lineno, text)` for every NON-COMMENT line mentioning mvnw.

    Comments are skipped because they explain the rule and therefore quote the
    broken form; counting them as violations is the prose-vs-code trap that has
    bitten this repository before.
    """
    found: list[tuple[str, int, str]] = []
    for path in _census_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            if "mvnw" in text:
                found.append((path.name, lineno, text))
    return found


def mvnw_invocations() -> list[tuple[str, int, str]]:
    return [row for row in mvnw_lines() if _INVOKES_RE.search(row[2])]


def test_the_probe_found_the_invocations() -> None:
    """A census that silently finds nothing is greener than a bug."""
    invocations = mvnw_invocations()
    assert len(invocations) >= 1, (
        "expected at least 1 mvnw invocation (scripts/seed_maven_cache.sh), "
        f"found {invocations} — the probe or the seeding owner moved"
    )
    names = {name for name, _, _ in invocations}
    assert SEEDER.name in names, (
        f"{SEEDER.name} no longer invokes mvnw — if that is deliberate, this "
        "gate's premise changed and should be revisited"
    )


def test_no_workflow_executes_mvnw_directly() -> None:
    offenders = [
        (name, lineno, text)
        for name, lineno, text in mvnw_invocations()
        if not _THROUGH_SH_RE.search(text)
    ]
    assert not offenders, (
        "these invoke mvnw without an interpreter: "
        f"{offenders} — the file is committed 100644, so a direct exec fails with "
        "'Permission denied' and exit 126 (the #159/#203 failure)"
    )


def test_the_reason_still_holds() -> None:
    """Verify the premise rather than trusting the comment.

    If `mvnw` ever gains the exec bit, this clause goes red on purpose: the ban
    above would no longer be forced, and that is a decision to take knowingly
    (and to record here), not to leave as a rule whose reason has expired.
    """
    proc = subprocess.run(
        ["git", "ls-files", "-s", MVNW],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        import pytest

        pytest.skip(f"git could not read the index for {MVNW}: {proc.stderr.strip()}")
    mode = proc.stdout.split()[0]
    assert mode == "100644", (
        f"{MVNW} is committed as {mode}; the 'invoke through sh' rule was written "
        "because it is 100644 — revisit the rule (and this gate) before relaxing it"
    )
