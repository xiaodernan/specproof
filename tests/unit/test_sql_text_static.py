"""SQL text handed to a database executor must be provably constant.

bandit's B608 fires on any string concatenation that reaches `execute()`, and it
cannot see through the two shapes this codebase actually uses to stay safe:
concatenating module-level constant fragments, and interpolating an identifier
that an allowlist regex has already rejected. That is why `python -m bandit -r
... -ll` reported seven medium findings on the security job the first time CI
could run at all (see ROADMAP §28.1) while the code was in fact safe — and a
scanner nobody can satisfy is a scanner everybody silences.

This gate is the stronger claim, and it is the one that has to hold: for every
`execute`/`executemany` call in the shipped packages, the first argument is
either

  * a literal; a concatenation/modulo of things that are themselves constant
    (module-level constants, local bindings, loop targets, container literals
    and literal-dict subscripts, `str.join`/`str.replace`/`str.format` results,
    `_to_mysql(...)` of a constant, or the string a same-module helper returns);
  * an f-string whose interpolations are constants or identifiers that a guard
    in the same function validated and rejects — `if not <re>.fullmatch(name):
    continue/raise/return` before the call;
  * a name forwarded from a caller (`sql`, `stmt`, ...). The obligation moves up
    a frame rather than vanishing, so the call sites feeding such a helper are
    checked here too.

A function parameter is *not* constant by default — the whole point of the file
is that data and SQL text are not interchangeable. Anything that fails is a
finding, and a finding must be either fixed or named in `NON_STATIC_SQL_SITES`
with the reason it is safe. The register cannot rot: an entry that stops being a
finding fails the suite, and a finding that is not registered fails the suite.
"""
from __future__ import annotations

import ast
import re
from collections.abc import Mapping
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

#: Shipped packages — the same set CI scans with bandit.
PACKAGES = (
    "agent", "api", "cli", "storage", "providers", "evidence",
    "observability", "sandbox", "experiments", "integrations",
)

#: Receivers whose `execute`/`executemany` runs SQL. `conn.cursor().execute` is
#: recognised as "cursor()".
_EXECUTORS = frozenset({"execute", "executemany"})
_RECEIVER_NAMES = frozenset({
    "cur", "cursor", "conn", "_conn", "connection", "db", "_db", "cursor()",
})

#: Parameter names that carry SQL text from the caller. A helper with one of
#: these is a pass-through executor: its own body is exempt, its call sites are
#: held to the same standard as a direct `execute`.
_EXECUTOR_PARAMS = frozenset({"sql", "statement", "stmt", "query"})

#: Names whose value a guard has allowlisted by aborting.
_GUARD_FUNCS = frozenset({"fullmatch", "match", "search"})

#: A finding that is safe but not provable by the rules above, keyed by
#: "<file>::<the call, as source>". Empty is the goal. Every entry needs a reason
#: that says where the text comes from, and every entry is re-checked on every
#: run: the gate fails if the code it names is gone, so the register cannot drift
#: away from the code it describes.
NON_STATIC_SQL_SITES: dict[str, str] = {
    "storage/migrations.py::self._execute(conn, version, name, stmt)": (
        "one statement of a repository migration file: the text is read from "
        "MIGRATIONS_DIR/*.sql inside this repo (app-owned DDL, not request data), "
        "_split_statements only strips comments, and values still travel as "
        "bound parameters"
    ),
    "storage/mysql.py::cursor.execute(_sql, params)": (
        "transition_job_status_with_notify executes the SAME assembled "
        "statement as transition_job_status — both come from the shared "
        "_transition_statement helper (literal fragments + bound parameters, "
        "no request data). The static prover proves single-function "
        "dataflow, so the helper's return value needs this registration."
    ),
}


# ── binding collection ───────────────────────────────────────────────────────


def _aborts(body: list[ast.stmt]) -> bool:
    return any(
        isinstance(s, (ast.Continue, ast.Break, ast.Raise, ast.Return)) for s in body
    )


def _aborting_guards(function: ast.AST) -> set[str]:
    """Names validated by `if not <re>.fullmatch(name): continue/raise/return`."""
    guarded: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.If) or not _aborts(node.body):
            continue
        for call in ast.walk(node.test):
            if not isinstance(call, ast.Call) or not call.args:
                continue
            func = call.func
            name = func.attr if isinstance(func, ast.Attribute) else None
            if name in _GUARD_FUNCS and isinstance(call.args[0], ast.Name):
                guarded.add(call.args[0].id)
    return guarded


def _bind(
    target: ast.expr,
    value: ast.expr,
    env: dict[str, list[ast.expr]],
    module: ast.Module | None = None,
) -> None:
    if isinstance(target, ast.Name):
        env.setdefault(target.id, []).append(value)
    elif isinstance(target, ast.Starred):
        _bind(target.value, value, env, module)
    elif isinstance(target, (ast.Tuple, ast.List)):
        if isinstance(value, ast.IfExp):
            _bind(target, value.body, env, module)
            _bind(target, value.orelse, env, module)
        elif isinstance(value, (ast.Tuple, ast.List)) and len(target.elts) == len(value.elts):
            for sub, item in zip(target.elts, value.elts, strict=True):
                _bind(sub, item, env, module)
        elif isinstance(value, ast.Call) and module is not None:
            # `sql, params = _update_status_sql(...)`: bind each name to the
            # matching element of every tuple the helper returns.
            returned = _helper_return_tuples(module, _callee_name(value))
            if returned and all(len(r) == len(target.elts) for r in returned):
                for index, sub in enumerate(target.elts):
                    for elements in returned:
                        _bind(sub, elements[index], env, module)


def _collect(function: ast.AST, module: ast.Module) -> dict[str, list[ast.expr]]:
    """Module-level bindings plus this function's own, including loop targets."""
    env: dict[str, list[ast.expr]] = {}
    for node in list(module.body) + list(ast.walk(function)):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                _bind(target, node.value, env, module)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            _bind(node.target, node.value, env, module)
        elif isinstance(node, ast.For):
            _bind(node.target, node.iter, env, module)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    _bind(item.optional_vars, item.context_expr, env, module)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.args
            and node.func.attr in {"append", "extend"}
            and isinstance(node.func.value, ast.Name)
        ):
            _bind(node.func.value, node.args[0], env, module)
    return env


# ── the static-ness judgement ────────────────────────────────────────────────


def _is_static(
    node: ast.expr,
    env: dict[str, list[ast.expr]],
    forwarding: Mapping[str, bool],
    guards: frozenset[str],
    module: ast.Module,
    depth: int = 0,
) -> bool:
    if depth > 10:
        return False
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.Name):
        forwarded = forwarding.get(node.id)
        if forwarded is not None:
            # A parameter shadows any same-named module constant, and a parameter
            # that is not forwarded is data — `query` in `search_jobs` is a search
            # term, not a statement. Probe P2 is why this branch exists.
            return forwarded
        bindings = env.get(node.id)
        if not bindings:
            return False  # a parameter, or something this file cannot see
        return all(
            _is_static(b, env, forwarding, guards, module, depth + 1) for b in bindings
        )
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, (ast.Add, ast.Mod, ast.Mult)):
            return _is_static(node.left, env, forwarding, guards, module, depth + 1) and (
                _is_static(node.right, env, forwarding, guards, module, depth + 1)
            )
        return False
    if isinstance(node, ast.JoinedStr):
        return _fstring_is_static(node, env, forwarding, guards, module, depth)
    if isinstance(node, ast.IfExp):
        return _is_static(node.body, env, forwarding, guards, module, depth + 1) and (
            _is_static(node.orelse, env, forwarding, guards, module, depth + 1)
        )
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return all(
            _is_static(e, env, forwarding, guards, module, depth + 1) for e in node.elts
        )
    if isinstance(node, ast.Dict):
        return all(
            v is not None
            and _is_static(v, env, forwarding, guards, module, depth + 1)
            for v in node.values
        )
    if isinstance(node, ast.Subscript):
        # `sql = _CAS_BY_ACTION[action]` — one of a fixed set of constants. The
        # key may be data; the text that goes to the server is still a constant.
        containers = [node.value]
        if isinstance(node.value, ast.Name):
            containers = list(env.get(node.value.id) or [])
        if not containers:
            return False
        for container in containers:
            if isinstance(container, ast.Dict):
                ok = all(
                    v is not None
                    and _is_static(v, env, forwarding, guards, module, depth + 1)
                    for v in container.values
                )
            elif isinstance(container, (ast.List, ast.Tuple)):
                ok = all(
                    _is_static(e, env, forwarding, guards, module, depth + 1)
                    for e in container.elts
                )
            else:
                ok = False
            if not ok:
                return False
        return True
    if isinstance(node, ast.Call):
        return _call_is_static(node, env, forwarding, guards, module, depth)
    return False


def _fstring_is_static(
    node: ast.JoinedStr,
    env: dict[str, list[ast.expr]],
    forwarding: Mapping[str, bool],
    guards: frozenset[str],
    module: ast.Module,
    depth: int,
) -> bool:
    for part in node.values:
        if not isinstance(part, ast.FormattedValue):
            continue
        if isinstance(part.value, ast.Name) and part.value.id in guards:
            continue  # allowlist-validated identifier
        if _is_static(part.value, env, forwarding, guards, module, depth + 1):
            continue
        return False
    return True


def _call_is_static(
    node: ast.Call,
    env: dict[str, list[ast.expr]],
    forwarding: Mapping[str, bool],
    guards: frozenset[str],
    module: ast.Module,
    depth: int,
) -> bool:
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else (
        func.id if isinstance(func, ast.Name) else None
    )

    def sub(expr: ast.expr) -> bool:
        return _is_static(expr, env, forwarding, guards, module, depth + 1)

    if name == "_to_mysql":  # placeholder translation; the text is unchanged
        return bool(node.args) and sub(node.args[0])
    if name == "join" and isinstance(func, ast.Attribute):
        if not sub(func.value):
            return False
        for arg in node.args:
            if isinstance(arg, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
                if not sub(arg.elt):
                    return False
            elif not sub(arg):
                return False
        return True
    if name in {"replace", "format", "upper", "lower", "strip"} and isinstance(
        func, ast.Attribute
    ):
        return sub(func.value) and all(sub(a) for a in node.args)
    if name is not None and isinstance(func, ast.Name):
        returned = _helper_return_tuples(module, name)
        if returned is not None:
            return bool(returned) and all(
                elements and sub(elements[0]) for elements in returned
            )
    return False


def _helper_return_tuples(module: ast.Module, name: str) -> list[list[ast.expr]] | None:
    """Every tuple a same-module helper returns, as its element list.

    `sql, params = _update_status_sql(...)` is how this repo builds a statement
    beside its values; the statement half still has to be constant.
    """
    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            tuples = [
                list(sub.value.elts)
                for sub in ast.walk(node)
                if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Tuple)
            ]
            return tuples
    return None


# ── scanning ─────────────────────────────────────────────────────────────────


def _callee_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _receiver(node: ast.Call) -> str | None:
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr not in _EXECUTORS:
        return None
    value = func.value
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    if isinstance(value, ast.Call):
        return "cursor()" if _callee_name(value) == "cursor" else None
    return None


def _params(function: ast.AST) -> list[str]:
    args = function.args
    return [
        a.arg for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
    ]


def _forwarded_names(function: ast.AST, params: frozenset[str]) -> frozenset[str]:
    """Parameters this function hands to an executor *as the statement itself*.

    Only a whole-argument pass-through counts: `cur.execute(statement, values)`,
    `cur.execute(stmt.replace("?", "%s"))`, or a branch that picks between such
    forms. A name that merely appears *inside* a bigger expression — a search term
    called `query` interpolated into an f-string — is data, and probe P2 caught
    exactly that name being waved through.
    """
    forwarded: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if _receiver(node) not in _RECEIVER_NAMES:
            continue
        name = _bare_parameter(node.args[0], params)
        if name is not None:
            forwarded.add(name)
    return frozenset(forwarded)


def _param_states(function: ast.AST) -> Mapping[str, bool]:
    """Every parameter of `function`, mapped to "is this the statement itself?".

    A parameter is *not* constant by default; the only parameters this gate may
    wave through are the ones the function hands to an executor as the whole
    first argument, because then the obligation moves to that caller. The
    difference matters for the ones that look like SQL by name: `query` in a
    search body is a search term, and treating it as a statement is how probe P2
    produced a finding against safe code.
    """
    params = frozenset(_params(function))
    forwarded = _forwarded_names(function, params)
    return {name: name in forwarded for name in params}


def _bare_parameter(node: ast.expr, params: frozenset[str]) -> str | None:
    """The parameter `node` is, when it is nothing but that parameter."""
    if isinstance(node, ast.Name):
        return node.id if node.id in params else None
    if isinstance(node, ast.IfExp):
        left = _bare_parameter(node.body, params)
        right = _bare_parameter(node.orelse, params)
        return left if left is not None and left == right else None
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "replace"
    ):
        return _bare_parameter(node.func.value, params)
    return None


def executor_helpers(module: ast.Module) -> dict[str, list[int]]:
    """Helper name -> argument positions carrying SQL it executes itself.

    Only a helper that really reaches an executor with its own parameter counts:
    a parser that happens to name an argument `sql` (`_split_statements(sql)`) or
    a search body named `query` owns no SQL text and must not be dragged into
    this rule.
    """
    helpers: dict[str, list[int]] = {}
    for node in ast.walk(module):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        params = [p for p in _params(node) if p != "self"]
        positions = [i for i, name in enumerate(params) if name in _EXECUTOR_PARAMS]
        if not positions:
            continue
        forwarded = {
            N.id
            for N in ast.walk(node)
            if isinstance(N, ast.Call)
            and N.args
            and _receiver(N) in _RECEIVER_NAMES
            and isinstance(N.args[0], ast.expr)
            for N in ast.walk(N.args[0])
            if isinstance(N, ast.Name)
        }
        if forwarded & set(params):
            helpers[node.name] = [
                i for i, name in enumerate(params) if name in _EXECUTOR_PARAMS and name in forwarded
            ]
    return helpers


def _scan_function(
    function: ast.AST,
    module: ast.Module,
    relative: str,
    findings: list[tuple[str, int]],
) -> None:
    env = _collect(function, module)
    forwarding = _param_states(function)
    guards = frozenset(_aborting_guards(function))
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if _receiver(node) not in _RECEIVER_NAMES:
            continue
        if _is_static(node.args[0], env, forwarding, guards, module):
            continue
        findings.append((relative, node.lineno))


def _scan_helper_calls(
    module: ast.Module,
    helpers: dict[str, list[int]],
    relative: str,
    findings: list[tuple[str, int]],
) -> None:
    """A pass-through executor is only as safe as what its callers hand it."""
    if not helpers:
        return
    for function in [
        n for n in ast.walk(module)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]:
        env = _collect(function, module)
        forwarding = _param_states(function)
        guards = frozenset(_aborting_guards(function))
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            positions = helpers.get(_callee_name(node) or "")
            if not positions:
                continue
            for position in positions:
                if position >= len(node.args):
                    continue  # keyword-passed or defaulted; nothing to judge here
                argument = node.args[position]
                if _is_static(argument, env, forwarding, guards, module):
                    continue
                findings.append((relative, node.lineno))


def non_static_sql_sites(root: Path | None = None) -> list[tuple[str, str]]:
    """(repo-relative file, the call as source) for every unprovable execute()."""
    base = root if root is not None else REPO
    findings: list[tuple[str, str]] = []
    for package in PACKAGES:
        for path in sorted((base / package).rglob("*.py")):
            module = ast.parse(path.read_text(encoding="utf-8"))
            relative = path.relative_to(base).as_posix()
            raw: list[tuple[str, int]] = []
            for function in [
                n for n in ast.walk(module)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]:
                _scan_function(function, module, relative, raw)
            _scan_helper_calls(module, executor_helpers(module), relative, raw)
            for name, line in raw:
                findings.append((name, _call_source(module, line)))
    return sorted(set(findings))


def _call_source(module: ast.Module, line: int) -> str:
    """The call on `line`, whitespace-collapsed, as a reviewable anchor."""
    for node in ast.walk(module):
        if isinstance(node, ast.Call) and node.lineno == line:
            return " ".join(ast.unparse(node).split())
    return f"<line {line}>"


def _key(finding: tuple[str, str]) -> str:
    return f"{finding[0]}::{finding[1]}"


# ── the gate ─────────────────────────────────────────────────────────────────


def test_no_sql_text_reaches_an_executor_without_proof() -> None:
    unregistered = [f for f in non_static_sql_sites() if _key(f) not in NON_STATIC_SQL_SITES]
    assert not unregistered, (
        "SQL text reaches a database executor without a proof it is constant: "
        f"{[_key(f) for f in unregistered]}. Either build the text from constants "
        "(or interpolate an identifier a fullmatch guard has rejected), or name the "
        "site in NON_STATIC_SQL_SITES with the reason it is safe."
    )


def test_the_register_is_not_lying() -> None:
    found = {_key(f) for f in non_static_sql_sites()}
    stale = sorted(set(NON_STATIC_SQL_SITES) - found)
    assert not stale, (
        f"{stale} are registered as unprovable but are no longer findings; drop them "
        "so the register keeps describing real debt"
    )


def test_each_registered_site_still_matches_the_code_it_describes() -> None:
    for registered, reason in sorted(NON_STATIC_SQL_SITES.items()):
        path, _, code = registered.partition("::")
        assert len(reason.strip()) >= 40, (
            f"{registered} is registered with '{reason}'; a reason has to say where "
            "the text comes from, not just that it is fine"
        )
        source = " ".join((REPO / path).read_text(encoding="utf-8").split())
        assert code in source, (
            f"{registered} no longer appears in {path}; the reason attached to it "
            "describes code that moved or changed — re-review it"
        )


def test_the_scan_actually_read_something() -> None:
    """A blind scan must not read as 'every call is provably constant'."""
    calls = 0
    for package in PACKAGES:
        for path in (REPO / package).rglob("*.py"):
            calls += path.read_text(encoding="utf-8").count(".execute(")
    assert calls >= 50, f"only {calls} execute() calls found — the scan read nothing"


def test_the_receiver_set_is_not_vacuous() -> None:
    """The scan only means something if it recognises this repo's receivers."""
    recognised = 0
    for package in PACKAGES:
        for path in (REPO / package).rglob("*.py"):
            module = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(module):
                if (
                    isinstance(node, ast.Call)
                    and node.args
                    and _receiver(node) in _RECEIVER_NAMES
                ):
                    recognised += 1
    assert recognised >= 50, (
        f"only {recognised} executor calls recognised — _RECEIVER_NAMES no longer "
        "matches how this repo names its cursors"
    )


def suppression_sites() -> dict[str, list[int]]:
    """Files with a trailing `# nosec` suppression and the lines it sits on.

    Only trailing suppressions count — a comment *about* suppressions is not one.
    """
    sites: dict[str, list[int]] = {}
    for relative, number, _ in _suppression_lines():
        sites.setdefault(relative, []).append(number)
    return sites


def _suppression_lines() -> list[tuple[str, int, str]]:
    lines: list[tuple[str, int, str]] = []
    for package in PACKAGES:
        for path in sorted((REPO / package).rglob("*.py")):
            relative = path.relative_to(REPO).as_posix()
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "# nosec" in line and not line.lstrip().startswith("#"):
                    lines.append((relative, number, line))
    return lines


def test_every_suppression_states_a_reason() -> None:
    """A suppression must say why, and say it where the scanner cannot misread it.

    `# nosec` silences bandit on its line and explains nothing, so each one here
    carries a reason. Where that reason sits is not a style choice: text written
    AFTER the directive is parsed by bandit as further test ids (measured -- 61
    "Test in comment" warnings from one run), which turns a scoped suppression into
    one that hides every check on the line, including a future real finding. So the
    reason goes before the directive, or on the line above it, and the directive's
    own tail is test ids and nothing else. tests/security/
    test_bandit_suppressions_are_earned.py is the other half: it asks bandit.
    """
    offenders = []
    for relative, number, line in _suppression_lines():
        directive = line.rfind("# nosec")
        after = line[directive + len("# nosec"):].strip()
        if not re.fullmatch(r"(B\d{3}(\s+)?)+", after):
            offenders.append(f"{relative}:{number} tail is not ids-only: {after!r}")
            continue
        before = line[:directive].split("#", 1)[1] if "#" in line[:directive] else ""
        previous = _previous_line(relative, number)
        if before.strip() or previous.strip():
            continue
        offenders.append(f"{relative}:{number} suppresses without a stated reason")
    assert not offenders, (
        f"{offenders} -- write the reason before the directive (or on the line above); "
        "text after it is read by bandit as test ids"
    )


def _previous_line(relative: str, number: int) -> str:
    """The line above, used as the second legal place for a reason."""
    path = REPO / relative
    lines = path.read_text(encoding="utf-8").splitlines()
    return lines[number - 2] if number >= 2 else ""


def test_the_suppression_scan_is_not_vacuous() -> None:
    sites = suppression_sites()
    assert len(sites) >= 3, (
        f"only {len(sites)} files with a suppression found — the scan read nothing, "
        "so the reason rule above proves nothing"
    )


def test_a_parameter_is_never_treated_as_constant() -> None:
    """The hole this file exists to close: `execute(sql + user_value)`."""
    tree = ast.parse(
        "def f(cur, user_value, ids):\n"
        "    cur.execute('SELECT * FROM t WHERE id = ' + user_value)\n"
    )
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    env = _collect(function, tree)
    arg = function.body[0].value.args[0]  # type: ignore[attr-defined]
    params = frozenset(p.arg for p in function.args.args)
    states = dict.fromkeys(params, False)
    assert not _is_static(arg, env, states, frozenset(), tree)
    # ... and the same statement with the value inlined as a literal is fine.
    literal = ast.parse("'SELECT * FROM t WHERE id = 1'", mode="eval").body
    assert _is_static(literal, env, states, frozenset(), tree)


def test_a_forwarding_helper_is_checked_at_its_call_sites() -> None:
    """`_execute(sql=...)` moves the obligation up a frame, it does not erase it."""
    unsafe = ast.parse(
        "def _run(cur, statement, values=()):\n"
        "    cur.execute(statement, values)\n"
        "\n"
        "def call(cur, user_sql):\n"
        "    _run(cur, user_sql)\n"
    )
    findings: list[tuple[str, int]] = []
    helpers = executor_helpers(unsafe)
    assert helpers == {"_run": [1]}
    _scan_helper_calls(unsafe, helpers, "synthetic.py", findings)
    assert findings, "a caller handing a parameter to a pass-through executor was missed"

    safe = ast.parse(
        "def _run(cur, statement, values=()):\n"
        "    cur.execute(statement, values)\n"
        "\n"
        "def call(cur, ids):\n"
        "    _run(cur, 'SELECT * FROM t WHERE id = %s', (ids,))\n"
    )
    findings = []
    helpers = executor_helpers(safe)
    _scan_helper_calls(safe, helpers, "synthetic.py", findings)
    assert not findings, "a constant handed to a pass-through executor was refused"


def test_a_parameter_named_like_sql_is_not_a_statement_by_its_name() -> None:
    """Probe P2: `query` interpolated into the text is data, not proof.

    The mutation that found this: `search_jobs` in `storage/mysql.py` was changed
    to execute `f"...{where} AND id = '{query}'"`. The old judgement waved
    `query` through because the parameter's *name* is on the executor list, and
    called that f-string provably constant — a false negative on the one shape
    this file exists to catch. Naming is not evidence; only handing the value
    over as the statement moves the obligation to the caller.
    """
    tree = ast.parse(
        "def search_jobs(cur, query):\n"
        "    where = ' WHERE status = %s'\n"
        "    cur.execute(f\"SELECT id FROM jobs{where} AND id = '{query}'\")\n"
    )
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    env = _collect(function, tree)
    states = _param_states(function)
    assert states == {"cur": False, "query": False}, (
        f"nothing here hands a parameter over as the statement; got {states}"
    )
    call = function.body[1].value  # type: ignore[attr-defined]
    assert not _is_static(call.args[0], env, states, frozenset(), tree), (
        "a search term interpolated into executed text was treated as if it "
        "were the statement itself"
    )


def test_a_parameter_handed_over_as_the_statement_moves_the_obligation_up() -> None:
    """The other half of the same rule: a real pass-through is not a finding."""
    tree = ast.parse(
        "def _run(cur, statement, values=()):\n"
        "    cur.execute(statement, values)\n"
    )
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef)
    env = _collect(function, tree)
    states = _param_states(function)
    assert states == {"cur": False, "statement": True, "values": False}, (
        f"only the parameter that is the whole first argument is forwarded; got {states}"
    )
    call = function.body[0].value  # type: ignore[attr-defined]
    assert _is_static(call.args[0], env, states, frozenset(), tree), (
        "the caller's obligation must land on the caller, not be refused here"
    )


def test_only_a_whole_argument_pass_through_counts_as_forwarding() -> None:
    """`.replace(...)` keeps the value the statement; `+` glues it into one."""
    translated = ast.parse(
        "def _run(cur, statement, values=()):\n"
        "    cur.execute(statement.replace('?', '%s'), values)\n"
    )
    glued = ast.parse(
        "def _run(cur, statement, values=()):\n"
        "    cur.execute('SELECT * FROM t WHERE ' + statement, values)\n"
    )
    for tree, expected, call_index in ((translated, True, 0), (glued, False, 0)):
        function = tree.body[0]
        assert isinstance(function, ast.FunctionDef)
        env = _collect(function, tree)
        states = _param_states(function)
        assert states["statement"] is expected, (
            f"{ast.unparse(function.body[0])!r}: forwarding said {states['statement']}"
        )
        call = function.body[call_index].value  # type: ignore[attr-defined]
        assert _is_static(call.args[0], env, states, frozenset(), tree) is expected
