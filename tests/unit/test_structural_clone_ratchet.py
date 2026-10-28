"""#498 — the structural-clone ratchet; #514 — the same-name near-clone lens.

A scan of the shipped packages used to find 16 pairs of byte-identical function
bodies; #483–#497 removed or gated most of them. This file is the ratchet: a
**new** copy-pasted body turns it red, and removing a known one turns it red
too until the roster is updated — so the roster stays a claim about the tree
rather than a snapshot of one afternoon.

Why it matters: two copies of one decision are equal until someone edits one.
The pairs that stayed correct in this repo were the ones a test pinned; the
unpinned ones drifted (the env-truthy set drifted into ``MINIO_SECURE=1``
meaning TLS **off**, #474).

Two lenses, because #514 measured that one lens was blind in a specific way:

* ``_clones()`` — bodies of 25+ nodes that are identical once the docstring is
  stripped and constant-valued keywords are folded into positional order. Names
  may differ, so a paste-and-rename is still caught here if the body is big
  enough.
* ``_near_clones()`` — bodies of 10+ nodes that share a **name** and are
  identical once every identifier is renamed too. Abstract stubs (``...`` /
  ``pass``) are excluded: two protocol declarations are not one decision.

A third failure class showed up in #516, and it is not about the lenses at all: a
package missing from ``PACKAGES`` is never opened by either one. ``contracts`` and
``providers`` were both missing — 20 modules of shipped code outside the door — and
``providers`` did hold a byte-identical copy of the 429 wait policy. ``PACKAGES`` is
therefore now reconciled against the shipping allow-list in ``pyproject.toml``, and
every tracked top-level Python root has to be either compared or excluded by name.

The known list is NOT an endorsement. Each entry states why it is still there;
shrinking it is progress.
"""
from __future__ import annotations

import ast
import hashlib
import subprocess
from collections import defaultdict
from collections.abc import Iterable, Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Packages whose modules ship in the product (tests and scripts excluded).
#: #516 measured this list as a hand-maintained census with two holes in it:
#: `contracts` (2 modules, imported by `storage/` and `integrations/`) and
#: `providers` (18 modules, imported by `retrieval/`) were in no lens at all, so
#: neither ever compared a copy that lived there — and `providers` turned out to
#: hold a byte-identical copy of the 429 wait policy. `services` is the Java
#: control plane and contributes no Python modules; it is listed so the census
#: reads as deliberate, and the shipped-package gate checks the list against
#: `[tool.setuptools.packages.find].include` instead of trusting it.
PACKAGES = (
    "agent", "api", "cli", "contracts", "craft", "devtools", "evidence",
    "experiments", "integrations", "mcp", "observability", "providers",
    "retrieval", "sandbox", "services", "storage",
)

#: Roots the census deliberately does NOT compare, with what #516 measured there.
#: Adding them one at a time on top of the shipped census yields `scripts` +8
#: exact / +13 near, `bench` +4 / +7 and `tests` +93 / +162 groups — so "not
#: compared" must never be read as "clean". `plugins` (protocol only) and `ops`
#: (drills driven from `scripts/`) were measured at zero new groups either way;
#: they are excluded because nothing shipped imports them, which is also why
#: `test_the_census_compares_nothing_unshipped` keeps them out of PACKAGES.
EXCLUDED_ROOTS = ("bench", "ops", "plugins", "scripts", "tests")

#: In PACKAGES but contributing no Python to compare: the Spring Boot control
#: plane. Listed so the census reads as deliberate, and re-measured by
#: `test_the_census_has_no_stale_or_empty_entries` rather than remembered.
NO_PYTHON_ROOTS = frozenset({"services"})

#: Bodies smaller than this are usually one-line delegations where a shared
#: helper would add more indirection than it removes.
MIN_NODES = 25

#: #514 measured the floor as the real blind spot, not spelling: at 10 nodes and
#: name-keyed, the shipped tree holds 21 cross-file groups, and 16 of them are
#: **byte-identical modulo the docstring** — copies the 25-node floor has never
#: compared. Below 10 the population is dominated by one-line delegations.
NEAR_MIN_NODES = 10

Clone = frozenset[tuple[str, str]]  # {(relative path, function name)}

#: Groups that still exist, each with the reason it has not been merged.
KNOWN_CLONES: dict[Clone, str] = {
    frozenset(
        {
            ("storage/agent_jobs.py", "__init__"),
            ("storage/identity.py", "__init__"),
            ("storage/object_metadata.py", "__init__"),
        }
    ): "SQLite store constructor (connect + Row factory + lock + ensure_schema); "
    "merging needs a base class, and a hierarchy for five lines costs more than it saves",
    frozenset(
        {
            ("api/routes/web.py", "_capsule_dirs"),
            ("mcp/tools.py", "_capsule_dirs"),
        }
    ): "cross-layer path resolution, pinned by test_capsule_and_report_paths_agree "
    "(#493); merging needs an owner decision on where the path lives",
    frozenset(
        {
            ("api/routes/web.py", "_eval_report_path"),
            ("mcp/tools.py", "_eval_report_path"),
        }
    ): "same cross-layer decision as _capsule_dirs (#493)",
    frozenset(
        {
            ("craft/adapters/go_adapter.py", "_read_text_or_none"),
            ("craft/adapters/node_adapter.py", "_read_text_or_none"),
        }
    ): "the adapter lane's file reader; #513 merged this pair's sibling "
    "(`_as_text`, three copies) into sandbox.runner.child_output_text, so the "
    "lane has one merge point left here — a shared reader needs the same "
    "cross-package decision and these two files are not on that path yet",
    frozenset(
        {
            ("storage/agent_jobs.py", "connection"),
            ("storage/billing.py", "connection"),
            ("storage/identity.py", "connection"),
            ("storage/mysql.py", "connection"),
            ("storage/object_metadata.py", "connection"),
        }
    ): "two-line contextmanager delegating to unit_of_work(self._connect); a mixin "
    "would add indirection for two lines AND weaken the return type from "
    "Iterator[pymysql.Connection] to Iterator[Any] across five stores — worse than "
    "the duplication it removes",
    frozenset(
        {
            ("craft/tools.py", "__init__"),
            ("mcp/client.py", "__init__"),
        }
    ): "two unrelated classes that happen to share a two-line constructor; "
    "coincidence, not a shared contract",
    frozenset(
        {
            ("providers/openai_compatible.py", "_wait_retry_after_or_exponential"),
            ("retrieval/embeddings.py", "_wait_retry_after_or_exponential"),
        }
    ): "one 429 decision — honour Retry-After, else capped exponential — written "
    "twice, byte-identical, and #516 only saw it because `providers` was missing "
    "from PACKAGES. NOT endorsed: the helper each copy calls has already drifted "
    "(measured over 16 response shapes — the two agree on every header value and "
    "differ on exactly three malformed-response shapes, where `providers` returns "
    "None and `retrieval` raises AttributeError, which costs the embeddings client "
    "two of its three attempts). Pinned by "
    "test_retry_after_readers_policy_table.py; merging changes behaviour on a live "
    "call path, so it is queued as #517 with its own arms.",
}

#: #514 — groups the same-name lens sees and the 25-node floor did not.
#: Each entry says why the copy stays; the ones worth merging are queued in
#: DEEP_OPTIMIZATION_PLAN.md, ranked by what silent drift would cost.
KNOWN_NEAR_CLONES: dict[Clone, str] = {
    # ---- the four MySQL/SQLite stores: one driver, four copies of each shim ----
    frozenset(
        {
            ("storage/agent_jobs.py", "_connect"),
            ("storage/billing.py", "_connect"),
            ("storage/identity.py", "_connect"),
            ("storage/object_metadata.py", "_connect"),
        }
    ): "`pymysql.connect(**self._connect_kwargs)` — the kwargs dict is built per store "
    "at construction, so a shared helper would take a dict the caller already owns and "
    "return nothing the caller cannot do in one line. Same reasoning #512 applied to the "
    "`__init__` trio.",
    frozenset(
        {
            ("storage/agent_jobs.py", "_to_mysql"),
            ("storage/billing.py", "_to_mysql"),
            ("storage/identity.py", "_to_mysql"),
            ("storage/object_metadata.py", "_to_mysql"),
        }
    ): "`sql.replace('?', '%s')` sits next to each store's SQL constants; merging it into "
    "a shared module would leave the constants importing a function from elsewhere while "
    "the dialect itself is one call. Queued as a merge candidate, not endorsed — a drift "
    "here breaks every query in whichever store edited one copy.",
    frozenset(
        {
            ("storage/agent_jobs.py", "close"),
            ("storage/billing.py", "close"),
            ("storage/identity.py", "close"),
            ("storage/object_metadata.py", "close"),
        }
    ): "`with self._lock: self._conn.close()` — the lock and the connection are both "
    "instance state of a class that has no base; this is the #512 conclusion again, "
    "reached from the other end.",
    frozenset(
        {
            ("storage/agent_jobs.py", "get"),
            ("storage/object_metadata.py", "get"),
        }
    ): "same fetch-then-map shape, and the only difference the lens had to rename away "
    "is the row mapper (`_row_to_job` vs `_row_to_metadata`) — the mapper IS the "
    "contract, so the bodies cannot be shared without parameterising over types.",
    frozenset(
        {
            ("storage/invoice_cron.py", "stop"),
            ("storage/outbox_relay.py", "stop"),
        }
    ): "`self._running = False` on two independent loop classes; no shared base exists "
    "and a one-line setter would not be it.",
    # ---- the backend clients: readiness, teardown, constructors ----
    frozenset(
        {
            ("storage/elasticsearch.py", "close"),
            ("storage/mongodb.py", "close"),
            ("storage/redis.py", "close"),
        }
    ): "`if self._client: self._client.close(); self._client = None` — three clients, no "
    "common ancestor; the pattern is the whole body.",
    frozenset(
        {
            ("storage/elasticsearch.py", "is_ready"),
            ("storage/redis.py", "is_ready"),
        }
    ): "ping-or-False, differing only in the metrics wrapper (`_timed_es` vs "
    "`_timed_redis`). The wrapper is the point: readiness has to be timed per backend.",
    frozenset(
        {
            ("storage/elasticsearch.py", "__init__"),
            ("storage/minio.py", "__init__"),
        }
    ): "config-or-from_env plus a None client — the #512 conclusion, and the reason this "
    "group only appears once identifiers are renamed (`ElasticsearchConfig` vs `MinIOConfig`).",
    frozenset(
        {
            ("api/identity/oidc.py", "close"),
            ("integrations/github_checks.py", "close"),
        }
    ): "`self._http.close()` on two unrelated httpx owners in two different packages; "
    "coincidence of the same field name, not a shared contract.",
    frozenset(
        {
            ("craft/memory.py", "clear"),
            ("providers/semantic_cache.py", "clear"),
        }
    ): "`self._entries.clear()` on two dict-backed caches that share no base and no "
    "owner — the body is the entire meaning of `dict.clear()`, so there is no "
    "decision here to share; the same conclusion as the `close` pair above, reached "
    "from the other end. Newly visible because #516 put `providers` in the census.",
    # ---- decisions that are genuinely one decision, queued to merge ----
    frozenset(
        {
            ("craft/schemas.py", "sha256_hex"),
            ("sandbox/cache_verify.py", "sha256_hex"),
            ("storage/object_metadata.py", "sha256_hex"),
        }
    ): "the canonical digest format, three copies across three packages. tests/ import "
    "one of them, so today the other two could change the digest of the same bytes in "
    "silence — pinned by test_copied_timestamp_and_digest_formats_agree; merging is the "
    "same cross-layer owner decision #493 recorded for `_capsule_dirs`, so it is queued "
    "with that decision rather than resolved here.",
    frozenset(
        {
            ("craft/budget.py", "_env_int"),
            ("craft/llm.py", "_env_int"),
        }
    ): "83 nodes of identical env parsing whose only difference is the exception type "
    "(`BudgetError` vs `LLMUnavailableError`) — the exception is the caller-facing "
    "contract, so sharing needs the type passed in. Already pinned by "
    "test_env_int_readers_policy_table.py, which tables six env-int readers including "
    "these two; that is why this pair stays listed rather than being merged blind.",
    frozenset(
        {
            ("agent/contracts/parser.py", "_running_loop"),
            ("agent/nodes/compile_contracts.py", "_running_loop"),
        }
    ): "the #271 fix (probe get_running_loop, never get_event_loop) written twice inside "
    "one package; a third call site should import it, and that merge is queued.",
    frozenset(
        {
            ("craft/adapters/go_adapter.py", "get_supported_goals"),
            ("craft/adapters/node_adapter.py", "get_supported_goals"),
        }
    ): "`return cls.SUPPORTED_GOALS` — the Adapter protocol method each adapter must "
    "answer for itself; an ABC default would hide which adapter forgot to declare goals.",
}

_SCAN_CACHE: tuple[set[Clone], set[Clone]] | None = None


def _shipped_files() -> list[str]:
    out = subprocess.run(
        ("git", "ls-files", "--", *(f"{pkg}/*.py" for pkg in PACKAGES)),
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=180,
        encoding="utf-8",
    )
    files = [line for line in out.stdout.splitlines() if line]
    assert len(files) > 100, f"shipped-file census collapsed: {len(files)} files"
    return files


def _functions() -> Iterator[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef]]:
    for rel in _shipped_files():
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield rel, node


def _without_docstring(fn: ast.FunctionDef | ast.AsyncFunctionDef):
    """A private copy with its docstring removed; the input is never mutated.

    Docstrings legitimately differ between copies; everything else has to match
    for a group to count as a clone.
    """
    clone = ast.parse(ast.unparse(fn)).body[0]
    body = list(clone.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        clone.body = body[1:] or [ast.Pass()]
    return clone


def _fold_constant_keywords(fn) -> None:
    """`f(a, k=b)` with a literal `b` becomes `f(a, b)`.

    #513's measured victim: three copies of one decoder, and the ratchet called
    two of them clones because the third wrote `errors="replace"` positionally.
    One `ast.keyword` node was enough to hide a copy.
    """
    for call in ast.walk(fn):
        if isinstance(call, ast.Call) and call.keywords:
            kept = []
            for kw in call.keywords:
                if isinstance(kw.value, ast.Constant):
                    call.args.append(kw.value)
                else:
                    kept.append(kw)
            call.keywords = kept


def _rename_identifiers(fn) -> None:
    """Every name bound inside the body becomes `v0, v1, ...` in first-use order.

    An upper bound on the paste-and-rename class: it also renames globals, which
    is why the near lens additionally requires the two copies to share a
    function name.
    """
    slots: dict[str, str] = {}

    def slot(name: str) -> str:
        slots.setdefault(name, f"v{len(slots)}")
        return slots[name]

    for sub in ast.walk(fn):
        if isinstance(sub, ast.Name):
            sub.id = slot(sub.id)
        elif isinstance(sub, ast.arg):
            sub.arg = slot(sub.arg)


def _is_abstract_stub(fn) -> bool:
    """A body that is only `...` (or `pass`) once the docstring is gone."""
    if len(fn.body) != 1:
        return False
    stmt = fn.body[0]
    if isinstance(stmt, ast.Pass):
        return True
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is Ellipsis
    )


def _digest(fn) -> str:
    return hashlib.sha256(
        ast.dump(fn, annotate_fields=True, include_attributes=False).encode()
    ).hexdigest()


def _scan() -> tuple[set[Clone], set[Clone]]:
    """One pass over the shipped packages, both lenses."""
    exact: dict[str, set[Clone]] = defaultdict(set)
    near: dict[tuple[str, str], set[Clone]] = defaultdict(set)
    for rel, fn in _functions():
        size = sum(1 for _ in ast.walk(fn))
        if size < NEAR_MIN_NODES:
            continue
        stripped = _without_docstring(fn)
        if _is_abstract_stub(stripped):
            continue
        _fold_constant_keywords(stripped)
        if size >= MIN_NODES:
            exact[_digest(stripped)].add((rel, fn.name))
        _rename_identifiers(stripped)
        near[(fn.name, _digest(stripped))].add((rel, fn.name))

    def spanning(groups: Iterable[set[Clone]]) -> set[Clone]:
        return {
            frozenset(members)
            for members in groups
            if len({rel for rel, _ in members}) >= 2
        }

    return spanning(exact.values()), spanning(near.values())


def _clones() -> set[Clone]:
    global _SCAN_CACHE
    if _SCAN_CACHE is None:
        _SCAN_CACHE = _scan()
    return _SCAN_CACHE[0]


def _near_clones() -> set[Clone]:
    global _SCAN_CACHE
    if _SCAN_CACHE is None:
        _SCAN_CACHE = _scan()
    return _SCAN_CACHE[1]


def test_no_new_copy_pasted_function_bodies() -> None:
    found = _clones()
    new = sorted(found - set(KNOWN_CLONES), key=sorted)
    assert not new, (
        "new structurally identical function bodies appeared: "
        + "; ".join(", ".join(f"{rel}::{name}" for rel, name in group) for group in new)
        + ". Share the implementation, or add the pair to KNOWN_CLONES with the reason "
        "it must stay duplicated."
    )


def test_the_known_clone_roster_is_still_true() -> None:
    found = _clones()
    gone = sorted(set(KNOWN_CLONES) - found, key=sorted)
    assert not gone, (
        "these pairs are no longer clones, so the roster is stale: "
        + "; ".join(", ".join(f"{rel}::{name}" for rel, name in group) for group in gone)
        + ". Remove them from KNOWN_CLONES — the roster is a claim about the tree."
    )


def test_every_known_clone_states_a_reason() -> None:
    for group, reason in KNOWN_CLONES.items():
        assert reason.strip(), f"{sorted(group)} has no stated reason"
        assert len({rel for rel, _ in group}) >= 2, f"{sorted(group)} is not cross-file"


def test_no_new_same_name_near_clones() -> None:
    # A group the first lens already endorses is not a new finding for the second;
    # the near population is a superset of the exact one, so the allowances union.
    allowed = set(KNOWN_CLONES) | set(KNOWN_NEAR_CLONES)
    found = _near_clones()
    new = sorted(found - allowed, key=sorted)
    assert not new, (
        "new same-name copies of one decision appeared: "
        + "; ".join(
            ", ".join(f"{rel}::{name}" for rel, name in sorted(group)) for group in new
        )
        + ". Share the implementation, or add the group to KNOWN_NEAR_CLONES with the "
        "reason it must stay duplicated."
    )


def test_the_known_near_clone_roster_is_still_true() -> None:
    found = _near_clones()
    gone = sorted(set(KNOWN_NEAR_CLONES) - found, key=sorted)
    assert not gone, (
        "these groups are no longer near-clones, so the roster is stale: "
        + "; ".join(
            ", ".join(f"{rel}::{name}" for rel, name in sorted(group)) for group in gone
        )
        + ". Remove them from KNOWN_NEAR_CLONES — the roster is a claim about the tree, "
        "and a merged-away entry is progress that must be recorded."
    )


def test_every_known_near_clone_states_a_reason_and_spans_files() -> None:
    for group, reason in KNOWN_NEAR_CLONES.items():
        assert reason.strip(), f"{sorted(group)} has no stated reason"
        assert len({rel for rel, _ in group}) >= 2, f"{sorted(group)} is not cross-file"
        assert len({name for _, name in group}) == 1, f"{sorted(group)} is not same-name"


def test_the_near_lens_sees_what_the_25_node_floor_hid() -> None:
    """The measured reason the second lens exists, encoded so it cannot rot back.

    `sha256_hex` is three byte-identical copies across three packages (18 nodes
    each). The original lens never compared them — it starts at 25. #516 merged
    the `_now_iso` copies this test used to name, and the digest trio is the
    same-shaped claim that is still true (it is queued, not merged: #516's
    measurement is that a *fifth* producer of that format lived in `contracts/`,
    a package the census did not include).
    """
    trio = frozenset(
        {
            ("craft/schemas.py", "sha256_hex"),
            ("sandbox/cache_verify.py", "sha256_hex"),
            ("storage/object_metadata.py", "sha256_hex"),
        }
    )
    assert trio in _near_clones(), sorted(map(sorted, _near_clones()))
    assert trio not in _clones(), "the 25-node floor moved; re-measure this claim"


def test_a_positional_copy_of_a_call_is_the_same_clone() -> None:
    """Reverse control for the keyword fold: one `ast.keyword` may not hide a copy.

    This is the exact shape #513 found living in the tree as a third copy the
    roster insisted was two.
    """
    keyword_form = 'def f(value):\n    return value.decode("utf-8", errors="replace")\n'
    positional_form = 'def f(value):\n    return value.decode("utf-8", "replace")\n'

    def digest_of(src: str) -> str:
        fn = _without_docstring(ast.parse(src).body[0])
        _fold_constant_keywords(fn)
        return _digest(fn)

    assert digest_of(keyword_form) == digest_of(positional_form)
    different = 'def f(value):\n    return value.decode("utf-8", errors="strict")\n'
    assert digest_of(keyword_form) != digest_of(different), (
        "the fold collapsed a real difference: only literal keyword ARGUMENTS may move"
    )


def _tracked_python_roots() -> set[str]:
    """Every top-level directory that holds tracked Python."""
    out = subprocess.run(
        ("git", "ls-files", "*.py"),
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=180,
        encoding="utf-8",
    )
    roots = {line.split("/", 1)[0] for line in out.stdout.splitlines() if "/" in line}
    assert len(roots) >= 15, f"root census collapsed: {sorted(roots)}"
    return roots


def test_every_shipped_package_is_compared_by_the_census() -> None:
    """#516's root cause: PACKAGES was a hand-typed tuple with holes in it.

    The two lenses can only compare a body they are told to open. `contracts` and
    `providers` were both absent, so a whole package of shipped code sat outside
    the door — and `providers` turned out to carry a byte-identical copy of the
    429 wait policy that had never been looked at. The shipping allow-list in
    ``pyproject.toml`` is the definition of "ships in the product", so the census
    is now checked against it instead of against someone's memory.
    """
    from tests.unit.test_packaging_ships_every_imported_package import shipped_packages

    shipped = set(shipped_packages())
    assert shipped, "probe broken: the shipping allow-list parsed empty"
    missing = shipped - set(PACKAGES)
    assert not missing, (
        f"{sorted(missing)} ship in the product but are not in the clone census, so "
        "no lens will ever compare a copy that lives there. Add the root to PACKAGES "
        "(and judge whatever it reveals) or stop shipping it."
    )


def test_no_tracked_python_root_is_unclassified() -> None:
    """The same hole, from the other side: a new top-level root must be judged.

    An untracked-by-both-lists root is the state #516 found `contracts` and
    `providers` in — it is not a missing entry in one list, it is a package nobody
    ever decided about.
    """
    unclassified = _tracked_python_roots() - set(PACKAGES) - set(EXCLUDED_ROOTS)
    assert not unclassified, (
        f"{sorted(unclassified)} holds tracked Python but is neither compared nor "
        "excluded with a reason. Classify it in PACKAGES or EXCLUDED_ROOTS."
    )


def test_the_census_compares_nothing_unshipped() -> None:
    """Reverse control: the census may not quietly grow into the test tree.

    Comparing `tests/` would fold 93 exact and 162 near groups into a roster whose
    job is to describe shipped code, and the ratchet would go red for duplicated
    fakes instead of duplicated decisions.
    """
    from tests.unit.test_packaging_ships_every_imported_package import shipped_packages

    extra = set(PACKAGES) - set(shipped_packages()) - NO_PYTHON_ROOTS
    assert not extra, f"{sorted(extra)} are compared but not shipped"
    for root in NO_PYTHON_ROOTS:
        directory = ROOT / root
        files = sorted(directory.rglob("*.py")) if directory.is_dir() else []
        assert not [f for f in files if "__pycache__" not in f.parts], (
            f"{root} was exempted as non-Python but now holds Python: re-measure it"
        )


def test_the_two_rosters_do_not_repeat_the_same_prose() -> None:
    """A group the first lens already carries stays in one place.

    `KNOWN_NEAR_CLONES` is the set of groups the 25-node floor could not see; adding a
    group that is already endorsed above would mean two reasons for one claim, and
    only one of them would get updated when the copy is merged away.
    """
    overlap = set(KNOWN_CLONES) & set(KNOWN_NEAR_CLONES)
    assert not overlap, sorted(map(sorted, overlap))


def test_a_renamed_copy_is_a_near_clone_only_when_the_name_matches() -> None:
    """Reverse control for the rename, shaped like the finding that motivated it.

    `craft/budget.py::_env_int` and `craft/llm.py::_env_int` are 83 nodes of
    identical env parsing that differ only in which exception they raise — and an
    exception class is a `Name`, so renaming collapses them. Attribute names are
    deliberately NOT renamed: `self._active` vs `self._running` is a different
    piece of state, not the same decision written twice.
    """
    tail = "\n    try:\n        return int(raw)\n    except ValueError:\n        raise {}(name)\n"
    budget = f"def _env_int(name, default, raw):\n{tail.format('BudgetError')}"
    llm = f"def _env_int(name, default, raw):\n{tail.format('LLMUnavailableError')}"
    other_name = f"def _env_number(name, default, raw):\n{tail.format('LLMUnavailableError')}"

    def near_key(src: str) -> tuple[str, str]:
        node = ast.parse(src).body[0]
        stripped = _without_docstring(node)
        _fold_constant_keywords(stripped)
        _rename_identifiers(stripped)
        return node.name, _digest(stripped)

    assert near_key(budget) == near_key(llm)
    assert near_key(budget) != near_key(other_name), (
        "the near lens must key on the shared name; without it every two-statement "
        "method in the repo would join one group"
    )


def test_two_abstract_stubs_are_not_a_shared_decision() -> None:
    """The false-positive class the node floor existed to keep out, kept out by rule.

    Dropping to 10 nodes admits 93 protocol/ABC declarations across 86 names; two
    `...` bodies are not evidence that someone pasted a decision.
    """
    one = 'def collect(self, prepared: object) -> object:\n    """Collect."""\n    ...\n'
    two = 'def collect(self, workspace: str) -> object:\n    ...\n'

    def stub(src: str) -> bool:
        return _is_abstract_stub(_without_docstring(ast.parse(src).body[0]))

    assert stub(one) and stub(two)

    real = 'def collect(self, prepared: object) -> object:\n    return prepared.value\n'
    assert not stub(real)
