"""One owner for the plane a payload contract is checked against.

WHY THIS EXISTS. ``apps/web/src/api.ts`` declares, in TypeScript, what the browser
believes a response looks like. ``api/routes/*.py`` publishes, in Python, what the
response actually is. Nothing in the repository compared the two before #543: the
only witness was a hand-rolled regex inside each of four test files, and those four
copies disagreed about what an interface even is (one read ``api.ts`` only, so the
two *private* interfaces in ``agent/pages/AgentSettings.tsx`` were invisible to it).

#542 landed the first real hole found by hand -- a required key the degraded branch
did not answer -- and its D-section leg checks exactly one endpoint. A hole of that
shape, on any other endpoint, is silent today: the browser reads ``undefined`` and
renders it as a zero, an empty string, or a missing card.

THE RULES, each one sentence:

  E1  an endpoint is ``@<router>.<verb>("<path>")`` on a router object the module
      itself declares; the prefix is read from that declaration, never assumed.
  E2  a frontend call site is ``apiGet/Post/Put/Patch/Delete(<Type>?)(<first arg>)``;
      the path is read concatenation-aware -- quoted literals keep their text,
      anything else contributes one ``{}`` slot. A site whose path comes from a
      variable cannot be paired, and says so.
  E3  a pair is ``(verb, normalized path)``. The verb is part of the identity: the
      same path serves a GET list and a POST create with different payloads, and a
      path-only pairing invents mismatches (measured while writing this: it produced
      two false "required-not-published" findings on ``/agent/jobs``).
  E4  the published key set is folded, with a stated depth limit. Foldable: a dict
      literal; a local name bound to one; ``name.update(k=...)`` / ``name["k"] = ...``;
      ``**name`` / ``**call()``; ``return helper(...)`` one module-hop and two hops
      through the import graph. NOT foldable, and reported as unbounded rather than
      guessed: a comprehension whose keys come from data (``public_model_config``),
      a ``|`` whose left side is unbounded, a call into a module we cannot resolve.
  E5  the check is PER BRANCH. A route that answers key set A on the happy path and B
      on the degraded path does not "publish A ∪ B" -- the browser gets whichever it
      got, so every required key must appear in every branch. This is the #542 hole
      and the reason ``total`` over branches would be a weaker rule.

Test files under ``__tests__`` are excluded from pairing: they assert against mocks,
so a mismatch there is not a user-visible one. The exclusion is a *counted* rule
(``excluded_call_sites``), so it cannot quietly become the whole population.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from tests._scan_walk import product_roots

#: How many module hops a payload fold may follow. Two covers `route -> service -> store`
#: (measured: `/jobs`); three would be guessing.
_PAYLOAD_DEPTH = 2

#: Files that are not consumers of the product's payloads.
_TEST_PATH_PARTS = ("__tests__",)
_TEST_SUFFIXES = (".test.ts", ".test.tsx")

HTTP_VERBS = ("get", "post", "put", "patch", "delete")
_CLIENT_VERBS = {
    "apiGet": "get",
    "apiPost": "post",
    "apiPut": "put",
    "apiPatch": "patch",
    "apiDelete": "delete",
}


@dataclass(frozen=True)
class Endpoint:
    module: str
    router: str
    verb: str
    path: str
    handler: str
    line: int

    @property
    def key(self) -> tuple[str, str]:
        return (self.verb, normalize_path(self.path))


@dataclass(frozen=True)
class CallSite:
    file: str
    line: int
    verb: str
    path: str
    type_expr: str
    #: Where the declared type was read from: the call's own generic argument, the
    #: enclosing function's `Promise<T>` return type, or nowhere.
    typed_by: str = "none"

    @property
    def candidates(self) -> tuple[str, ...]:
        return path_candidates(self.path)

    @property
    def key(self) -> tuple[str, str]:
        return (self.verb, self.candidates[0])


@dataclass(frozen=True)
class Pair:
    """One frontend call site and the endpoint that answers it.

    ``exact`` is False when the pairing only worked after dropping a reading of the
    variable-suffix kind -- a slot no ``/`` introduces. The gate registers those
    pairings by name instead of letting them pass for an exact contract.
    """

    site: CallSite
    endpoint: Endpoint
    exact: bool


@dataclass(frozen=True)
class Member:
    name: str
    optional: bool
    type_text: str


@dataclass(frozen=True)
class CallShape:
    """One call-shaped mention of an api client, kept or rejected, with its left window.

    ``window`` is the text the definition guard reads. A gate needs it to check that
    everything the guard rejected *is* a declaration, because the guard is the only
    place where a consumer can disappear without an error (#543 measured eight).
    """

    file: str
    line: int
    name: str
    is_call: bool
    window: str


@dataclass
class Payload:
    """What the fold can say about one handler: per-branch key sets, or why it cannot.

    ``branches`` is empty exactly when every return was unbounded.

    ``conditional`` names the fold's one known overstatement. Keys added by
    ``name.update(...)`` / ``name["k"] = ...`` merge into every branch, because
    telling "set on both the try and the except arm" (so always present) from "set
    only inside one `if`" (so sometimes absent) needs control-flow paths this owner
    does not build. ``conditional`` records the keys that were mutated from a nested
    statement, so the gate can *roster* the overstatement instead of pretending it
    does not exist: a hole of the "only published on one control path" shape is out of
    this number's reach, and is registered as such rather than claimed as covered.
    """

    branches: list[set[str]] = field(default_factory=list)
    unbounded: list[str] = field(default_factory=list)
    conditional: set[str] = field(default_factory=set)

    @property
    def published(self) -> set[str]:
        out: set[str] = set()
        for keys in self.branches:
            out |= keys
        return out

    @property
    def always(self) -> set[str]:
        """Keys every branch publishes -- the only set a frontend may treat as present."""
        if not self.branches:
            return set()
        out = set(self.branches[0])
        for keys in self.branches[1:]:
            out &= keys
        return out


def normalize_path(path: str) -> str:
    """`/jobs/{job_id}` and `/jobs/${id}` and `/jobs/{}?x=1` all become `/jobs/{}`."""
    stripped = re.sub(r"\?.*$", "", path)
    out = re.sub(r"\{[^{}]*\}", "{}", stripped)
    out = re.sub(r"/+$", "", out)
    return out or "/"


def path_candidates(raw: str) -> tuple[str, ...]:
    """The keys one call site may pair against, most specific first.

    A gap that is not slash-separated (`"/api/v1/admin/users" + q`, where `q` is a
    query string) and a missing segment (`"/jobs/" + id`) read the same once the
    variable is gone -- but only the second leaves a `/` in front of the slot. So every
    bare gap offers a second reading, and `pairings` records which reading matched: the
    rescue is countable instead of silent, and a site that pairs only on the loose
    reading cannot pass for an exact contract.
    """
    out = [normalize_path(raw)]
    for stem in _bare_stems(raw):
        trimmed = normalize_path(stem)
        if trimmed not in out:
            out.append(trimmed)
    return tuple(out)


def _bare_stems(built: str) -> list[str]:
    """The path taken up to each gap that a `/` does not introduce.

    `"/agent/jobs" + (q ? "?" + q : "")` leaves two slots behind, so a reading that only
    trims a *trailing* slot calls it an orphan and the list route it asks for stays in
    the register as "nobody consumes me". A slash-preceded gap is a real segment and
    gets no rescue: reading `"/jobs/" + id` as `/jobs` would invent a contract no caller
    asked for.
    """
    out: list[str] = []
    for match in re.finditer(r"\{\}", built):
        start = match.start()
        if start == 0 or built[start - 1] == "/":
            continue
        out.append(built[:start])
    return out


# --------------------------------------------------------------------------
# E1 -- the endpoint table


def api_routers(root: Path) -> dict[str, str]:
    """`"module.path:router_var" -> prefix`, for every APIRouter the api/ tree declares."""
    out: dict[str, str] = {}
    for py in sorted((root / "api").rglob("*.py")):
        module = ".".join(py.relative_to(root).with_suffix("").parts)
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in tree.body:
            if not (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Call)
                and ast.unparse(node.value.func) == "APIRouter"
            ):
                continue
            prefix = ""
            for kw in node.value.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                    prefix = str(kw.value.value)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[f"{module}:{target.id}"] = prefix
    return out


def endpoints(root: Path) -> list[Endpoint]:
    routers = api_routers(root)
    out: list[Endpoint] = []
    for key, prefix in sorted(routers.items()):
        module_name, var = key.split(":")
        py = root / (module_name.replace(".", "/") + ".py")
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and isinstance(dec.func.value, ast.Name)
                    and dec.func.value.id == var
                    and dec.func.attr in HTTP_VERBS
                    and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                    and isinstance(dec.args[0].value, str)
                ):
                    continue
                out.append(
                    Endpoint(
                        module=module_name,
                        router=var,
                        verb=dec.func.attr,
                        path=prefix + dec.args[0].value,
                        handler=node.name,
                        line=node.lineno,
                    )
                )
    return out


# --------------------------------------------------------------------------
# TS declarations (api.ts is not the only host -- see AgentSettings.tsx)


def _split_members(body: str) -> list[Member]:
    """Top-level `name: type;` pairs in an object-type body, brace/bracket aware."""
    out: list[Member] = []
    depth = 0
    buf = ""
    for ch in body:
        if ch in "{[(":
            depth += 1
            buf += ch
        elif ch in "})]":
            depth -= 1
            buf += ch
        elif ch == ";" and depth == 0:
            member = _one_member(buf)
            if member is not None:
                out.append(member)
            buf = ""
        else:
            buf += ch
    member = _one_member(buf)
    if member is not None:
        out.append(member)
    return out


def _one_member(chunk: str) -> Member | None:
    chunk = re.sub(r"/\*.*?\*/", "", chunk, flags=re.S)
    chunk = re.sub(r"//[^\n]*", "", chunk).strip()
    m = re.match(r"^(\w+)(\?)?\s*:\s*(.+)$", chunk, re.S)
    if m is None:
        return None
    return Member(m.group(1), bool(m.group(2)), " ".join(m.group(3).split()))


def _block_after(text: str, open_brace_at: int) -> str:
    """Body of the brace block that starts at `open_brace_at` (the char is a `{`)."""
    depth = 0
    i = open_brace_at
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace_at + 1 : i]
        i += 1
    return text[open_brace_at + 1 :]


_DECL_PATTERNS = (
    re.compile(r"^(?:export\s+)?interface\s+(\w+)[^{}]*\{", re.M),
    re.compile(r"^(?:export\s+)?type\s+(\w+)\s*=\s*\{", re.M),
)


def _rel_in_web(web_src: Path, ts: Path) -> str:
    """A repo-facing path for a frontend file, so findings read as `apps/web/src/...`.

    Derived from the tail of `web_src` (`apps/web/src`) rather than from a repo root
    argument, because the two frontend readers take only the source tree; an arm copy
    of the repo keeps the same tail, so the label stays true.
    """
    return f"{'/'.join(web_src.parts[-3:])}/{ts.relative_to(web_src).as_posix()}"


def ts_declarations(web_src: Path) -> dict[str, tuple[str, list[Member]]]:
    """Every interface/type-alias object shape in the frontend, with its host file.

    Non-exported declarations are included on purpose: `ModelConfig` lives in a page
    and is invisible to an `export interface` lens (#543 measures that).
    """
    out: dict[str, tuple[str, list[Member]]] = {}
    for ts in sorted(list(web_src.rglob("*.ts")) + list(web_src.rglob("*.tsx"))):
        rel = _rel_in_web(web_src, ts)
        text = ts.read_text(encoding="utf-8")
        for pattern in _DECL_PATTERNS:
            for m in pattern.finditer(text):
                members = _split_members(_block_after(text, m.end() - 1))
                if members:
                    out.setdefault(m.group(1), (rel, members))
    return out


def members_of_type(type_expr: str, decls: dict[str, tuple[str, list[Member]]]) -> tuple[
    set[str], set[str], list[str]
]:
    """(required, optional, notes) for a TS type expression used at a call site."""
    expr = " ".join(type_expr.split())
    if expr.startswith("{"):
        members = _split_members(_block_after(expr, 0))
        return _split_required(members), {m.name for m in members if m.optional}, []
    m = re.fullmatch(r"(\w+)(?:\s*\|\s*null)?(?:\s*\[\s*\])?", expr)
    if m is None:
        return set(), set(), [f"type expression not understood: {expr[:48]!r}"]
    name = m.group(1)
    entry = decls.get(name)
    if entry is None:
        return set(), set(), [f"type {name!r} is not declared in apps/web/src"]
    members = entry[1]
    notes = []
    if expr.endswith("[]"):
        notes.append(f"{name} is an array; the envelope is not this type")
    return _split_required(members), {m.name for m in members if m.optional}, notes


def _split_required(members: list[Member]) -> set[str]:
    return {m.name for m in members if not m.optional}


# --------------------------------------------------------------------------
# E2 -- frontend call sites


#: The client verb only; the type argument is read by `_call_at`, which balances the
#: angle brackets instead of capturing them with a non-greedy regex.
_CALL_RE = re.compile(r"\b(apiGet|apiPost|apiPut|apiPatch|apiDelete)\b\s*")


def _first_arg(text: str, after_paren: int) -> str:
    depth = 0
    buf = ""
    for ch in text[after_paren:]:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif ch == "," and depth == 0:
            break
        buf += ch
    return buf


def _path_of_argument(arg: str) -> tuple[str, bool]:
    """Concatenation-aware path. Returns (path, is_variable_built).

    Each non-literal gap becomes one `{}` slot, so `"/jobs/" + encodeURIComponent(id)`
    reads as `/jobs/{}` -- the same shape the backend declares as `/jobs/{job_id}`.
    """
    quoted = re.finditer(r"(['\"`])(.*?)\1", arg, re.S)
    literals = [(m.start(), m.end(), m.group(2)) for m in quoted]
    out = ""
    pos = 0
    variable = False
    for start, end, content in literals:
        if arg[pos:start].strip(" +"):
            variable = True
            out += "{}"
        out += content
        pos = end
    if arg[pos:].strip(" +"):
        variable = True
        out += "{}"
    out = re.sub(r"\$\{[^{}]*\}", "{}", out)
    return out, variable


def _read_angle(text: str, start: int) -> tuple[str, int] | None:
    """The balanced `<...>` block at `start`, returning (inner text, index just past it).

    A non-greedy regex capture stops at the *first* `>`, which silently truncates a
    nested generic (`apiGet<{ job: { id: string; status: string } }>(...)` read as
    `{ job: { id: string; status: string ` -- a type whose members are then invented
    from a fragment). `=>` is skipped because in a type position it is an arrow, not a
    closer.
    """
    if start >= len(text) or text[start] != "<":
        return None
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i], i + 1
        elif ch == "=" and text[i : i + 2] == "=>":
            i += 1
        i += 1
    return None


def _promise_annotation(text: str, call_start: int) -> str:
    """The enclosing declaration's `Promise<T>`, when the call itself is untyped.

    `createVerification(...): Promise<{ job_id: string; status: string }>` followed by
    `apiPost("/jobs", payload)` declares a real contract one line up; reading only the
    call's generic argument would drop the app's most-used endpoint from the census.
    Accepted only while no other `function` / arrow sits between the annotation and the
    call, so the type cannot be borrowed from a finished sibling scope -- an untyped
    site whose value is genuinely discarded (a login probe) stays untyped, and the gate
    counts it instead of guessing.
    """
    index = text.rfind("): Promise<", 0, call_start)
    if index == -1:
        return ""
    read = _read_angle(text, index + len("): Promise"))
    if read is None:
        return ""
    between = text[read[1] : call_start]
    if "function " in between or "=>" in between:
        return ""
    return read[0].strip()


def _call_at(text: str, pos: int) -> tuple[str, int] | None:
    """`(type argument, index just past the opening paren)` for a client call at `pos`."""
    type_expr = ""
    if pos < len(text) and text[pos] == "<":
        read = _read_angle(text, pos)
        if read is None:
            return None
        type_expr, pos = read[0].strip(), read[1]
    if pos >= len(text) or text[pos] != "(":
        return None
    return type_expr, pos + 1


def frontend_calls(web_src: Path) -> tuple[list[CallSite], int]:
    """(pairs candidates, excluded test-file sites)."""
    out: list[CallSite] = []
    excluded = 0
    for ts in sorted(list(web_src.rglob("*.ts")) + list(web_src.rglob("*.tsx"))):
        rel = _rel_in_web(web_src, ts)
        text = ts.read_text(encoding="utf-8")
        if any(part in _TEST_PATH_PARTS for part in ts.parts) or ts.name.endswith(_TEST_SUFFIXES):
            for match in _CALL_RE.finditer(text):
                if not _is_call(text, match):
                    continue
                found = _call_at(text, match.end())
                if found is None:
                    continue
                if _path_of_argument(_first_arg(text, found[1]))[0].startswith("/"):
                    excluded += 1
            continue
        for match in _CALL_RE.finditer(text):
            if not _is_call(text, match):
                continue
            found = _call_at(text, match.end())
            if found is None:
                continue
            type_expr, after_paren = found
            typed_by = "generic" if type_expr else "none"
            arg = _first_arg(text, after_paren)
            path, _built = _path_of_argument(arg)
            if not path.startswith("/"):
                continue
            if not type_expr:
                type_expr = _promise_annotation(text, match.start())
                if type_expr:
                    typed_by = "return-annotation"
            line = text[: match.start()].count("\n") + 1
            out.append(
                CallSite(rel, line, _CLIENT_VERBS[match.group(1)], path, type_expr, typed_by)
            )
    return out, excluded


#: A declaration keyword that immediately precedes the client name declares *it*; one
#: that merely appears further back does not. Unanchored, `"const data = await
#: apiGet<X>(...)"` reads like a definition. The A12 arm measured the cost of that
#: reading on this tree: eight path-bearing mentions were judged declarations -- five of
#: them product census sites (`const answer = apiGet<{ principal ... }>("/auth/me")`,
#: `const updated = await apiPost<ModelConfig>(...)`, and three more), which is why the
#: census read 23 sites instead of 28, and three inside `__tests__`, which is why the
#: excluded count read 1 instead of 4. A tool that loses population does not fail; it
#: hands the roster leg a stale list and stays green.
_DECL_HEAD = re.compile(r"\b(?:function|const|let|var)$")


def _is_call(text: str, m: re.Match[str]) -> bool:
    """A definition line (`export async function apiGet<T>(...)`) is not a call site."""
    head = text[max(0, m.start() - 40) : m.start()].rstrip()
    return _DECL_HEAD.search(head) is None


def call_shapes(web_src: Path) -> list[CallShape]:
    """Every call-shaped mention of an api client in a product file, kept or rejected.

    ``frontend_calls`` returns the survivors; this returns the whole population so a
    gate can audit the guard itself instead of trusting it. Test files are left out
    because their mentions are counted as an exclusion, not as consumers.
    """
    out: list[CallShape] = []
    for ts in sorted(list(web_src.rglob("*.ts")) + list(web_src.rglob("*.tsx"))):
        if any(part in _TEST_PATH_PARTS for part in ts.parts):
            continue
        if ts.name.endswith(_TEST_SUFFIXES):
            continue
        rel = _rel_in_web(web_src, ts)
        text = ts.read_text(encoding="utf-8")
        for match in _CALL_RE.finditer(text):
            if text[match.end() : match.end() + 1] not in ("<", "("):
                continue
            out.append(
                CallShape(
                    file=rel,
                    line=text[: match.start()].count("\n") + 1,
                    name=match.group(1),
                    is_call=_is_call(text, match),
                    window=text[max(0, match.start() - 40) : match.start()].rstrip(),
                )
            )
    return out


# --------------------------------------------------------------------------
# E4 -- the payload fold


def _keys_of_dict(
    node: ast.Dict, resolve: Callable[..., set[str] | None]
) -> set[str] | None:
    """Top-level literal keys of a dict expression, following `**` through `resolve`."""
    out: set[str] = set()
    for key, value in zip(node.keys, node.values, strict=True):
        if key is None:
            got = resolve(value)
            if got is None:
                return None
            out |= got
        elif isinstance(key, ast.Constant) and isinstance(key.value, str):
            out.add(key.value)
        else:
            return None
    return out


def payload_of(root: Path, endpoint: Endpoint) -> Payload:
    """What the endpoint publishes, per return branch, or why the fold stopped."""
    module_path = root / (endpoint.module.replace(".", "/") + ".py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    handler = _find_function(tree, endpoint.handler)
    if handler is None:
        return Payload(unbounded=[f"handler {endpoint.handler} not found"])
    return _payload_of_function(_build_fold(root, module_path, handler, tree), 0)


def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


@dataclass(frozen=True)
class _Fold:
    """One fold target: a function, the module that holds it, and the repo root.

    Threading the root instead of reading a module-level global is deliberate: a gate
    that runs against a copied tree (an arm worktree) must fold against *that* tree,
    and a process-wide `Path.cwd()` hint would make the answer depend on which test
    ran last.

    ``types`` is how a receiver name becomes a class: `{parameter: Type}` from
    annotations plus `{local: Type}` from `name = Type(...)` and `self.attr = Type(...)`.
    Without it `service.list_jobs(...)` is an unresolvable call, the fold stops at the
    route, and every cross-module payload reads as "unbounded" -- a gate that never
    says anything.
    """

    root: Path
    module_path: Path
    fn: ast.FunctionDef | ast.AsyncFunctionDef
    tree: ast.Module
    class_name: str | None
    types: dict[str, str]


def _build_fold(
    root: Path,
    module_path: Path,
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
    tree: ast.Module,
) -> _Fold:
    class_name = _class_of_module(tree, fn)
    types = _receiver_types(fn, tree)
    if class_name is not None:
        # `self._store.search_jobs(...)` is typed in the constructor, not in the
        # method: without the class's own `__init__`, every service-layer hop would
        # read as unresolvable and the fold would stop at the route.
        for key, value in _class_attribute_types(tree, class_name).items():
            types.setdefault(key, value)
    return _Fold(
        root=root,
        module_path=module_path,
        fn=fn,
        tree=tree,
        class_name=class_name,
        types=types,
    )


def _class_attribute_types(tree: ast.Module, class_name: str) -> dict[str, str]:
    """`self.attr = Cls()` / `self.attr: Cls` facts from every constructor of the class."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == class_name):
            continue
        for inner in node.body:
            if not isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if inner.name != "__init__":
                continue
            for key, value in _receiver_types(inner, tree).items():
                if key.startswith("self."):
                    out.setdefault(key, value)
    return out


def _class_of_module(tree: ast.Module, fn: ast.AST) -> str | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for inner in node.body:
                if inner is fn:
                    return node.name
    return None


def _strip_optional(text: str) -> str:
    """`MySQLStore | None` / `Optional[MySQLStore]` -> `MySQLStore`."""
    text = re.sub(r"Optional\[(.+)\]", r"\1", text)
    parts = [p.strip() for p in text.split("|") if p.strip() and p.strip() != "None"]
    return parts[0] if len(parts) == 1 else ""


def _class_of_expr(expr: ast.expr | None) -> str | None:
    """The class an expression produces, when the expression says so plainly."""
    if expr is None:
        return None
    if isinstance(expr, ast.Call):
        return ast.unparse(expr.func)
    if isinstance(expr, ast.BoolOp):
        for value in expr.values:
            got = _class_of_expr(value)
            if got:
                return got
        return None
    if isinstance(expr, ast.IfExp):
        return _class_of_expr(expr.body) or _class_of_expr(expr.orelse)
    if isinstance(expr, ast.Await):
        return _class_of_expr(expr.value)
    return None


def _receiver_types(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, tree: ast.Module
) -> dict[str, str]:
    types: dict[str, str] = {}
    for arg in list(fn.args.posonlyargs) + list(fn.args.args) + list(fn.args.kwonlyargs):
        if arg.annotation is not None:
            name = _strip_optional(ast.unparse(arg.annotation))
            if name:
                types[arg.arg] = name
    for node in _own_nodes(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    got = _class_of_expr(node.value)
                    if got:
                        types[target.id] = got
                elif (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    got = _class_of_expr(node.value)
                    if got:
                        types[f"self.{target.attr}"] = got
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Attribute)
            and isinstance(node.target.value, ast.Name)
            and node.target.value.id == "self"
        ):
            name = _strip_optional(ast.unparse(node.annotation))
            if name:
                types[f"self.{node.target.attr}"] = name
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    got = _class_of_expr(node.value)
                    if got:
                        types.setdefault(target.id, got)
    return types


def _own_nodes(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    """Nodes that belong to `fn` itself, not to a closure defined inside it.

    A closure that builds the payload is a separate branch set: counting its returns
    as this handler's would report keys the handler never returns.
    """
    stack = list(ast.iter_child_nodes(fn))
    out: list[ast.AST] = []
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        out.append(node)
        stack.extend(ast.iter_child_nodes(node))
    return out


def _payload_of_function(fold: _Fold, depth: int) -> Payload:
    bindings: dict[str, list[ast.expr]] = {}
    mutations: dict[str, set[str]] = {}
    conditional_by_name: dict[str, set[str]] = {}
    nodes = sorted(
        _own_nodes(fold.fn),
        key=lambda n: (getattr(n, "lineno", 0), getattr(n, "col_offset", 0)),
    )
    body_statements = {id(node) for node in fold.fn.body}
    for node in nodes:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and node.value is not None
            and isinstance(node.target, ast.Name)
        ):
            # `result: dict[str, Any] = {...}` is the service layer's normal way to
            # build a payload; reading only plain Assign made every such handler look
            # unbounded.
            targets, value = [node.target], node.value
        for target in targets:
            if isinstance(target, ast.Name) and value is not None:
                bindings.setdefault(target.id, []).append(value)
            elif (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and isinstance(target.slice, ast.Constant)
                and isinstance(target.slice.value, str)
            ):
                mutations.setdefault(target.value.id, set()).add(target.slice.value)
                if id(node) not in body_statements:
                    conditional_by_name.setdefault(target.value.id, set()).add(target.slice.value)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "update"
            and isinstance(node.func.value, ast.Name)
        ):
            bucket = mutations.setdefault(node.func.value.id, set())
            for keyword in node.keywords:
                if keyword.arg:
                    bucket.add(keyword.arg)
            if id(node) not in body_statements:
                # Reached only inside an `if`/`try`/`except`: the keys are published on
                # some paths, not on every response. See `Payload.conditional`.
                conditional_by_name.setdefault(node.func.value.id, set()).update(
                    keyword.arg for keyword in node.keywords if keyword.arg
                )

    callee_conditional: set[str] = set()

    def resolve(expr: ast.expr, seen: frozenset[str] = frozenset()) -> set[str] | None:
        """Keys of an expression, or None where the fold refuses to guess."""
        if isinstance(expr, ast.Constant) and expr.value is None:
            # `None` publishes no keys; it is a value, not a fold failure. `found:
            # dict | None = None` followed by `found = {...}` is this repo's standard
            # "maybe-absent artifact" shape, and treating the null binding as
            # unbounded would stop the fold at every artifact endpoint.
            return set()
        if isinstance(expr, ast.Dict):
            return _keys_of_dict(expr, resolve)
        if isinstance(expr, ast.Name):
            if expr.id in seen or expr.id not in bindings:
                return None
            out: set[str] = set()
            for bound in bindings[expr.id]:
                got = resolve(bound, seen | {expr.id})
                if got is None:
                    return None
                out |= got
            out |= mutations.get(expr.id, set())
            # A local's conditional keys travel with that local: `document["_console"]
            # = ...` in a handler whose response is `{"job_id": ..., "status": ...}` is
            # not a payload key at all, and a function-wide bag would report it as one.
            callee_conditional.update(conditional_by_name.get(expr.id, set()))
            return out
        if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
            left, right = resolve(expr.left), resolve(expr.right)
            return None if left is None or right is None else left | right
        if isinstance(expr, ast.Call):
            return _resolve_call(fold, expr, depth, callee_conditional)
        return None

    payload = Payload()
    for node in nodes:
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        if isinstance(node.value, ast.Constant) and node.value.value is None:
            # `return None` is a branch that publishes no keys, not a fold failure: a
            # handler that answers null really does answer nothing, and hiding it
            # inside `unbounded` would let it escape the per-branch rule.
            payload.branches.append(set())
            continue
        keys = resolve(node.value)
        if keys is None:
            payload.unbounded.append(
                f"return {ast.unparse(node.value)[:60]} (line {node.lineno})"
            )
        else:
            payload.branches.append(keys)
    if not payload.branches and not payload.unbounded:
        payload.unbounded.append("handler has no value-returning branch")
    payload.conditional = callee_conditional
    return payload


def _resolve_call(
    fold: _Fold, call: ast.Call, depth: int, callee_conditional: set[str] | None = None
) -> set[str] | None:
    """Follow `helper(...)` into its returns, within `_PAYLOAD_DEPTH` module hops."""
    if depth >= _PAYLOAD_DEPTH:
        return None
    target = _callee(fold, ast.unparse(call.func))
    if target is None:
        return None
    inner_fold = _load_fold(fold.root, target[0], target[1])
    if inner_fold is None:
        return None
    nested = _payload_of_function(inner_fold, depth + 1)
    if nested.branches and not nested.unbounded:
        if callee_conditional is not None:
            # A spread of the helper inherits its "only on some paths" keys: saying
            # `**artifact` always publishes `signed_path` would be a lie the caller
            # cannot see.
            callee_conditional.update(nested.conditional)
        out: set[str] = set()
        for keys in nested.branches:
            out |= keys
        return out
    # A partial answer is not an answer: one branch we cannot fold means the
    # caller's key set is not a fact.
    return None


def _load_fold(root: Path, module_path: Path, name: str) -> _Fold | None:
    """Parse a callee's module and take its function.

    A method and a module-level function can share a name; callers that want a method
    check `_defines_method` first, so this stays the simple "find the def" step.
    """
    tree = _parse(module_path)
    if tree is None:
        return None
    fn = _find_function(tree, name)
    if fn is None:
        return None
    return _build_fold(root, module_path, fn, tree)


def _callee(fold: _Fold, dotted: str) -> tuple[Path, str] | None:
    """Where does `name(...)` / `service.method(...)` / `self.store.method(...)` live?

    Returns (file, function name) or None when the receiver cannot be typed. Naming a
    module here by guesswork would turn the fold's answer into a fiction, so every
    shape either resolves through an import this module actually writes or stops.
    """
    parts = dotted.split(".")
    if len(parts) == 1:
        if _defines(fold.tree, parts[0]):
            return fold.module_path, parts[0]
        # `from providers.config import public_model_config` makes a bare name a
        # cross-module call; refusing it would report the route as unbounded for the
        # wrong reason (the callee's own shape is the real answer).
        for module_path in _imported_candidate_modules(fold):
            if _defines(_parse(module_path), parts[0]):
                return module_path, parts[0]
        return None
    if len(parts) == 2:
        head, leaf = parts
        if head == "self":
            if fold.class_name and _defines_method(fold.tree, fold.class_name, leaf):
                return fold.module_path, leaf
            return None
        receiver = fold.types.get(head)
        if receiver is not None:
            return _locate(fold, receiver, leaf)
        imported = _imported_module(fold, head)
        if imported is not None and _defines(_parse(imported), leaf):
            return imported, leaf
        return None
    if len(parts) == 3 and parts[0] == "self":
        attr = fold.types.get(f"self.{parts[1]}")
        if attr is None:
            return None
        return _locate(fold, attr, parts[2])
    return None


def _locate(fold: _Fold, class_name: str, method: str) -> tuple[Path, str] | None:
    """`VerificationApplicationService` + `list_jobs` -> (file, "list_jobs")."""
    module_path = _class_module(fold, class_name)
    if module_path is None:
        return None
    tree = _parse(module_path)
    if tree is None:
        return None
    if _defines_method(tree, class_name, method):
        return module_path, method
    if _defines(tree, method):
        return module_path, method
    return None


def _class_module(fold: _Fold, class_name: str) -> Path | None:
    """The file that declares `class_name`, following this module's own imports."""
    leaf = class_name.split(".")[-1]
    for module_path in [fold.module_path, *_imported_candidate_modules(fold)]:
        tree = _parse(module_path)
        if tree is None:
            continue
        if any(isinstance(node, ast.ClassDef) and node.name == leaf for node in ast.walk(tree)):
            return module_path
    return None


def _defines(tree: ast.Module | None, name: str) -> bool:
    """A module-level `def name` -- not a method, not a closure."""
    if tree is None:
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
        for node in tree.body
    )


def _defines_method(tree: ast.Module | None, class_name: str, method: str) -> bool:
    if tree is None:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for inner in node.body:
                if (
                    isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and inner.name == method
                ):
                    return True
    return False


def _parse(module_path: Path) -> ast.Module | None:
    try:
        return ast.parse(module_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _imported_candidate_modules(fold: _Fold) -> list[Path]:
    """Every repo module this module imports from, in source order."""
    src = _source(fold.module_path)
    if src is None:
        return []
    out: list[Path] = []
    for match in re.finditer(r"^(?:from|import)\s+([\w.]+)", src, re.M):
        path = _module_path(fold.root, match.group(1))
        if path is not None and path not in out:
            out.append(path)
    for match in re.finditer(r"^from\s+\.([\w.]+)\s+import", src, re.M):
        dotted = match.group(1).replace(".", "/")
        for candidate in (
            fold.module_path.parent / (dotted + ".py"),
            fold.module_path.parent / dotted / "__init__.py",
        ):
            if candidate.exists() and candidate not in out:
                out.append(candidate)
    return out


def _imported_module(fold: _Fold, head: str) -> Path | None:
    """`import a.b as head` / `from a import b` where the head names a module."""
    src = _source(fold.module_path)
    if src is None:
        return None
    for match in re.finditer(r"^(?:from|import)\s+([\w.]+)(?:\s+as\s+(\w+))?", src, re.M):
        dotted, alias = match.group(1), match.group(2)
        if alias == head or dotted.split(".")[-1] == head or dotted == head:
            return _module_path(fold.root, dotted)
    return None


def _module_path(root: Path, dotted: str) -> Path | None:
    """Resolve a dotted import head to a file, inside the derived product plane only.

    The root check is ``tests/_scan_walk.product_roots``, not a list typed here: eight
    hand-copied names are the artifact #541 opened on, and a fold that resolves helpers
    through a private plane would be reporting on a tree of its own making.
    """
    parts = dotted.split(".")
    if parts[0] not in product_roots(root):
        return None
    candidate = root / "/".join(parts)
    if candidate.with_suffix(".py").exists():
        return candidate.with_suffix(".py")
    init = candidate / "__init__.py"
    return init if init.exists() else None


def _source(module_path: Path) -> str | None:
    try:
        return module_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def web_src(root: Path) -> Path:
    """The frontend source tree -- one place, so a gate cannot scan half the repo."""
    return root / "apps" / "web" / "src"


def pairings(root: Path) -> tuple[list[Pair], list[CallSite]]:
    """(pairs, call sites that no endpoint answers) -- the verb is part of the identity."""
    table = {ep.key: ep for ep in endpoints(root)}
    calls, _excluded = frontend_calls(web_src(root))
    pairs, orphan = [], []
    for site in calls:
        endpoint = None
        matched = None
        for index, candidate in enumerate(site.candidates):
            endpoint = table.get((site.verb, candidate))
            if endpoint is not None:
                matched = index == 0
                break
        if endpoint is None:
            orphan.append(site)
        else:
            pairs.append(Pair(site, endpoint, bool(matched)))
    return pairs, orphan


__all__ = [
    "CallShape",
    "CallSite",
    "call_shapes",
    "Endpoint",
    "Member",
    "Pair",
    "Payload",
    "api_routers",
    "endpoints",
    "frontend_calls",
    "members_of_type",
    "normalize_path",
    "pairings",
    "path_candidates",
    "payload_of",
    "ts_declarations",
    "web_src",
]
