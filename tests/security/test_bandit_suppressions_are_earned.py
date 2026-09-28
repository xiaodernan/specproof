"""Every shipped suppression must be earned, scoped, and readable by the scanner.

The security job in CI (`ci.yml`, the bandit step) is only as good as its
suppressions, and a suppression is a hand-written claim about a machine's
behaviour. Three such claims were measured here rather than assumed, and this
file turns each into a check that runs bandit itself:

1. bandit parses whatever follows its directive as *test ids*. A reason written
   after the directive therefore became a list of nonsense ids -- measured at 61
   "Test in comment" warnings on one run -- and, having no valid id, behaved as a
   bare directive that hides *every* finding on that line, including one a later
   change introduces. So the reason goes first and the tail is ids-only.
2. Naming ids scopes the hiding: a directive listing the wrong id left the real
   finding reported (measured -- the B108 at `sandbox/runner.py` survived a
   directive naming B104). So the ids must be exactly the ones bandit reports at
   that line, which is only knowable by running bandit with the directive removed.
3. A directive written where there is no code is still parsed. An explanatory
   comment that quoted the directive silently became a suppression on a comment
   line, so prose may not contain it on a full-line comment.

CI gates MEDIUM and above (`-ll`), so that is the population this file holds to a
zero; the LOW findings it deliberately ignores are still used to scope ids,
because a directive naming a test bandit never reports is a directive that has
stopped meaning anything.
"""
from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[2]
CI_FILE = REPO / ".github" / "workflows" / "ci.yml"

#: `<reason>  # nosec B608 B104` -- the directive last, ids-only after it.
TAIL_RE = re.compile(r"#\s*nosec\b(?P<ids>[^#]*)$")
#: the shape bandit acts on -- a hash immediately followed by the word
DIRECTIVE_RE = re.compile(r"#\s*nosec\b", re.I)
ID_RE = re.compile(r"B\d{3}")
#: how bandit talks about a directive it cannot use
PROSE_AS_ID = "Test in comment"
DEAD_DIRECTIVE = "nosec encountered"


def _ci_bandit_command() -> list[str]:
    """The bandit invocation CI actually runs, read from the workflow itself.

    Deriving the package list and the severity flag from ci.yml is the point: a
    gate that hard-codes its own population can quietly stop covering the one CI
    scans, and then a green gate proves nothing about the green job.
    """
    lines = CI_FILE.read_text(encoding="utf-8").splitlines()
    joined, start = [], None
    for i, ln in enumerate(lines):
        if "python -m bandit" in ln:
            start = i
            break
    assert start is not None, "ci.yml has no bandit step for this gate to mirror"
    for ln in lines[start:]:
        joined.append(ln.strip().rstrip("\\"))
        if not ln.strip().endswith("\\"):
            break
    cmd = " ".join(joined).split()
    assert cmd[:2] == ["python", "-m"], f"unexpected bandit invocation in ci.yml: {cmd[:4]}"
    cmd[0:2] = [sys.executable, "-m"]  # run the interpreter this suite runs on
    return cmd


def _bandit(cwd: Path, args: list[str], report: Path) -> tuple[int, list[dict], str]:
    proc = subprocess.run(
        [*args, "-f", "json", "-o", str(report), "-q"],
        cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    results: list[dict] = []
    if report.exists() and report.read_text(encoding="utf-8").strip():
        raw = json.loads(report.read_text(encoding="utf-8", errors="replace"))
        results = raw.get("results", [])
    return proc.returncode, results, (proc.stderr or "") + (proc.stdout or "")


def _shipped_py_files() -> list[Path]:
    packages = _ci_packages()
    return sorted(p for pkg in packages for p in (REPO / pkg).rglob("*.py"))


def _ci_packages() -> tuple[str, ...]:
    args = _ci_bandit_command()
    out, seen_r = [], False
    for a in args:
        if seen_r and re.fullmatch(r"[a-z_][a-z0-9_]*", a):
            out.append(a)
        if a == "-r":
            seen_r = True
    return tuple(out)


def _tail_sites() -> dict[str, dict[int, list[str]]]:
    """file -> line -> ids declared by the directive on that line."""
    sites: dict[str, dict[int, list[str]]] = {}
    for path in _shipped_py_files():
        rel = path.relative_to(REPO).as_posix()
        for n, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = TAIL_RE.search(ln)
            if not m:
                continue
            sites.setdefault(rel, {})[n] = sorted(set(ID_RE.findall(m.group("ids"))))
    return sites


def _copy_shipped(root: Path) -> None:
    for pkg in _ci_packages():
        shutil.copytree(REPO / pkg, root / pkg)


def _rel(root: Path, filename: str) -> str:
    """bandit prints paths relative to the directory it was run in."""
    p = Path(filename)
    try:
        return p.relative_to(root).as_posix()
    except ValueError:
        return Path(filename).resolve().relative_to(REPO).as_posix()


def _strip_run() -> list[dict]:
    """One bandit run over one stripped copy, at every severity, cached.

    Cached because the three checks below read the same table; scanning the whole
    shipped tree three times made this file the slowest in the suite for no
    additional evidence.
    """
    global _STRIP_CACHE
    if _STRIP_CACHE is not None:
        return _STRIP_CACHE
    root = Path(tempfile.mkdtemp(prefix="specproof_bandit_"))
    try:
        _copy_shipped(root)
        for path in sorted(p for pkg in _ci_packages() for p in (root / pkg).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if "nosec" not in text:
                continue
            new = "\n".join(
                re.sub(r"\s*#\s*nosec\b[^#]*$", "", ln, flags=re.I).rstrip()
                for ln in text.splitlines()
            ) + "\n"
            path.write_text(new, encoding="utf-8", newline="\n")
        args = [sys.executable, "-m", "bandit", "-r", *_ci_packages(), "--skip", "B101", "-q"]
        # bandit's -l is a *minimum* severity filter, so "everything" is no -l at
        # all; CI's own cut is applied by the callers from the same run, never by a
        # flag that could silently narrow what this file sees.
        code, results, log = _bandit(root, args, root / "report.json")
        assert code in (0, 1), f"bandit did not run (exit {code}): {log[-400:]}"
        for r in results:
            r["_rel"] = _rel(root, r["filename"])
        _STRIP_CACHE = results
        return results
    finally:
        shutil.rmtree(root, ignore_errors=True)


_STRIP_CACHE: list[dict] | None = None


def _stripped_findings(all_severities: bool) -> dict[tuple[str, int], set[str]]:
    """(file, line) -> ids, from the single stripped run."""
    out: dict[tuple[str, int], set[str]] = {}
    for r in _strip_run():
        if not all_severities and r["issue_severity"] not in ("MEDIUM", "HIGH"):
            continue
        out.setdefault((r["_rel"], r["line_number"]), set()).add(r["test_id"])
    return out


# ── 1. the claim CI makes, on the plane CI scans ─────────────────────────────


def test_ci_bandit_command_exists_and_is_green_on_the_shipped_packages() -> None:
    cmd = _ci_bandit_command()
    assert "-ll" in cmd, f"CI no longer gates MEDIUM+, so this file's cut is stale: {cmd}"
    code, results, log = _bandit(REPO, cmd, Path(tempfile.mkdtemp()) / "r.json")
    assert code == 0, f"the CI bandit step is red here:\n{log[-1500:]}"
    assert not results, f"CI would fail on {len(results)} finding(s): " \
                        f"{[(r['test_id'], r['filename'], r['line_number']) for r in results]}"


def _directive_statement_spans(
    lines: list[str], directive_lines: set[int]
) -> list[tuple[int, int]]:
    """Spans of the statements that carry a directive on one of their lines.

    bandit keys a multi-line statement's finding to the line of its first string
    fragment but reports its directive bookkeeping at the statement's closing line,
    so a warning can name a line that holds no directive while still describing one
    that does. The AST span is what connects the two; guessing an offset would be a
    second hand-written claim about a machine we can just ask.
    """
    tree = ast.parse("\n".join(lines))
    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", None) or start
        if start is None:
            continue
        if any(start <= d <= end for d in directive_lines):
            spans.append((start, end))
    return spans


def test_bandit_does_not_read_any_of_our_prose_as_test_ids() -> None:
    """Zero "Test in comment" lines, and every "no failed test" line explained.

    "Test in comment" is the prose-as-ids signature: it must not appear at all.

    "nosec encountered, but no failed test" is different, and the difference was
    measured, not assumed. Deleting a directive makes bandit report at that very
    line (the two checks below), yet with the directive in place bandit still draws
    this warning for the statement's closing line -- its own bookkeeping, not an
    unneeded suppression. A warning is accepted only when it lands inside the AST
    span of a statement that carries a load-bearing directive; a warning about any
    other place is a directive this file cannot account for, and goes red.
    """
    code, results, log = _bandit(REPO, _ci_bandit_command(),
                                 Path(tempfile.mkdtemp()) / "r.json")
    assert code == 0
    prose = [ln for ln in log.splitlines() if PROSE_AS_ID in ln]
    assert not prose, (
        f"{len(prose)} directive word(s) were parsed as test ids, e.g. {prose[:3]} -- "
        "write the reason BEFORE the directive and keep it ids-only after"
    )
    sites = _tail_sites()
    reported = _stripped_findings(all_severities=True)
    load_bearing = {
        rel: {line for line, ids in per_line.items() if (rel, line) in reported}
        for rel, per_line in sites.items()
    }
    spans: dict[str, list[tuple[int, int]]] = {}
    unexplained = []
    for ln in log.splitlines():
        if DEAD_DIRECTIVE not in ln:
            continue
        m = re.search(r"file\s+(\S+?):(\d+)", ln)
        if not m:
            unexplained.append(f"unparseable warning: {ln.strip()}")
            continue
        rel = PurePosixPath(m.group(1).replace("\\", "/")).as_posix()
        line = int(m.group(2))
        if rel not in spans:
            path = REPO / rel
            if not path.exists():
                unexplained.append(f"{rel}:{line} is not a shipped file")
                continue
            spans[rel] = _directive_statement_spans(
                path.read_text(encoding="utf-8").splitlines(), load_bearing.get(rel, set()),
            )
        if not any(a <= line <= b for a, b in spans[rel]):
            unexplained.append(f"{rel}:{line} is outside every statement that carries a "
                               "directive proven to hide a finding")
    assert not unexplained, (
        f"{len(unexplained)} 'no failed test' warning(s) this file cannot account for: "
        f"{unexplained}"
    )


# ── 2. no suppression may be decorative ─────────────────────────────────────


def test_every_directive_hides_a_finding_on_its_own_line() -> None:
    sites = _tail_sites()
    assert sites, "no suppression found in the shipped packages -- the scan read nothing"
    reported = _stripped_findings(all_severities=True)
    decorative = [
        f"{rel}:{line} declares {ids}"
        for rel, per_line in sites.items()
        for line, ids in per_line.items()
        if (rel, line) not in reported
    ]
    assert not decorative, "suppressions that hide nothing (delete them or move them to " \
                           f"the line bandit flags): {decorative}"
    for rel, per_line in sites.items():
        for line, ids in per_line.items():
            assert ids, f"{rel}:{line} has a bare directive -- name the ids it hides"


def test_declared_ids_are_exactly_the_ids_bandit_reports() -> None:
    reported = _stripped_findings(all_severities=True)
    wrong = []
    for rel, per_line in _tail_sites().items():
        for line, declared in per_line.items():
            actual = sorted(reported.get((rel, line), set()))
            if declared != actual:
                wrong.append(f"{rel}:{line} declares {declared}, bandit reports {actual}")
    assert not wrong, "directive/test mismatch (a wrong id hides the wrong thing): " \
                      f"{wrong}"


# ── 3. a new finding cannot slip past unmarked ──────────────────────────────


def test_every_medium_plus_finding_is_answered_by_a_directive() -> None:
    medium = _stripped_findings(all_severities=False)
    sites = _tail_sites()
    assert medium, (
        f"bandit reports no MEDIUM+ finding once the directives are gone, yet "
        f"{sum(len(v) for v in sites.values())} directives are shipped"
    )
    unmarked = [f"{rel}:{line} {sorted(ids)}" for (rel, line), ids in sorted(medium.items())
                if line not in sites.get(rel, {})]
    assert not unmarked, f"new MEDIUM+ finding(s) with no suppression and no fix: {unmarked}"


# ── 4. the directive token may not hide inside prose ────────────────────────


def test_the_directive_appears_only_on_lines_of_code() -> None:
    """A directive needs code to attach to; prose that spells it is a silent suppression.

    The token checked here is the directive *shape* (`#` then nosec), not the word
    -- this file and the storage layer both discuss suppressions in prose, and the
    prose is only safe while it does not look like the thing bandit parses.
    """
    offenders = []
    checked = 0
    for path in _shipped_py_files():
        rel = path.relative_to(REPO).as_posix()
        for n, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not DIRECTIVE_RE.search(ln):
                continue
            checked += 1
            code = ln.split("#")[0].strip()
            if not code:
                offenders.append(f"{rel}:{n}: {ln.strip()[:70]}")
                continue
            m = TAIL_RE.search(ln)
            assert m, f"{rel}:{n} has a directive that is not the last comment on its line"
            tail = m.group("ids")
            assert re.fullmatch(r"(\sB\d{3})+\s*", tail), (
                f"{rel}:{n} directive tail is not ids-only: {tail.strip()[:60]!r} -- bandit "
                "reads this text as test ids, so prose here hides every finding on the line"
            )
    shipped = sum(len(v) for v in _tail_sites().values())
    assert shipped > 0, "the shipped packages carry no suppression at all -- scan broke"
    assert checked == shipped, f"{checked} directive-shaped lines vs {shipped} census sites"
    assert not offenders, (
        f"{len(offenders)} comment-only line(s) carry the directive, which bandit parses as "
        f"a suppression over nothing: {offenders}"
    )
