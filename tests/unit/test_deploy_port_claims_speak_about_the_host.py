"""The deploy plane's claim predicate must speak about the HOST, and the two
port-ownership planes must stay apart.

WHAT THIS ANSWERS
-----------------
The ledger carried a question for a long time (#475's queue, the #429
family's first half): the STATIC predicate ("which deploy declarations
occupy this number") and the RUNTIME predicate ("is this number held on
this host right now") — should they be merged into one?

MEASURED ANSWER: no, and this file is what makes the answer checkable.
The two are facts about two different planes:

  * deploy plane — "does a file in this repository publish this number on the
    host?"  True whether or not anything is running.
  * host plane — "is anything holding this number right now?"  True for an
    instant, and it changes under you.

A merged predicate would be wrong in BOTH directions: a compose file claims a
number even when nothing runs (so a runtime probe misses it), and a number
can be free now and claimed later (so a static scan cannot certify the host).
So each plane keeps its OWN owner and neither may reach into the other:

  deploy plane -> ``tests/unit/port_claims.py``
  host plane   -> ``tests/unit/port_probe.py``

WHAT WAS ACTUALLY BROKEN
------------------------
The static predicate used to live in
``tests/unit/test_invoice_cron_metrics_leg.py`` as ``_claims_the_number`` and
compared ``str(port)`` against each compose mapping's ``left`` (host side)
and ``right`` (container side) as STRINGS.

Every one of the 13 shipped mappings has a TEMPLATED host side —
``${MYSQL_PORT:-3306}`` — so a string comparison could never match it.  The
predicate's hits came entirely from the CONTAINER side, which is the side the
same file's own boundary note excludes ``expose:`` entries for:

    "``expose:`` entries are not in it because they declare an in-network
     container port, which cannot collide with a bind on the host"

E4's own docstring says the thing it wants to catch is "**a host mapping**
could take 9103 for another service".  The implementation could not see a
host mapping at all: a compose file publishing ``${SOME_PORT:-9103}:9103``
read as "0 claims".  That is a FALSE GREEN on exactly the question E4
exists to ask, and it was invisible because every shipped row happens to
have the same number on both sides of the colon.

THE RULES
---------
L1  the resolver reads a host side the way the host does: a template's
    default, a literal, a range, an address prefix — and an UNREADABLE host
    side is reported, never skipped.
L2  the predicate fires on the shapes that really publish the number: a
    templated host side, a literal host side, a range covering it.
L3  the predicate stays silent on the shapes that do not: a container-only
    row, a mapping whose CONTAINER side names the number, a neighbour.
L4  every shipped mapping's host side is READABLE — a row the resolver
    cannot read is a row the census is not talking about, and a "0 claims"
    reading over it is not evidence.
L5  the two planes do not reach into each other, and each occupancy shape
    has exactly one owner in the tree.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]

#: The deploy plane's owner. Overridable so the mutation arms can grade a
#: COPY: these are shared files, and an arm that mutated them in place would
#: risk breaking a concurrent lane's run. #475 and #292 ship the same idea.
CLAIMS_OWNER = Path(
    os.environ.get("SPECPROOF_PORT_CLAIMS_PATH", ROOT / "tests" / "unit" / "port_claims.py")
)
#: The host plane's owner, same convention.
PROBE_OWNER = Path(
    os.environ.get("SPECPROOF_PORT_PROBE_PATH", ROOT / "tests" / "unit" / "port_probe.py")
)
#: The leg that used to own the deploy predicate locally.
EXEMPT_LEG = Path(
    os.environ.get(
        "SPECPROOF_EXEMPT_LEG_PATH",
        ROOT / "tests" / "unit" / "test_invoice_cron_metrics_leg.py",
    )
)
#: The gate whose parser produces the compose mapping rows.
GATE_232 = ROOT / "tests" / "unit" / "test_listen_port_knobs_bind_the_scrape_roster.py"

SKIP_DIRS = {
    ".git", ".venv", ".venv312", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".ruff_cache", ".scratch", "node_modules", "dist", "build", "site-packages",
    "apps", "docs", ".local",
}

EXEMPT_NUMBER = 9103


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _claims() -> Any:
    return _load(CLAIMS_OWNER, "sp_port_claims")


def _gate232() -> Any:
    return _load(GATE_232, "sp_gate232_for_port_claims")


def tree_files() -> list[str]:
    """Every python file in the tree, pruning the directories that are noise."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel = Path(dirpath).relative_to(ROOT)
        for name in filenames:
            if name.endswith(".py"):
                out.append((rel / name).as_posix())
    return out


def imported_modules(source: str) -> set[str]:
    """The module names a file imports."""
    tree = ast.parse(source)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def called_attributes(source: str) -> set[str]:
    """Every attribute a file calls or reads."""
    tree = ast.parse(source)
    return {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}


# ---------------------------------------------------------------------------
# L1  the resolver reads the host side the way the host does
# ---------------------------------------------------------------------------


def test_a_templated_host_side_reads_as_its_default() -> None:
    """``${VAR:-N}`` and ``${VAR-N}`` both fall back to N."""
    owner = _claims()
    assert owner.host_ports("${MYSQL_PORT:-3306}").covers(3306)
    assert owner.host_ports("${MYSQL_PORT-3306}").covers(3306)
    assert not owner.host_ports("${MYSQL_PORT:-3306}").covers(3307)


def test_a_literal_host_side_reads_as_itself() -> None:
    owner = _claims()
    assert owner.host_ports("9103").covers(9103)
    assert not owner.host_ports("9103").covers(9104)


def test_a_range_reads_as_every_port_in_it() -> None:
    owner = _claims()
    ports = owner.host_ports("9100-9105")
    assert ports.covers(9100) and ports.covers(9103) and ports.covers(9105)
    assert not ports.covers(9106)


def test_an_address_prefix_is_not_read_as_a_port() -> None:
    """``127.0.0.1:9103`` publishes 9103, and the address is not a port."""
    owner = _claims()
    assert owner.host_ports("127.0.0.1:9103").covers(9103)
    assert not owner.host_ports("127.0.0.1:9103").covers(9104)


def test_a_container_only_row_publishes_no_host_port() -> None:
    """A row with no host side publishes nothing on the host."""
    owner = _claims()
    published = owner.host_ports("")
    assert not published.covers(9103)
    assert published.describe() == "no host port"


def test_an_unreadable_host_side_is_reported_not_skipped() -> None:
    """${VAR} has no default to read — that is a row the census cannot speak about.

    A skipped row is the false green this unit exists to close, so it has to
    be visible instead.
    """
    owner = _claims()
    published = owner.host_ports("${SOME_PORT}")
    assert published.unresolved == "${SOME_PORT}", published
    assert not published.covers(9103), "an unreadable row must not claim anything"


def test_an_unreadable_row_refuses_the_reading_entirely() -> None:
    """The refusal, not a smaller population.

    Skipping a row this module cannot read would hand the caller a "0
    claims" answer about a population it does not cover.  The house rule is
    "refuse, do not certify", so the reading stops.
    """
    owner = _claims()
    row = {"service": "node-exporter", "left": "${SOME_PORT}", "right": "9103"}
    with pytest.raises(owner.UnreadableHostSideError):
        owner.deploy_claims(9103, [row])


# ---------------------------------------------------------------------------
# L2  the predicate fires on the shapes that really publish the number
# ---------------------------------------------------------------------------


def test_a_templated_host_mapping_is_seen() -> None:
    """The false green this unit closes.

    This is the shape EVERY shipped mapping has.  A string comparison cannot
    see it, so a compose file publishing ${SOME_PORT:-9103}:9103 would have
    read as "no claim".
    """
    owner = _claims()
    row = {"service": "node-exporter", "left": "${SOME_PORT:-9103}", "right": "9103"}
    fired = owner.deploy_claims(9103, [row])
    assert fired, f"a templated host side publishing {EXEMPT_NUMBER} read as no claim"


def test_a_literal_host_mapping_is_seen() -> None:
    owner = _claims()
    row = {"service": "node-exporter", "left": "9103", "right": "9101"}
    assert owner.deploy_claims(9103, [row])


def test_a_range_covering_the_number_is_seen() -> None:
    owner = _claims()
    row = {"service": "node-exporter", "left": "9100-9105", "right": "9100-9105"}
    assert owner.deploy_claims(9103, [row])


def test_a_roster_job_targeting_the_number_is_seen() -> None:
    """The other half of the exemption: a job that SCRAPES the number reads it."""
    owner = _claims()
    roster = {"planted": {"host": "node-exporter", "port": 9103, "path": "/metrics"}}
    assert owner.roster_claims(9103, roster)
    assert not owner.roster_claims(9104, roster)


# ---------------------------------------------------------------------------
# L3  the predicate stays silent on the shapes that do not publish it
# ---------------------------------------------------------------------------


def test_the_container_side_is_not_a_host_claim() -> None:
    """A container port lives in the container's namespace.

    It cannot collide with a bind on the host, which is the very reason the
    same file excludes ``expose:`` entries.  Counting it made the predicate
    look like it could see host mappings when it could not.
    """
    owner = _claims()
    row = {"service": "node-exporter", "left": "3307", "right": "9103"}
    assert not owner.deploy_claims(9103, [row]), (
        "the container side of a mapping was read as a host claim"
    )


def test_a_neighbour_number_stays_silent() -> None:
    owner = _claims()
    row = {"service": "node-exporter", "left": "9104", "right": "9101"}
    assert not owner.deploy_claims(9103, [row])


# ---------------------------------------------------------------------------
# L4  the shipped population is readable
# ---------------------------------------------------------------------------


def test_every_shipped_host_side_is_readable() -> None:
    """A row the resolver cannot read is a row the census is not talking about.

    A "0 claims" reading over an unreadable population is not evidence, so
    the population has to be READABLE before its emptiness can be cited.
    """
    owner = _claims()
    mappings = _gate232()._all_mappings()
    assert len(mappings) >= 10, f"the compose mapping census collapsed to {len(mappings)} rows"
    unreadable = owner.unreadable_host_sides(mappings)
    assert not unreadable, (
        "these shipped mappings have a host side the deploy-plane owner cannot read, "
        "so its reading does not cover the population:\n  " + "\n  ".join(unreadable)
    )


def test_the_shipped_rows_are_the_templated_shape_the_owner_reads() -> None:
    """Why the bug was invisible, stated as a fact the gate can see.

    Every shipped host side is a template, so a predicate that compared
    strings would see NOTHING in the shipped population and every "0 claims"
    reading would have been a false green.
    """
    owner = _claims()
    mappings = _gate232()._all_mappings()
    templated = [row for row in mappings if "${" in row["left"]]
    assert templated, "no shipped mapping is templated — re-derive the measurement"
    assert len(templated) == len(mappings), (
        f"{len(templated)} of {len(mappings)} shipped mappings are templated; the "
        "measurement this unit rests on has changed shape"
    )
    for row in templated:
        assert owner.host_ports(row["left"]).unresolved is None, row


# ---------------------------------------------------------------------------
# L5  the two planes stay apart, and each shape has one owner
# ---------------------------------------------------------------------------


def test_the_deploy_owner_does_not_probe_the_host() -> None:
    """A deploy claim is a fact about the repository, not about this machine."""
    source = CLAIMS_OWNER.read_text(encoding="utf-8")
    imported = imported_modules(source)
    assert not any(name.split(".")[0] == "socket" for name in imported), (
        f"the deploy-plane owner imports socket: {sorted(imported)}"
    )
    assert "bind" not in called_attributes(source), (
        "the deploy-plane owner binds a socket — it has crossed into the host plane"
    )
    assert "getsockname" not in called_attributes(source)


def test_the_host_owner_does_not_read_deploy_files() -> None:
    """A host fact is a fact about this machine, not about the repository."""
    source = PROBE_OWNER.read_text(encoding="utf-8")
    imported = imported_modules(source)
    assert not any(name.split(".")[0] == "yaml" for name in imported), (
        f"the host-plane owner parses deploy files: {sorted(imported)}"
    )
    assert "open" not in called_attributes(source), (
        "the host-plane owner reads a file — it has crossed into the deploy plane"
    )
    assert "Path" not in called_attributes(source)


def test_neither_owner_imports_the_other() -> None:
    """The answer to 「合流」, as an import graph."""
    deploy_imports = imported_modules(CLAIMS_OWNER.read_text(encoding="utf-8"))
    host_imports = imported_modules(PROBE_OWNER.read_text(encoding="utf-8"))
    assert not any("port_probe" in name for name in deploy_imports), (
        "the deploy-plane owner reaches into the host plane"
    )
    assert not any("port_claims" in name for name in host_imports), (
        "the host-plane owner reaches into the deploy plane"
    )


def _occupancy_owners() -> dict[str, list[str]]:
    """Every function that decides occupancy, by the shape it uses."""
    out: dict[str, list[str]] = {}
    for rel in tree_files():
        try:
            tree = ast.parse((ROOT / rel).read_bytes())
        except (SyntaxError, ValueError):
            continue
        for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            binds_zero = False
            fixed: list[str] = []
            reads_back = False
            catches_oserror = False
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "bind"
                    and node.args
                ):
                    first = node.args[0]
                    if isinstance(first, ast.Tuple) and len(first.elts) == 2:
                        second = first.elts[1]
                        if isinstance(second, ast.Constant) and second.value == 0:
                            binds_zero = True
                        elif isinstance(second, ast.Constant) and isinstance(second.value, int):
                            fixed.append(str(second.value))
                        elif isinstance(second, ast.Name):
                            fixed.append(second.id)
                if isinstance(node, ast.Attribute) and node.attr == "getsockname":
                    reads_back = True
                if isinstance(node, ast.ExceptHandler) and node.type is not None:
                    names = (
                        [node.type.id]
                        if isinstance(node.type, ast.Name)
                        else [node.type.attr] if isinstance(node.type, ast.Attribute) else []
                    )
                    if "OSError" in names:
                        catches_oserror = True
            if binds_zero and reads_back:
                shape = "os-chosen"
            elif fixed and catches_oserror:
                shape = "fixed-number"
            else:
                continue
            out.setdefault(shape, []).append(f"{rel}:{fn.lineno} {fn.name}()")
    return out


def test_each_occupancy_shape_has_exactly_one_owner() -> None:
    """#475's rule, extended to the shape its rule could not see.

    #475 pinned "binds 0 AND reads the number back" to one owner.  The other
    shape — "bind a NAMED port and read OSError as held" — was invisible to
    that rule, and it had a home of its own inside a test file.
    """
    owners = _occupancy_owners()
    for shape in ("os-chosen", "fixed-number"):
        found = owners.get(shape, [])
        assert len(found) == 1, (
            f"the {shape} occupancy probe is defined {len(found)}x — one fact, one owner:\n  "
            + "\n  ".join(found)
        )
        assert found[0].startswith("tests/unit/port_probe.py:"), (
            f"the {shape} occupancy probe is owned by {found[0]}, not by the host-plane owner"
        )


def test_the_leg_no_longer_owns_the_deploy_predicate() -> None:
    """The predicate that used to live in the leg moved to the owner module."""
    source = EXEMPT_LEG.read_text(encoding="utf-8")
    tree = ast.parse(source)
    local = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_claims_the_number", "claims", "deploy_claims", "host_ports"}
    ]
    assert not local, f"the leg still defines the deploy predicate: {local}"
    assert "port_claims" in source, "the leg does not read the deploy-plane owner"


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
