"""A tiny SQL-semantics fake for the MySQL statements this codebase sends.

Why this module exists
----------------------
The reclaimer's fake used to dispatch on the statement's TEXT PREFIX
(``sql.startswith("UPDATE verification_jobs SET status = 'QUEUED'")``)
and read the bound parameters BY POSITION (``params[0]`` is the TTL).
Two things follow from that, and both are bad:

1. **The fake's own rule was a hand-written second opinion.** The fake
   decided "stale" by comparing ``row["status"] == "RUNNING"`` — a rule
   the production ``WHERE`` clause never had to agree with. When the
   reclaimer's status set widened to every in-flight state, the fake
   still said "RUNNING only" and the test still passed: the test was
   measuring the fake, not the code.
2. **Reordering the placeholders silently changed the meaning.** The
   production statement and the fake's parameter positions were welded
   together; a harmless-looking reorder broke the test with a
   ``ValueError: invalid literal for int()`` instead of a real
   behavioural difference.

This module EVALUATES the statement instead of pattern-matching it:

* the conditions are read out of the SQL text;
* the parameters are bound by the order the placeholders APPEAR in the
  statement, not by a hardcoded index;
* the rows are filtered and updated by what the SQL actually says.

So a production statement that drops a guard now fails the test that
uses it — a dropped ``updated_at`` guard means a fresh row gets
reclaimed, and the fake will now say so.

Scope
-----
This is NOT a SQL engine. It understands the statement shapes this
codebase actually sends (SELECT with a WHERE, UPDATE with a SET and a
WHERE, the operators below). Anything it does not recognise RAISES,
loudly, rather than quietly pretending to have evaluated it — a fake
that shrugs at an unknown statement is a fake that stops testing.

Supported conditions
---------------------
``col = %s``            ``col = 'literal'``
``col IN (%s, ...)``    ``col < (NOW(3) - INTERVAL %s SECOND)``
``col IS NULL``         ``col IS NOT NULL``

Supported assignments
---------------------
``col = %s``            ``col = 'literal'``    ``col = NULL``
``col = col + 1``
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

__all__ = ["SqlFakeCursor", "SqlFakeTable", "UnsupportedSqlError"]


class UnsupportedSqlError(RuntimeError):
    """Raised when the fake meets a statement shape it does not model.

    A fake that shrugs at an unknown statement is a fake that has
    stopped testing. Refusing loudly is the point.
    """


#: ``col < (NOW(3) - INTERVAL %s SECOND)`` — the staleness guard.
_CUTOFF_RE = re.compile(
    r"^(\w+)\s*<\s*\(\s*NOW\(3\)\s*-\s*INTERVAL\s+%s\s+SECOND\s*\)$",
    re.IGNORECASE,
)
#: ``col = %s``
_EQ_PARAM_RE = re.compile(r"^(\w+)\s*=\s*%s$")
#: ``col = 'literal'``
_EQ_LITERAL_RE = re.compile(r"^(\w+)\s*=\s*'([^']*)'$")
#: ``col IN (%s, %s, ...)``
_IN_RE = re.compile(r"^(\w+)\s+IN\s*\((.*)\)$", re.IGNORECASE)
#: ``col IS NULL`` / ``col IS NOT NULL``
_IS_RE = re.compile(r"^(\w+)\s+IS\s+(NOT\s+)?NULL$", re.IGNORECASE)
#: ``TIMESTAMPDIFF(SECOND, col, NOW(3)) > col2`` — the budget guard.
_TIMESTAMPDIFF_RE = re.compile(
    r"^TIMESTAMPDIFF\s*\(\s*SECOND\s*,\s*(\w+)\s*,\s*NOW\(3\)\s*\)\s*>\s*(\w+)$",
    re.IGNORECASE,
)
#: ``col = col + 1``
_INCREMENT_RE = re.compile(r"^(\w+)\s*=\s*(\w+)\s*\+\s*(\d+)$")
#: ``col = NULL``
_SET_NULL_RE = re.compile(r"^(\w+)\s*=\s*NULL$", re.IGNORECASE)


def _split_top_level(text: str, separator: str = ",") -> list[str]:
    """Split on *separator* at depth zero (parens are respected).

    The separator may be more than one character (" AND ").
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    index = 0
    width = len(separator)
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if depth == 0 and text.startswith(separator, index):
            parts.append("".join(current))
            current = []
            index += width
            continue
        current.append(char)
        index += 1
    tail = "".join(current)
    if tail.strip():
        parts.append(tail)
    return [part.strip() for part in parts if part.strip()]


def _placeholders(text: str) -> int:
    """How many ``%s`` placeholders the text carries."""
    return text.count("%s")


class _Binder:
    """Hands out the bound parameters in the order the SQL mentions them."""

    def __init__(self, params: list[Any]) -> None:
        self._params = list(params)
        self._cursor = 0

    def take(self) -> Any:
        if self._cursor >= len(self._params):
            raise UnsupportedSqlError(
                "the statement asks for more parameters than were bound "
                f"(asked {self._cursor + 1}, bound {len(self._params)})"
            )
        value = self._params[self._cursor]
        self._cursor += 1
        return value

    def take_all(self) -> list[Any]:
        return [self.take() for _ in range(len(self._params) - self._cursor)]

    @property
    def remaining(self) -> int:
        return len(self._params) - self._cursor


class SqlFakeTable:
    """The rows a statement reads and writes.

    ``rows`` is a dict keyed by the row's id. ``now`` is the clock the
    ``NOW(3)`` in the statements refers to.
    """

    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        now: datetime | None = None,
    ) -> None:
        self.now = now or datetime(2026, 8, 20, 12, 0, 0)
        self.rows: dict[str, dict[str, Any]] = {
            str(row["id"]): dict(row) for row in (rows or [])
        }
        #: Every statement the code sent — asserted on where the TEXT
        #: itself is the thing under test.
        self.statements: list[str] = []
        #: Called with (sql, table) just before an UPDATE is applied — the
        #: seam a test uses to make another writer win the race. It lives
        #: on the TABLE (not the connection) because the store opens a
        #: fresh connection per operation.
        self.before_update: Callable[[str, SqlFakeTable], None] | None = None

    def cutoff(self, ttl_seconds: int) -> datetime:
        return self.now - timedelta(seconds=ttl_seconds)


class SqlFakeCursor:
    """A cursor that evaluates the statement against a :class:`SqlFakeTable`."""

    def __init__(self, table: SqlFakeTable) -> None:
        self.table = table
        self.sql = ""
        self.params: list[Any] = []
        self._rows: list[dict[str, Any]] = []
        self.rowcount = 0

    # ── the cursor protocol the store uses ────────────────────────
    def execute(
        self, sql: str, params: tuple[Any, ...] | list[Any] | None = None,
    ) -> None:
        self.sql = sql
        self.table.statements.append(sql)
        self.params = list(params or [])
        self._rows = []
        self.rowcount = 0

        if self.table.before_update is not None and sql.lstrip().upper().startswith(
            "UPDATE"
        ):
            self.table.before_update(sql, self.table)

        binder = _Binder(self.params)
        statement = " ".join(sql.split())
        head = statement.split(None, 1)[0].upper()
        if head == "SELECT":
            self._rows = self._select(statement, binder)
        elif head == "UPDATE":
            self.rowcount = self._update(statement, binder)
        else:
            raise UnsupportedSqlError(f"the fake does not model: {statement[:80]!r}")

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    # ── the evaluator ─────────────────────────────────────────────
    def _select(self, statement: str, binder: _Binder) -> list[dict[str, Any]]:
        where = self._where_clause(statement)
        rows = list(self.table.rows.values())
        if where:
            conditions = _split_top_level(where, " AND ")
            # The predicate is compiled ONCE: the parameters belong to the
            # statement, not to the rows it is applied to.
            predicate = self._compile(conditions, binder)
            rows = [row for row in rows if predicate(row)]
        order = self._order_by(statement)
        if order:
            keys = [key.strip() for key in order.split(",")]
            rows.sort(key=lambda row: tuple(str(row.get(key)) for key in keys))
        return [dict(row) for row in rows]

    def _update(self, statement: str, binder: _Binder) -> int:
        set_clause, where = self._set_and_where(statement)
        assignments = _split_top_level(set_clause, ",")
        conditions = _split_top_level(where, " AND ") if where else []
        # The assignments and the predicate are compiled once, in the order
        # the placeholders APPEAR in the statement — the SET clause first
        # (it precedes the WHERE clause in the text), then the conditions.
        compiled = [self._compile_assignment(item, binder) for item in assignments]
        predicate = self._compile(conditions, binder) if conditions else None
        changed = 0
        for row in list(self.table.rows.values()):
            if predicate is not None and not predicate(row):
                continue
            for apply in compiled:
                apply(row)
            changed += 1
        return changed

    def _compile(
        self, conditions: list[str], binder: _Binder,
    ) -> Callable[[dict[str, Any]], bool]:
        """Turn the WHERE conditions into a predicate, binding once."""
        checks = [self._compile_condition(item, binder) for item in conditions]
        return lambda row: all(check(row) for check in checks)

    def _compile_condition(
        self, condition: str, binder: _Binder,
    ) -> Callable[[dict[str, Any]], bool]:
        condition = " ".join(condition.split())

        match = _CUTOFF_RE.match(condition)
        if match:
            column, ttl = match.group(1), int(binder.take())
            cutoff = self.table.cutoff(ttl)
            return lambda row: (
                row.get(column) is not None and row.get(column) < cutoff
            )

        match = _EQ_PARAM_RE.match(condition)
        if match:
            column = match.group(1)
            wanted = str(binder.take())
            return lambda row: str(row.get(column)) == wanted

        match = _EQ_LITERAL_RE.match(condition)
        if match:
            column, wanted = match.group(1), match.group(2)
            return lambda row: str(row.get(column)) == wanted

        match = _IN_RE.match(condition)
        if match:
            column = match.group(1)
            wanted_set: list[str] = []
            for item in _split_top_level(match.group(2), ","):
                if item == "%s":
                    wanted_set.append(str(binder.take()))
                else:
                    wanted_set.append(item.strip().strip("'"))
            return lambda row: str(row.get(column)) in wanted_set

        match = _TIMESTAMPDIFF_RE.match(condition)
        if match:
            age_column, limit_column = match.group(1), match.group(2)
            now = self.table.now
            return lambda row: (
                row.get(age_column) is not None
                and (now - row.get(age_column)).total_seconds()
                > float(row.get(limit_column) or 0)
            )

        match = _IS_RE.match(condition)
        if match:
            column = match.group(1)
            negated = bool(match.group(2))
            return lambda row: (row.get(column) is not None) if negated else (
                row.get(column) is None
            )

        raise UnsupportedSqlError(f"the fake does not model the condition: {condition!r}")

    def _compile_assignment(
        self, assignment: str, binder: _Binder,
    ) -> Callable[[dict[str, Any]], None]:
        assignment = " ".join(assignment.split())

        match = _EQ_PARAM_RE.match(assignment)
        if match:
            column = match.group(1)
            value = binder.take()
            return lambda row: row.__setitem__(column, value)

        match = _EQ_LITERAL_RE.match(assignment)
        if match:
            column, value = match.group(1), match.group(2)
            return lambda row: row.__setitem__(column, value)

        match = _SET_NULL_RE.match(assignment)
        if match:
            column = match.group(1)
            return lambda row: row.__setitem__(column, None)

        match = _INCREMENT_RE.match(assignment)
        if match:
            column, source, step = match.group(1), match.group(2), int(match.group(3))
            return lambda row: row.__setitem__(
                column, int(row.get(source) or 0) + step
            )

        raise UnsupportedSqlError(f"the fake does not model the assignment: {assignment!r}")

    # ── statement shape helpers ───────────────────────────────────
    @staticmethod
    def _where_clause(statement: str) -> str:
        upper = statement.upper()
        index = upper.find(" WHERE ")
        if index < 0:
            return ""
        clause = statement[index + len(" WHERE "):]
        for terminator in (" ORDER BY ", " LIMIT "):
            cut = clause.upper().find(terminator)
            if cut >= 0:
                clause = clause[:cut]
        return clause.strip()

    @staticmethod
    def _order_by(statement: str) -> str:
        upper = statement.upper()
        index = upper.find(" ORDER BY ")
        if index < 0:
            return ""
        return statement[index + len(" ORDER BY "):].strip()

    @staticmethod
    def _set_and_where(statement: str) -> tuple[str, str]:
        upper = statement.upper()
        set_index = upper.find(" SET ")
        if set_index < 0:
            raise UnsupportedSqlError(f"the fake does not model the statement: {statement[:80]!r}")
        after_set = statement[set_index + len(" SET "):]
        where_index = after_set.upper().find(" WHERE ")
        if where_index < 0:
            return after_set.strip(), ""
        return (
            after_set[:where_index].strip(),
            after_set[where_index + len(" WHERE "):].strip(),
        )
