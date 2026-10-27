"""The ledger's queue pointers must resolve, and the free-port probe must have ONE owner.

Two gates, one file, because they are the two halves of the same #475 unit.

GATE 1 — a queue pointer must resolve.
----------------------------------------
The ledger's "下一号队列" blocks are instructions for the next lane. A pointer
in one that names a file which does not exist is an instruction nobody can
follow, and a lane that follows it anyway either stalls or invents the file.
Measured before writing: of the 724 path-like tokens the ledger names, 4 sit
inside a queue block, and **one** of them names a file that has never existed
in git — ``agent/multi_port.py``, in the #429 queue line. The other three are
``.scratch/`` working notes and one doc that exists but is untracked.

The ruler had to be measured before it was chosen, because the obvious one
(worktree-relative path exists) is a false-positive machine: its 55 "misses"
were mostly relative shorthands (``commands/demo.py``, ``pages/Dashboard.tsx``),
ellipsis forms (``.../cli/...``), synthetic probe paths inside a test
scenario (``app/my_tests/helper.py``), third-party paths inside site-packages,
and language lists (``Rust/Python/Go/Node.js``). Two rulers were rejected for
exactly that reason before this one was chosen.

This ruler resolves a reference by SUFFIX against the tree (component-wise),
so a shorthand still resolves, and it EXEMPTS three shapes the repo itself
uses, each for a stated reason:
  * ``.scratch/...`` — the ledger's own working area. The project's other
    census gates skip it too (test_subprocess_text_encoding.py's SKIP_DIRS
    lists ".scratch"), so a pointer into it is a working note, not a promise
    about a shipped file.
  * ``.local/...`` — the operator's local config/secrets area.
  * a leading ``...`` — a deliberate shorthand for "some path above here".

GATE 2 — the free-port probe has one owner.
------------------------------------------
The probe that asks the OS for a free port was written THREE times: twice
under a name (``_free_port`` in two files, byte-identical bodies) and once
inline. The census that reads port provenance (#427's) resolved those calls
inside the calling file, so a copy that is fixed in one file and not the
other would make one gate certify the wrong thing about the product.

#475 moved the probe into ``tests/unit/port_probe.py`` and taught the census
to follow a call into an audited owner. This gate pins the result: the probe
shape (binds 0 AND reads the number back — the census's own rule) must be
defined exactly ONCE in the tree, and it must be that owner.

A gate nobody has seen red is not a gate, so both rules are exercised below on
synthetic input as well as on the real artefacts.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
#: The ledger the gate reads. Overridable so the mutation arms can run
#: against a COPY: this ledger is a shared work tree that other lanes append
#: to, and an arm that mutated the live file would risk clobbering their
#: section (or being clobbered by it).
LEDGER = Path(
    os.environ.get(
        "SPECPROOF_LEDGER_PATH",
        ROOT / "docs" / "operations" / "DEEP_OPTIMIZATION_PLAN.md",
    )
)

#: The audited owner of the free-port probe.
OWNER = "tests/unit/port_probe.py"
OWNER_MODULE = "tests.unit.port_probe"

#: The census that reads port provenance, and the list of owners it may follow.
CENSUS = ROOT / "tests" / "unit" / "test_scrape_roster_ports_answer_their_own_numbers.py"

#: A path-like token: a slash, a known extension, no spaces, no globs.
PATH = re.compile(
    r"(?<![\w./-])"
    r"((?:[\w.-]+/)+[\w.-]+\.(?:py|md|yml|yaml|toml|json|txt|sh|ps1|xml|ini|cfg|html|ts|tsx|js))"
    r"(?![\w/])"
)

#: Shapes the repo itself uses that are NOT promises about a shipped file.
EXEMPT_PREFIXES = {
    ".scratch/": "the ledger's own working area (other census gates skip it too)",
    ".local/": "the operator's local config/secrets area",
}

#: A line that says a path is ABSENT is recording a correction, not pointing
#: at a file. Without this the ledger cannot write down "that file never
#: existed" — which is exactly the correction #475 had to make — and the gate
#: would charge the correction for the very absence it reports.
ABSENT_MARKERS = ("从未存在", "不存在", "已删除", "幽灵", "空指针", "0 命中")

SKIP_DIRS = {
    ".git", ".venv", ".venv312", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".scratch", "node_modules", "dist", "build", "site-packages",
}


# --------------------------------------------------------------------------
# the ledger's queue blocks
# --------------------------------------------------------------------------


def queue_lines(text: str) -> set[int]:
    """Line numbers inside a "下一号队列" block.

    A block runs from its heading until a blank line or the next heading, so
    the bullets under it are the instructions and the prose after it is not.
    """
    out: set[int] = set()
    inside = False
    for i, line in enumerate(text.splitlines(), start=1):
        if "下一号队列" in line or line.strip().startswith("**下一号"):
            inside = True
            out.add(i)
            continue
        if inside:
            if not line.strip() or line.startswith(("## ", "### ")):
                inside = False
                continue
            out.add(i)
    return out


def path_refs(text: str) -> dict[str, list[int]]:
    """Every path-like token in the text, with the LINES that name it.

    A line is listed once per path, however many times the path appears on
    it — a line that names the same file three times is one line, not three
    instructions.
    """
    out: dict[str, set[int]] = {}
    for i, line in enumerate(text.splitlines(), start=1):
        for m in PATH.finditer(line):
            out.setdefault(m.group(1), set()).add(i)
    return {path: sorted(lines) for path, lines in out.items()}


def tree_files(root: Path) -> list[str]:
    """Every file in the tree, relative and POSIX-separated.

    Walks with PRUNING: ``rglob`` descends into every virtualenv on the disk
    and only discards the files afterwards, which cost this gate 158s on the
    first run. A skipped directory must not even be opened — the same rule
    the repo's other census gates already follow.
    """
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel = Path(dirpath).relative_to(root)
        for name in filenames:
            out.append((rel / name).as_posix())
    return out


def resolves(ref: str, files: list[str]) -> bool:
    """Whether the reference names a file that is really there.

    Suffix resolution, component-wise: ``commands/demo.py`` resolves to
    ``cli/specproof/commands/demo.py`` and ``agent/util.ts`` to
    ``apps/web/src/agent/util.ts``.
    """
    if ref in files:
        return True
    parts = ref.split("/")
    n = len(parts)
    return any(f.split("/")[-n:] == parts for f in files)


def is_exempt(ref: str) -> bool:
    return ref.startswith("...") or ref.startswith("…") or any(
        ref.startswith(pfx) for pfx in EXEMPT_PREFIXES
    )


def records_an_absence(line: str) -> bool:
    """Whether this line says a path is ABSENT (a correction, not a pointer)."""
    return any(marker in line for marker in ABSENT_MARKERS)


def unresolved_queue_pointers(text: str, files: list[str]) -> list[tuple[str, int]]:
    """Every path in a queue block that names nothing, with its line."""
    blocks = queue_lines(text)
    lines = text.splitlines()
    out: list[tuple[str, int]] = []
    for ref, where in path_refs(text).items():
        if is_exempt(ref) or resolves(ref, files):
            continue
        for line in where:
            if line in blocks and not records_an_absence(lines[line - 1]):
                out.append((ref, line))
    return sorted(out)


# --------------------------------------------------------------------------
# the free-port probe's shape
# --------------------------------------------------------------------------


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute):
            return func.attr
        if isinstance(func, ast.Name):
            return func.id
    return None


def is_probe(fn: ast.FunctionDef) -> bool:
    """The census's own rule: binds 0 AND reads the number back.

    Either half alone would let a leg that really picked a fixed number
    certify itself as kernel-chosen.
    """
    binds_zero = any(
        isinstance(node, ast.Call)
        and _call_name(node) == "bind"
        and any(
            isinstance(sub, ast.Constant) and sub.value == 0
            for arg in node.args
            for sub in ast.walk(arg)
        )
        for node in ast.walk(fn)
    )
    reads_back = any(
        isinstance(node, ast.Attribute) and node.attr == "getsockname"
        for node in ast.walk(fn)
    )
    return binds_zero and reads_back


def probe_definitions(root: Path) -> list[tuple[str, int, str]]:
    """Every (file, line, name) that defines the probe shape."""
    out: list[tuple[str, int, str]] = []
    for rel in tree_files(root):
        if not rel.endswith(".py"):
            continue
        try:
            tree = ast.parse((root / rel).read_bytes())
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and is_probe(node):
                out.append((rel, node.lineno, node.name))
    return sorted(out)


# --------------------------------------------------------------------------
# GATE 1 — queue pointers resolve
# --------------------------------------------------------------------------

LEDGER_TEXT = LEDGER.read_text(encoding="utf-8")
FILES = tree_files(ROOT)


def test_the_ledger_queue_blocks_were_found() -> None:
    """A collapsed parse must not read as "no violations"."""
    blocks = queue_lines(LEDGER_TEXT)
    assert len(blocks) >= 10, f"only {len(blocks)} queue lines found — the lens changed shape"
    refs = path_refs(LEDGER_TEXT)
    assert len(refs) >= 100, f"only {len(refs)} path references parsed"


def test_every_queue_pointer_resolves() -> None:
    """The red this unit closes: ``agent/multi_port.py`` never existed."""
    bad = unresolved_queue_pointers(LEDGER_TEXT, FILES)
    assert not bad, (
        "these queue pointers name a file that is not there, so the instruction "
        "cannot be followed:\n  "
        + "\n  ".join(f"{ref} (line {line})" for ref, line in bad)
    )


def test_a_phantom_pointer_is_refused() -> None:
    """Reverse control: the ruler must be able to say no."""
    fragment = (
        "## #900 下一号队列\n"
        "- **#901**: 修 `agent/does_not_exist.py` 的读法。\n"
    )
    bad = unresolved_queue_pointers(fragment, FILES)
    assert bad == [("agent/does_not_exist.py", 2)], bad


def test_a_pointer_outside_a_queue_block_is_not_charged() -> None:
    """The scope matters: a prose mention is not an instruction."""
    fragment = "## #900\n\n正文提到 `agent/does_not_exist.py` 这个文件。\n"
    assert unresolved_queue_pointers(fragment, FILES) == []


def test_the_exempt_shapes_are_exempt() -> None:
    fragment = (
        "## #900 下一号队列\n"
        "- `.scratch/arm900.py` 的臂表。\n"
        "- `.../cli/specproof/commands/eval.py` 的路径。\n"
        "- `.local/llm.json` 的凭据。\n"
    )
    assert unresolved_queue_pointers(fragment, FILES) == []


def test_a_line_recording_an_absence_is_not_a_pointer() -> None:
    """The ledger must be able to write down "that file never existed".

    Without this, the correction #475 had to make would be charged for the
    very absence it reports — the gate would fire on the fix.
    """
    fragment = (
        "## #900 下一号队列\n"
        "- `agent/multi_port.py` 从未存在（`git log --all` 0 命中），已收口。\n"
    )
    assert unresolved_queue_pointers(fragment, FILES) == []


def test_a_pointer_line_without_an_absence_marker_is_still_charged() -> None:
    """The exemption is the MARKER, not the queue block."""
    fragment = (
        "## #900 下一号队列\n"
        "- `agent/multi_port.py` L15 的读法要看。\n"
    )
    assert unresolved_queue_pointers(fragment, FILES) == [("agent/multi_port.py", 2)]


# --------------------------------------------------------------------------
# GATE 2 — the free-port probe has one owner
# --------------------------------------------------------------------------


def test_the_free_port_probe_has_exactly_one_owner() -> None:
    """The duplication this unit closed: three copies, byte-identical."""
    found = probe_definitions(ROOT)
    assert len(found) == 1, (
        f"the free-port probe is defined {len(found)}x — one fact, one owner:\n  "
        + "\n  ".join(f"{rel}:{line} {name}()" for rel, line, name in found)
    )
    rel, _, name = found[0]
    assert rel == OWNER, f"the probe's owner is {rel}, expected {OWNER}"
    assert name == "free_port", f"the owner's function is {name}()"


def test_the_census_names_an_owner_that_exists() -> None:
    """The census may only follow modules that are really there."""
    source = CENSUS.read_text(encoding="utf-8")
    match = re.search(r"_SHARED_OWNER_MODULES\s*=\s*\((.*?)\)", source, re.S)
    assert match is not None, "the census no longer declares _SHARED_OWNER_MODULES"
    modules = re.findall(r'"([^"]+)"', match.group(1))
    assert modules, "the census's owner list is empty — every cross-file call is blind again"
    for module in modules:
        path = ROOT / Path(*module.split(".")).with_suffix(".py")
        assert path.is_file(), f"the census may follow {module}, which does not exist"
    assert OWNER_MODULE in modules, (
        f"the census does not follow {OWNER_MODULE}, so a call into the owner "
        "would be charged as blind"
    )


def test_the_owner_defines_what_the_census_looks_up() -> None:
    """The census resolves the owner's OWN name, so the owner must define it."""
    source = (ROOT / OWNER).read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "free_port" in names, f"{OWNER} defines {sorted(names)}"


def test_a_second_probe_definition_would_be_refused() -> None:
    """Reverse control: the shape census must reject a duplicate."""
    duplicate = (
        "import socket\n"
        "def _free_port() -> int:\n"
        "    probe = socket.socket()\n"
        "    probe.bind(('127.0.0.1', 0))\n"
        "    port = int(probe.getsockname()[1])\n"
        "    probe.close()\n"
        "    return port\n"
    )
    tree = ast.parse(duplicate)
    probes = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and is_probe(n)]
    assert len(probes) == 1, probes
    # and the census's rule needs BOTH halves
    no_read_back = (
        "import socket\n"
        "def _free_port() -> int:\n"
        "    probe = socket.socket()\n"
        "    probe.bind(('127.0.0.1', 0))\n"
        "    probe.close()\n"
        "    return 12345\n"
    )
    tree2 = ast.parse(no_read_back)
    assert not [
        n for n in ast.walk(tree2) if isinstance(n, ast.FunctionDef) and is_probe(n)
    ], "a helper that binds 0 but never reads the number back is not the probe"
