"""#522 — three shipped sentences said "Nothing on the existing call path imports this
module", and a resolved import graph says all three were false as written.

`providers/resilience.py`, `providers/semantic_cache.py` and `providers/router.py` each
carried that sentence in their module docstring. The intent behind it was sound — none
of the three is *turned on* unless an operator asks — but the sentence is about imports,
and imports are measurable. Measured, over a graph that resolves relative edges and
derives its entry roots from packaging:

* ``providers.resilience`` is imported at module top level by
  ``integrations/notify/webhook.py``, which calls :func:`classify_retry` on every failed
  notification send, and by ``providers/client_policy.py``;
* ``providers.router`` and ``providers.semantic_cache`` are both imported at module top
  level by ``craft/loop.py`` and by ``providers/client_policy.py``;
* all three are reachable from an entry root following **top-level edges only**, so they
  are on the deployment's import path even under the strictest reading.

What is actually true, and what the docstrings now say instead, is about *construction*:
the only product site that builds a ``ModelRouter``, a ``RetryPolicy`` or a
``SemanticCache`` is ``providers/client_policy.py``, behind
``SPECPROOF_PROVIDER_POLICY=1``, and no product call site hands ``CraftLoop`` a
``router=`` or a ``semantic_cache=`` — so those branches stay inert and the loop's
``router_fallback_count`` / ``cache_hits`` are measured zeros. A wrong sentence about a
real switch costs nothing; a wrong sentence that *replaces* the switch is how an
unwired capability gets advertised as a delivered one.

Building the ruler found three more grammar holes, each with a reverse control below,
because every one of them silently changed an answer rather than crashing:

* **relative edges**: a census that filters ``node.level == 0`` reports
  ``providers/client_policy.py`` as imported by no product code, when
  ``providers/openai_compatible.py`` reaches it with ``from .client_policy import`` — the
  edge exists and is on the strict path. #517's own dependency leg had that filter, and
  it is fixed there;
* **line-wrapped prose**: a line-local search for the claim phrase finds 1 of the 3
  modules; two of them wrap "the existing" across a newline;
* **the walk's exclusions**: ``tests/_scan_walk.PRUNE_DIRS`` listed the exact name
  ``.venv`` while this tree's virtualenv is ``.venv312``, so the first graph this file
  was written against walked **7,341** files of which **6,141** lived under
  ``.venv312/`` — and ``classify_root()`` had no ``unrooted`` bucket yet, so a deny-list
  called every one of them product code. ``agent/security_scanner.py`` fixed that prefix
  family in #443; the shared walk had simply never been told.

Two of the three holes were found by a claim not holding, and one by a claim holding for
the wrong reason: this file's own prose quoted the graph's size as 1,199 modules, and by
the time the number was re-measured the same tree had 1,202 while a fresh checkout of the
commit being shipped has 1,197. **A count in a docstring is a measurement of one tree at
one moment**, and a shared working copy is not that tree — so the legs below pin
invariants (every walked file is a module; a fabricated ``.venv312`` is invisible to the
walk, not merely to the rule) and quote numbers only where the number is what the claim
is about, always with the tree it came from.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

import pytest

from agent.security_scanner import _should_exclude
from tests._import_graph import (
    NESTED,
    TOP,
    build_graph,
    classify_root,
    dotted_of,
    entry_roots,
    importers_of,
    module_file_of,
    reachable_from,
    read,
)
from tests._scan_walk import PRUNE_DIRS, pruned_dir, walk_files

REPO = Path(__file__).resolve().parents[2]

#: The three modules that claimed to be unimported. Rostered rather than hardcoded inside
#: one assert: a fourth module that reaches for the same sentence has to be measured too,
#: not missed.
CLAIMANTS = ("providers/resilience.py", "providers/semantic_cache.py", "providers/router.py")

#: Whitespace-normalised on purpose — see ``test_the_claim_finder_is_not_line_local``.
CLAIM_RE = re.compile(
    r"nothing\s+on\s+the\s+existing\s+call\s+path\s+imports\s+this\s+module", re.IGNORECASE
)

SWITCH = "SPECPROOF_PROVIDER_POLICY"

#: Whole-word on purpose: the old name is a prefix of the renamed one arm A6 fabricated.
SWITCH_TOKEN_RE = re.compile(rf"\b{SWITCH}\b")

#: The three pieces the policy layer is built from, plus the breaker it is handed.
POLICY_TYPES = frozenset({"ModelRouter", "RetryPolicy", "SemanticCache", "CircuitBreaker"})


@functools.lru_cache(maxsize=1)
def _graph() -> dict[str, list[tuple[str, str]]]:
    return build_graph(REPO)


@functools.lru_cache(maxsize=1)
def _reach() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    graph = _graph()
    roots = entry_roots(graph)
    return (
        reachable_from(roots, graph),
        reachable_from(roots, graph, frozenset({TOP, NESTED})),
    )


@functools.lru_cache(maxsize=1)
def _product_files() -> list[str]:
    """Cached with the graph: six legs below ask for the same 250-file population.

    `module_file_of` stats the tree per name, so recomputing this per leg costs more than
    the censuses that use it.
    """
    return sorted(module_file_of(name) for name in _graph() if classify_root(name) == "product")


@functools.cache
def _tree(rel: str) -> ast.Module:
    """One parse per product file, shared by the five censuses below.

    Uncached this file spends ~50s re-reading the same 250 modules; the number that made
    the walk worth pruning is the same number that makes a census affordable to re-run, so
    a gate that measures the whole tree should not pay for it once per claim.
    """
    return ast.parse(read(REPO / rel))


def _module_of(rel: str) -> str:
    dotted = rel[: -len(".py")].replace("/", ".")
    return dotted[: -len(".__init__")] if dotted.endswith(".__init__") else dotted


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def _enclosing_function(tree: ast.Module, node: ast.AST) -> str:
    parent = _parents(tree).get(node)
    while parent is not None:
        if isinstance(parent, ast.FunctionDef | ast.AsyncFunctionDef):
            return parent.name
        parent = _parents(tree).get(parent)
    return "<module>"


# --- the sentence itself ------------------------------------------------------------


def test_the_claim_phrase_no_longer_appears_in_product_code() -> None:
    """Nobody may claim to be unimported while an importer exists.

    This is the reverse control for the whole file: the finder is proven live on a
    fabricated sentence below, so a green here means the tree really stopped saying it,
    not that the regex stopped working.
    """
    offenders = [rel for rel in _product_files() if CLAIM_RE.search(read(REPO / rel))]
    assert offenders == [], offenders


def test_the_claim_finder_is_not_line_local() -> None:
    """A finder that reads one line at a time finds one of three claims.

    Measured on the tree as #522 found it: `providers/resilience.py` had the sentence on
    one line, `semantic_cache.py` wrapped it after "the" and `router.py` after "existing"
    — a line-local grep reported a population of 1 where the truth was 3.

    The same population has a second hole. `semantic_cache.py` writes the claim
    mid-sentence, so its "nothing" is lower-case: searching for the sentence as the other
    two modules spell it finds 2 of 3. Both controls are asserted on fabrications, because
    a finder that broke would pass the census the same way a finder that is blind does.
    """
    wrapped = "It is OFF by default, and nothing on the\nexisting call path imports this module."
    single = "Nothing on the existing call path imports this module, so nothing happens."
    lowercase = "It is OFF by default, and nothing on the existing call path imports this module."
    assert CLAIM_RE.search(wrapped) is not None
    assert CLAIM_RE.search(single) is not None
    assert sum(1 for line in wrapped.splitlines() if CLAIM_RE.search(line)) == 0
    assert CLAIM_RE.search(lowercase) is not None
    assert "Nothing on the existing call path imports this module" not in lowercase


@pytest.mark.parametrize(
    ("rel", "importers"),
    [
        (
            "providers/resilience.py",
            ["integrations/notify/webhook.py:top", "providers/client_policy.py:top"],
        ),
        ("providers/semantic_cache.py", ["craft/loop.py:top", "providers/client_policy.py:top"]),
        ("providers/router.py", ["craft/loop.py:top", "providers/client_policy.py:top"]),
    ],
)
def test_a_former_claimant_is_imported_by_product_code_at_top_level(
    rel: str, importers: list[str]
) -> None:
    """The claim was falsifiable with a graph: each module has a top-level importer.

    Pinned to the measured set rather than "non-empty", so the day one of these edges
    moves this leg says which one — and the docstring has to be re-measured instead of
    re-remembered.
    """
    assert importers_of(_module_of(rel), _graph())["product"] == importers


@pytest.mark.parametrize("rel", CLAIMANTS)
def test_a_former_claimant_is_reachable_under_the_strict_reading(rel: str) -> None:
    """Top-level edges only, from a derived entry root — the harshest honest ruler.

    The sentence was about "the existing call path", so this follows only edges that fire
    at import time. All three still turn up, which is what made the original claim wrong
    rather than merely unprovable.
    """
    strict, _ = _reach()
    assert _module_of(rel) in strict


def test_classify_retry_is_called_on_a_live_product_path() -> None:
    """The specific edge that made the resilience sentence false.

    Two call sites in product code, and only one of them is the argument: `RetryPolicy`
    calls it on itself from inside the module, while
    `integrations/notify/webhook.py:240` calls it to decide whether a failed
    notification send retries. The prediction written before the battery said one site;
    the extra line is the producer's own executor, so the census now names both instead
    of counting a total.

    Keyed by (file, enclosing function), not by line number. The first version pinned
    `webhook.py:240`, which meant deleting one import line above it — a change with no
    bearing on the claim — moved the call and reddened the leg. The address belongs in
    the message, and the fact belongs in the key.
    """
    calls = {}
    for rel in _product_files():
        tree = _tree(rel)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "classify_retry"
            ):
                calls[f"{rel} in {_enclosing_function(tree, node)}()"] = node.lineno
    assert set(calls) == {
        "providers/resilience.py in _classify()",
        "integrations/notify/webhook.py in send()",
    }, calls


# --- what the sentence was trying to say -------------------------------------------


def test_the_switch_owns_every_product_construction() -> None:
    """One gate, one site: the policy layer is built in exactly one product module.

    `CircuitBreaker` is deliberately absent from the answer rather than padded in: no
    product site constructs one, because `RetryPolicy` takes a breaker as an argument.
    The only breakers built in the tree are in `ops/drills.py`, which the leg below
    files under a different bucket on purpose.
    """
    sites: dict[str, set[str]] = {}
    for rel in _product_files():
        for node in ast.walk(_tree(rel)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in POLICY_TYPES
            ):
                sites.setdefault(node.func.id, set()).add(rel)
    assert sites == {
        "ModelRouter": {"providers/client_policy.py"},
        "RetryPolicy": {"providers/client_policy.py"},
        "SemanticCache": {"providers/client_policy.py"},
    }, sites


def test_the_operator_drill_is_not_counted_as_the_call_path() -> None:
    """`ops/drills.py` constructs a breaker and a policy — and is not a deployment.

    Listing it separately is the point: a product-only census can say "no CircuitBreaker
    is built in product code" truthfully while this file keeps its own bucket.
    """
    assert importers_of("providers.resilience", _graph())["non_product"] == ["ops/drills.py:top"]


def test_the_restatement_names_the_switch_it_now_relies_on() -> None:
    """A restated sentence is a claim too, so the gate is read from code, not prose.

    All three docstrings now say the layer is turned on by
    ``SPECPROOF_PROVIDER_POLICY=1``; this checks the variable really is what
    `client_policy_enabled` reads, and that each module still says so.

    Both halves compare tokens, not substrings. Arm A6 renamed the constant to
    ``SPECPROOF_PROVIDER_POLICY_V2`` and a `SWITCH in text` check let it through — the
    same false-negative class #517 recorded for the dsv4 header name. So the code side
    reads the *assigned literal* out of the AST, and the prose side matches the name as a
    whole word, which a renamed-with-a-suffix string cannot satisfy.
    """
    text = read(REPO / "providers/client_policy.py")
    tree = ast.parse(text)
    enabled = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "client_policy_enabled"
    )
    literal = next(
        getattr(node.value, "value", None)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "ENV_POLICY" for t in node.targets)
    )
    assert literal == SWITCH, f"the code reads {literal!r}, the restatements name {SWITCH!r}"
    assert "os.environ" in ast.unparse(enabled), ast.unparse(enabled)[:200]
    for rel in CLAIMANTS:
        assert SWITCH_TOKEN_RE.search(read(REPO / rel)), f"{rel} no longer names the switch"


def test_no_product_call_site_hands_the_loop_a_router_or_cache() -> None:
    """The loop's router and cache branches are inert for one reason: nobody passes them.

    Measured as keyword arguments rather than as prose, and the two product sites that do
    spell `router=` / `semantic_cache=` are `CraftLoop.from_checkpoint` relaying its own
    parameters — an internal forward, not a deployment choosing a cheap tier. The leg
    therefore pins the *enclosing function*, so the day a third call site appears in a
    real command it goes red instead of being excused by the count.
    """
    sites: list[tuple[str, str, str]] = []
    for rel in _product_files():
        tree = _tree(rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for kw in node.keywords:
                    if kw.arg in {"router", "semantic_cache"}:
                        sites.append((rel, kw.arg, _enclosing_function(tree, node)))
    assert sites == [
        ("craft/loop.py", "router", "from_checkpoint"),
        ("craft/loop.py", "semantic_cache", "from_checkpoint"),
    ], sites


def test_the_product_craft_loop_sites_are_named_and_take_no_policy_kwargs() -> None:
    """Where a deployment really builds the loop, so "unconfigured" has an address.

    `api/agent_runtime.py` and `cli/specproof/commands/craft.py` are the two sites; the
    keyword lists are pinned so a future `router=` there fails the leg above *and* names
    the file that changed here.
    """
    sites: dict[str, list[str]] = {}
    for rel in _product_files():
        if rel == "craft/loop.py":
            continue
        tree = _tree(rel)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name in {"CraftLoop", "from_checkpoint"}:
                sites[f"{rel}:{name}"] = sorted(k.arg for k in node.keywords if k.arg)
    assert sites == {
        "api/agent_runtime.py:CraftLoop": [
            "client",
            "exec_mode",
            "fix_registry",
            "job_id",
            "lease_ttl_seconds",
            "store",
            "tool_registry",
        ],
        "cli/specproof/commands/craft.py:CraftLoop": [
            "budget",
            "client",
            "fix_registry",
            "skip_self_verify",
        ],
        "cli/specproof/commands/craft.py:from_checkpoint": ["budget", "fix_registry"],
    }, sites


# --- the ruler, and the three ways it lied -----------------------------------------


def test_entry_roots_are_derived_and_exist() -> None:
    """"The existing call path" starts at named modules, checked to be in the graph.

    `api.server` and `mcp.server` are listed because no packaging metadata names them;
    this leg is what keeps that list from rotting into fiction, and it is why the
    reachability legs above are about a real deployment.
    """
    assert entry_roots(_graph()) == ["api.server", "cli.specproof.main", "mcp.server"]


def test_relative_edges_are_visible_and_a_level_zero_census_is_blind() -> None:
    """The grammar hole #517 shipped with, measured on the file that has the edges.

    `providers/openai_compatible.py` reaches its siblings with `from .x import`. A census
    that keeps only `level == 0` sees none of them, and so reports
    `providers/client_policy.py` — the module holding the switch — as imported by no
    product code. Both numbers are asserted: the naive reader's empty set is the reverse
    control that keeps this leg from passing because the finder broke.
    """
    tree = ast.parse(read(REPO / "providers/openai_compatible.py"))
    relative = [node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level]
    naive = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module
    }
    assert len(relative) == 8, len(relative)
    assert not any(module.endswith("client_policy") for module in naive), naive
    assert importers_of("providers.client_policy", _graph())["product"] == [
        "providers/openai_compatible.py:top"
    ]


def test_the_shared_walk_never_descends_into_a_local_environment() -> None:
    """`.venv` as a name missed this tree's `.venv312`; a prefix rule catches the family.

    Measured before the fix, with only `.git` and `.scratch` held back so the live arm
    worktree could not move under the census: the exact-name list walked **7,341** `.py`
    files in a working copy that has this project's own `.venv312` (7,343 the day the
    renumber re-measured it) and **6,141** of them sat under `.venv312/` (6,138 of those
    under `site-packages`); the shipped walk returned one entry per real source file,
    which is the invariant `test_no_walked_file_is_dropped_from_the_graph` pins instead of
    quoting a count — this file already rotted two prose counts by being added to a tree
    that other lanes also write into. A fresh checkout of the same commit walks 1,197 and
    has **no `.venv312` at all**, which is why the walk-level exposure needs
    `test_a_local_environment_is_invisible_to_the_walk_not_just_to_the_rule` to fabricate
    one: on a clean tree this leg would stay green with the rule broken.
    The leading dot is what keeps the rule narrow — `.venue/` and `vendor/` are real
    source directories.

    Arm A5 measured the cost of the first version of this leg, which asked
    `name.split(".")[0].startswith(".venv")`. A walked venv file becomes
    `.venv312/Lib/site-packages/openai/types.py`, whose **first** dotted segment is the
    empty string in front of the leading dot, so that assert compared `""` to `.venv` and
    could never fail — arm A5 ran the whole battery with the walk unpruned and went green.
    Asking whether the name starts with a dot is the same question answered honestly.
    """
    strays = sorted(name for name in _graph() if name.startswith("."))
    assert strays == [], f"{len(strays)} modules under a dot-directory, e.g. {strays[:3]}"
    assert pruned_dir(".venv312") is True
    assert pruned_dir(".venv-py312") is True
    assert pruned_dir(".venue") is False
    assert pruned_dir("vendor") is False


def test_a_local_environment_is_invisible_to_the_walk_not_just_to_the_rule(
    tmp_path: Path,
) -> None:
    """`pruned_dir` answering True is a different fact from the walk never descending.

    Arm A5 reverted one line of `walk_files` and turned the rule back into a name, so the
    fence has to sit on the walk itself. Fabricated here rather than measured on this
    tree, because the real `.venv312` is pruned and so proves nothing about what the
    second half of this leg is for: `.venv312` is **not** in `PRUNE_DIRS`, which is exactly
    why a list of names was never going to catch it.
    """
    env = tmp_path / ".venv312" / "Lib" / "site-packages" / "demo"
    env.mkdir(parents=True)
    (env / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    assert walk_files(tmp_path, frozenset({".py"})) == []
    assert ".venv312" not in PRUNE_DIRS


def test_no_walked_file_is_dropped_from_the_graph() -> None:
    """Every file the census walks is a module in the graph — nothing disappears parsing.

    `build_graph` skips what it cannot parse, and a census that loses a file silently
    reports a smaller population while still passing. Measured on a fresh checkout of the
    commit this ships in: 1,197 walked, 1,197 modules, none dropped — the equality below
    is what stops that from quietly becoming 1,197 and 1,196. Asserting the *names* rather
    than the two counts is what makes a future drop say which file went, and it costs a
    dict lookup per file instead of a second parse of the tree.

    The same equality broke once already, and not because of parsing: a probe written to
    re-measure this number put a second tree on `sys.path` while walking the first, and
    reported 1,202 walked against 1,197 modules with zero unparseable files. Two rulers
    over two trees is the same failure the leg was written for, wearing a different hat —
    so `walked` and `graph` below are taken from one `REPO`, in one process.
    """
    walked = [rel for _path, rel in walk_files(REPO, frozenset({".py"}))]
    graph = _graph()
    missing = sorted(rel for rel in walked if dotted_of(rel) not in graph)
    assert missing == [], missing
    assert len(graph) == len(walked), (len(graph), len(walked))


@pytest.mark.parametrize(
    ("path", "excluded_by_both"),
    [
        (".venv312/Lib/site-packages/openai/types.py", True),
        (".venv/lib/python3.12/site-packages/x.py", True),
        (".venv312/Lib/site-packages/test_numpy.py", True),
        (".venue/hall/seat.py", False),
        ("providers/router.py", False),
        ("bench/tasks/task-05-add-tests/fixture/repo/App.java", False),
    ],
)
def test_the_two_exclusion_lists_still_agree_on_the_local_environment(
    path: str, excluded_by_both: bool
) -> None:
    """#443 fixed the prefix family on the scanner side; this fence asks who else knows.

    The parity leg in `test_security_scanner_excludes_are_segment_exact.py` pinned
    `.local` and left `.venv312` unpinned, which is how the shared walk stayed a stale
    copy of a policy the product had already widened. The agreement is asserted only on
    the question the two lists share — is this path somebody's local environment — and
    not on `tests/`, where they answer different jobs: the product self-scan skips it, the
    leak walk has to read it. A `test_numpy.py` inside a venv is the case that looks like
    a test file and is neither.
    """
    assert pruned_dir(path.split("/")[0]) is excluded_by_both, path
    assert _should_exclude(path) is excluded_by_both, path


def test_a_file_at_the_repository_root_is_not_product_code(tmp_path: Path) -> None:
    """A stray root script in someone's working copy cannot satisfy a claim.

    Fabricated rather than measured on this tree, because this tree's root strays belong
    to another lane: `pkg/a.py` reaches `pkg.b` through a relative edge and `stray.py`
    reaches it absolutely, and only the package counts as product.
    """
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "a.py").write_text("from . import b\n", encoding="utf-8")
    (tmp_path / "pkg" / "b.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "stray.py").write_text("import pkg.b\n", encoding="utf-8")
    small = build_graph(tmp_path)
    assert importers_of("pkg.b", small, tmp_path) == {
        "product": ["pkg/a.py:top"],
        "tests": [],
        "non_product": [],
        "unrooted": ["stray.py:top"],
    }


def test_an_empty_importer_list_is_not_a_dead_module() -> None:
    """`providers/__init__.py` has no importers and still runs in every deployment.

    `import providers.base` executes the package's `__init__` without naming it as an
    import target, so "nobody imports it" means "nobody re-exports through it". Recorded
    because the sentence this file exists to retire was written by someone who read an
    empty list the other way.
    """
    strict, _ = _reach()
    assert importers_of("providers", _graph())["product"] == []
    assert "providers.base" in strict


def test_a_module_reachable_only_in_the_loose_reading_is_named() -> None:
    """Two questions, two answers, kept apart: `api.agent_runtime` is a nested-only edge.

    It is imported only from inside function bodies (`api/routes/agent_console.py`), so
    the strict walk never gets there while the loose one does. This is the shape that a
    blanket "nothing imports it" and a blanket "it is wired" both get wrong, and it is why
    the reachability helper returns two sets.
    """
    strict, loose = _reach()
    assert "api.agent_runtime" not in strict
    assert "api.agent_runtime" in loose


def test_the_mcp_bridge_really_is_off_the_deployment_path() -> None:
    """The one claim in the family that the strictest ruler confirms.

    `providers/mcp_bridge.py` is imported at top level by `craft/mcp_wiring.py`, and
    `craft.mcp_wiring` has no product importer of its own — so both are absent from the
    **loose** set, which is the only reading under which the word "nothing" is honest.
    Recorded so the next number that wires craft's MCP tools into an entry root deletes
    this leg on purpose instead of by accident.
    """
    _, loose = _reach()
    assert importers_of("providers.mcp_bridge", _graph())["product"] == [
        "craft/mcp_wiring.py:top"
    ]
    assert importers_of("craft.mcp_wiring", _graph())["product"] == []
    assert "providers.mcp_bridge" not in loose
    assert "craft.mcp_wiring" not in loose
