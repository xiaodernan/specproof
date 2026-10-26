"""#471 — a numeric environment knob the operator left blank must not kill the process.

A compose file that interpolates a variable nobody set hands the process ``K=``:
a declared knob whose value is empty. Measured over the shipped packages, a bare
``int(os.getenv("K", "9100"))`` then raises
``ValueError: invalid literal for int() with base 10: ''`` inside the constructor
that reads it — before any of the surrounding startup verdicts can be written, so
the operator gets a traceback instead of the stack they asked for, and the knob
they meant to leave alone is what killed it.

The repo already has a convention for the string knobs: blank means unset
(``SPECPROOF_INVOICE_PERIOD`` is read as ``.strip()`` then ``override or
fallback``; ``storage/config_guard.py`` counts ``not value`` as unset). A numbered
knob follows it through ``storage/env_config.py``, which is what the converted
shipped reads now call. A value that is neither blank nor a number is a different
thing — a mistaken intent, not an absent one — so it is refused with the knob
named, the offending text quoted and the default it would have used stated.

Two things this file is careful about, because both fail silently:

* **The census is derived, not typed.** Which shipped reads coerce an env value at
  all is read out of the parse tree over the packages ``pyproject.toml`` declares,
  so a new bare coercion is charged instead of hidden.
* **The other spelling is enumerated, and then run.** ``raw = os.getenv(name);
  int(raw)`` is how a second population of shipped readers works, and a subtree
  scan never sees it — the coercion's argument is a local name. Those readers are
  censused by the same pass, named in ``_GENERIC_COERCERS`` and ``_KNOB_PROBES``,
  and each one is *called* with a blank value, so "already tolerant" is a
  measurement rather than a guess and the roster size is whatever the tree says.

The boundary is equally deliberate: the helper refuses text that is not a number,
but it invents no range. An out-of-range port keeps its documented fate (the bind
refusal, #276/#272/#427), because silently clamping a knob would bind a port the
operator never asked for — the exact sin this batch exists to remove.

The graded bytes come from the worktree (``git ls-files`` supplies the population,
the disk supplies the text), the same basis the sibling structural gates use.
``test_the_scan_charges_every_forbidden_shape_it_claims_to`` shows the extractors
actually fire, so the set equalities below are not passes by blindness.
"""

from __future__ import annotations

import ast
import functools
import importlib
import inspect
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from api.auth import enforce_rate_limit
from storage import env_config as _env_config
from storage.env_config import EnvKnobError, float_env, int_env

ROOT = Path(__file__).resolve().parents[2]

#: The coercions that turn text into a number. Only these two names are charged:
#: ``str``/``bool`` reads have their own documented fates elsewhere.
_COERCE = {"int", "float"}

#: The ``storage/env_config.py`` readers — the compliant spelling.
_HELPERS = ("int_env", "float_env")

#: Direct coercions that do not go through the helper, and the structural reason
#: each is nevertheless safe. Admission is by (file, scope), never by line: line
#: numbers move with every unrelated commit and a stale line pin is a silent
#: exemption. ``try-guarded`` is re-derived from the parse tree on every run, so
#: deleting the handler that justifies a row turns this table red.
_GUARDED_DIRECT: dict[str, str] = {
    "storage/elasticsearch.py::ElasticsearchConfig.from_env": "try-guarded",
    "experiments/external_state.py::build_redis_client": "try-guarded",
}

#: A name no shipped code reads, so probing a generic coercer cannot be confused
#: by the real environment of the machine running this test.
_PROBE_KNOB = "M471_PROBE_KNOB_UNSET_ANYWHERE"
_PROBE_DEFAULT = 4242

#: Readers that name their knob only through a parameter, so the census cannot
#: say which knob they guard — they are probed with a sentinel default instead.
_GENERIC_COERCERS: set[tuple[str, str]] = {
    ("agent/nodes/run_deep_experiments.py", "_env_int"),
    ("craft/budget.py", "_env_int"),
    ("craft/llm.py", "_env_int"),
    ("mcp/tools.py", "_env_int"),
    ("providers/openai_compatible.py", "_env_int"),
    ("retrieval/embeddings.py", "_env_int"),
    ("retrieval/rerank.py", "_env_int"),
    ("sandbox/runner.py", "_budget"),
}


def _drive_required_jdk(monkeypatch: pytest.MonkeyPatch) -> Any:
    """``SPECPROOF_REQUIRE_JDK`` left blank: no JDK is required, and no reason given."""
    from agent.preflight import ENV_REQUIRE_JDK, _required_jdk

    monkeypatch.setenv(ENV_REQUIRE_JDK, "")
    return _required_jdk(None)


def _drive_repo_bytes(monkeypatch: pytest.MonkeyPatch) -> Any:
    """``SPECPROOF_MAX_REPO_BYTES`` blank: the shipped cap, and no warning."""
    from agent.repo_safety import MAX_REPO_BYTES_ENV, _resolve_max_repo_bytes

    monkeypatch.setenv(MAX_REPO_BYTES_ENV, "")
    warnings: list[str] = []
    got = _resolve_max_repo_bytes(None, warnings)
    assert warnings == [], f"an empty knob warned {warnings}"
    return got


def _drive_scan_keys(monkeypatch: pytest.MonkeyPatch) -> Any:
    """``SPECPROOF_REDIS_SCAN_MAX_KEYS`` blank: the documented cap."""
    from experiments.external_state import MAX_SCANNED_KEYS_ENV, max_scanned_keys

    monkeypatch.setenv(MAX_SCANNED_KEYS_ENV, "")
    return max_scanned_keys()


def _drive_json_limit(monkeypatch: pytest.MonkeyPatch) -> Any:
    """``SPECPROOF_MAX_JSON_BYTES`` blank: whatever the caller passed in."""
    from api.middleware import _current_json_limit

    monkeypatch.setenv("SPECPROOF_MAX_JSON_BYTES", "")
    return _current_json_limit(_PROBE_DEFAULT)


def _drive_bcrypt(monkeypatch: pytest.MonkeyPatch) -> Any:
    """``SPECPROOF_BCRYPT_ROUNDS`` blank: bcrypt's shipped cost, not a crash."""
    from api.identity.config import bcrypt_rounds

    monkeypatch.setenv("SPECPROOF_BCRYPT_ROUNDS", "")
    return bcrypt_rounds()


def _drive_github_app(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Every GitHub App knob blank: the app is unconfigured, which is a fate.

    This is the reader #260 left behind — it reads four knobs and answers
    ``None`` when none of them carry text, so an empty interpolation from a
    compose file skips publishing instead of killing the check run.
    """
    from integrations.github_checks import GitHubAppConfig

    for knob in (
        "GITHUB_APP_ID",
        "GITHUB_APP_INSTALLATION_ID",
        "GITHUB_APP_PRIVATE_KEY",
        "GITHUB_APP_PRIVATE_KEY_FILE",
    ):
        monkeypatch.setenv(knob, "")
    return GitHubAppConfig.from_env()


#: Readers that name one fixed knob: how to drive it blank, and the value that
#: must come back. Each fate was measured on this host before being written.
_KNOB_PROBES: dict[tuple[str, str], tuple[Any, Any]] = {
    ("agent/preflight.py", "_required_jdk"): (_drive_required_jdk, (None, "")),
    ("agent/repo_safety.py", "_resolve_max_repo_bytes"): (
        _drive_repo_bytes,
        2_147_483_648,
    ),
    ("api/identity/config.py", "bcrypt_rounds"): (_drive_bcrypt, 12),
    ("api/middleware.py", "_current_json_limit"): (_drive_json_limit, _PROBE_DEFAULT),
    ("experiments/external_state.py", "max_scanned_keys"): (_drive_scan_keys, 200),
    ("integrations/github_checks.py", "GitHubAppConfig.from_env"): (
        _drive_github_app,
        None,
    ),
}


def _module_of(rel: str) -> Any:
    """The live module behind a census path."""
    return importlib.import_module(rel[: -len(".py")].replace("/", "."))


def _attr_path(module: Any, dotted: str) -> Any:
    """Resolve a census scope against the module the census read.

    A scope is ``function`` or ``Class.method`` because that is what ``_scope_of``
    reports. Resolving it here rather than importing the target by hand binds each
    probe to the very object the scan charged: a test that quietly drove a
    lookalike helper would report the roster surviving while the shipped reader
    still crashed.
    """
    found = module
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


# ───────────────────────────── the scan ─────────────────────────────
def _shipped_package_globs() -> list[str]:
    """The top-level package globs ``pyproject.toml`` says ship.

    Reading the allow-list rather than retyping a directory table is what keeps
    this census from drifting from what actually reaches an operator.
    """
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    needle = "include = ["
    start = text.index(needle) + len(needle)
    blob = text[start : text.index("]", start)]
    items = [item.strip().strip('"').strip("'") for item in blob.split(",") if item.strip()]
    assert len(items) >= 10, f"pyproject's shipped package list collapsed: {items}"
    return [item.rstrip("*") or item for item in items]


def _shipped_files() -> list[str]:
    out = subprocess.run(
        ("git", "ls-files", "--", *(f"{g}/*.py" for g in _shipped_package_globs())),
        cwd=ROOT,
        capture_output=True,
        check=True,
        timeout=180,
    )
    files = [line for line in out.stdout.decode("utf-8", "replace").splitlines() if line]
    assert len(files) > 100, f"shipped-file census collapsed: {len(files)} files"
    return files


def _is_env_read(node: ast.AST) -> bool:
    """``os.getenv(K)`` / ``os.environ.get(K)`` / ``os.environ[K]``.

    A bare ``attr in {"getenv", "get"}`` test counts ``int(row.get("count"))`` as
    an environment read: an earlier draft of this census reached 113 rows over 36
    files that way, and the population it would have exempted was fiction.
    """
    if isinstance(node, ast.Call):
        func = node.func
        if not isinstance(func, ast.Attribute):
            return False
        owner = func.value
        if func.attr == "getenv":
            return (isinstance(owner, ast.Name) and owner.id == "os") or (
                isinstance(owner, ast.Attribute) and owner.attr == "os"
            )
        if func.attr == "get":
            return isinstance(owner, ast.Attribute) and owner.attr == "environ"
        return False
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "environ"
    )


def _read_names_its_knob(node: ast.AST) -> bool:
    """Whether this environment read states its knob in the source text.

    ``os.getenv(name)`` inside a private coercer states nothing, which is exactly
    why the coercer rather than the call site is the unit of account for it.
    """
    return _knob_of(node) is not None


def _knob_of(node: ast.AST) -> str | None:
    """The literal env name a read states, or ``None`` when it states none."""
    if isinstance(node, ast.Call):
        first = node.args[0] if node.args else None
    elif isinstance(node, ast.Subscript):
        first = node.slice
    else:
        return None
    value = first.value if isinstance(first, ast.Constant) else None
    return value if isinstance(value, str) else None


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _scopes(tree: ast.AST) -> list[tuple[int, int, str, bool]]:
    """``(start, end, dotted name, is_function)`` for every class and def frame."""

    found: list[tuple[int, int, str, bool]] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = getattr(child, "name", None)
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and name:
                dotted = f"{prefix}.{name}" if prefix else name
                found.append(
                    (
                        child.lineno,
                        child.end_lineno or child.lineno,
                        dotted,
                        isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)),
                    )
                )
                visit(child, dotted)
            else:
                visit(child, prefix)

    visit(tree, "")
    return found


def _scope_of(scopes: list[tuple[int, int, str, bool]], line: int) -> str:
    """The innermost function frame holding ``line``, as a dotted name.

    Classes are part of the name (``ElasticsearchConfig.from_env``) but never the
    frame itself: a module-level coercion belongs to no function, and charging it
    to a class would blame the wrong carrier.
    """
    best: tuple[int, str] | None = None
    for start, end, dotted, is_function in scopes:
        if is_function and start <= line <= end and (best is None or start >= best[0]):
            best = (start, dotted)
    return best[1] if best else "<module>"


def _handler_swallows(exc: ast.expr | None) -> bool:
    """Whether this ``except`` would catch a numeric parse failure."""
    names = {"ValueError", "Exception", "BaseException"}
    if isinstance(exc, ast.Name):
        return exc.id in names
    if isinstance(exc, ast.Attribute):
        return exc.attr in names
    if isinstance(exc, ast.Tuple):
        return any(_handler_swallows(item) for item in exc.elts)
    return False


def _guarded_lines(tree: ast.AST) -> set[int]:
    """Lines inside a ``try`` whose handler catches a numeric parse failure.

    The claim is only that the parse failure does not escape, so a handler that
    turns it into a named refusal counts, and one that catches ``KeyError`` does
    not. An empty ``set`` is a real answer and the census legs refuse it rather
    than letting it certify a pass.
    """
    covered: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not any(_handler_swallows(handler.type) for handler in node.handlers):
            continue
        for stmt in node.body:
            for inner in ast.walk(stmt):
                lineno = getattr(inner, "lineno", None)
                if lineno is not None:
                    covered.add(lineno)
    return covered


def _module_numbers(tree: ast.AST) -> dict[str, float]:
    """Module-level ``NAME = <number>`` bindings, so a named default resolves."""
    out: dict[str, float] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            value = node.value.value
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        out[target.id] = value
    return out


def _resolve_number(node: ast.AST | None, consts: dict[str, float]) -> float | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value if not isinstance(node.value, bool) else None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _resolve_number(node.operand, consts)
        return None if inner is None else -inner
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    return None


def _bound_env_names(fn: ast.AST) -> set[str]:
    """Local names this frame assigned straight out of the environment.

    ``raw = os.getenv(name, "").strip()`` binds the text one level under a
    ``.strip()`` call, so the read has to be found anywhere in the value:
    matching only a bare ``os.getenv(...)`` root lost four of the shipped
    coercers on the first draft of this scan.
    """
    found: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            if not any(_is_env_read(sub) for sub in ast.walk(node.value)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    found.add(target.id)
    return found


def _touches_bound_names(node: ast.expr, bound: set[str]) -> bool:
    """Whether this argument is, or is built from, a name read from the environment.

    ``int(raw.strip())`` is the same crash as ``int(raw)``; a rule keyed on the
    argument being exactly the bound name would call it compliant and go green
    while shipping the traceback.
    """
    return any(
        isinstance(sub, ast.Name) and sub.id in bound for sub in ast.walk(node)
    )


def _file_scan(rel: str, source: str) -> dict[str, Any]:
    """One file's three populations, from its parse tree.

    Takes the source text rather than a path so the shape witness can drive it
    with fixtures, and the shipped census with worktree bytes, through the same
    code — a fixture-only extractor is how an absence gate goes blind.
    """
    tree = ast.parse(source)
    scopes = _scopes(tree)
    guarded = _guarded_lines(tree)
    consts = _module_numbers(tree)
    bound = {
        _scope_of(scopes, node.lineno): _bound_env_names(node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    helper_reads: list[dict[str, Any]] = []
    direct: dict[str, dict[str, Any]] = {}
    two_step: dict[str, list[int]] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        scope = _scope_of(scopes, node.lineno)
        key = f"{rel}::{scope}"
        if node.func.id in _HELPERS:
            knob = _knob_of_call(node)
            assert knob is not None, (
                f"{key}:{node.lineno}: an env_config reader is handed a knob name that is "
                "not literal text, so no census can name the knob this process reads"
            )
            assert len(node.args) == 2, (
                f"{key}:{node.lineno}: {node.func.id}({knob}) takes no default, and the "
                "refusal text promises the operator the default it would have used"
            )
            helper_reads.append(
                {
                    "rel": rel,
                    "scope": scope,
                    "knob": knob,
                    "reader": node.func.id,
                    "default_text": ast.unparse(node.args[1]),
                    "default": _resolve_number(node.args[1], consts),
                    "line": node.lineno,
                }
            )
            continue
        if node.func.id not in _COERCE or not node.args:
            continue
        reads = [sub for sub in ast.walk(node) if _is_env_read(sub)]
        named = [knob for knob in (_knob_of(read) for read in reads) if knob]
        arg = node.args[0]
        if named and len(named) == len(reads):
            row = direct.setdefault(key, {"knobs": [], "lines": [], "guarded": True})
            row["knobs"] = sorted({*row["knobs"], *named})
            row["lines"] = sorted({*row["lines"], node.lineno})
            row["guarded"] = row["guarded"] and node.lineno in guarded
            continue
        if reads or _touches_bound_names(arg, bound.get(scope, set())):
            two_step.setdefault(key, [])
            two_step[key] = sorted({*two_step[key], node.lineno})
    return {
        "helper_reads": helper_reads,
        "direct": direct,
        "two_step": two_step,
        "guarded_lines": guarded,
        "config_rows": _config_knobs(rel, tree, consts),
    }


def _knob_of_call(node: ast.Call) -> str | None:
    """The literal first argument of a helper call."""
    first = node.args[0] if node.args else None
    value = first.value if isinstance(first, ast.Constant) else None
    return value if isinstance(value, str) else None


def _config_knobs(rel: str, tree: ast.AST, consts: dict[str, float]) -> list[dict[str, Any]]:
    """Knobs a config class reads in ``from_env`` against its own field defaults.

    A class declaring ``port: int = 3306`` whose ``from_env`` passes
    ``int_env("MYSQL_PORT", 9999)`` would give two answers to "what is the
    default", and the refusal text quotes one of them. This pairs the two
    spellings up out of the tree instead of trusting either.
    """
    rows: list[dict[str, Any]] = []
    for cls in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
        fields: dict[str, ast.expr] = {}
        for stmt in cls.body:
            if (
                isinstance(stmt, ast.AnnAssign)
                and isinstance(stmt.target, ast.Name)
                and stmt.value is not None
            ):
                fields[stmt.target.id] = stmt.value
        for fn in (
            node
            for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name == "from_env"
        ):
            for call in (node for node in ast.walk(fn) if isinstance(node, ast.Call)):
                if not (isinstance(call.func, ast.Name) and call.func.id == "cls"):
                    continue
                for kw in call.keywords:
                    if kw.arg is None or not isinstance(kw.value, ast.Call):
                        continue
                    if _call_name(kw.value) not in _HELPERS:
                        continue
                    knob = _knob_of_call(kw.value)
                    if knob is None or len(kw.value.args) != 2:
                        continue
                    rows.append(
                        {
                            "rel": rel,
                            "cls": cls.name,
                            "field": kw.arg,
                            "knob": knob,
                            "reader_default": _resolve_number(kw.value.args[1], consts),
                            "field_default": _resolve_number(fields.get(kw.arg), consts),
                            "field_declares": kw.arg in fields,
                        }
                    )
    return rows


@functools.lru_cache(maxsize=1)
def _scan() -> dict[str, Any]:
    """Every shipped numeric environment read, bucketed by spelling.

    The buckets must partition reality: a coercion naming one literal knob and one
    computed knob is charged to the direct scan (the literal is the knob an
    operator can set) rather than disappearing into the other table.
    """
    merged: dict[str, Any] = {
        "helper_reads": [],
        "direct": {},
        "two_step": {},
        "config_rows": [],
        "unread": [],
    }
    for rel in _shipped_files():
        path = ROOT / rel
        if not path.is_file():
            merged["unread"].append(f"{rel}: listed by git, missing from the worktree")
            continue
        try:
            result = _file_scan(rel, path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError) as exc:
            merged["unread"].append(f"{rel}: {type(exc).__name__}: {exc}")
            continue
        merged["helper_reads"].extend(result["helper_reads"])
        merged["direct"].update(result["direct"])
        merged["two_step"].update(result["two_step"])
        merged["config_rows"].extend(result["config_rows"])
    merged["unguarded_direct"] = {
        key: row for key, row in merged["direct"].items() if not row["guarded"]
    }
    return merged


# ───────────────────────────── behaviour ─────────────────────────────
def test_an_empty_assignment_gives_the_documented_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``K=`` is unset, not a crash — for ``int_env`` and ``float_env`` alike.

    Whitespace is the same statement: a compose file interpolating ``${VAR:- }``,
    or an operator who typed a space and saved, means "leave this alone", and the
    value that reaches the process is the documented default.
    """
    monkeypatch.setenv(_PROBE_KNOB, "")
    assert int_env(_PROBE_KNOB, 9100) == 9100
    assert float_env(_PROBE_KNOB, 3600.0) == 3600.0
    for text in (" ", "   ", "\t", " \n"):
        monkeypatch.setenv(_PROBE_KNOB, text)
        assert int_env(_PROBE_KNOB, 5) == 5, f"{text!r} is not read as unset"
        assert float_env(_PROBE_KNOB, 2.5) == 2.5, f"{text!r} is not read as unset"
    monkeypatch.delenv(_PROBE_KNOB, raising=False)
    assert int_env(_PROBE_KNOB, 9100) == 9100


def test_a_real_value_still_reaches_the_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tolerating blank must not have cost the knob its purpose.

    A reader that always answered the default would pass the leg above, so this
    drives the same functions with the values an operator actually writes.
    """
    for text, expected in (
        ("9103", 9103),
        (" 9103 ", 9103),
        ("+8080", 8080),
        ("0", 0),
        ("-1", -1),
        ("1_000", 1000),
    ):
        monkeypatch.setenv(_PROBE_KNOB, text)
        assert int_env(_PROBE_KNOB, 9100) == expected, f"{text!r} did not reach the process"
    monkeypatch.setenv(_PROBE_KNOB, "0.5")
    assert float_env(_PROBE_KNOB, 3600.0) == 0.5


def test_a_value_that_is_neither_blank_nor_a_number_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Silently defaulting a mistaken intent would bind a port nobody asked for.

    The refusal has to be readable in a container log, so it names the knob,
    quotes the offending text and states the default it would have used — and it
    is a ``ValueError``, because ``storage/elasticsearch.py`` already handles that
    class and a new base would turn a tolerated value into a crash.
    """
    assert issubclass(EnvKnobError, ValueError)
    monkeypatch.setenv(_PROBE_KNOB, "910o")
    with pytest.raises(EnvKnobError) as raised:
        int_env(_PROBE_KNOB, 9100)
    text = str(raised.value)
    assert _PROBE_KNOB in text and "910o" in text and "9100" in text, text
    monkeypatch.setenv(_PROBE_KNOB, "9.5")
    with pytest.raises(EnvKnobError) as int_refusal:
        int_env(_PROBE_KNOB, 5)
    assert "9.5" in str(int_refusal.value), (
        "an int knob truncating a fractional value would silently halve a timeout"
    )
    monkeypatch.setenv(_PROBE_KNOB, "abc")
    with pytest.raises(EnvKnobError) as float_refusal:
        float_env(_PROBE_KNOB, 3600.0)
    assert "3600.0" in str(float_refusal.value), str(float_refusal.value)


def test_the_helper_invents_no_range(monkeypatch: pytest.MonkeyPatch) -> None:
    """The disclosed boundary: text is parsed, never overruled.

    ``99999`` is not a usable port, and the honest fate for it is the bind
    refusal the operator already reads (#276/#272/#427), not a default chosen on
    their behalf here. Pinned in both directions so a later "validation" cannot
    quietly start ignoring a knob.
    """
    monkeypatch.setenv(_PROBE_KNOB, "99999")
    assert int_env(_PROBE_KNOB, 9100) == 99999
    monkeypatch.setenv(_PROBE_KNOB, "-5")
    assert int_env(_PROBE_KNOB, 9100) == -5
    monkeypatch.setenv(_PROBE_KNOB, "0")
    assert int_env(_PROBE_KNOB, 9100) == 0


def test_every_config_knob_that_is_left_blank_yields_the_class_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fate at the entry points that actually start the stack.

    Every row comes from the parse tree: a ``from_env`` classmethod handing a
    ``cls(...)`` keyword to ``storage/env_config.py``. Blank each knob in turn and
    the built config must carry that class's own documented default — the number
    a reader of the class gets with no environment at all.
    """
    scan = _scan()
    rows = scan["config_rows"]
    assert rows, "no shipped config class reads a numeric knob through the helper"
    by_rel: dict[str, list[dict[str, Any]]] = {}
    for read in scan["helper_reads"]:
        by_rel.setdefault(read["rel"], []).append(read)
    failures: list[str] = []
    for row in rows:
        assert row["field_declares"], (
            f"{row['rel']}::{row['cls']}.from_env passes {row['knob']} to {row['field']}=, "
            "which the class does not declare as a field"
        )
        module = importlib.import_module(row["rel"][: -len(".py")].replace("/", "."))
        cls = getattr(module, row["cls"])
        for other in by_rel[row["rel"]]:
            if other["knob"] != row["knob"]:
                monkeypatch.delenv(other["knob"], raising=False)
        for blank in ("", "   "):
            monkeypatch.setenv(row["knob"], blank)
            got = getattr(cls.from_env(), row["field"])
            if got != row["field_default"]:
                failures.append(
                    f"{row['rel']}::{row['cls']}.{row['field']} with {row['knob']}={blank!r} "
                    f"gave {got!r}; the class default is {row['field_default']!r}"
                )
    assert not failures, "\n".join(failures)


def test_the_default_the_reader_promises_is_the_default_the_class_declares() -> None:
    """One number per knob, or the refusal text is a lie.

    ``EnvKnobError`` tells the operator the documented default, and the dataclass
    carries its own. The scan reads both out of the same tree; this refuses the
    pair disagreeing — including when both name a module constant rather than
    spelling a number, which is where a hand-copied default would drift.
    """
    rows = _scan()["config_rows"]
    assert rows, "no shipped config class reads a numeric knob through the helper"
    drift = [
        f"{row['rel']}::{row['cls']}.{row['field']} knob {row['knob']}: reader default "
        f"{row['reader_default']!r}, class default {row['field_default']!r}"
        for row in rows
        if row["reader_default"] != row["field_default"]
    ]
    assert not drift, "\n".join(drift)


def test_a_garbage_knob_names_itself_at_the_store_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal must survive the way the config is actually built.

    Reaching ``int_env`` is one thing; reaching it through ``from_env()``, where
    the operator's ``K=abc`` is read between a host string and a password, is the
    path a deploy takes. Each refusal must still name its own knob.
    """
    rows = _scan()["config_rows"]
    assert rows, "no shipped config class reads a numeric knob through the helper"
    scan = _scan()
    by_rel: dict[str, list[dict[str, Any]]] = {}
    for read in scan["helper_reads"]:
        by_rel.setdefault(read["rel"], []).append(read)
    for row in rows:
        module = importlib.import_module(row["rel"][: -len(".py")].replace("/", "."))
        cls = getattr(module, row["cls"])
        # One garbage knob per run, so the message names the knob this row set.
        # Sibling knobs of the same config are cleared first: they are read before
        # this one inside ``from_env()``, and a leftover value from a previous row
        # would make the config refuse a knob the test never touched.
        for other in by_rel[row["rel"]]:
            if other["knob"] != row["knob"]:
                monkeypatch.delenv(other["knob"], raising=False)
        monkeypatch.setenv(row["knob"], "not-a-number")
        with pytest.raises(EnvKnobError) as raised:
            cls.from_env()
        assert row["knob"] in str(raised.value), (
            f"{row['rel']}::{row['cls']} refused {row['knob']} without naming it: {raised.value}"
        )


def test_an_empty_rate_limit_knob_keeps_the_endpoint_answering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The knob that gates traffic must not gate the process out instead.

    ``api/auth.py`` reads the cap per request, above its fail-open ``try``: an
    empty ``SPECPROOF_RATE_LIMIT_PER_MIN`` raised inside the dependency, which is
    a 500 on every route the limiter protects. These calls go through the real
    ``enforce_rate_limit`` with a real request scope, so the answer is the status
    line an operator would see, not a unit of the helper.
    """

    class _AlwaysOverLimit:
        """A Redis double that reports the window as already past any cap."""

        def __init__(self) -> None:
            self.client = self

        def incr(self, key: str) -> int:
            return 999

        def expire(self, key: str, ttl: int) -> None:
            return None

    monkeypatch.setattr("storage.redis.RedisStore", _AlwaysOverLimit)

    def _request() -> Request:
        return Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "GET",
                "path": "/api/jobs",
                "raw_path": b"/api/jobs",
                "query_string": b"",
                "root_path": "",
                "scheme": "http",
                "headers": [(b"x-api-key", b"m471-probe-key")],
                "client": ("127.0.0.1", 50000),
                "server": ("testserver", 80),
            }
        )

    monkeypatch.setenv("SPECPROOF_RATE_LIMIT_PER_MIN", "")
    with pytest.raises(HTTPException) as blank:
        enforce_rate_limit(_request())
    assert blank.value.status_code == 429, blank.value.detail
    assert "60 requests/min" in blank.value.detail, (
        f"an empty cap answered {blank.value.detail!r}, not the documented default of 60"
    )
    monkeypatch.setenv("SPECPROOF_RATE_LIMIT_PER_MIN", "7")
    with pytest.raises(HTTPException) as capped:
        enforce_rate_limit(_request())
    assert "7 requests/min" in capped.value.detail, capped.value.detail
    monkeypatch.setenv("SPECPROOF_RATE_LIMIT_PER_MIN", "many")
    with pytest.raises(EnvKnobError) as refused:
        enforce_rate_limit(_request())
    assert "SPECPROOF_RATE_LIMIT_PER_MIN" in str(refused.value)


def test_an_injected_value_still_outranks_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ternary shape the two long-running loops use.

    ``storage/invoice_cron.py`` and ``agent/worker.py`` consult the knob only when
    the caller passed no value, so a blank environment must not overrule a
    constructor argument — and must not crash while deciding not to. Both fates
    are checked on one object, because the guard is a single ``else``.
    """
    from storage.billing import SqliteBillingStore, seed_default_plans
    from storage.invoice_cron import DEFAULT_INTERVAL_SECONDS, DEFAULT_METRICS_PORT, InvoiceCron

    billing = SqliteBillingStore(tmp_path / "billing.db")
    try:
        seed_default_plans(billing)
        monkeypatch.setenv("INVOICE_CRON_INTERVAL_SECONDS", "")
        monkeypatch.setenv("INVOICE_CRON_METRICS_PORT", "")
        blank_run = InvoiceCron(billing)
        assert blank_run.interval == DEFAULT_INTERVAL_SECONDS, blank_run.interval
        assert blank_run.metrics_port == DEFAULT_METRICS_PORT, blank_run.metrics_port
        injected = InvoiceCron(billing, interval=7.5, metrics_port=9199)
        assert (injected.interval, injected.metrics_port) == (7.5, 9199), (
            "an explicit constructor value lost to the environment"
        )
        monkeypatch.setenv("INVOICE_CRON_METRICS_PORT", "9o103")
        assert InvoiceCron(billing, metrics_port=9103).metrics_port == 9103, (
            "a refused knob overruled the value the caller passed for it"
        )
        with pytest.raises(EnvKnobError) as raised:
            InvoiceCron(billing, interval=1.0)
        assert "INVOICE_CRON_METRICS_PORT" in str(raised.value), str(raised.value)
    finally:
        billing.close()


# ───────────────────────────── the census ─────────────────────────────
def test_the_scan_charges_every_forbidden_shape_it_claims_to() -> None:
    """An absence claim is worth only what its extractor can see.

    The census legs below assert set equalities; a scan matching nothing would
    satisfy them. So every shape the scan promises to charge is driven through it
    here, and every shape it promises to leave alone is shown left alone. The
    literal-versus-computed knob split is the part that rots: ``os.environ``
    subscripts and ``name``-typed knobs are real shipped spellings, not fictions.
    """

    def _charge(source: str) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        result = _file_scan("fixture.py", source)
        return result["direct"], result["two_step"], result["helper_reads"]

    direct, two_step, _ = _charge(
        "import os\n\n\ndef read():\n    return int(os.environ['X_PORT'])\n"
    )
    assert list(direct.values())[0]["knobs"] == ["X_PORT"], direct
    assert list(direct)[0] == "fixture.py::read", direct
    assert two_step == {}, two_step
    direct, two_step, _ = _charge(
        "import os\n\n\ndef read():\n    return int(os.getenv('X_PORT', '9'))\n"
    )
    assert list(direct.values())[0]["knobs"] == ["X_PORT"], direct
    assert direct and two_step == {}
    direct, two_step, _ = _charge(
        "import os\n\n\ndef read(env):\n    return int(env['X_PORT'])\n"
    )
    assert (direct, two_step) == ({}, {}), (
        f"a dict the caller handed in charged as the process environment: {direct} {two_step}"
    )
    _, two_step, _ = _charge(
        "import os\n\n\ndef _env_int(name, default):\n"
        "    raw = os.getenv(name, '')\n    return int(raw)\n"
    )
    assert list(two_step) == ["fixture.py::_env_int"], two_step
    _, two_step, _ = _charge(
        "import os\n\n\ndef _env_int(name, default):\n    return int(os.getenv(name, default))\n"
    )
    assert list(two_step) == ["fixture.py::_env_int"], two_step
    _, two_step, _ = _charge(
        "import os\n\n\ndef read():\n    raw = os.environ.get('X')\n    return float(raw)\n"
    )
    assert list(two_step) == ["fixture.py::read"], two_step
    _, two_step, _ = _charge(
        "import os\n\n\ndef read():\n    raw = os.getenv(NAME)\n    return float(raw.strip())\n"
    )
    assert list(two_step) == ["fixture.py::read"], two_step
    direct, two_step, helper_rows = _charge(
        "import os\n\n\ndef read(port):\n"
        "    return int(port), os.environ.get('X'), int('7'), int_env('Y_PORT', 9)\n"
    )
    assert (direct, two_step) == ({}, {}), (direct, two_step)
    assert [(row["knob"], row["default_text"], row["default"]) for row in helper_rows] == [
        ("Y_PORT", "9", 9)
    ], helper_rows
    scopes = _scopes(ast.parse("class C:\n    def m(self):\n        x = 1\n"))
    assert _scope_of(scopes, 3) == "C.m"
    assert _scope_of(_scopes(ast.parse("x = int(os.environ['Y'])")), 1) == "<module>"
    body = "def read():\n    try:\n        return int('x')\n"
    catches_parse = ast.parse(body + "    except ValueError:\n        return 1\n")
    catches_other = ast.parse(body + "    except KeyError:\n        return 1\n")
    assert 3 in _guarded_lines(catches_parse), (
        "a handler that catches the parse failure does not cover its try body"
    )
    assert _guarded_lines(catches_other) == set(), (
        "a handler for an unrelated exception certified a numeric parse failure"
    )


def test_no_shipped_read_coerces_an_environment_value_to_a_number_by_hand() -> None:
    """The census is this fix's own guard rail.

    Every shipped numeric env read now goes through ``storage/env_config.py``,
    except the rows in ``_GUARDED_DIRECT``, each safe because a handler catches
    the parse failure — re-derived from the tree on every run, not remembered
    from the batch that wrote it. The compliant population is pinned as a floor
    as well as the exemption by name: a scan that lost sight of either half would
    otherwise certify the other.
    """
    scan = _scan()
    assert not scan["unread"], "\n".join(scan["unread"])
    charged = set(scan["direct"])
    assert charged == set(_GUARDED_DIRECT), (
        f"shipped direct coercions {sorted(charged)} no longer match the pinned "
        f"exemptions {sorted(_GUARDED_DIRECT)}: a new hand-written coercion of an "
        "env value belongs in storage/env_config.py, and a stale row here is an "
        "exemption nobody can point at"
    )
    assert not scan["unguarded_direct"], (
        f"{sorted(scan['unguarded_direct'])} coerce an env value outside any "
        "handler that catches a parse failure: an empty assignment kills the "
        "process there, which is the defect #471 removed"
    )
    for key, row in sorted(scan["direct"].items()):
        assert row["guarded"], f"{key} is listed as exempt but is unguarded"
        assert row["knobs"], f"{key} is charged without naming a knob"
        assert key in _GUARDED_DIRECT and _GUARDED_DIRECT[key] == "try-guarded", key
    helper_reads = scan["helper_reads"]
    assert len(helper_reads) >= 18, (
        f"only {len(helper_reads)} shipped reads go through the helper: #471 "
        "converted 18 hand-written coercions, and a scan that lost sight of them "
        "would certify the exemption table while shipping the crash"
    )
    assert {row["rel"] for row in helper_reads} >= {
        "agent/worker.py",
        "api/auth.py",
        "storage/invoice_cron.py",
        "storage/mysql.py",
        "storage/redis.py",
    }, sorted({row["rel"] for row in helper_reads})


def test_the_second_spelling_is_enumerated_and_survives_an_empty_knob(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every reader the direct rule cannot see is named, and then run.

    These coerce through a local name or a knob handed in by the caller, so the
    census refuses the roster drifting in either direction and drives each entry
    with the knob blank. Generic coercers get a sentinel default, because the knob
    they read belongs to whoever calls them; knob-specific readers are driven
    through their own documented name and answer their own documented default. On
    a garbage value an entry must either answer a default or refuse with the knob
    named — the one fate not allowed is an unhandled parse error, which is what
    this batch removed from the other spelling.
    """
    found = set(_scan()["two_step"])
    generic = {f"{rel}::{scope}" for rel, scope in _GENERIC_COERCERS}
    probed = {f"{rel}::{scope}" for rel, scope in _KNOB_PROBES}
    assert not generic & probed, sorted(generic & probed)
    pinned = generic | probed
    assert pinned, "the second-spelling tables are empty, so nothing is being watched"
    assert found == pinned, (
        f"second-spelling roster drifted: found {sorted(found - pinned)}, "
        f"pinned but gone {sorted(pinned - found)}. Each of these coerces an env "
        "value through a local name or a caller-supplied knob, so the direct "
        "census cannot see it: add the reader to this table and prove its blank "
        "fate, or route it through storage/env_config.py"
    )
    for key in sorted(generic):
        rel, scope = key.split("::", 1)
        fn = _attr_path(_module_of(rel), scope)
        monkeypatch.setenv(_PROBE_KNOB, "")
        assert fn(_PROBE_KNOB, _PROBE_DEFAULT) == _PROBE_DEFAULT, (
            f"{key} did not answer the default for an empty assignment"
        )
        monkeypatch.setenv(_PROBE_KNOB, "abc")
        try:
            answered = fn(_PROBE_KNOB, _PROBE_DEFAULT)
        except BaseException as exc:  # noqa: BLE001 — the fate is the claim
            refused = str(exc)
            assert "invalid literal" not in refused, (
                f"{key} still raises the raw parse error: {refused}"
            )
            assert _PROBE_KNOB in refused, f"{key} refused without naming the knob: {refused}"
        else:
            assert answered == _PROBE_DEFAULT, (
                f"{key} turned 'abc' into {answered!r} instead of refusing it or "
                "defaulting it"
            )
    for rel_scope, (drive, expected) in sorted(_KNOB_PROBES.items()):
        rel, scope = rel_scope
        key = f"{rel}::{scope}"
        # Resolve the censused carrier before probing it: a probe pointed at a
        # lookalike function would prove nothing about the reader the scan found.
        assert callable(_attr_path(_module_of(rel), scope)), key
        assert drive(monkeypatch) == expected, (
            f"{key} did not answer its documented default {expected!r} for an "
            "empty assignment"
        )


def test_every_helper_read_names_its_knob_and_its_default_in_the_source() -> None:
    """A knob named by an expression cannot be censused, refused, or documented.

    Three promises depend on the text being readable where it is written: this
    census, the ops documentation that lists the knobs, and the refusal message
    that quotes the default it would have used. The scan already refuses a
    non-literal name and a missing argument, so this leg's work is the numeric
    default — a knob whose default is computed at call time has no single
    documented number to promise.
    """
    rows = _scan()["helper_reads"]
    assert rows, "no shipped read goes through storage/env_config.py"
    unreadable = [
        f"{row['rel']}:{row['line']} {row['reader']}({row['knob']}, {row['default_text']})"
        for row in rows
        if row["default"] is None
    ]
    assert not unreadable, (
        "these defaults resolve to no number this census can read:\n"
        + "\n".join(sorted(unreadable))
    )


def test_the_helper_tuple_is_the_surface_the_module_declares(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_HELPERS`` must name what ``storage/env_config.py`` actually declares.

    The tuple is hand-typed because the census charges only readers that answer a
    number, so a rename is invisible to it by construction: every shipped read
    would leave the census, ``helper_reads`` would empty, and the direct rule
    would still find nothing to charge — this gate reporting a compliant tree from
    a roster that no longer contains its own subject. Deriving the surface from
    ``__all__`` plus the ``(name, default)`` signature shape and comparing the two
    makes a rename land here, on gate #235's reader recognition, and on the
    shipped call sites in the same commit.
    """
    declared: list[str] = []
    for name in _env_config.__all__:
        obj = getattr(_env_config, name)
        if isinstance(obj, type) or not callable(obj):
            continue
        params = list(inspect.signature(obj).parameters)
        assert params == ["name", "default"], f"storage/env_config.{name} takes {params}"
        declared.append(name)
    assert tuple(sorted(declared)) == tuple(sorted(_HELPERS)), (
        f"storage/env_config.py declares the (name, default) readers {sorted(declared)} "
        f"while this census charges {_HELPERS}: a read through the undeclared name is "
        "counted as neither the compliant spelling nor a coercion, so it disappears"
    )

    # The names must still answer a number, or the equality above pins a surface
    # that no longer coerces and both sides are fictions.
    for name in _HELPERS:
        reader = getattr(_env_config, name)
        monkeypatch.delenv(_PROBE_KNOB, raising=False)
        assert reader(_PROBE_KNOB, _PROBE_DEFAULT) == _PROBE_DEFAULT, (
            f"{name} did not answer the default for an unset knob"
        )
        monkeypatch.setenv(_PROBE_KNOB, "12")
        answered = reader(_PROBE_KNOB, _PROBE_DEFAULT)
        assert isinstance(answered, (int, float)) and not isinstance(answered, bool), (
            f"{name} answered {answered!r} for a numeric assignment, not a number"
        )
        assert answered == 12, f"{name} answered {answered!r} for '12'"
