"""#480 — the Java disclosure clauses, derived from the route table's values.

Three test files used to type, by hand, the sentence the Java skip note
carries: 「仓库无 …」 and 「… test 均无法运行」. A hand-typed sentence is a
second copy of production's wording, and a copy goes stale in silence —
#423 measured exactly that direction: a gradle-only repository was still told
「无 pom.xml」 after the route table had learned about gradle.

These helpers compose the clauses from the TABLE's values — the marker names
and the command stems — so:

* a production note that stops quoting the table is red (the clause is not
  in the note), and
* a production note that quotes a hand-written subset is red too (the clause
  carries every marker the table declares, the note carries fewer).

The clauses are read at call time, so a leg that swaps a route row sees the
disclosure move with the table.
"""

from __future__ import annotations

from craft import gates


def java_serving() -> gates._JavaServing:
    """The route table's Java view, read at call time."""
    return gates._java_serving()


def missing_markers_clause(serving: gates._JavaServing | None = None) -> str:
    """「仓库无 …」 — the build files no Java route could have answered for."""
    view = serving if serving is not None else java_serving()
    return "仓库无 " + " / ".join(view.markers)


def unrunnable_commands_clause(serving: gates._JavaServing | None = None) -> str:
    """「… test 均无法运行」 — the commands that have no build file to run."""
    view = serving if serving is not None else java_serving()
    return "·".join(view.stems) + " test 均无法运行"
