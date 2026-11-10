"""Gate: the edge's route table must own every path exactly once.

WHY THIS GATE EXISTS.  Two planes answer HTTP at the edge: the Spring Boot
control plane (tenants, users, a read-only job facade, the GitHub webhook)
and the Python agent runtime (the product API the web UI talks to).  Which
plane owns which path is a fact somebody has to write down — and before
this gate existed, nobody had.  The measurement that started it: the two
planes own 9 and 66 routes, and exactly ONE path is owned by BOTH
(``GET /health``).  That is the same shape as the ``execute`` collision
that #545 had to settle in the fake classifier: two things answer the same
path and no file says which one wins.

MEASURED, NOT ASSUMED.  Both censuses are re-derived from the code on
every run — the control plane's from its Spring MVC annotations, the agent
runtime's from its FastAPI decorators through the AST (not a regex over
lines, which cannot tell ``@router.get("/x")`` from a mention of it in a
comment).  The route table is then held against them, so a route added to
either plane without a decision shows up as a red here rather than as a 404
in production.

THE RULES, and the failure each one closes:

  R1  every plane route is served by exactly ONE route of the table, and
      that route points at the plane that owns it.  A path claimed by the
      other plane is a path where the deployment silently changes meaning.
  R2  a route that is deliberately not served at the edge must SAY so, with
      a reason, and no table route may serve it to its own plane — a
      declaration that is not true is worse than no declaration.
  R3  the catch-all must not match before a specific route.  The gateway
      sorts the route definitions by their ``order`` (lower first, stable)
      and matches in THAT order — so a gate that only knew the file order
      would read ``order: -1`` on the catch-all as "still last" while the
      runtime matches it first: a green gate over a broken edge.
  R4  no dead route: a route that claims nothing is a typo that answers
      404 for a path somebody thought was served.
  R5  no route of one plane may claim a route of the other plane.
  R6  each route says which plane it is for, and its upstream variable
      must be that plane's variable — a copy-paste that points a
      control-plane route at the agent runtime is red.
  R7  the probes themselves must not collapse: a census that finds
      nothing reads as "no problem", which is the trap this repository
      has been bitten by before.

The path matching below is Spring's PathPattern semantics — a ``{var}``
matches EXACTLY ONE segment, ``**`` matches the rest.  That is not a
detail: the agent runtime's job sub-resources live one segment deeper
than the control plane's job item (``/api/v1/jobs/{id}/stages`` under
``/api/v1/jobs/{id}``), so a gateway that matched by prefix would swallow
six routes of the other plane.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "services" / "gateway" / "src" / "main" / "resources" / "application.yml"
CP_API = (ROOT / "services" / "control-plane" / "src" / "main" / "java"
          / "dev" / "specproof" / "controlplane" / "api")
AGENT_API = ROOT / "api"

#: The upstream URL variable each plane is reached through.  A route's URI
#: must name its own plane's variable: the URI is env-driven, so the
#: variable name is what says which plane a route really points at.
PLANE_UPSTREAM = {
    "control-plane": "SPECPROOF_CONTROL_PLANE_URL",
    "agent-runtime": "SPECPROOF_AGENT_RUNTIME_URL",
}

#: The route pattern that claims everything.
CATCH_ALL = "/**"

_HTTP_VERBS = {"get", "post", "put", "delete", "patch", "head", "options"}


@dataclass(frozen=True)
class ServiceRoute:
    """One route one plane serves."""

    plane: str
    method: str          # GET / POST / … or ANY (a mount serves every method)
    path: str
    where: str


@dataclass(frozen=True)
class TableRoute:
    """One route of the edge's table."""

    rid: str
    plane: str
    uri: str
    patterns: tuple[str, ...]
    methods: tuple[str, ...]   # empty = every method
    order: int = 0


# ── the two censuses ──────────────────────────────────────────────────────
def _join(prefix: str, sub: str) -> str:
    p = (prefix or "").rstrip("/")
    s = (sub or "").lstrip("/")
    if p and s:
        return f"{p}/{s}"
    if p:
        return p
    if s:
        return "/" + s
    return "/"


_JAVA_CLASS = re.compile(r"^(?:public\s+)?(?:final\s+)?class\s")
_JAVA_CLASS_MAPPING = re.compile(r'^@RequestMapping\(\s*(?:value\s*=\s*)?"([^"]*)"')
_JAVA_METHOD_MAPPING = re.compile(
    r'^@(Get|Post|Put|Delete|Patch|Request)Mapping(?:\(\s*(?:value\s*=\s*)?"([^"]*)"\s*\))?'
)


def control_plane_routes() -> list[ServiceRoute]:
    """The control plane's routes, from its Spring MVC annotations."""
    out: list[ServiceRoute] = []
    for path in sorted(CP_API.glob("*.java")):
        prefix = ""
        in_class = False
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if not in_class:
                found = _JAVA_CLASS_MAPPING.match(stripped)
                if found:
                    prefix = found.group(1)
                if _JAVA_CLASS.match(stripped):
                    in_class = True
                continue
            found = _JAVA_METHOD_MAPPING.match(stripped)
            if found:
                verb = found.group(1)
                out.append(ServiceRoute(
                    plane="control-plane",
                    method="ANY" if verb == "Request" else verb.upper(),
                    path=_join(prefix, found.group(2) or ""),
                    where=f"{path.relative_to(ROOT)}:{lineno}",
                ))
    return out


def agent_runtime_routes() -> list[ServiceRoute]:
    """The agent runtime's routes, from its FastAPI decorators (AST)."""
    out: list[ServiceRoute] = []
    for path in sorted(AGENT_API.rglob("*.py")):
        if path.name.startswith("test_") or "__pycache__" in path.relative_to(AGENT_API).parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        prefixes: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                call = node.value
                if isinstance(call.func, ast.Name) and call.func.id == "APIRouter":
                    prefix = ""
                    for keyword in call.keywords:
                        if (keyword.arg == "prefix"
                                and isinstance(keyword.value, ast.Constant)
                                and isinstance(keyword.value.value, str)):
                            prefix = keyword.value.value
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            prefixes[target.id] = prefix
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if not isinstance(decorator, ast.Call):
                        continue
                    func = decorator.func
                    if not isinstance(func, ast.Attribute):
                        continue
                    if func.attr.lower() not in _HTTP_VERBS:
                        continue
                    owner = func.value
                    if not isinstance(owner, ast.Name):
                        continue
                    sub = ""
                    if (decorator.args and isinstance(decorator.args[0], ast.Constant)
                            and isinstance(decorator.args[0].value, str)):
                        sub = decorator.args[0].value
                    out.append(ServiceRoute(
                        plane="agent-runtime",
                        method=func.attr.upper(),
                        path=_join(prefixes.get(owner.id, ""), sub),
                        where=f"{path.relative_to(ROOT)}:{node.lineno}",
                    ))
            elif (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
                call = node.value
                if (isinstance(call.func, ast.Attribute) and call.func.attr == "mount"
                        and call.args and isinstance(call.args[0], ast.Constant)
                        and isinstance(call.args[0].value, str)):
                    out.append(ServiceRoute(
                        plane="agent-runtime",
                        method="ANY",
                        path=_join("", str(call.args[0].value)),
                        where=f"{path.relative_to(ROOT)}:{node.lineno}",
                    ))
    return out


# ── the edge's table ──────────────────────────────────────────────────────
def _table_document() -> dict:
    return yaml.safe_load(TABLE.read_text(encoding="utf-8"))


def table_routes() -> list[TableRoute]:
    """The edge's routes, in the order the gateway matches them.

    The gateway sorts the route definitions by their ``order`` (lower first,
    stable for equal orders) and matches in THAT order — not in the order the
    file happens to list them.  A gate that only knew the file order would
    read ``order: -1`` on the catch-all as "still last" while the runtime
    matches it first: a green gate over a broken edge.  So the sort happens
    here, once, and every rule below reads the sorted list.
    """
    raw = _table_document()["spring"]["cloud"]["gateway"]["routes"]
    out: list[TableRoute] = []
    for entry in raw:
        patterns: list[str] = []
        methods: list[str] = []
        for predicate in entry.get("predicates") or []:
            key, _, value = str(predicate).partition("=")
            key = key.strip()
            if key == "Path":
                patterns.extend(part.strip() for part in value.split(",") if part.strip())
            elif key == "Method":
                methods.extend(part.strip().upper() for part in value.split(",") if part.strip())
            else:
                raise AssertionError(
                    f"{TABLE.relative_to(ROOT)}: the route {entry.get('id')!r} uses a "
                    f"predicate this gate does not model: {predicate!r}. The gate's "
                    "matching is only sound while it knows every predicate in the "
                    "table — teach it, or remove the predicate."
                )
        out.append(TableRoute(
            rid=str(entry.get("id", "")),
            plane=str((entry.get("metadata") or {}).get("plane", "")),
            uri=str(entry.get("uri", "")),
            patterns=tuple(patterns),
            methods=tuple(methods),
            order=int(entry.get("order", 0) or 0),
        ))
    out.sort(key=lambda route: route.order)   # stable: equal orders keep the file order
    return out


def internal_only() -> list[tuple[str, str, str, str]]:
    """Routes deliberately not served at the edge: (plane, method, path, reason)."""
    block = _table_document().get("specproof", {}).get("gateway", {}).get("internal-only") or []
    return [(str(e.get("plane", "")), str(e.get("method", "")).upper(),
             str(e.get("path", "")), str(e.get("reason", "")))
            for e in block]


# ── matching ──────────────────────────────────────────────────────────────
def _segments(path: str) -> list[str]:
    return [part for part in path.split("/") if part != ""]


def path_matches(pattern: str, path: str) -> bool:
    """Spring's PathPattern semantics: ``{var}`` is ONE segment, ``**`` is the rest."""
    pattern_parts = _segments(pattern)
    path_parts = _segments(path)
    index = 0
    for part in pattern_parts:
        if part == "**":
            return True
        if index >= len(path_parts):
            return False
        if part.startswith("{") and part.endswith("}"):
            if path_parts[index] == "":
                return False
        elif part != path_parts[index]:
            return False
        index += 1
    return index == len(path_parts)


def route_matches(route: TableRoute, service: ServiceRoute) -> bool:
    if not any(path_matches(pattern, service.path) for pattern in route.patterns):
        return False
    if not route.methods:
        return True
    if service.method == "ANY":
        return True
    return service.method in route.methods


def first_match(routes: list[TableRoute], service: ServiceRoute) -> TableRoute | None:
    """The route that answers this path — the FIRST one, because order is the match."""
    for route in routes:
        if route_matches(route, service):
            return route
    return None


def is_catch_all(route: TableRoute) -> bool:
    return any(pattern == CATCH_ALL for pattern in route.patterns)


# ── the legs ──────────────────────────────────────────────────────────────
def test_the_probes_found_the_censuses() -> None:
    """A census that finds nothing is greener than a bug."""
    control = control_plane_routes()
    agent = agent_runtime_routes()
    table = table_routes()

    assert len(control) >= 8, (
        f"the control-plane census collapsed: {len(control)} routes — the "
        f"annotation reader stopped understanding the controllers"
    )
    assert len(agent) >= 40, (
        f"the agent-runtime census collapsed: {len(agent)} routes — the AST "
        f"reader stopped understanding the routers"
    )
    assert len(table) >= 2, (
        f"the edge's table holds {len(table)} route(s) — the table moved or the "
        f"reader stopped understanding it"
    )
    assert {r.plane for r in control} == {"control-plane"}
    assert {r.plane for r in agent} == {"agent-runtime"}


def test_every_plane_route_is_served_by_the_plane_that_owns_it() -> None:
    """R1 — one owner per path, and it is the plane that has the code."""
    table = table_routes()
    declared = {(plane, method, path) for plane, method, path, _ in internal_only()}
    offenders: list[str] = []
    for service in control_plane_routes() + agent_runtime_routes():
        key = (service.plane, service.method, service.path)
        if key in declared:
            continue
        match = first_match(table, service)
        if match is None:
            offenders.append(
                f"{service.method} {service.path} ({service.plane}, {service.where}) "
                f"is served by NO route of the table"
            )
        elif match.plane != service.plane:
            offenders.append(
                f"{service.method} {service.path} belongs to the {service.plane} "
                f"({service.where}) but the edge serves it to the {match.plane} "
                f"(route {match.rid!r})"
            )
    assert not offenders, (
        "the edge does not serve these routes to the plane that owns them:\n  "
        + "\n  ".join(offenders)
        + "\nEither give the path to its own plane, or declare it internal-only "
          "with the reason (specproof.gateway.internal-only in the same file)."
    )


def test_a_route_of_one_plane_is_not_claimed_by_the_other() -> None:
    """R5 — a route that claims the other plane's path is a swallow."""
    table = table_routes()
    offenders: list[str] = []
    for route in table:
        if is_catch_all(route):
            continue
        for service in control_plane_routes():
            if service.plane == route.plane:
                continue
            if route_matches(route, service):
                offenders.append(
                    f"route {route.rid!r} ({route.plane}) claims "
                    f"{service.method} {service.path} of the {service.plane} "
                    f"({service.where})"
                )
        for service in agent_runtime_routes():
            if service.plane == route.plane:
                continue
            if route_matches(route, service):
                offenders.append(
                    f"route {route.rid!r} ({route.plane}) claims "
                    f"{service.method} {service.path} of the {service.plane} "
                    f"({service.where})"
                )
    assert not offenders, (
        "these routes of the table claim a path of the other plane:\n  "
        + "\n  ".join(offenders)
        + "\nA path that is served by both planes is a path whose meaning "
          "depends on deployment order."
    )


def test_no_route_of_the_table_is_dead() -> None:
    """R4 — a route that claims nothing is a typo."""
    table = table_routes()
    services = control_plane_routes() + agent_runtime_routes()
    offenders: list[str] = []
    for route in table:
        if is_catch_all(route):
            continue
        claimed = [s for s in services if s.plane == route.plane and route_matches(route, s)]
        if not claimed:
            offenders.append(
                f"route {route.rid!r} ({route.plane}) claims no route of the "
                f"{route.plane} — it answers 404 for a path nobody serves"
            )
    assert not offenders, "\n".join(offenders)


def test_the_catch_all_comes_last() -> None:
    """R3 — the catch-all must not match before a specific route."""
    table = table_routes()
    catch_alls = [r.rid for r in table if is_catch_all(r)]
    assert len(catch_alls) == 1, (
        f"the table holds {len(catch_alls)} catch-all route(s) {catch_alls} — there "
        f"must be exactly one, and it must match last"
    )
    assert is_catch_all(table[-1]), (
        f"the catch-all is {catch_alls[0]!r} but the last route in the MATCH order "
        f"is {table[-1].rid!r} — a catch-all that matches first shadows every "
        f"specific route behind it (the match order is the `order` field first and "
        f"the file order second, so `order: -1` on the catch-all does this)"
    )


def test_an_internal_only_declaration_is_true() -> None:
    """R2 — a declaration that is not true is worse than none."""
    table = table_routes()
    services = control_plane_routes() + agent_runtime_routes()
    by_key = {(s.plane, s.method, s.path): s for s in services}
    offenders: list[str] = []
    for plane, method, path, reason in internal_only():
        key = (plane, method, path)
        if key not in by_key:
            offenders.append(
                f"{plane} {method} {path} is declared internal-only but that "
                f"plane serves no such route — the declaration is stale"
            )
            continue
        if not reason.strip():
            offenders.append(
                f"{plane} {method} {path} is declared internal-only with no reason"
            )
        for route in table:
            if route.plane != plane:
                continue
            if route_matches(route, by_key[key]):
                offenders.append(
                    f"{plane} {method} {path} is declared internal-only, but route "
                    f"{route.rid!r} serves it to its own plane — the declaration "
                    f"is not true"
                )
    assert not offenders, "\n".join(offenders)


def test_the_table_says_which_plane_each_route_is_for() -> None:
    """R6 — the plane is written down, and the URI agrees with it."""
    table = table_routes()
    offenders: list[str] = []
    seen: set[str] = set()
    for route in table:
        if route.rid in seen:
            offenders.append(f"route id {route.rid!r} appears twice")
        seen.add(route.rid)
        if route.plane not in PLANE_UPSTREAM:
            offenders.append(
                f"route {route.rid!r} declares plane {route.plane!r} — known planes "
                f"are {sorted(PLANE_UPSTREAM)}"
            )
            continue
        variable = PLANE_UPSTREAM[route.plane]
        if variable not in route.uri:
            offenders.append(
                f"route {route.rid!r} declares the {route.plane} but its URI "
                f"({route.uri!r}) does not name that plane's variable {variable}"
            )
    assert not offenders, "\n".join(offenders)
