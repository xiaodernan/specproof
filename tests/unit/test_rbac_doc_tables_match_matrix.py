r"""#114: the human RBAC tables must say what ROLE_MATRIX enforces.

The same rule — who may do what to which resource — is written down four times:

    api/identity/principal.py::ROLE_MATRIX   the value the middleware enforces
    docs/architecture/MULTI_TENANT_DESIGN.md §2   the table test docstrings cite
    docs/api/auth/README.md                       the table API readers meet first
    apps/web/src/ui/accessRoles.ts                the sidebar's three lists

The last one has been re-derived from the matrix since #112. The two markdown
tables had no reader at all, and the drift was not hypothetical: §2's
auditor/admin cell said 无 while the matrix granted `admin:audit` — both the
grant and docs/api/auth/README.md's 审计视图 cell landed in 0d85586, and §2 was
never updated. A person who read §2 and "corrected" the code would have removed
auditor's access to the audit trail (#96's page) that #112's gate then locks in.

So each table is read from its own heading down, cell by cell, and every cell
becomes a set of actions compared to the matrix cell beside it. Two things are
taken from the doc rather than assumed: the section the rows live in (an
unanchored scan would read a different table in the same file as the contract)
and the column order (the header names the resources, so swapping two columns
reddens instead of being misread as a wrong grant).

The Chinese phrase table below is a translation layer, not a second source: it
names phrases, and every action set it produces either comes from the module
(ALL_ACTIONS, for 全) or is checked against the module's cells. A phrase nobody
uses fails this file, so the table cannot rot into a list of meanings for words
that no longer appear.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from api.identity.principal import ALL_ACTIONS, ROLE_MATRIX, ROLE_VALUES

REPO = Path(__file__).resolve().parents[2]

#: doc -> the heading whose section holds the contract table. Both docs use the
#: same heading text; the gate refuses a doc where it matches twice.
DOC_TABLES = {
    "docs/architecture/MULTI_TENANT_DESIGN.md": "RBAC 矩阵",
    "docs/api/auth/README.md": "RBAC 矩阵",
}

#: Resources in the order the tables must list them, unless the header says
#: otherwise — see `section_header` for where the order is actually read.
RESOURCES = ("jobs", "cases", "billing", "admin")

#: header cell -> matrix resource. The docs spell the second column
#: "cases/certificates"; a column nobody has registered here is refused by name
#: instead of being matched positionally.
COLUMN_VOCAB = {
    "jobs": "jobs",
    "cases/certificates": "cases",
    "billing": "billing",
    "admin": "admin",
}

#: "全" means "every action this resource has" — taken from the module, never typed.
ALL = "ALL"

#: phrase -> action set. Exact match only: a reworded cell goes red here rather
#: than being guessed at by substring.
PHRASES: dict[str, object] = {
    "全": ALL,
    "无": frozenset(),
    "读": frozenset({"read"}),
    "读(全租户审计视图)": frozenset({"read"}),
    "读+触发": frozenset({"read", "trigger"}),
    "读+验签": frozenset({"read", "verify"}),
    "用户/Token 管理": frozenset({"users", "tokens"}),
    "审计视图": frozenset({"audit"}),
    "审计视图(admin:audit)": frozenset({"audit"}),
}

ROW_RE = re.compile(r"^\|\s*(\w+)\s*\|(.*)$")


def rbac_section(doc: str, anchor: str) -> list[str]:
    """The lines of the RBAC section, from its heading to the next one."""
    path = REPO / doc
    assert path.is_file(), f"{doc} is gone — the scope of this gate is stale"
    lines = path.read_text(encoding="utf-8").splitlines()
    heads = [i for i, line in enumerate(lines) if line.startswith("#") and anchor in line]
    assert len(heads) == 1, (
        f"{doc}: {len(heads)} headings contain {anchor!r}. This gate reads the table "
        "under one heading; with two it cannot say which is the contract, and a scan "
        "that takes both would let one table cover for the other's drift"
    )
    start = heads[0]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("#")), len(lines))
    return lines[start:end]


def section_header(doc: str, anchor: str) -> tuple[str, ...]:
    """The resource columns the table declares, in the order it declares them."""
    headers = [line for line in rbac_section(doc, anchor) if line.strip().startswith("| 角色")]
    assert len(headers) == 1, (
        f"{doc}: {len(headers)} rows start with 角色 under {anchor!r} — the table needs "
        "exactly one header row for this gate to know what its columns mean"
    )
    cells = [c.strip() for c in headers[0].strip().strip("|").split("|")]
    unknown = [c for c in cells[1:] if c not in COLUMN_VOCAB]
    assert not unknown, (
        f"{doc}: column(s) {unknown} are not registered in COLUMN_VOCAB; add the mapping "
        "(and the resource to RESOURCES) or the table now holds a resource this gate "
        "cannot read"
    )
    return tuple(COLUMN_VOCAB[c] for c in cells[1:])


def table_rows(doc: str, anchor: str) -> dict[str, list[str]]:
    """role -> its cells, for every RBAC row in this doc's section."""
    rows: dict[str, list[str]] = {}
    for line in rbac_section(doc, anchor):
        m = ROW_RE.match(line.strip())
        if not m or m.group(1) not in set(ROLE_VALUES):
            continue
        cells = [c.strip() for c in m.group(2).rstrip().strip("|").split("|")]
        if len(cells) != len(RESOURCES):
            # A 3-cell row would otherwise zip-pair onto the wrong resources and
            # report a grant nobody wrote.
            raise AssertionError(
                f"{doc}: row for {m.group(1)!r} has {len(cells)} cells, expected "
                f"{len(RESOURCES)}: {line.strip()[:120]}"
            )
        assert m.group(1) not in rows, (
            f"{doc}: {m.group(1)!r} appears twice under {anchor!r} — which row is the "
            "contract? Disambiguate before this gate reads either"
        )
        rows[m.group(1)] = cells
    return rows


def actions_for(cell: str, resource: str) -> frozenset[str]:
    phrase = PHRASES.get(cell)
    if phrase is ALL:
        return ALL_ACTIONS[resource]
    if isinstance(phrase, frozenset):
        return phrase
    raise AssertionError(
        f"{cell!r} is not registered in PHRASES (resource {resource!r}). Register "
        "it with the exact action set it means, or restore the wording the table "
        "used before — do not let the gate start guessing at a role's rights."
    )


def compared_cells(doc: str) -> list[tuple[str, str, str, frozenset[str], frozenset[str]]]:
    """(doc, role, resource, doc's action set, matrix's action set) per cell."""
    anchor = DOC_TABLES[doc]
    out = []
    rows = table_rows(doc, anchor)
    missing = sorted(set(ROLE_VALUES) - set(rows))
    assert not missing, f"{doc}: no RBAC row for role(s) {missing}"
    extra = sorted(set(rows) - set(ROLE_VALUES))
    assert not extra, f"{doc}: rows for unknown role(s) {extra} — ROLE_VALUES?"
    for role in ROLE_VALUES:
        for resource, cell in zip(section_header(doc, anchor), rows[role], strict=True):
            out.append((doc, role, resource, actions_for(cell, resource),
                        ROLE_MATRIX[role][resource]))
    return out


@pytest.mark.parametrize("doc", sorted(DOC_TABLES))
def test_the_table_states_every_matrix_cell(doc: str) -> None:
    """One test per table: a doc that drifts alone must redden alone.

    A single test over both tables cannot tell "one copy is stale" from "both
    are stale", and the union reading would even pass while one table lost a
    role row and the other kept it.
    """
    cells = compared_cells(doc)
    assert len(cells) == len(ROLE_VALUES) * len(RESOURCES), (
        f"{doc}: compared {len(cells)} cells, expected "
        f"{len(ROLE_VALUES)}×{len(RESOURCES)}"
    )
    wrong = [
        f"| {role} | {resource} | says {sorted(doc_set)} but ROLE_MATRIX "
        f"enforces {sorted(matrix_set)}"
        for _, role, resource, doc_set, matrix_set in cells
        if doc_set != matrix_set
    ]
    assert not wrong, (
        f"{doc}: the human table and the enforced matrix disagree:\n  "
        + "\n  ".join(wrong)
    )


@pytest.mark.parametrize("doc", sorted(DOC_TABLES))
def test_the_table_declares_the_columns_the_gate_reads(doc: str) -> None:
    """The column order comes from the header, so it must be the matrix's."""
    assert section_header(doc, DOC_TABLES[doc]) == RESOURCES, (
        f"{doc}: its header declares {section_header(doc, DOC_TABLES[doc])} while this "
        f"gate's RESOURCES is {RESOURCES}; one of them is stale, and a silent "
        "positional read would pair cells with the wrong resources"
    )


def test_the_phrase_table_explains_only_phrases_in_use() -> None:
    """Dead glossary entries are how a translation layer rots."""
    used = {
        cell
        for doc in sorted(DOC_TABLES)
        for row in table_rows(doc, DOC_TABLES[doc]).values()
        for cell in row
    }
    dead = sorted(set(PHRASES) - used)
    assert not dead, (
        f"PHRASES registers {dead} but no table cell uses them; drop them, or "
        "the gate is claiming meanings for words nobody wrote"
    )
    unexplained = sorted(used - set(PHRASES))
    assert not unexplained, f"table cells with no registered meaning: {unexplained}"


def test_the_matrix_has_no_resource_the_tables_cannot_column() -> None:
    """The column list is the tables' shape; a 5th resource would go unread."""
    for role, resources in ROLE_MATRIX.items():
        assert set(resources) == set(RESOURCES), (
            f"ROLE_MATRIX[{role!r}] has {sorted(resources)} but the markdown "
            f"tables have columns {sorted(RESOURCES)} — add the column to both "
            "tables and to RESOURCES, or this gate reads less than the matrix holds"
        )
    for resource, actions in ALL_ACTIONS.items():
        assert resource in RESOURCES, f"ALL_ACTIONS has {resource!r} outside the columns"
        assert actions, f"ALL_ACTIONS[{resource!r}] is empty; 全 would mean 无"
