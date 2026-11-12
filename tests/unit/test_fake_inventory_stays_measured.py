"""The fake inventory must keep saying what it says — and say who changed it.

The queue item "replace the remaining hand-written fakes with an evaluator"
was re-framed by MEASURING what those fakes actually are
(docs/architecture/FAKE_INVENTORY.md): most of them do not speak SQL at all,
and only the ones that do are anything a query evaluator could stand in for.

That measurement is only worth anything if it stays true, so this gate has
always re-run the classifier. What it did NOT have until #601 was an answer to
the next question, which is the one a red actually raises. The failure used to
be four integers plus a comment hand-copying "the ten classes that moved last
time" — a roster that went stale the moment four more fakes landed. The gate
could say "265 is not what I measure" and leave a reader to work out by hand
which classes moved, into which bucket, and in whose commit. That hand-work is
what a gate is supposed to spare people, and a copied measurement is exactly
the thing that rots.

So the numbers now travel with the commit whose tree they were measured on,
and the difference between that tree and this one is re-derived by the shipped
classifier and named class by class. Nothing in this file quotes a roster.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "classify_test_fakes.py"
RULE_SCRIPT = REPO_ROOT / "scripts" / "find_rule_shaped_sql_fakes.py"
INVENTORY = REPO_ROOT / "docs" / "architecture" / "FAKE_INVENTORY.md"

#: The census, and the tree it was measured on. The two are ONE fact: a count
#: with no commit cannot be re-derived, and a drift report explains the
#: difference against whatever tree it is handed. The leg marked ``slow``
#: re-measures this pair on every CI run; the numbers here are what
#: ``scripts/classify_test_fakes.py`` gave on that commit, not what anybody
#: last typed.
PIN_COMMIT = "71e5b6ecd47104a30cae7833d7a1103496e7079a"
PIN_COUNTS = {"sql-fake": 22, "store-duck-type": 42, "plain-double": 223}


def _classifier():
    spec = importlib.util.spec_from_file_location("classify_test_fakes", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # The module defines a dataclass, and dataclasses look their own
    # module up in sys.modules — so it has to be REGISTERED before it
    # is executed, not just loaded.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(*args: str) -> str | None:
    """git's answer, or None when git itself refuses."""
    proc = subprocess.run(("git", *args), cwd=REPO_ROOT, capture_output=True)
    return proc.stdout.decode("utf-8", "replace") if proc.returncode == 0 else None


def test_the_script_runs() -> None:
    module = _classifier()
    fakes = module.collect()
    assert fakes, "the classifier found no fakes at all — it stopped working"


def test_the_counts_are_pinned() -> None:
    """The numbers the inventory quotes, re-measured on every run.

    A change here means the fakes changed shape — which is worth a
    conversation, not a silent edit of the document. The conversation comes
    pre-paid: the message re-measures ``PIN_COMMIT``'s tree with the shipped
    classifier and names every class that entered, left or changed bucket,
    with its file, line, methods and the commit that laid that line down.
    Building it costs ~15 s, which is why it rides on the failure message and
    not on the green path.
    """
    module = _classifier()
    fakes = module.collect()
    buckets = module.counts(fakes)

    assert buckets == PIN_COUNTS, (
        f"the census is pinned at {PIN_COUNTS} (total "
        f"{sum(PIN_COUNTS.values())}) as measured on {PIN_COMMIT}, and this "
        f"tree measures {buckets} (total {len(fakes)}).\n"
        + module.explain_drift(PIN_COMMIT, fakes))


@pytest.mark.slow
def test_the_pin_pair_is_self_consistent() -> None:
    """``PIN_COUNTS`` is what the classifier measures on ``PIN_COMMIT``.

    Without this leg, "move the numbers" and "move the commit" are two
    separate edits, and a lane that does only the first leaves every later
    red explaining itself against the wrong tree — which does not read like a
    broken tool, it reads like evidence. This is the leg that says the drift
    report's own base is real.

    Marked ``slow`` because it unpacks a whole tree and parses it (~15 s): CI
    runs it, an inner loop can deselect it with ``-m 'not slow'``.
    """
    module = _classifier()
    try:
        pinned = module.census_at(PIN_COMMIT)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        pytest.skip(
            f"this checkout cannot measure {PIN_COMMIT} ({exc}); the same "
            "check runs wherever the history is complete")

    assert module.counts(pinned) == PIN_COUNTS, (
        f"PIN_COUNTS {PIN_COUNTS} is not what the classifier measures on "
        f"PIN_COMMIT {PIN_COMMIT}, which gives {module.counts(pinned)} — the "
        "pin is a pair, and it has to be moved as one")
    assert len(pinned) == sum(PIN_COUNTS.values()), (
        f"the pinned buckets add up to {sum(PIN_COUNTS.values())} but "
        f"{PIN_COMMIT}'s census holds {len(pinned)} classes")


def test_the_drift_base_is_a_commit_this_history_reaches() -> None:
    """A dangling PIN_COMMIT is a silent loss, so it is checked while green.

    The counts leg compares numbers, so it stays green through a history
    rewrite — while the attribution the next red prints has lost the tree it
    compares against. Two git calls, no tree unpacking.
    """
    if _git("rev-parse", "--git-dir") is None:
        pytest.skip(f"{REPO_ROOT} is not a git checkout, so no rev can be measured")

    assert _git("rev-parse", "--verify", "--quiet",
                f"{PIN_COMMIT}^{{commit}}") is not None, (
        f"PIN_COMMIT {PIN_COMMIT} is not a commit this repository can reach: "
        "the drift report has nothing to compare against. Move it to the "
        "commit whose tree the counts came from.")
    assert _git("merge-base", "--is-ancestor", PIN_COMMIT, "HEAD") is not None, (
        f"PIN_COMMIT {PIN_COMMIT} is not in HEAD's own past, so the tree it "
        "names is not an ancestor of the tree being measured, and a report "
        "about the difference between them would describe a history that does "
        "not contain this one.")


def test_each_entrant_is_attributed_to_a_commit_or_to_the_working_tree(
        tmp_path: Path) -> None:
    """Who brought the class in — answered with real git, on a throwaway repo.

    The owner line is the part of the report a reader acts on, and it has
    answers only git can give: a class that arrived in a commit is blamed to
    that commit; a class that is only in the working tree — the case that
    actually happens, since the gate goes red the moment somebody adds a fake
    and BEFORE they commit it — is blamed to the all-zero revision, which is
    not a commit and must not be rendered as one; and a class in a file that
    HEAD does not have is new work, which git says by refusing the path.
    Invented censuses cannot test any of that: they hand the owner in, so they
    only prove the renderer prints what it is given.
    """
    module = _classifier()
    repo = tmp_path / "repo"
    probe = repo / "tests" / "unit" / "test_probe.py"
    probe.parent.mkdir(parents=True)

    def commit(message: str) -> None:
        for args in (("add", "."),
                     ("-c", "user.email=probe@example", "-c", "user.name=probe",
                      "commit", "-qm", message)):
            proc = subprocess.run(("git", *args), cwd=repo, capture_output=True)
            assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")

    subprocess.run(("git", "init", "-q"), cwd=repo, capture_output=True, check=True)
    # line 1 is committed, line 6 arrives in the second commit, line 9 does not
    # arrive in any commit.
    probe.write_text("class FakeCommitted:\n    pass\n", encoding="utf-8")
    commit("the first probe commit")
    probe.write_text(
        "class FakeCommitted:\n    pass\n\n\n"
        "class FakeLanded:\n    pass\n", encoding="utf-8")
    commit("the second probe commit")
    probe.write_text(
        "class FakeCommitted:\n    pass\n\n\n"
        "class FakeLanded:\n    pass\n\n\n"
        "class FakeUncommitted:\n    pass\n", encoding="utf-8")

    owners = module._owners(
        [("tests/unit/test_probe.py", 6), ("tests/unit/test_probe.py", 9)],
        since="HEAD~1", repo_root=repo)

    landed = owners[("tests/unit/test_probe.py", 6)]
    assert "the second probe commit" in landed, landed

    uncommitted = owners[("tests/unit/test_probe.py", 9)]
    assert "uncommitted" in uncommitted and "zero revision" in uncommitted, (
        f"git blamed an uncommitted line to {uncommitted!r}, and the report "
        "would hand the reader a sha that resolves to nothing")

    # The third answer: a line that predates the pin cannot be the arrival of
    # a class the pin's census did not have, so the report says so instead of
    # quoting a commit as if it were the cause.
    before = module._owners([("tests/unit/test_probe.py", 1)], since="HEAD",
                            repo_root=repo)
    assert "at or before" in before[("tests/unit/test_probe.py", 1)], before

    # The fourth: a file nobody has ever committed. blame refuses the path,
    # and "no answer from git" would blame the tool for the reader's own
    # uncommitted work — this is the shape a new fake in a new file takes.
    fresh = ("tests/unit/test_probe_fresh.py", 1)
    (repo / "tests/unit/test_probe_fresh.py").write_text(
        "class FakeBrandNew:\n    pass\n", encoding="utf-8")
    brand_new = module._owners([fresh], since="HEAD", repo_root=repo)
    assert "not in git at all" in brand_new[fresh], brand_new


def test_a_moved_count_names_which_classes_moved_it() -> None:
    """The report on invented censuses — real drift is not how you test prose.

    Waiting for somebody to add a fake is not a way to find out whether the
    message names the right class, so each shape of drift gets its case here:
    an entrant, a disappearance, a class that changed bucket, and a
    reformatting that must NOT be reported as anything.
    """
    module = _classifier()
    fake = module.FakeClass

    def at(path: str, line: int, name: str, *methods: str):
        return fake(path=path, line=line, name=name, methods=list(methods))

    pin = [
        at("tests/unit/test_a.py", 3, "FakeCursor", "execute", "cursor"),
        at("tests/unit/test_a.py", 20, "FakeStore", "save"),
        at("tests/unit/test_b.py", 7, "FakeThing", "__init__"),
        at("tests/unit/test_gone.py", 1, "FakeLeaving", "get"),
        at("tests/unit/test_multi.py", 4, "FakeRedis", "__init__"),
        at("tests/unit/test_multi.py", 9, "FakeRedis", "__init__"),
    ]
    now = [
        at("tests/unit/test_a.py", 3, "FakeCursor", "execute", "cursor"),
        # only its line moved, and the shape is unchanged
        at("tests/unit/test_a.py", 24, "FakeStore", "save"),
        # the one class that changed bucket without arriving or leaving
        at("tests/unit/test_b.py", 7, "FakeThing", "__init__", "enqueue"),
        at("tests/unit/test_c.py", 2, "FakeArrived", "__init__"),
        # a file that defines the same name twice: WHICH definition moved is
        # not knowable from the two trees, and the report must not pretend
        at("tests/unit/test_multi.py", 4, "FakeRedis", "__init__", "put"),
        at("tests/unit/test_multi.py", 9, "FakeRedis", "__init__"),
    ]
    report = module.describe_drift(
        pin, now, since="deadbeef",
        owners={("tests/unit/test_c.py", 2): "abc1234 #601 the entrant's commit"},
        judge_changes="")

    # The arithmetic, so the prose and the totals can be read together.
    assert "sql-fake 1 -> 1" in report, report
    assert "store-duck-type 2 -> 3" in report, report
    assert "plain-double 3 -> 2" in report, report

    # Each class is named where it sits, with the methods that decided it.
    assert "entered plain-double" in report, report
    assert "tests/unit/test_c.py:2 FakeArrived [__init__]" in report, report
    assert "entered store-duck-type" in report, report
    assert ("tests/unit/test_multi.py:4 FakeRedis [__init__, put]"
            in report), report
    assert "a class left the census" in report, report
    assert "tests/unit/test_gone.py:1 FakeLeaving [get]" in report, report
    # No exit_causes were supplied for it, and the report says THAT instead of
    # printing an empty "last touched by:" a reader would read as a name.
    assert "no commit in that range touched the file" in report, report
    assert ("a class changed buckets: FakeThing plain-double -> "
            "store-duck-type") in report, report

    # The commit is quoted when it was looked up, and git's silence is said
    # out loud rather than left as a blank a reader fills in with a guess.
    assert "brought in by: abc1234 #601 the entrant's commit" in report, report
    assert "brought in by: no answer from git" in report, report

    # A bucket move with no arriving class has two possible causes. With no
    # classifier commit in the range the report RULES the rule out instead of
    # leaving the reader to hunt for a fake that did not change.
    assert ("the classifier has no commit in this range, so it is the "
            "method list") in report, report

    # A moved line number is not drift: naming it would send the reader after
    # a class that did not change at all.
    assert "FakeStore" not in report, report
    assert "FakeCursor" not in report, report

    # And the report's own arithmetic: the classes it names must account, per
    # bucket, for the difference in the tallies it printed.
    assert module.drift_between(pin, now).reconciles(pin, now), report


def test_a_judge_change_is_said_as_the_other_cause() -> None:
    """Drift has two causes, and only one of them is a class.

    A bucket move with no new class is usually the RULE having moved, and a
    report that only listed classes would leave the reader hunting for a fake
    that does not exist. So the classifier's own history in the range is
    quoted beside them.
    """
    module = _classifier()
    fake = module.FakeClass
    pin = [fake(path="tests/unit/test_b.py", line=7, name="FakeThing",
                methods=["__init__"])]
    now = [fake(path="tests/unit/test_b.py", line=7, name="FakeThing",
                methods=["__init__", "get"])]
    report = module.describe_drift(pin, now, since="deadbeef",
                                  judge_changes="1234567 #545 execute alone")
    assert "the classifier itself moved in this range" in report, report
    assert "1234567 #545 execute alone" in report, report
    assert "no new class" in report, report
    assert "rule — see the classifier line below" in report, report


def test_identical_trees_are_reported_as_no_drift() -> None:
    """The green half of the renderer, which the real gate never walks.

    ``describe_drift`` is reached from a red path in the gate, so without this
    case nothing would notice if it started claiming movement where the two
    trees are the same.
    """
    module = _classifier()
    census = module.collect()
    report = module.describe_drift(census, census, since=PIN_COMMIT)
    assert "nothing moved: the same classes in the same buckets." in report, report
    assert "entered" not in report, report


def test_execute_alone_is_not_a_sql_surface() -> None:
    """The collision, pinned at the predicate — not only in the totals.

    The aggregate count can say "one class moved" but not WHY. `execute`
    means two different things in this tree: run a statement, or run a
    build tool (`DummyAdapter`). These four edges keep the exception from
    widening into "ignore execute everywhere": another SQL surface still
    makes the class a SQL fake, and a store surface still wins over a lone
    execute.
    """
    module = _classifier()
    fake = module.FakeClass

    def kind(methods: list[str]) -> str:
        return fake(path="x", line=1, name="FakeX", methods=methods).kind

    assert kind(["execute"]) == "plain-double"
    assert kind(["execute", "cursor"]) == "sql-fake"
    assert kind(["execute", "save"]) == "store-duck-type"
    assert kind(["cursor"]) == "sql-fake"


def test_the_inventory_quotes_the_measured_numbers() -> None:
    """The document and the measurement must agree, figure by figure.

    Each needle is built from what the census says right now, so the
    document cannot keep a figure the code no longer has — including three
    that used to be prose with no reader at all: how many files the SQL fakes
    live in, how many of those are a cursor plus a connection, and the share
    the inventory rounds out of the first two columns of its own table.
    """
    module = _classifier()
    fakes = module.collect()
    sql = [f for f in fakes if f.kind == "sql-fake"]
    stores = sum(1 for f in fakes if f.kind == "store-duck-type")
    plain = sum(1 for f in fakes if f.kind == "plain-double")
    by_file = Counter(f.path for f in sql)
    split = sum(1 for count in by_file.values() if count > 1)
    share = round(100 * len(sql) / len(fakes), 1)

    text = INVENTORY.read_text(encoding="utf-8")
    assert f"| **SQL 假** | **{len(sql)}** |" in text
    assert f"| 仓储鸭子类型 | {stores} |" in text
    assert f"| 普通替身 | {plain} |" in text
    assert f"一共 {len(fakes)} 个" in text
    assert f"{share}%）" in text
    assert f"分布在 **{len(by_file)} 个文件**里" in text
    assert f"其中 {split} 处是" in text
    assert f"SQL 替身 {len(by_file)} 处" in text
    # The document has to name the tree its numbers came from, or a reader
    # cannot tell whether the figures are stale or the code is.
    assert f"`{PIN_COMMIT[:7]}`" in text, (
        f"FAKE_INVENTORY.md does not name the commit its numbers were "
        f"measured on ({PIN_COMMIT})")


def test_no_sql_fake_decides_by_the_statement_text() -> None:
    """A fake that DECIDES by the SQL text is a second opinion.

    That is the shape a query evaluator replaces — the fake decides what
    the statement means, and the production WHERE clause never has to
    agree with it. The measurement found exactly two, and both dispatch
    on the QUESTION ("is this a COUNT? an existence probe?"), not on a
    rule about the data — so replacing them would change what the test
    measures.

    If this gate goes red, a fake started deciding by the statement's
    meaning: either it becomes the evaluator's job, or the reason it
    genuinely needs its own rule is written down here.
    """
    spec = importlib.util.spec_from_file_location(
        "find_rule_shaped_sql_fakes", RULE_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    found = module.collect()
    assert len(found) == 2, (
        "the set of SQL fakes that decide by the statement text moved: "
        + "; ".join(f"{f.path}:{f.line} {f.name}" for f in found)
    )
    # And the two that remain are the ones the inventory names, with the
    # reason they stay.
    names = {f.name for f in found}
    assert names == {"_FakeCursor", "FakeCursor"}
    text = INVENTORY.read_text(encoding="utf-8")
    assert "test_audit_action_parity.py::_FakeCursor" in text
    assert "test_web_api.py::FakeCursor" in text
    assert "不换" in text
