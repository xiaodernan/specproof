"""The edge route table has THREE copies. Only one of them is the truth.

WHICH COPIES. The edge's route table — "which plane answers this path" —
is written down in three places:

  1. ``services/gateway/src/main/resources/application.yml`` — the runtime
     truth. The gateway matches in the order of that list.
  2. ``services/gateway/src/test/java/.../GatewayApplicationTests.java`` —
     the Java runtime test, which names the routes it expects. It fails
     when the YAML changes, but only when somebody runs Maven.
  3. ``infra/grafana/dashboards/specproof-slo.json`` — the Grafana panel
     "Edge 路由归属表（application.yml）". This is what an **operator**
     reads to find out which plane owns a path, and it is a hand-written
     markdown table inside a dashboard JSON.

WHAT WAS WRONG (measured, 2026-11-10). Copy 3 is enforced by **nothing**.
Reading it against copy 1 found that the catch-all row has **three** cells
in a **four**-column table::

    | agent-runtime-default | Path=/** | agent-runtime |

A markdown row with fewer cells than the header fills the columns from the
left, so the panel renders the catch-all's **path** as "Path=/**" and its
**plane** as "agent-runtime" — with the plane column **empty**. The one
row an operator most needs to read correctly (the catch-all swallows
everything not claimed above) is the one row whose plane column is
blank, and nothing in the repository would have said so.

THE RULES, each one closing one hole:

  R1  the dashboard table and the YAML list the SAME routes, in the SAME
      order (the order is the gateway's match order).
  R2  every row has all four cells. A short row renders into the wrong
      columns — a table that looks right and is not.
  R3  each row says the same methods, paths and plane as the YAML. The
      methods cell is "ANY" for a route that claims no ``Method``
      predicate — writing "GET" there would be inventing a restriction
      the edge does not have.
  R4  the Java test names the same routes as the YAML, so a route added
      to the YAML is caught **without** Maven in the loop (the Java test
      would catch it too, but only on a JDK).

Nothing here talks to a running gateway: this is a gate over the three
written copies, and the runtime reading of the same table is asserted by
the Java test that boots the edge.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "services" / "gateway" / "src" / "main" / "resources" / "application.yml"
DASHBOARD = ROOT / "infra" / "grafana" / "dashboards" / "specproof-slo.json"
JAVA_TEST = (
    ROOT
    / "services"
    / "gateway"
    / "src"
    / "test"
    / "java"
    / "dev"
    / "specproof"
    / "gateway"
    / "GatewayApplicationTests.java"
)

#: The panel an operator reads to find the plane that owns a path.
PANEL_TITLE = "Edge 路由归属表"

#: The column count the table declares in its header.
COLUMNS = ("route id", "method", "path", "plane")

#: What the method cell says for a route that claims NO Method predicate.
ANY_METHOD = "ANY"


@dataclass(frozen=True)
class EdgeRoute:
    """One route of the edge, as the YAML declares it."""

    route_id: str
    plane: str
    methods: tuple[str, ...]
    paths: tuple[str, ...]


def _routes() -> list[EdgeRoute]:
    """The YAML route table, in the order the gateway matches it."""
    document = yaml.safe_load(TABLE.read_text(encoding="utf-8"))
    entries = document["spring"]["cloud"]["gateway"]["routes"]
    routes: list[EdgeRoute] = []
    for entry in entries:
        methods: list[str] = []
        paths: list[str] = []
        for predicate in entry.get("predicates", []):
            name, _, value = predicate.partition("=")
            if name == "Path":
                paths = [part.strip() for part in value.split(",") if part.strip()]
            elif name == "Method":
                methods = [part.strip().upper() for part in value.split(",") if part.strip()]
        routes.append(
            EdgeRoute(
                route_id=str(entry["id"]),
                plane=str(entry["metadata"]["plane"]),
                methods=tuple(methods) if methods else (ANY_METHOD,),
                paths=tuple(paths),
            )
        )
    return routes


def _panel(document: dict) -> dict:
    """The one dashboard panel that is the edge's route table."""
    found: list[dict] = []

    def walk(panels: list[dict]) -> None:
        for panel in panels:
            title = str(panel.get("title", ""))
            if title.startswith(PANEL_TITLE):
                found.append(panel)
            walk(panel.get("panels", []))

    walk(document.get("panels", []))
    assert len(found) == 1, (
        f"expected exactly one {PANEL_TITLE!r} panel, found {len(found)} — "
        "the dashboard and the gate must agree on which panel it is"
    )
    return found[0]


def _dashboard_rows() -> list[list[str]]:
    """The rows of the panel's markdown table, as raw cell lists.

    A row with fewer cells than the header is kept AS IS — its shortness
    is the defect this gate exists to catch, so it must not be padded
    away before the check.
    """
    document = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = _panel(document)
    content = panel.get("options", {}).get("content", "")
    rows: list[list[str]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or cells[0] == COLUMNS[0]:
            continue
        if set(cells[0]) == {"-"}:
            continue
        rows.append(cells)
    return rows


def _java_route_ids() -> list[str]:
    """The route ids the Java runtime test names, in the order it lists them."""
    source = JAVA_TEST.read_text(encoding="utf-8")
    quoted = re.findall(r'"([a-z0-9\-]+)"', source)
    known = {route.route_id for route in _routes()}
    # The ids appear inside the assertion's containsExactlyInAnyOrder(...)
    # list; keep the ones that are route ids, in first-appearance order.
    seen: list[str] = []
    for token in quoted:
        if token in known and token not in seen:
            seen.append(token)
    return seen


def test_the_dashboard_has_exactly_one_edge_route_table_panel() -> None:
    document = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    panel = _panel(document)
    assert "route id" in panel.get("options", {}).get("content", ""), (
        "the panel does not carry a route table at all"
    )


def test_the_dashboard_table_lists_the_same_routes_in_the_same_order() -> None:
    rows = _dashboard_rows()
    assert [row[0] for row in rows] == [route.route_id for route in _routes()], (
        "the dashboard's route table does not match application.yml — the "
        "order matters too: it is the order the gateway matches in"
    )


def test_every_dashboard_row_has_all_four_cells() -> None:
    """A short row renders into the wrong columns.

    The catch-all row used to have three cells in a four-column table,
    which put "Path=/**" in the *path* column and left the *plane* column
    empty — the one row an operator most needs to read correctly.
    """
    for row in _dashboard_rows():
        assert len(row) == len(COLUMNS), (
            f"row {row[0]!r} has {len(row)} cells, the table declares "
            f"{len(COLUMNS)}: {row!r} — a short row renders into the wrong "
            "columns"
        )


def test_each_dashboard_row_says_the_same_thing_as_the_yaml() -> None:
    routes = {route.route_id: route for route in _routes()}
    for row in _dashboard_rows():
        route = routes[row[0]]
        methods = tuple(part.strip() for part in row[1].split(",") if part.strip())
        paths = tuple(part.strip() for part in row[2].split(",") if part.strip())
        assert methods == route.methods, (
            f"{route.route_id}: the dashboard says methods {methods}, the YAML "
            f"declares {route.methods}"
        )
        assert paths == route.paths, (
            f"{route.route_id}: the dashboard says paths {paths}, the YAML "
            f"declares {route.paths}"
        )
        assert row[3] == route.plane, (
            f"{route.route_id}: the dashboard says plane {row[3]!r}, the YAML "
            f"declares {route.plane!r}"
        )


def test_the_catch_all_row_says_it_claims_every_method() -> None:
    """The catch-all claims no Method predicate — writing "GET" would lie."""
    routes = {route.route_id: route for route in _routes()}
    catch_all = routes["agent-runtime-default"]
    assert catch_all.methods == (ANY_METHOD,)
    row = next(row for row in _dashboard_rows() if row[0] == "agent-runtime-default")
    assert row[1] == ANY_METHOD, (
        f"the catch-all row claims methods {row[1]!r} — the YAML declares no "
        "Method predicate, so it claims every method"
    )
    assert row[3] == catch_all.plane


def test_the_java_test_names_the_same_routes_as_the_yaml() -> None:
    """A route added to the YAML is caught without Maven in the loop."""
    assert _java_route_ids() == [route.route_id for route in _routes()]
