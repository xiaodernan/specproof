"""Gate: every tracked file must survive its own encoding.

WHAT WAS MEASURED (before this gate existed).  Two tracked files are
**UTF-16LE** — `docs/architecture/requirements-frozen-20260820.txt` (the
frozen `pip freeze` snapshot, 172 lines) and `docs/eval/unit-report.txt`
(a pytest session log) — while every other tracked file is UTF-8.  The
signature is `FF FE` followed by every second byte zero: the shape a
Windows shell redirection leaves behind (PowerShell 5.1 writes UTF-16LE).

The frozen snapshot is the one with a consequence: it is a
`requirements.txt`, and **pip reads requirements files as UTF-8** — so the
file that exists to pin the environment cannot be read by the tool that
would install from it.  The evaluation log is the same class: a log nobody
can grep.

And the ledger itself had lost nine characters to U+FFFD (the replacement
character), across four lines, which is damage in an audit trail.

WHY A GATE AND NOT A FIX.  The encoding of a file is decided once, by
whatever wrote it, and nothing in this repository looked at it again.  A
file can go back to UTF-16 without anybody noticing — that is exactly the
class this repository's gates exist for.

THE RULES:

  R1  the census is not collapsed.  A census that finds nothing reads as
      "no problem", and this repository has been bitten by that shape
      before.
  R2  every tracked file DECODES as UTF-8 — unless its suffix is in the
      binary registry, and that registry says why.  A new binary format
      (a ``.tar``, say) has to be declared with a reason; a new text format
      needs no declaration at all.
  R3  an exemption that is no longer needed is stale: a file in the binary
      registry that now decodes as UTF-8 means the registry is lying.
  R4  no tracked text file carries U+FFFD.  A replacement character is
      lossy damage: the character it replaced is gone, and in an audit
      trail a hole is not a formatting choice.
  R5  the frozen dependency snapshot is a requirements file pip can read:
      every non-empty line is ``name==version``.  R2 says "it decodes";
      this says "the tool that needs it can use it".

WHAT THIS GATE DOES NOT SAY.  It says nothing about line endings.  Encoding
and line endings are two different questions — an arm harness of mine once
reported a line-ending difference as a fidelity failure, and the mistake
was worth this sentence.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Suffixes whose content is bytes.  Each one says why it is exempt —
#: an exemption without a reason is a hole with a name on it.
BINARY_SUFFIXES: dict[str, str] = {
    ".zip": "a frozen artifact bundle — bytes, not text",
    ".png": "an image",
    ".bundle": "a Gradle bundle — bytes, not text",
    ".jar": "the Maven wrapper jar — bytes, not text",
}

#: The frozen pip snapshot — the file whose encoding has a consequence.
FROZEN_SNAPSHOT = "docs/architecture/requirements-frozen-20260820.txt"

_REQUIREMENT_LINE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*==[^\s]+$")


def _tracked() -> list[str]:
    """The tracked paths, read as BYTES.

    Decoding the listing as text is itself a trap: this repository has
    paths whose bytes are not valid in the console's code page, and a
    listing that cannot be decoded is a listing that finds nothing.
    """
    raw = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT,
                         capture_output=True).stdout
    return [p.decode("utf-8", "surrogateescape") for p in raw.split(b"\0") if p]


def _read(rel: str) -> bytes | None:
    path = ROOT / rel
    if not path.is_file():
        return None
    return path.read_bytes()


def test_the_census_is_not_collapsed() -> None:
    """R1 — a census that finds nothing is greener than a bug."""
    files = _tracked()
    assert len(files) >= 2000, (
        f"the tracked-file census collapsed: {len(files)} files — the listing "
        f"is not being read"
    )
    text_files = [f for f in files if Path(f).suffix.lower() not in BINARY_SUFFIXES]
    assert len(text_files) >= 2000, (
        f"the text-file census collapsed: {len(text_files)} of {len(files)} "
        f"files — the binary registry now claims nearly everything"
    )


def test_every_tracked_file_decodes_as_utf8() -> None:
    """R2 — one encoding for the whole repository."""
    offenders: list[str] = []
    for rel in _tracked():
        if Path(rel).suffix.lower() in BINARY_SUFFIXES:
            continue
        raw = _read(rel)
        if raw is None:
            continue
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            window = raw[max(0, exc.start - 16):exc.start + 16]
            offenders.append(
                f"{rel}: {exc.reason} at byte {exc.start}; around it: {window!r}"
            )
    assert not offenders, (
        "these tracked files do not decode as UTF-8:\n  "
        + "\n  ".join(offenders)
        + "\nA file written through a Windows redirection lands in UTF-16LE "
          "(FF FE, then every second byte zero), and a tool that reads it as "
          "UTF-8 sees garbage.  If the file really is binary, declare its "
          "suffix in BINARY_SUFFIXES with the reason."
    )


def test_a_binary_exemption_is_never_stale() -> None:
    """R3 — an exemption that is no longer needed is a lie waiting to be found."""
    stale: list[str] = []
    for rel in _tracked():
        suffix = Path(rel).suffix.lower()
        if suffix not in BINARY_SUFFIXES:
            continue
        raw = _read(rel)
        if raw is None:
            continue
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        stale.append(
            f"{rel} ({suffix}: {BINARY_SUFFIXES[suffix]}) now decodes as UTF-8 — "
            f"the exemption is not needed any more"
        )
    assert not stale, "\n".join(stale)


def test_no_tracked_text_file_carries_a_replacement_character() -> None:
    """R4 — a hole in an audit trail is damage, not formatting."""
    offenders: list[str] = []
    for rel in _tracked():
        if Path(rel).suffix.lower() in BINARY_SUFFIXES:
            continue
        raw = _read(rel)
        if raw is None:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue      # leg R2 already reports the file
        for lineno, line in enumerate(text.splitlines(), 1):
            if "\ufffd" in line:
                offenders.append(f"{rel}:{lineno}  {line.strip()[:120]}")
    assert not offenders, (
        "these tracked files carry U+FFFD (the replacement character — the "
        "character it stood for is gone):\n  " + "\n  ".join(offenders)
    )


def test_the_frozen_snapshot_is_a_requirements_file_pip_can_read() -> None:
    """R5 — the tool that needs the file must be able to use it."""
    path = ROOT / FROZEN_SNAPSHOT
    assert path.is_file(), f"{FROZEN_SNAPSHOT} is missing"
    raw = path.read_bytes()
    text = raw.decode("utf-8")       # a UnicodeDecodeError here is the answer
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    assert lines, f"{FROZEN_SNAPSHOT} is empty"
    bad = [line for line in lines if not _REQUIREMENT_LINE.match(line)]
    assert not bad, (
        f"{FROZEN_SNAPSHOT} holds {len(bad)} line(s) that are not "
        f"`name==version`: {bad[:5]} — pip would refuse this file, and the "
        f"file exists to be installed from"
    )
