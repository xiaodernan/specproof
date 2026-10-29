"""Shared import-graph resolution for the reachability claims.

Three shipped docstrings say "Nothing on the existing call path imports this module".
The only honest ruler for that sentence is a graph, not a grep — and building one
showed why the greps keep being wrong. #522's first census looked at nothing but
`node.level == 0` imports and reported `providers/client_policy.py`,
`providers/probe_result.py` and `providers/responses_protocol.py` as imported by
nobody in product code. All three were artifacts of the grammar:
`providers/openai_compatible.py` reaches its policy layer with
`from .client_policy import ClientPolicy` — a level-1 relative import the census could
not see. Measured over the tree, eight test files already parse imports with their own
loop and exactly one of them does PEP 328 anchor arithmetic; the others either drop
relative edges or record `.router` as a top-level module literally named ``router``.

So the resolution lives here once, for the same reason `tests/_scan_walk.py` exists:
two hand-written grammars about the same tree is the drift this repo fences against.
And living here means inheriting that walk's exclusions, which is how this module found
a second one: `PRUNE_DIRS` listed the exact name `.venv`, this tree's virtualenv is
called `.venv312`, and the first graph this module built was walked from **7,341** files
of which **6,141** lived under `.venv312/` — and `classify_root()` then still had no
`unrooted` bucket, so every one of them was counted as product code. #443 had already
fixed that prefix family on the scanner side; the shared walk simply predated the fix. Two
independent fences close it now — the walk prunes the family by prefix, and a module
whose first path segment is empty is `unrooted` rather than product — which is why
`test_unwired_layer_claims_match_the_import_graph.py` pins both, and why it pins
"no walked file is dropped from the graph" instead of quoting a module count: every count
this file has carried in prose has since moved (1,199 → 1,200 → 1,197 in a fresh checkout,
1,202 in a working copy holding other lanes' untracked files), and a figure you can only
recover by re-running the census is not a claim about the code.

Two claims are kept apart on purpose, because the sentence in those docstrings
conflates them:

* **imported** — an edge exists in the graph (this module resolves it, relative or not);
* **reached at runtime** — the edge is at module top level rather than nested inside a
  function or a guard, and the call path from an entry root exists. `entry_roots()`
  derives them from `[project.scripts]` plus the server modules, so "the existing call
  path" is a checked list and not a mood.

A third distinction turned out to matter for the same reason: a module sitting at the
repository root is not part of the deployment either. `classify_root()` therefore answers
from the packages packaging can actually see (a directory with an `__init__.py`), and
files that are not under one — a dev-root script, or another lane's scratch file in a
working copy — land in their own bucket instead of being called product code by default.
"""

from __future__ import annotations

import ast
import functools
import tomllib
from collections import deque
from pathlib import Path

from tests._scan_walk import walk_files

REPO = Path(__file__).resolve().parents[1]

#: Roots that are not a deployment's own call path. `tests` reachability says a
#: capability has a sentinel, not that a job uses it; `ops`/`bench`/`scripts`/
#: `devtools`/`plugins` are operator- or tool-facing.
NON_PRODUCT_ROOTS = frozenset({"tests", "bench", "ops", "scripts", "devtools", "plugins"})

#: An import edge's two shapes. "top" fires at import time; "nested" is a runtime
#: question (a function body, a guarded block), so it is reported separately rather
#: than silently counted as wiring.
TOP = "top"
NESTED = "nested"

BUCKETS = ("product", "tests", "non_product", "unrooted")


@functools.cache
def local_package_roots(repo: Path = REPO) -> frozenset[str]:
    """Top-level directories packaging can see — a directory with an ``__init__.py``.

    Derived rather than written down for the same reason `shipped_packages()` in
    `test_packaging_ships_every_imported_package.py` derives the include list: an
    allow-list copied by hand is a list of the names someone remembered.

    Cached because `classify_root()` runs once per module per census and this tree has
    ~1,200 of them (1,197 in a fresh checkout at shipping time): un-cached, every leg of
    `test_unwired_layer_claims_match_the_import_graph.py` re-listed the repository root
    once per module (measured on one loaded machine: that leg alone took 58.8s of a 119s
    file, ~48,000 `stat` calls for a directory that does not change during a session).
    Keyed by `repo`, so a test that builds its own tree still measures its own tree.
    """
    return frozenset(
        child.name
        for child in repo.iterdir()
        if child.is_dir() and (child / "__init__.py").exists()
    )


def classify_root(dotted: str, repo: Path = REPO) -> str:
    """Which bucket a module belongs to, by the first segment of its path.

    ``unrooted`` is not a synonym for ``product``. It means "not under a package any
    distribution can import" — a dev-root script. On a clean tree it is empty; in a
    working copy with someone else's scratch files at the root it is exactly those, and
    reading it as product code would let a file that never ships satisfy a claim about
    the call path.
    """
    root = dotted.split(".")[0]
    if root == "tests":
        return "tests"
    if root in NON_PRODUCT_ROOTS:
        return "non_product"
    if root in local_package_roots(repo):
        return "product"
    return "unrooted"


def read(path: Path) -> str:
    """utf-8-sig, because CPython accepts a BOM and `utf-8` does not.

    The first census died on `tests/unit/test_eval_resume_reuses_measured_cases.py`,
    which ships with a BOM. A census that crashes on a real file has a hole in it, and
    the hole looks like a finding about the file.
    """
    return path.read_text(encoding="utf-8-sig")


def dotted_of(rel: str) -> str:
    dotted = rel[: -len(".py")].replace("/", ".")
    return dotted[: -len(".__init__")] if dotted.endswith(".__init__") else dotted


def package_of(rel: str) -> str:
    """The package a file sits in — the anchor a relative import is resolved against."""
    return ".".join(rel.split("/")[:-1])


def resolve(level: int, module: str | None, pkg: str) -> str:
    """PEP 328: level 1 is the current package, each extra level goes up one."""
    anchor = pkg
    for _ in range(level - 1):
        anchor = anchor.rpartition(".")[0]
    return f"{anchor}.{module}" if module else anchor


#: A node that puts an import behind a runtime decision rather than an import.
_NESTABLE = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.If, ast.Try, ast.With)


def imports_of(tree: ast.Module, pkg: str) -> list[tuple[str, str]]:
    """(resolved target, kind) for every import in the module.

    Both the module and each `from x import y` symbol are recorded, so a re-export
    through a package `__init__` still shows as an edge to the real home.
    """
    found: list[tuple[str, str]] = []

    def visit(node: ast.AST, depth: int) -> None:
        kind = TOP if depth == 0 else NESTED
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Import):
                found.extend((alias.name, kind) for alias in child.names)
            elif isinstance(child, ast.ImportFrom):
                base = (
                    child.module
                    if child.level == 0
                    else resolve(child.level, child.module, pkg)
                )
                if base:
                    found.append((base, kind))
                found.extend(
                    (f"{base}.{alias.name}" if base else alias.name, kind)
                    for alias in child.names
                )
            visit(child, depth + (1 if isinstance(child, _NESTABLE) else 0))

    visit(tree, 0)
    return found


def build_graph(repo: Path = REPO) -> dict[str, list[tuple[str, str]]]:
    """Every parseable ``*.py`` in the tree, keyed by dotted module name."""
    graph: dict[str, list[tuple[str, str]]] = {}
    for path, rel in walk_files(repo, frozenset({".py"})):
        try:
            tree = ast.parse(read(path))
        except SyntaxError:
            continue
        graph[dotted_of(rel)] = imports_of(tree, package_of(rel))
    return graph


def _module_named(target: str, graph: dict[str, list[tuple[str, str]]]) -> str | None:
    """Longest prefix of an import string that is actually a module in the graph."""
    parts = target.split(".")
    while parts:
        candidate = ".".join(parts)
        if candidate in graph:
            return candidate
        parts.pop()
    return None


def module_file_of(dotted: str, repo: Path = REPO) -> str:
    """The path a dotted module was read from, as ``a/b.py`` or ``a/b/__init__.py``.

    Rebuilding the path from the name is not enough: `providers` is a package, and the
    first version of `importers_of` reported its `__init__` re-export as a module
    literally called ``providers.py``.
    """
    as_module = repo / f"{dotted.replace('.', '/')}.py"
    if as_module.exists():
        return as_module.relative_to(repo).as_posix()
    return f"{dotted.replace('.', '/')}/__init__.py"


def importers_of(
    target: str,
    graph: dict[str, list[tuple[str, str]]] | None = None,
    repo: Path = REPO,
) -> dict[str, list[str]]:
    """Who imports ``target``, partitioned by product / tests / operator-facing code.

    Each entry is ``"<path>:<kinds>"`` where kinds is ``top``, ``nested`` or both, so a
    caller that cares about *wiring* can ignore the nested shape instead of pretending
    the two are the same fact.

    Empty ``product`` means *no import statement names this module*, which is not the
    same as *never executes*: ``import providers.base`` runs ``providers/__init__.py``
    without ever mentioning the package as an import target, so the graph shows
    ``providers`` with no importers while ``providers.base`` is strictly reachable. Read
    an empty list here as "nothing re-exports through it", never as "it is dead code".
    """
    graph = graph if graph is not None else build_graph(repo)
    out: dict[str, list[str]] = {bucket: [] for bucket in BUCKETS}
    for source, edges in graph.items():
        if source == target:
            continue
        kinds = {kind for raw, kind in edges if _module_named(raw, graph) == target}
        if not kinds:
            continue
        suffix = ",".join(sorted(kinds))
        out[classify_root(source, repo)].append(f"{module_file_of(source, repo)}:{suffix}")
    for bucket in out:
        out[bucket] = sorted(out[bucket])
    return out


def console_script_roots(repo: Path = REPO) -> list[str]:
    """The module part of every ``[project.scripts]`` entry — derived, not remembered."""
    data = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8-sig"))
    roots = []
    for target in (data.get("project", {}).get("scripts", {}) or {}).values():
        module = str(target).split(":")[0].strip()
        if module:
            roots.append(module)
    return sorted(set(roots))


def entry_roots(graph: dict[str, list[tuple[str, str]]] | None = None) -> list[str]:
    """The deployment's own entry points: the console script plus the served modules.

    `api.server` and `mcp.server` cannot be derived from packaging metadata — they are
    started by `python -m uvicorn api.server:app` and as an stdio MCP server — so they
    are listed here and each one is *checked* to exist in the graph by the gate that
    uses this, which is what keeps the list from rotting into fiction.
    """
    graph = graph if graph is not None else build_graph()
    listed = [*console_script_roots(), "api.server", "mcp.server"]
    return sorted({root for root in listed if root in graph})


def reachable_from(
    roots: list[str],
    graph: dict[str, list[tuple[str, str]]],
    kinds: frozenset[str] = frozenset({TOP}),
) -> dict[str, list[str]]:
    """BFS over resolved edges: module -> the path that first reached it.

    The default follows top-level edges only, because a nested import is not wiring —
    following it would let a function body claim a call path for the module containing
    it. Passing ``frozenset({TOP, NESTED})`` gives the other question, which is worth
    having separately: "can a deployment reach this at all, if some branch is taken".
    A module absent from the loose set has no reachable edge in either shape, and that
    is the only finding strong enough to write the word *nothing* about.
    """
    seen: dict[str, list[str]] = {root: [] for root in roots if root in graph}
    queue = deque(sorted(seen))
    while queue:
        current = queue.popleft()
        for raw, kind in graph.get(current, []):
            if kind not in kinds:
                continue
            nxt = _module_named(raw, graph)
            if nxt is None or nxt in seen:
                continue
            seen[nxt] = seen[current] + [current]
            queue.append(nxt)
    return seen
