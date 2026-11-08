"""Classify the hand-written fakes in the test suite: SQL fake or not?

The ledger's queue item said "replace the remaining hand-written fakes
with an evaluator" — and then measured that the framing was WRONG: most
of those fakes are not SQL fakes at all, they are method-level duck
types (they implement the repository's methods, not a SQL surface). A
query evaluator can replace the first kind; replacing the second kind
with one would turn it into a real store, which is a different kind of
change entirely.

This script makes that distinction countable and repeatable, so the
queue item can be re-framed from measurements instead of from a hunch.

A count that moved is not an explanation, so the script can also say
WHICH classes moved it: ``census_at`` runs this same classifier over a
commit's own tree, and ``explain_drift`` compares that against the
current census and names each entrant, exit and bucket change with its
file, line, methods and the commit that brought it (``git blame`` on the
class definition line). The inventory gate calls it from its failure
message, so a red arrives already attributed.

Usage:
    python scripts/classify_test_fakes.py                # the report
    python scripts/classify_test_fakes.py --json         # machine-readable
    python scripts/classify_test_fakes.py --explain-drift REV   # what moved since REV
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import shutil
import subprocess
import tarfile
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_SUBDIR = "tests"
TESTS = REPO_ROOT / TEST_SUBDIR

#: The buckets, in the order the inventory lists them. ``FakeClass.kind`` only
#: ever answers with one of these, which is what makes a tally over ``BUCKETS``
#: a complete census rather than a list of whatever happened to be counted.
BUCKETS = ("sql-fake", "store-duck-type", "plain-double")

#: The surface a QUERY EVALUATOR could stand in for: it speaks SQL.
SQL_SURFACE = frozenset({
    "execute", "executemany", "fetchone", "fetchall", "fetchmany",
    "cursor", "commit", "rollback", "query", "select", "insert", "update",
})

#: The surface of a STORE/REPOSITORY double: it speaks the domain's
#: methods. A query evaluator is NOT a drop-in for these.
STORE_SURFACE = frozenset({
    "save", "save_and_flush", "find", "find_by_id", "find_all", "find_one",
    "get", "set", "delete", "update", "list", "iter", "scan", "publish",
    "xadd", "lpush", "rpush", "incr", "expire", "enqueue", "dequeue",
    "claim", "ack", "nack", "heartbeat", "renew", "put", "fetch",
})


@dataclass
class FakeClass:
    path: str
    line: int
    name: str
    methods: list[str] = field(default_factory=list)

    @property
    def sql_surface(self) -> list[str]:
        """The SQL surface this class speaks.

        ``execute`` ALONE is not the SQL surface: the name collides. The
        adapter protocol's ``execute`` means "run the build tool" (see
        ``tests/unit/test_adapter_protocol.py::DummyAdapter``, added by
        #431), so a class that speaks only ``execute`` is far more likely to
        be some other protocol's command than a database client. So
        ``execute`` counts only when the SAME class shows at least one more
        SQL-surface method (``cursor`` / ``fetch*`` / ``commit`` /
        ``rollback`` / ...). Every other method of the surface counts on its
        own — a fake connection that offers nothing but ``cursor`` is still a
        SQL fake.

        Measured, not assumed (#545): this rule leaves the census at the
        commit that pinned the inventory (#374, ``462340d``) bit-for-bit
        unchanged (20 / 43 / 192, total 255), and on ``origin/master``
        (``de746b6``, #544) it moves exactly ONE class: ``DummyAdapter``
        (sql-fake -> plain-double), giving 20 / 43 / 202, total 265. The old
        rule on the same tree gives 21 / 43 / 201. A stricter rule keeps the
        census a lower bound, which is the direction the inventory's own
        honest boundary already claims.
        """
        sql = [m for m in self.methods if m in SQL_SURFACE]
        if set(sql) == {"execute"}:
            return []
        return sql

    @property
    def store_surface(self) -> list[str]:
        return [m for m in self.methods if m in STORE_SURFACE]

    @property
    def kind(self) -> str:
        if self.sql_surface:
            return "sql-fake"
        if self.store_surface:
            return "store-duck-type"
        return "plain-double"


def _is_fake_name(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered.startswith(("fake", "stub", "mock", "dummy"))
        or lowered.endswith(("fake", "stub", "mock", "double", "store", "db"))
        or "fake" in lowered
    )


def _classes(path: Path, root: Path) -> list[FakeClass]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    found: list[FakeClass] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not _is_fake_name(node.name):
            continue
        methods = [
            item.name for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        found.append(FakeClass(
            path=str(path.relative_to(root)).replace("\\", "/"),
            line=node.lineno,
            name=node.name,
            methods=methods,
        ))
    return found


def collect(root: Path = REPO_ROOT) -> list[FakeClass]:
    everything: list[FakeClass] = []
    for path in sorted((root / TEST_SUBDIR).rglob("*.py")):
        everything.extend(_classes(path, root))
    return everything


def counts(fakes: list[FakeClass]) -> dict[str, int]:
    """The tally the inventory quotes, counted from the census it names."""
    off_bucket = {fake.kind for fake in fakes} - set(BUCKETS)
    assert not off_bucket, (
        f"a fake landed outside BUCKETS ({sorted(off_bucket)}): the "
        "classifier's `kind` and the census's denominator no longer agree"
    )
    tally = dict.fromkeys(BUCKETS, 0)
    for fake in fakes:
        tally[fake.kind] += 1
    return tally


def _git(*args: str, cwd: Path) -> str:
    """One git call, or a failure the caller has to describe."""
    proc = subprocess.run(("git", *args), cwd=cwd, capture_output=True, check=True)
    return proc.stdout.decode("utf-8", "replace")


def _git_rc(*args: str, cwd: Path) -> int:
    """A git call whose ANSWER is its exit code, so nonzero is not a failure.

    ``merge-base --is-ancestor`` says 1 for "not an ancestor" and 128 for
    "I cannot tell"; both are reasons not to claim anything, and neither is a
    reason to crash somebody else's failure message.
    """
    return subprocess.run(("git", *args), cwd=cwd, capture_output=True).returncode


def census_at(rev: str, *, repo_root: Path = REPO_ROOT) -> list[FakeClass]:
    """THIS classifier's answer for the tree ``rev`` names.

    The comparison only means something if both censuses come from the same
    code, so the pinned tree is measured rather than remembered: ``git
    archive`` writes that tree's bytes for ``tests/`` and ``tarfile`` unpacks
    them into a temporary directory. Nothing is written into the tree anybody
    is working in, and a rule change shows up as a rule change (see
    ``classifier_moved_in``) instead of masquerading as new code.

    Raises what git raises: ``CalledProcessError`` for a rev this repository
    cannot reach (a shallow checkout), ``FileNotFoundError`` for no git at
    all. ``explain_drift`` turns both into prose; the gate that only needs the
    current census never gets here.
    """
    archive = subprocess.run(
        ["git", "-C", str(repo_root), "archive", "--format=tar", rev, TEST_SUBDIR],
        capture_output=True, check=True,
    ).stdout
    staging = Path(tempfile.mkdtemp(prefix="fake-census-"))
    try:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
            tf.extractall(staging, filter="data")
        return collect(staging)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def classifier_moved_in(rev: str, *, repo_root: Path = REPO_ROOT) -> str:
    """The commits that changed the JUDGE between ``rev`` and here.

    Drift has two causes — the fakes changed, or the rule did — and only the
    first is visible in the census. This names the second when it happened, so
    a bucket move with no new class does not read like a phantom.
    """
    log = _git("log", "--oneline", f"{rev}..HEAD", "--", __file__, cwd=repo_root)
    return log.strip()


def _owners(lines: list[tuple[str, int]], *, since: str,
            repo_root: Path) -> dict[tuple[str, int], str]:
    """For each ``file:line``, what git says laid that line down.

    Blamed WITHOUT a revision range, on purpose: ``git blame since..HEAD``
    grades the commit at the END of the range, so a line that exists only in
    the working tree is not merely unattributed — the call is refused outright
    ("file has only N lines"). That is the case that matters most, because the
            gate goes red the moment somebody adds a fake, BEFORE they commit it.
    Without a range the same line comes back blamed to the all-zero revision,
    which is worth printing as what it is.

    A refused blame is two different answers, and the common one is not a
    gap in the tooling: ``git blame`` refuses a path HEAD does not have, which
    says the FILE is new work — not that this checkout cannot read history.
    """
    owners: dict[tuple[str, int], str] = {}
    for path, line in lines:
        try:
            blame = _git("blame", "-L", f"{line},{line}", "-s", "--", path,
                         cwd=repo_root)
        except subprocess.CalledProcessError:
            if _git_rc("rev-parse", "--verify", "--quiet", f"HEAD:{path}",
                       cwd=repo_root) != 0:
                owners[(path, line)] = (
                    "uncommitted — this file is not in git at all, so the "
                    "class is new work in this working tree")
            continue
        head = blame.split(maxsplit=1)
        if not head:
            continue
        sha = head[0]
        if set(sha) <= {"0"}:
            owners[(path, line)] = (
                "uncommitted in this working tree (git blames it to the "
                "zero revision)")
            continue
        # A boundary commit — the repository root, or wherever the blame had
        # to stop — is printed with a leading "^" that is NOT part of the sha.
        # Handed back to git it means "every ref except this commit", so
        # `show -s` exits 0 with no bytes at all and _owners would publish an
        # empty string as though git had named something.
        sha = sha.removeprefix("^")
        try:
            subject = _git("show", "-s", "--format=%h %s", sha,
                           cwd=repo_root).strip()
        except subprocess.CalledProcessError:
            continue
        if _git_rc("merge-base", "--is-ancestor", sha, since,
                   cwd=repo_root) == 0:
            subject += (f" — laid down at or before {since[:7]}, so the class "
                        "arrived by a rename or an edit, not by new lines")
        owners[(path, line)] = subject
    return owners


@dataclass
class Drift:
    """The difference between two censuses, class by class.

    Every field is a statement about an OCCURRENCE of a class, because a file
    may define the same name several times (measured: 25 of the 244 distinct
    names in ``tests/`` repeat, up to twelve times in
    ``test_redis_stream.py``). ``moved`` is therefore only used where the
    pairing cannot be ambiguous — one definition of that name, one bucket
    change. Elsewhere the difference is reported as an exit and an entry, which
    is true without claiming which definition it was.
    """

    entered: list[FakeClass] = field(default_factory=list)
    exited: list[FakeClass] = field(default_factory=list)
    moved: list[tuple[FakeClass, FakeClass]] = field(default_factory=list)

    def entered_by_bucket(self) -> dict[str, list[FakeClass]]:
        grouped: dict[str, list[FakeClass]] = {bucket: [] for bucket in BUCKETS}
        for fake in self.entered:
            grouped[fake.kind].append(fake)
        return grouped

    def is_empty(self) -> bool:
        return not (self.entered or self.exited or self.moved)

    def reconciles(self, pin: list[FakeClass], now: list[FakeClass]) -> bool:
        """Do the named classes add up to the difference in the totals?

        A report that lists three entrants while the SQL bucket gained four
        would send the reader after the wrong thing, so the prose and the
        arithmetic are checked against each other rather than trusted.
        """
        before, after = counts(pin), counts(now)
        for bucket in BUCKETS:
            gained = sum(1 for f in self.entered if f.kind == bucket)
            lost = sum(1 for f in self.exited if f.kind == bucket)
            moved_in = sum(1 for _, new in self.moved if new.kind == bucket)
            moved_out = sum(1 for old, _ in self.moved if old.kind == bucket)
            if after[bucket] - before[bucket] != gained - lost + moved_in - moved_out:
                return False
        return True


def _key(fake: FakeClass) -> tuple[str, str]:
    return (fake.path, fake.name)


def drift_between(pin: list[FakeClass], now: list[FakeClass]) -> Drift:
    """Pair two censuses by (file, class name) and report what did not cancel.

    Line numbers are NOT part of the identity: one insertion above a class
    moves every definition below it, and a gate keyed on lines would report
    the whole file as new. Two occurrences of the same name cancel when their
    bucket AND their method list agree, so reformatting a fake is not drift.
    """
    by_key: dict[tuple[str, str], list[FakeClass]] = {}
    for fake in pin:
        by_key.setdefault(_key(fake), []).append(fake)
    after: dict[tuple[str, str], list[FakeClass]] = {}
    for fake in now:
        after.setdefault(_key(fake), []).append(fake)

    drift = Drift()
    for key in sorted(set(by_key) | set(after)):
        old = by_key.get(key, [])
        new = after.get(key, [])
        shapes_old = Counter((f.kind, tuple(f.methods)) for f in old)
        shapes_new = Counter((f.kind, tuple(f.methods)) for f in new)
        unmatched_old = []
        for fake in old:
            shape = (fake.kind, tuple(fake.methods))
            if shapes_new[shape] > 0:
                shapes_new[shape] -= 1
            else:
                unmatched_old.append(fake)
        unmatched_new = []
        for fake in new:
            shape = (fake.kind, tuple(fake.methods))
            if shapes_old[shape] > 0:
                shapes_old[shape] -= 1
            else:
                unmatched_new.append(fake)

        if len(old) == len(new) == 1 and unmatched_old and unmatched_new:
            drift.moved.append((unmatched_old[0], unmatched_new[0]))
            continue
        drift.exited.extend(unmatched_old)
        drift.entered.extend(unmatched_new)

    drift.entered.sort(key=lambda f: (f.kind, f.path, f.line))
    drift.exited.sort(key=lambda f: (f.kind, f.path, f.line))
    drift.moved.sort(key=lambda pair: (pair[1].kind, pair[1].path, pair[1].line))
    return drift


def _where(fake: FakeClass) -> str:
    return f"{fake.path}:{fake.line} {fake.name} [{', '.join(fake.methods)}]"


def describe_drift(
    pin: list[FakeClass],
    now: list[FakeClass],
    *,
    since: str,
    owners: dict[tuple[str, int], str] | None = None,
    exit_causes: dict[str, str] | None = None,
    judge_changes: str = "",
) -> str:
    """What moved between two censuses, class by class, in as many words.

    Kept free of git so the prose can be tested on invented censuses: waiting
    for real drift to happen is not a way to find out whether a message names
    the right thing. ``owners`` and ``exit_causes`` are what the caller looked
    up; absent, the report says so instead of inventing an owner.
    """
    owners = owners or {}
    exit_causes = exit_causes or {}
    drift = drift_between(pin, now)
    before, after = counts(pin), counts(now)

    out: list[str] = [
        f"census at the pin ({since}) against the census read here:",
        "      " + "   ".join(
            f"{bucket} {before[bucket]} -> {after[bucket]}" for bucket in BUCKETS
        ) + f"   (total {sum(before.values())} -> {sum(after.values())})",
    ]
    if drift.is_empty():
        if before == after:
            out.append("  nothing moved: the same classes in the same buckets.")
            return "\n".join(out)
        out.append(
            f"  no class-by-class difference between the two trees, yet the "
            f"tallies differ ({before} vs {after}): the numbers in the pin do "
            "not come from the commit in the pin. Move both together.")
        return "\n".join(out)

    for bucket, items in drift.entered_by_bucket().items():
        if not items:
            continue
        out.append(f"  {len(items)} class(es) entered {bucket}:")
        for fake in items:
            out.append(f"      {_where(fake)}")
            owner = owners.get((fake.path, fake.line))
            if owner:
                out.append(f"        brought in by: {owner}")
            else:
                out.append(
                    "        brought in by: no answer from git — the line "
                    "could not be blamed here even though the file is in "
                    "HEAD, so read the file (a shallow checkout?)")
    for fake in drift.exited:
        out.append(f"  a class left the census: {_where(fake)}")
        out.append(
            f"      as measured at {since}; last touched since by: "
            + (exit_causes.get(fake.path)
               or "nothing — no commit in that range touched the file, so the "
                  "class left the tree without one (an uncommitted change?)"))
    for old, new in drift.moved:
        out.append(f"  a class changed buckets: {new.name} "
                   f"{old.kind} -> {new.kind} at {_where(new)}")
        out.append(
            "      no new class, so this is either the method list or the "
            + ("rule — see the classifier line below" if judge_changes
               else "rule; the classifier has no commit in this range, "
                    "so it is the method list"))
    if judge_changes:
        out.append("  the classifier itself moved in this range:")
        out.extend(f"      {line}" for line in judge_changes.splitlines())
    out.append(
        "what to do: the inventory is a MEASUREMENT, so either put the fake "
        "back, or re-measure and move the pin as one step — PIN_COUNTS and "
        "PIN_COMMIT together in tests/unit/test_fake_inventory_stays_measured.py "
        "plus the figures in docs/architecture/FAKE_INVENTORY.md, with the "
        f"reason. `python scripts/classify_test_fakes.py --explain-drift {since}` "
        "prints this again.")
    return "\n".join(out)


def drift_evidence(since: str, now: list[FakeClass], *,
                   repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Everything ``describe_drift`` wants, with each tree measured ONCE.

    ``{"unavailable": …}`` when git cannot answer — a shallow checkout, no git
    on PATH — which is a finding to report, not a crash to raise in the middle
    of somebody else's failure message.
    """
    try:
        pin = census_at(since, repo_root=repo_root)
        judge_changes = classifier_moved_in(since, repo_root=repo_root)
        drift = drift_between(pin, now)
        return {
            "pin": pin,
            "now": now,
            "since": since,
            "owners": _owners([(f.path, f.line) for f in drift.entered],
                              since=since, repo_root=repo_root),
            "exit_causes": {
                fake.path: _git("log", "--oneline", "-1", f"{since}..HEAD",
                                "--", fake.path, cwd=repo_root).strip()
                or None
                for fake in drift.exited
            },
            "judge_changes": judge_changes,
            "drift": drift,
        }
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        return {"unavailable": str(exc), "since": since}


def render_drift(evidence: dict[str, Any]) -> str:
    """The report for one ``drift_evidence`` reading."""
    if "unavailable" in evidence:
        since = evidence["since"]
        return (
            "the census moved, and the reason cannot be read here: measuring "
            f"{since}'s tree needs git history this checkout does not have "
            f"({evidence['unavailable']}). Reproduce it where the history is "
            f"complete: `python scripts/classify_test_fakes.py "
            f"--explain-drift {since}`")
    drift = evidence["drift"]
    assert drift.reconciles(evidence["pin"], evidence["now"]), (
        f"the drift report does not add up to the totals it explains: "
        f"{counts(evidence['pin'])} -> {counts(evidence['now'])} over {drift}")
    return describe_drift(
        evidence["pin"], evidence["now"], since=evidence["since"],
        owners=evidence["owners"], exit_causes=evidence["exit_causes"],
        judge_changes=evidence["judge_changes"])


def explain_drift(since: str, now: list[FakeClass], *,
                  repo_root: Path = REPO_ROOT) -> str:
    """Why the current census is not the one the inventory quotes.

    The only path here that reads git history, so it belongs in a failure
    message and on a command line — never on a green run.
    """
    return render_drift(drift_evidence(since, now, repo_root=repo_root))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="machine-readable output")
    parser.add_argument("--explain-drift", metavar="REV", default=None,
                        help="name the classes that moved the counts since REV; "
                             "exit 1 when they did (the gate's failure message "
                             "runs the same derivation)")
    args = parser.parse_args(argv)

    fakes = collect()
    buckets: dict[str, list[FakeClass]] = {bucket: [] for bucket in BUCKETS}
    for fake in fakes:
        buckets[fake.kind].append(fake)

    if args.explain_drift:
        evidence = drift_evidence(args.explain_drift, fakes)
        print(render_drift(evidence))
        if "unavailable" in evidence:
            return 2
        return 0 if counts(evidence["pin"]) == counts(fakes) else 1

    if args.json:
        print(json.dumps({
            "total": len(fakes),
            "counts": {k: len(v) for k, v in buckets.items()},
            "sql_fakes": [
                {
                    "path": f.path, "line": f.line, "name": f.name,
                    "sql_methods": f.sql_surface,
                }
                for f in buckets["sql-fake"]
            ],
        }, indent=2, ensure_ascii=False))
        return 0

    print(f"Hand-written fakes in tests/: {len(fakes)}\n")
    for kind, items in buckets.items():
        print(f"  {kind:18s} {len(items)}")
    print()
    print("The SQL fakes — the only ones a query evaluator could stand in for:")
    for fake in buckets["sql-fake"]:
        print(f"    {fake.path}:{fake.line} {fake.name}"
              f"  [{', '.join(fake.sql_surface)}]")
    print()
    print("The store duck types — an evaluator is NOT a drop-in for these:")
    for fake in buckets["store-duck-type"]:
        print(f"    {fake.path}:{fake.line} {fake.name}"
              f"  [{', '.join(fake.store_surface[:6])}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
