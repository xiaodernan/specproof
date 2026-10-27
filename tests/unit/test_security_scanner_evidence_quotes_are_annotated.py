"""Every `# specproof-nosec` directive in the repo must earn its silence.

Three gates live here, and they answer three different questions:

1. **Can the audit see the tree?** A walk that over-prunes would make the other
   two gates pass for the wrong reason, so the scanned-file count is asserted
   before anything else.

2. **Is every directive load-bearing and reasoned?** A directive that names a
   pattern which does not fire on its line hides nothing — it reads like a
   suppression without being one. The same is true of a directive with no
   reason in front of it, which is the shape this repo already paid for once
   with bandit's `# nosec` ids (see
   `tests/security/test_bandit_suppressions_are_earned.py`).

3. **Is the repo's secret posture actually clean?** `scan_directory` over the
   whole tree must report no CRITICAL/HIGH finding. This is the gate a
   *missing* directive fails, and it is what makes gate 2 non-vacuous in the
   other direction: if directive detection broke, the suppressions would stop
   applying and this gate would go red.

Gate 3 is also what keeps the optimization ledger honest. That file quotes
evidence verbatim — it has to, that is its job — and a quoted snippet that
matches a pattern is flagged like any other line. Annotating such a line with
a named directive is the sanctioned way to say "this one is on purpose";
quietly widening the placeholder list or the exclude list is not.

Directives are only audited in files the scanner actually reads: a directive
in `tests/` or in `agent/security_scanner.py` itself is inert by construction,
because those paths are excluded, and auditing them would flag the module's
own documentation of the mechanism.

This module's name contains ``security_scanner`` on purpose: the no-leak gates
(``tests/security/test_no_key_leak.py``, ``tests/security/test_no_secrets.py``)
skip files whose path contains that string, because a file that talks about
secret patterns legitimately contains secret-shaped strings.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from agent.security_scanner import (
    _NOSEC_RE,
    _SECRET_PATTERNS,
    _directive_names,
    _should_exclude,
    _walk_scannable,
    scan_directory,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _firing_patterns(line: str) -> set[str]:
    """Pattern names whose regex matches this line — same flags the scan uses."""
    return {
        name
        for pattern, name, _severity in _SECRET_PATTERNS
        if re.search(pattern, line, re.IGNORECASE)
    }


def _repo_directives() -> list[dict[str, object]]:
    """Every directive in a file the scanner reads, with what it actually hides.

    ``_directive_names`` is the shipped parser, so "hides" is what the mechanism
    really does rather than what a substring reading of the tail suggests: a
    directive that names anything but whole pattern names is malformed, and a
    malformed directive hides nothing.
    """
    found: list[dict[str, object]] = []
    for rel, path in _walk_scannable(PROJECT_ROOT):
        if _should_exclude(rel):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError, OSError):
            continue
        for lineno, line in enumerate(content.splitlines(), 1):
            m = _NOSEC_RE.search(line)
            if m is None:
                continue
            names = m.group("names")
            parsed = _directive_names(line)
            found.append(
                {
                    "path": rel,
                    "line": lineno,
                    "reason": line[: m.start()].strip().rstrip("#").strip(),
                    "names": names.strip(),
                    "parsed": list(parsed),
                    "hides": sorted(n for n in _firing_patterns(line) if n in parsed),
                }
            )
    return found


_DIRECTIVES = _repo_directives()


def test_the_directive_audit_is_not_vacuous() -> None:
    """The audit must have something to audit, and must see a real tree.

    If this fails because the tree genuinely carries no directive any more,
    delete this module deliberately — do not let it pass silently, because a
    vacuous audit is indistinguishable from a clean one.
    """
    assert _DIRECTIVES, (
        f"no `# specproof-nosec` directive found under {PROJECT_ROOT}; if that is "
        "deliberate, delete this module rather than leaving it vacuous"
    )


@pytest.mark.parametrize(
    "directive",
    _DIRECTIVES,
    ids=lambda d: f"{d['path']}:{d['line']}",
)
def test_a_directive_hides_a_finding_that_really_fires(directive: dict[str, object]) -> None:
    """Dead-directive detection: the directive must silence a real finding.

    A directive naming nothing that fires on its line is a leftover or a typo.
    It is not a security hole on its own — it hides nothing — but it reads like
    a suppression, which is exactly how a stale `# nosec` id misleads a reviewer.
    A directive whose tail is not a list of whole pattern names is malformed:
    it silences nothing either, and it is the shape a line that merely MENTIONS
    the mechanism takes, so it must not pass as a directive.
    """
    assert directive["hides"], (
        f"{directive['path']}:{directive['line']} carries a `# specproof-nosec` "
        f"naming {directive['names']!r}, but "
        + (
            "the tail is not a list of whole pattern names — the directive is malformed"
            if not directive["parsed"]
            else "no pattern fires on that line — the directive is dead"
        )
    )


@pytest.mark.parametrize(
    "directive",
    _DIRECTIVES,
    ids=lambda d: f"{d['path']}:{d['line']}",
)
def test_a_directive_has_a_reason_in_front_of_it(directive: dict[str, object]) -> None:
    """The reason goes FIRST — the shape bandit already paid for on this repo.

    ``_NOSEC_RE`` anchors the directive at end-of-line, so anything written
    after it lands in the names group and stops being a reason. A directive
    with nothing in front of it is an unexplained silencing.
    """
    assert directive["reason"], (
        f"{directive['path']}:{directive['line']} has a `# specproof-nosec` "
        "with no reason in front of it"
    )


def test_the_repo_reports_no_critical_or_high_finding() -> None:
    """The repo's secret posture: no CRITICAL/HIGH anywhere the scanner reads.

    This is the gate a *missing* directive fails. It also proves the walk is
    not over-pruning: a scan that read almost nothing would trivially pass.
    """
    result = scan_directory(str(PROJECT_ROOT))
    severe = [f for f in result.findings if f.severity in ("CRITICAL", "HIGH")]
    assert result.scanned_files > 1000, (
        f"only {result.scanned_files} files scanned — the walk is over-pruning, "
        "so a clean result here would mean nothing"
    )
    assert severe == [], "\n".join(
        f"  [{f.severity}] {f.path}:{f.line} — {f.pattern_name}" for f in severe
    )


def test_finding_paths_use_forward_slashes(tmp_path: Path) -> None:
    """`SecurityFinding.path` must be spelled the way git spells changed files.

    `craft/gates.py` and `craft/verify.py` attribute findings to changed files
    with ``entry.path not in changed_set``, and ``changed`` comes from git diff —
    always forward-slashed. The scan used to build the relative path with
    ``str(Path.relative_to(...))``, which is back-slashed on Windows, so on this
    OS *every* finding failed that membership test and the "only changed files
    block" rule quietly became "nothing blocks".

    A regression here is invisible on Linux and total on Windows, which is why
    it gets its own fence rather than riding on the posture gate.
    """
    nested = tmp_path / "apps" / "web"
    nested.mkdir(parents=True)
    (nested / "a.ts").write_text('api_key: "sk-' + "a" * 40 + '"\n', encoding="utf-8")

    result = scan_directory(str(tmp_path))

    assert result.findings, "expected the planted key to be reported"
    for finding in result.findings:
        assert "\\" not in finding.path, (
            f"{finding.path!r} uses a backslash; it will never match a git "
            "changed-file path on Windows"
        )
        assert finding.path == "apps/web/a.ts"
