"""Gate: every path an evidence document cites must be one the repository carries.

WHY THIS EXISTS.  The ledger's own evidence gate has policed the LEDGER's
evidence blocks since #476 — "a record's evidence must be real", and "a path
that exists only on this machine is not carried".  The stand-alone documents
under ``docs/evidence/`` were never covered by that gate, and they drifted.
The 2026-11-23 census found **five** citations the repository does not carry:

  * ``stress-2026-11-19.md`` cited the k6 script of that run under
    ``%TEMP%\\opencode\\stress-8027.js`` — a path that exists on exactly one
    machine, in a directory nobody else has;
  * ``audit-chain.md`` credited ``agent/graphs/audit_graph.py`` — the file is
    ``auditor_graph.py``;
  * ``gazette-feature.md`` cited ``pages/Observe.tsx`` — the file is
    ``apps/web/src/pages/Observe.tsx``;
  * ``weekly-2026-11-18-weekly-out.md`` cited its report artifact twice
    under the harness's temp-suffix name, which was committed under a
    date-named file instead.

A path the repository does not carry is not evidence: it cannot be opened,
it cannot be re-run, and the next reader goes looking for a file that was
never there.  The rule is the ledger's rule — applied to the documents the
ledger's rule never reached.

THE RULES, each one sentence:

  R1  the census is not collapsed — the scanner must find the documents and
      the citations, or every rule below passes vacuously;
  R2  no evidence document may cite a path that exists only on this machine
      (a drive letter, a home directory, a temp directory);
  R3  every repository-relative path an evidence document cites must be one
      the repository carries (tracked, or declared generated) — the SAME
      rule, and the SAME owner, as the ledger's evidence gate;
  R4  the ruler must still see — a synthetic machine-local citation and a
      synthetic missing path are both caught, so a scanner that quietly
      stopped matching fails instead of passing.

WHAT THIS GATE DOES NOT SAY.  It says nothing about whether a measurement
was good, only about whether the thing it names can be opened and re-run.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.unit.test_ledger_evidence_claims_are_true import RepoPaths

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE_DIR = ROOT / "docs" / "evidence"

#: An extension that means "this token names a file".  The ruler demands one:
#: a first pass that accepted "anything with a slash" charged `768/768`,
#: `zh/en` and `11/11` as paths, and a ruler wider than the thing it measures
#: is the named failure mode in this repository.
_EXT = (
    r"(?:py|js|mjs|cjs|ts|tsx|jsx|json|md|yml|yaml|sh|ps1|css|scss|html|htm"
    r"|jar|txt|log|csv|tsv|xml|ini|cfg|toml|sql|go|java|kt|rb|rs|php)"
)
#: A relative path: at least one directory separator, then a file name.
_RELATIVE = re.compile(rf"(?<![\w./\\-])(?:[\w.\-]+[\\/])+[\w.\-]+\.{_EXT}\b")
#: An absolute Windows path.
_ABSOLUTE_WIN = re.compile(rf"(?<![\w])([A-Za-z]:[\\/][\w.\\ -]*?\.{_EXT})\b")
#: A POSIX absolute path.
_ABSOLUTE_POSIX = re.compile(rf"(?<![\w])(/(?:[\w.\-]+/)*[\w.\-]+\.{_EXT})\b")
#: A Windows home directory written with forward slashes.
_HOME_FWD = re.compile(rf"(?<![\w])(Users/[\w.\-]+(?:/[\w.\-]+)*\.{_EXT})\b")
#: A tilde path.
_TILDE = re.compile(rf"(?<![\w])(~/(?:[\w.\-]+/)*[\w.\-]+\.{_EXT})\b")

#: A path rooted where only ONE machine has it.
_MACHINE_LOCAL = re.compile(
    r"^(?:[A-Za-z]:[\\/]|/home/|/Users/|/var/tmp/|/tmp/|~|Users/)"
)


#: A placeholder that stands for the repository root.  The path after it is
#: a repository path, and the scanner has to SEE it: the first version of the
#: lookbehind refused a match preceded by "/", so every ``<repo>/...``
#: citation escaped the gate whole.
_PLACEHOLDER = re.compile(r"(?:<repo(?:sitory)?>|\$\{REPO\}|\bREPO)[/\\]")


def citations(text: str) -> list[tuple[str, int]]:
    """``(path, line)`` for every path-shaped token in a document.

    URLs are not paths: ``http://127.0.0.1:8027`` is an address, and a
    document that shows a live port is not making a claim about a file.
    """
    found: list[tuple[str, int]] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        scrubbed = re.sub(r"https?://\S+", " ", line)
        scrubbed = _PLACEHOLDER.sub(" ", scrubbed)
        for pattern in (_ABSOLUTE_WIN, _ABSOLUTE_POSIX, _HOME_FWD, _TILDE,
                        _RELATIVE):
            for match in pattern.finditer(scrubbed):
                found.append((match.group(1) if match.groups() else match.group(0),
                              lineno))
    return found


def is_machine_local(path: str) -> bool:
    return bool(_MACHINE_LOCAL.match(path))


def is_repository_relative(path: str) -> bool:
    """Whether this path is a repo-relative one that git can be asked about.

    A path outside the repository (a POSIX absolute path, a drive letter) is
    NOT this gate's business for R3: `git check-ignore` refuses to even
    answer for a path outside the work tree ("is outside repository at"),
    and a probe that raises instead of answering is a BROKEN probe, not a
    red one.  R2 is where an absolute path is judged.
    """
    if not path or path.startswith(("/", "\\")):
        return False
    if is_machine_local(path):
        return False
    return ":" not in path.split("/")[0]


def documents() -> list[Path]:
    return sorted(EVIDENCE_DIR.glob("*.md"))


def all_citations() -> list[tuple[str, str, int]]:
    """``(document, path, line)`` for every citation in every document."""
    out: list[tuple[str, str, int]] = []
    for doc in documents():
        text = doc.read_text(encoding="utf-8", errors="replace")
        for path, lineno in citations(text):
            out.append((doc.name, path, lineno))
    return out


#: The repository's own file set — the SAME owner as the ledger's gate.
REPO = RepoPaths(ROOT)


# ---------------------------------------------------------------------------
# R1  the census is not collapsed
# ---------------------------------------------------------------------------


def test_the_evidence_document_census_is_not_collapsed() -> None:
    """R1 — a census that finds nothing is greener than a bug."""
    docs = documents()
    assert len(docs) >= 20, (
        f"only {len(docs)} evidence documents under {EVIDENCE_DIR.name}/ — the "
        "census is not reading what it is meant to read"
    )
    claims = all_citations()
    assert len(claims) >= 25, (
        f"only {len(claims)} path citations found across {len(docs)} documents "
        "— the scanner stopped matching"
    )
    names = {name for name, _p, _l in claims}
    assert len(names) >= 10, (
        f"the citations come from only {len(names)} document(s): {sorted(names)}"
    )


# ---------------------------------------------------------------------------
# R2  no machine-local path
# ---------------------------------------------------------------------------


def test_no_evidence_document_cites_a_path_that_exists_only_on_this_machine() -> None:
    """R2 — a path under %TEMP% is not evidence for anybody else."""
    offenders = [
        f"{name}:{lineno}  {path}"
        for name, path, lineno in all_citations()
        if is_machine_local(path)
    ]
    assert not offenders, (
        "these evidence documents cite a path that exists only on this "
        "machine:\n  " + "\n  ".join(offenders)
        + "\nA reader on another machine cannot open it, and a reader on this "
          "machine cannot re-run it either.  Cite the tool the repository "
          "carries."
    )


# ---------------------------------------------------------------------------
# R3  a cited path must be one the repository carries
# ---------------------------------------------------------------------------


def test_every_cited_path_is_carried_by_the_repository() -> None:
    """R3 — the ledger's rule, applied to the documents it never reached."""
    claims = [(name, path, line) for name, path, line in all_citations()
              if is_repository_relative(path)]
    carried = REPO.carries(path for _name, path, _line in claims)
    offenders = [
        f"{name}:{lineno}  {path}"
        for name, path, lineno in claims
        if path not in carried
    ]
    assert not offenders, (
        "these evidence documents cite a path the repository does not carry:\n  "
        + "\n  ".join(offenders)
        + "\nA misspelled module, a truncated path, or a report artifact that "
          "was committed under another name are all the same defect: the "
          "reader is sent to a file that was never there."
    )


# ---------------------------------------------------------------------------
# R4  the ruler must still see
# ---------------------------------------------------------------------------


def test_the_scanner_catches_a_machine_local_path_and_a_missing_path() -> None:
    """R4 — a ruler that cannot fail proves nothing."""
    synthetic = (
        "The run used `C:/Users/someone/AppData/Local/Temp/run/stress.js`\n"
        "and `agent/graphs/audit_graph.py`.\n"
    )
    found = [path for path, _lineno in citations(synthetic)]
    assert any(is_machine_local(path) for path in found), (
        f"the scanner no longer sees a machine-local path: {found}"
    )
    assert "agent/graphs/audit_graph.py" in found, (
        f"the scanner no longer sees a repository-relative path: {found}"
    )
    # and the missing path is NOT carried, so R3 would catch it
    assert is_repository_relative("agent/graphs/audit_graph.py")
    carried = REPO.carries(["agent/graphs/audit_graph.py"])
    assert "agent/graphs/audit_graph.py" not in carried, (
        "the witness path is now carried by the repository — the witness no "
        "longer proves anything; pick a path that does not exist"
    )
