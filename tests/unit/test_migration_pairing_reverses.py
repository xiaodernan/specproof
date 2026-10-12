"""Gate: a down migration must restore what its up migration takes away.

``MULTI_TENANT_DESIGN.md`` says "迁移必须前向可回滚 (up/down 成对)" and 10 of 14
up migrations ship a ``down/`` file, but nothing checked that the pair is
actually a pair — that the second file reverses the first. Measured against a
real MySQL (#244), two ways it breaks:

* **An up that destroys rather than adds.** ``0006`` drops a foreign key *by
  name* (``contract_approvals_ibfk_1``) to reshape a primary key. Its down
  restored every index and column it had added, and no foreign key at all, so
  a rollback left ``contract_approvals`` referencing nothing while the file's
  header claimed to "restore the pre-0006 data shape". Re-running the up after
  the down failed with ``Can't DROP 'contract_approvals_ibfk_1'`` — the round
  trip the pairing promises did not exist.
* **A down that drops nothing** because its up adds nothing (``0012`` rewrites
  rows with a DELETE and adds one unique key). Judging the pair by symmetry in
  length would call that broken when it is correct.

The asymmetry is the point: ``ADD X`` / ``DROP X`` is the obvious direction,
while a ``DROP`` inside an up migration is invisible to it and has to be shown
to be answered by the down.
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[2] / "infra" / "mysql" / "migrations"

#: What an up migration creates.
_ADD = {
    "index": re.compile(r"\bADD\s+(?:UNIQUE\s+)?(?:INDEX|KEY)\s+`?(\w+)`?", re.I),
    "column": re.compile(r"\bADD\s+COLUMN\s+`?(\w+)`?", re.I),
    "table": re.compile(
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?", re.I),
    "foreign_key": re.compile(
        r"\bADD\s+CONSTRAINT\s+`?(\w+)`?\s+FOREIGN\s+KEY", re.I),
}

#: What a down migration removes. ``DROP KEY`` and ``DROP INDEX`` are the same
#: statement to MySQL, and ``ADD UNIQUE KEY`` names its object where
#: ``DROP INDEX`` drops it, so both spellings land in "index".
_DROP = {
    "index": re.compile(r"\bDROP\s+(?:UNIQUE\s+)?(?:INDEX|KEY)\s+`?(\w+)`?", re.I),
    "column": re.compile(r"\bDROP\s+COLUMN\s+`?(\w+)`?", re.I),
    "table": re.compile(
        r"\bDROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?`?(\w+)`?", re.I),
    "foreign_key": re.compile(r"\bDROP\s+FOREIGN\s+KEY\s+`?(\w+)`?", re.I),
}

#: What an up migration destroys — each has to be answered by the down. Same
#: spellings as ``_DROP`` because the direction only changes who writes them.
_TAKES_AWAY = dict(_DROP)

#: Migrations that predate the up/down convention: 0001-0004 are the baseline
#: schema, and their headers state neither pairing nor reversibility. Listing
#: them is the point — the set is visible and reviewable, and adding 0015
#: without a down does not silently join it.
_BASELINE = frozenset({
    "0001_init.sql",
    "0002_cancel_audit.sql",
    "0003_job_summary.sql",
    "0004_github_checks.sql",
})


def _strip_comments(text: str) -> str:
    """Drop comment lines before any pattern sees the file.

    The headers are prose and freely name objects ("adding version to the key",
    "the unique key is about to enforce"), so an un-stripped read would report
    objects the migration never creates.
    """
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("--")
    )


def _objects(text: str, patterns: dict[str, re.Pattern[str]]) -> dict[str, set[str]]:
    body = _strip_comments(text)
    return {kind: set(pattern.findall(body)) for kind, pattern in patterns.items()}


def _paired() -> list[tuple[Path, Path]]:
    return [
        (up, MIGRATIONS / "down" / up.name)
        for up in sorted(p for p in MIGRATIONS.glob("*.sql") if p.is_file())
        if (MIGRATIONS / "down" / up.name).exists()
    ]


def test_every_up_is_either_paired_or_named_a_baseline() -> None:
    unpaired = [
        p.name for p in sorted(MIGRATIONS.glob("*.sql"))
        if p.is_file() and not (MIGRATIONS / "down" / p.name).exists()
    ]
    unexpected = sorted(set(unpaired) - _BASELINE)
    assert not unexpected, (
        "these up migrations ship no down/ file and are not in the baseline "
        f"set: {unexpected}. Either write infra/mysql/migrations/down/<name>.sql "
        "that reverses it, or — if it genuinely cannot be reversed — put it in "
        "_BASELINE with a comment saying why."
    )
    # A baseline entry nobody has is a stale escape hatch, not a guarantee.
    stale = sorted(_BASELINE - {p.name for p in MIGRATIONS.glob("*.sql")})
    assert not stale, f"_BASELINE lists migrations that no longer exist: {stale}"


def test_down_drops_everything_the_up_adds() -> None:
    problems: list[str] = []
    for up, down in _paired():
        adds = _objects(up.read_text(encoding="utf-8"), _ADD)
        drops = _objects(down.read_text(encoding="utf-8"), _DROP)
        for kind in sorted(_ADD):
            missing = adds[kind] - drops[kind]
            if missing:
                problems.append(f"{up.name}: up adds {kind} {sorted(missing)}, "
                                f"down never drops it")
    assert not problems, "\n".join(problems)


def test_down_refills_what_the_up_takes_away() -> None:
    """The direction the obvious check misses.

    An up migration that destroys — drops an FK, a column, an index — leaves a
    hole the down has to fill. 0006's did not, so a rollback left
    ``contract_approvals`` with no foreign key while its header claimed to
    restore the pre-0006 shape.
    """
    problems: list[str] = []
    for up, down in _paired():
        takes = _objects(up.read_text(encoding="utf-8"), _TAKES_AWAY)
        restores = _objects(down.read_text(encoding="utf-8"), _ADD)
        for kind in sorted(_TAKES_AWAY):
            lost = takes[kind] - restores[kind]
            if lost:
                problems.append(
                    f"{up.name}: up drops {kind} {sorted(lost)} but its down "
                    f"never re-adds it — a rollback would leave the schema "
                    f"missing an object the pre-migration state had"
                )
    assert not problems, "\n".join(problems)


def test_down_never_drops_something_the_up_never_added() -> None:
    """The mirror of the above, and the one MySQL rejects outright.

    A ``DROP`` for an object that is not there is not a silent hole — it is
    ``ERROR 1091`` mid-rollback, which stops the batch after some statements
    have already committed (MySQL commits DDL implicitly, so 0012's own header
    says the ALTER cannot share a transaction with the rest). So the safe
    failure mode here is a red gate before the incident, not during it.
    """
    problems: list[str] = []
    for up, down in _paired():
        creates = _objects(up.read_text(encoding="utf-8"), _ADD)
        removes = _objects(down.read_text(encoding="utf-8"), _DROP)
        for kind in sorted(_DROP):
            phantom = removes[kind] - creates[kind]
            if phantom:
                problems.append(
                    f"{up.name}: down drops {kind} {sorted(phantom)} that the "
                    f"up never added — rollback would fail ERROR 1091 after "
                    f"earlier statements already committed"
                )
    assert not problems, "\n".join(problems)


