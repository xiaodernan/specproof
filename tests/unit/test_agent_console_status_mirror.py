"""#173 — the Craft console's status vocabulary is enumerated in five places.

`api/routes/agent_console.py` holds two of them and `api/agent_runtime.py` one:

- `_TERMINAL_CONSOLE_STATUSES` / `_CANCELLABLE_STATUSES` (the run phase, pinned
  by #172),
- `STATUS_LABELS` (its own comment claims the labels are 「mirrored by the SPA
  timeline」),
- `_CONSOLE_TO_STORE_STATUS` (the `?status=` filter's translation to store
  words), and
- `console_status_label` (what the runtime can actually emit).

The SPA adds a fifth: `AGENT_STATUS_META` in `agent/util.ts`.

Measured at the base of this unit (HEAD, before the fix):

- `GET /agent/jobs` admits a filter value by `status not in STATUS_LABELS` and
  then translates it with `_CONSOLE_TO_STORE_STATUS[status]` — a DIRECT
  subscript into a DIFFERENT dict. The two key sets agreeing is the only thing
  standing between a 422 and a KeyError/500, and nothing pinned it;
- the filter's return annotation is `cast("Literal['pending', …]", …)`, a
  sixth hand-copy of the store vocabulary that lives inside the very function
  that translates to it;
- the two sides' Chinese words had already drifted: the API says
  「等待计划审批 Awaiting approval」 for `AWAITING_APPROVAL`, the console said
  「等待审批」. No reader compared the label texts, so the map's own comment was
  an unverified claim about a mirror nobody kept.

This gate reads each side from the artifact that owns it — the store vocabulary
comes from `storage/agent_jobs.py`'s own declaration, not from a copy of it
here — and pins all five enumerations against it.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from storage.agent_jobs import JOB_STATUSES

REPO = Path(__file__).resolve().parents[2]
RUNTIME = REPO / "api" / "agent_runtime.py"
CONSOLE = REPO / "api" / "routes" / "agent_console.py"
UTIL = REPO / "apps" / "web" / "src" / "agent" / "util.ts"

#: The two dicts the console route declares, plus the function that subscripts
#: one of them and casts to the other's words.
DICT_NAMES = ("STATUS_LABELS", "_CONSOLE_TO_STORE_STATUS")


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _assign_value(tree: ast.Module, name: str) -> ast.expr:
    """The right-hand side of a module-level `name = …` or `name: T = …`.

    AnnAssign matters: `STATUS_LABELS: dict[str, str] = {…}` is NOT an
    `ast.Assign`, so an Assign-only walk finds nothing for it and every clause
    built on that walk passes about an empty set.
    """
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
            and node.value is not None
        ):
            return node.value
    raise AssertionError(f"{name} is no longer a module-level assignment — probe broken")


def _dict_keys(node: ast.expr) -> set[str]:
    assert isinstance(node, ast.Dict), "expected a dict literal"
    words = {
        k.value
        for k in node.keys
        if isinstance(k, ast.Constant) and isinstance(k.value, str)
    }
    assert words, "dict literal parsed to no keys — probe broken"
    return words


def _dict_pairs(node: ast.expr) -> dict[str, str]:
    assert isinstance(node, ast.Dict), "expected a dict literal"
    pairs = {
        k.value: v.value
        for k, v in zip(node.keys, node.values, strict=True)
        if isinstance(k, ast.Constant)
        and isinstance(k.value, str)
        and isinstance(v, ast.Constant)
        and isinstance(v.value, str)
    }
    assert pairs, "dict literal parsed to no pairs — probe broken"
    return pairs


def console_dicts() -> dict[str, ast.expr]:
    tree = ast.parse(_source(CONSOLE))
    return {name: _assign_value(tree, name) for name in DICT_NAMES}


def label_map() -> dict[str, str]:
    return _dict_pairs(console_dicts()["STATUS_LABELS"])


def filter_map() -> dict[str, str]:
    return _dict_pairs(console_dicts()["_CONSOLE_TO_STORE_STATUS"])


def cast_words() -> set[str]:
    """The words inside `_store_status_for_filter`'s `cast("Literal[…]", …)`."""
    fn = None
    for node in ast.walk(ast.parse(_source(CONSOLE))):
        if isinstance(node, ast.FunctionDef) and node.name == "_store_status_for_filter":
            fn = node
    assert fn is not None, "_store_status_for_filter not found — probe broken"
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "cast"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            words = set(re.findall(r"'([a-z_]+)'", node.args[0].value))
            assert words, f"cast annotation {node.args[0].value!r} yielded no words"
            return words
    raise AssertionError("no string-first cast() inside _store_status_for_filter")


def emitted_tokens() -> set[str]:
    """What `console_status_label` can answer — the console vocabulary proper."""
    tree = ast.parse(_source(RUNTIME))
    fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "console_status_label":
            fn = node
    assert fn is not None, "console_status_label not found — probe broken"
    words: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and node.value is not None:
            for const in ast.walk(node.value):
                if (
                    isinstance(const, ast.Constant)
                    and isinstance(const.value, str)
                    and (const.value.isupper() or "_" in const.value)
                ):
                    words.add(const.value)
    assert words, "console_status_label returns no literal token — probe broken"
    return words


def web_labels() -> dict[str, str]:
    """`AGENT_STATUS_META`'s key → label text, read from the SPA's own source."""
    source = _source(UTIL)
    start = source.index("export const AGENT_STATUS_META")
    body = source[start : source.index("\n}", start)]
    pairs = dict(
        re.findall(r'^\s*"?([A-Z][A-Z_0-9]*)"?\s*:\s*\{\s*label:\s*"([^"]*)"', body, re.M)
    )
    assert pairs, "AGENT_STATUS_META parsed to no labels — probe broken"
    return pairs


def admission_guard() -> tuple[str, str]:
    """(the name the route tests against, the name it subscripts) for `?status=`.

    The gate below pins the two key sets, so it has to bind the REAL call site:
    a route that stopped consulting `STATUS_LABELS` would make the pin about
    two dicts nobody uses.
    """
    tree = ast.parse(_source(CONSOLE))
    tested: list[str] = []
    subscripted: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            left = node.left
            if (
                isinstance(left, ast.Name)
                and left.id == "status"
                and any(
                    isinstance(op, ast.NotIn)
                    and isinstance(comparator, ast.Name)
                    and comparator.id in DICT_NAMES
                    for op, comparator in zip(node.ops, node.comparators, strict=True)
                )
            ):
                tested += [
                    c.id
                    for c in node.comparators
                    if isinstance(c, ast.Name) and c.id in DICT_NAMES
                ]
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id in DICT_NAMES
        ):
            subscripted.append(node.value.id)
    # Uniqueness is part of the binding: with two candidate call sites the probe
    # would report whichever the walk happened to reach last, and a mutation of
    # the other one would still leave the pins "green".
    assert len(tested) == 1, f"{len(tested)} admission tests consult these dicts"
    assert len(subscripted) == 1, f"{len(subscripted)} subscripts consult these dicts"
    return tested[0], subscripted[0]


# ── the gate ─────────────────────────────────────────────────────────────────

def test_the_probe_reads_every_side_it_claims() -> None:
    """A gate that silently parses nothing is greener than a bug."""
    assert set(label_map()) >= set()
    assert len(label_map()) >= 4, label_map()
    assert len(filter_map()) >= 4, filter_map()
    assert len(web_labels()) >= 4, web_labels()
    assert len(emitted_tokens()) >= 4, emitted_tokens()
    assert len(cast_words()) >= 4, cast_words()
    # The producer this unit derives from, and the copy it charges, must not be
    # the same object: an empty store tuple would green-light every value clause.
    assert JOB_STATUSES, "storage declares no job statuses — nothing to derive from"
    # And the pins must sit on the live path: the route's admission test and the
    # translator's subscript are what make these two dicts load-bearing.
    tested, subscripted = admission_guard()
    assert tested == "STATUS_LABELS", (
        f"?status= is now admitted against {tested}, so the wording pin below "
        "describes a dict the request path never consults"
    )
    assert subscripted == "_CONSOLE_TO_STORE_STATUS", (
        f"the translator subscripts {subscripted} rather than the filter map, so "
        "the key/value clauses below no longer describe the request path"
    )


def test_the_status_filter_admits_only_what_it_can_translate() -> None:
    """`status not in STATUS_LABELS` answers 422; the next line subscripts a
    DIFFERENT dict. A token in the first set and not the second is a KeyError —
    a 500 for a filter value the route declared valid."""
    admitted = set(label_map())
    translatable = set(filter_map())
    untranslatable = admitted - translatable
    unadmittable = translatable - admitted
    assert not untranslatable, (
        f"?status={sorted(untranslatable)} passes the admission test and then "
        "subscripts _CONSOLE_TO_STORE_STATUS for a key it does not hold: the "
        "request that the route says is well-formed crashes instead"
    )
    assert not unadmittable, (
        f"{sorted(unadmittable)} is translatable but the admission test rejects it "
        "with a 422 — dead translation, and the next reader to delete it breaks "
        "the other direction"
    )


def test_the_filter_covers_the_store_vocabulary_that_storage_declares() -> None:
    """Values come from `storage/agent_jobs.py`'s own tuple, not a copy here.

    A word the store never writes makes the list query match nothing, which the
    console shows as 「暂无作业」 — indistinguishable from a real empty list (the
    #110 shape). A store status with no console word cannot be filtered at all.
    """
    store = set(JOB_STATUSES)
    values = set(filter_map().values())
    invented = values - store
    unreachable = store - values
    assert not invented, (
        f"the filter maps to {sorted(invented)}, which storage/agent_jobs.py never "
        "writes: the query returns nothing and the page reports an empty list"
    )
    assert not unreachable, (
        f"store statuses {sorted(unreachable)} have no console word, so no filter "
        "value can ever select those jobs"
    )


def test_the_cast_in_the_translator_is_the_store_vocabulary() -> None:
    """The `cast("Literal[…]", …)` sits in the function that produces the value,
    so it is a claim about the same words — a hand-copy that can rot while both
    dicts stay correct."""
    store = set(JOB_STATUSES)
    claimed = cast_words()
    assert claimed == store, (
        f"the cast promises {sorted(claimed)} while storage declares "
        f"{sorted(store)} — the type says one thing and the store writes another"
    )


def test_the_api_and_the_console_gloss_each_status_with_the_same_words() -> None:
    """`STATUS_LABELS`' comment says the labels are mirrored by the SPA
    timeline. Per token, both directions, on the TEXT — a key-set match with
    different wording is exactly the drift that made the claim false."""
    backend = label_map()
    frontend = web_labels()
    drift = {
        token: (backend[token], frontend[token])
        for token in sorted(set(backend) & set(frontend))
        if backend[token] != frontend[token]
    }
    assert not drift, (
        "\n".join(
            f"{token}: API 「{api}」 vs console 「{spa}」"
            for token, (api, spa) in drift.items()
        )
        + "\n— one of the two must change; the reader who sees both must not get "
        "two words for one state"
    )
    only_backend = set(backend) - set(frontend)
    only_frontend = set(frontend) - set(backend)
    assert not only_backend, (
        f"{sorted(only_backend)} is glossed by the API and the console has no word "
        "for it — the timeline prints the bare token"
    )
    assert not only_frontend, (
        f"{sorted(only_frontend)} is glossed in AGENT_STATUS_META but the API never "
        "names it — a dead label teaches the reader a state that cannot occur"
    )


def test_the_label_map_only_admits_statuses_the_runtime_can_emit() -> None:
    """`STATUS_LABELS` doubles as the filter's admission set. A token the
    runtime cannot return therefore selects nothing while answering 200 with an
    empty list, and a token it does return gets filtered out as 「未知状态」."""
    emitted = emitted_tokens()
    admitted = set(label_map())
    unreachable = admitted - emitted
    unadmitted = emitted - admitted
    assert not unreachable, (
        f"?status= accepts {sorted(unreachable)}, which console_status_label can "
        "never return: the filter answers 200 with an empty list for a state no "
        "job is ever in"
    )
    assert not unadmitted, (
        f"the runtime emits {sorted(unadmitted)} but the filter rejects it — a "
        "real state cannot be listed"
    )
