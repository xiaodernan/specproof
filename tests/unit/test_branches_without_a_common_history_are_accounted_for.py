"""WHAT WAS MEASURED -- the no-common-history register and its own rulers.

This gate re-measures #1548's reconciliation against the repository and compares
it to ``evidence/branch_reconciliation.py``. The split is deliberate (same shape
as ``evidence/verdict_channels.py``): the module declares adjudications, this file
owns the tape measure. A register that shipped its own measuring tool could not be
caught disagreeing with the repo, which is the only way a register becomes a lie.

Measured on ``origin/master`` at the time this gate was written:

* 110 refs in the ref store. 4 of them have no merge-base with master -- and only
  3 lines of work, because ``refs/tags/p0.5-verified-v1`` (an annotated tag object
  whose own sha is ``ea8e2dfb6...``) and
  ``refs/remotes/origin/release/p0.5-verified-v1`` peel to the same commit
  ``4145d95b7...``. A census keyed on names reports four orphan branches; the
  repository holds three. ``test_the_ref_population_is_measured_not_remembered``
  pins both counts and the peeling that reconciles them.
* Branch-only files: 2 + 10 + 0 = 12. Name-only tests (anchored ruler): 1 + 43 + 14
  = 58, of which 40 live in a file master also owns and 18 live in one file master
  does not have at all (``tests/integration/test_fault_scenarios.py``).
* ``_VALID_TRANSITIONS["FAILED"]`` in master measures 4 outgoing edges including
  QUEUED, while the branch's ``002_failed_terminal.sql`` states "FAILED transitions
  from {QUEUED, CANCELLED} -> {} (terminal)" and "Already applied in code". Both
  sentences cannot be true; master's is the measured one, so the verdict is
  ``reversed_by_master`` and shipping the migration would undo a decision.
* The two def rulers disagree on master by 7 names that are prose and nothing
  else -- they appear inside string literals in 10 files and are not a test
  definition anywhere in the tree. That is the number #1547's own census carried,
  because it used the unanchored shape. ``test_the_def_census_names_its_ruler``
  registers those 10 files and 7 names, so a new prose-only name has to be
  noticed instead of quietly inflating a population. The per-file disagreement is
  a bigger and much more volatile plane (27 files, 332 hits when this was
  written): a name invented in one file but defined for real in another does not
  change any census total, so that plane is measured and printed, never claimed.

Six rulers were broken while building and landing this gate, and the gate now
refuses to reproduce them:

1. ``git grep <rev>`` prints ``rev:path:text`` with no line number unless ``-n`` is
   passed. Parsing 4 fields off 3-field output dropped every line and the test-name
   census measured 0 for all three branches. An empty census read exactly like a
   clean repository.
2. ``git merge-base --all`` exits 1 for "no common history" and 128 for "that ref
   does not exist". Reading both as "no common history" turned a name I had just
   invented (``case-01-head``, which does not exist -- the flagship case uses
   ``head-v1``) into a fourth orphan lineage. The gate classifies by exit code.
3. Top-level YAML keys are vocabulary, not content. A regex over ``jobs:`` stopped
   at the first blank line and counted 1 job of 5 (and 1 of master's 8). Job ids are
   read with a YAML parser now.
4. Asking git the same question 110 times is a ruler with a cost: censusing the
   store with one ``merge-base`` per ref name made this the slowest test file in
   the repository (75s for one leg). Lineage is now computed once from
   ``rev-list --parents --all --reflog`` -- reachability, which is what
   merge-base answers -- and the fast ruler is re-asked the slow way for every
   registered name plus a deterministic sample, because the census is only
   worth having if both rulers give the same answer.
5. The clone-shape guard skipped whenever the register declared no names at all,
   and the legs that iterate the register's own tables took their denominator
   from those tables. Emptying the register produced six skips and one red instead
   of a census collapse going red at the population -- "the register says nothing"
   delivered as "there is nothing here to check", which is this lane's standing
   defect class wearing a guard's clothing. The guard now skips only for names the
   register does declare that this store does not have, and anything that counts
   files or names across the orphan lineages counts them over
   ``_measured_orphan_commits()``, which git answers and a register cannot talk
   out of. ``test_declared_successors_still_exist_in_master`` still iterates
   declarations, so it is vacuously green when the register is empty -- P2 and P3
   are the legs that own the population, and the arm table records exactly that.
6. ``_grep_word`` read the register itself. #1548 verified "8 passed" before its
   push, when ``origin/master`` did not yet contain ``evidence/branch_reconciliation.py``;
   the commit that shipped the register put the token ``config_hash`` into
   master's tree twice -- once as a ``REGISTERED_GAPS`` key, once inside the
   sentence that claims the name appears 0 times -- so the ruler that asks
   "is this SQL name anywhere in master?" answered yes and P8 went red on the
   pushed state (measured at ``3f493ea``, 1 failed / 7 passed, found by #1549's
   premise experiment rather than by anybody running the gate). The register was
   its own witness: writing a gap down closed it. ``SELF_WITNESS`` now holds the
   two files that carry claims -- the register and the ledger -- and both are
   pathspec-excluded from every ``git grep`` the gate makes, so the only hits
   that can close a gap are hits in something that could have taken the content.
   #1549's arm table records that planting the name in the ledger keeps P8 green
   while planting it in a migration reddens it.

WHAT THIS GATE DOES NOT SAY. It does not prove the dispositions are *right* -- only
that they are still checkable: a successor path that vanished, a symbol master no
longer has, or a rename whose master side was deleted all go red, and a human has to
re-adjudicate. It does not run the orphan branches' tests, does not fetch anything
(0 network), and does not certify on a clone where the registered refs are absent --
those legs skip with the count that resolved rather than fake a green.
"""

from __future__ import annotations

import ast
import importlib
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTER_PATH = ROOT / "evidence" / "branch_reconciliation.py"
REGISTER_MODULE = "evidence.branch_reconciliation"

#: The census base. The register declares the same string and one leg checks the
#: two agree -- a register may not quietly re-point its own baseline.
BASE = "origin/master"

PRESENT = "present"
ABSENT = "absent"
UNREADABLE = "unreadable"

_ANCHORED_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test_[A-Za-z0-9_]+)\s*\(")
_LOOSE_DEF = re.compile(r"\bdef\s+(test_[A-Za-z0-9_]+)\s*\(")
_SQL_NAMES = (
    re.compile(r"CREATE TABLE(?: IF NOT EXISTS)?\s+[`\"']?(\w+)", re.I),
    re.compile(r"ADD COLUMN(?: IF NOT EXISTS)?\s+[`\"']?(\w+)", re.I),
    re.compile(r"CREATE (?:UNIQUE )?INDEX(?: IF NOT EXISTS)?\s+[`\"']?(\w+)", re.I),
)
_HAS_A_NUMBER = re.compile(r"\d")


# ══════════════════════════════════════════════════════════════════════════
# register loading -- three states, because "absent" and "disagrees" differ
# ══════════════════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def _register() -> tuple[str, object, str]:
    """(state, module-or-None, reason). Never raises: a missing register is a
    finding, an unreadable one is a different finding, and an empty one is a third."""
    if not REGISTER_PATH.is_file():
        return ABSENT, None, f"{REGISTER_PATH.name} is not in the tree"
    source = REGISTER_PATH.read_text(encoding="utf-8", errors="replace")
    try:
        ast.parse(source)
    except SyntaxError as exc:
        return UNREADABLE, None, f"{REGISTER_PATH.name} does not parse: {exc.msg}"
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        module = importlib.import_module(REGISTER_MODULE)
    except Exception as exc:  # noqa: BLE001 - any import failure is "unreadable"
        return UNREADABLE, None, f"import failed: {type(exc).__name__}: {exc}"
    missing = [name for name in ("BASE_REF", "ORPHAN_COMMITS", "VERDICTS",
                                 "FILE_DISPOSITIONS", "RENAMED_TESTS", "RENAMED_JOBS",
                                 "NAME_ONLY_CENSUS", "REGISTERED_GAPS",
                                 "DEF_CENSUS_BLIND_SPOTS", "MEASURED_AT")
               if not hasattr(module, name)]
    if missing:
        return UNREADABLE, None, f"register carries no {missing}"
    return PRESENT, module, ""


def _reg():
    state, module, reason = _register()
    if state != PRESENT:
        pytest.fail(
            f"the reconciliation register is {state} ({reason}). A repository where "
            "nothing has been reconciled and a repository whose reconciliation was "
            "deleted are different states; this gate refuses to read either as "
            "'no orphan refs'. Register: evidence/branch_reconciliation.py"
        )
    return module


# ══════════════════════════════════════════════════════════════════════════
# rulers -- exit codes are part of the measurement, not noise
# ══════════════════════════════════════════════════════════════════════════

def _git(argv: list[str], allow: tuple[int, ...] = (0,)) -> tuple[int, str]:
    proc = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="surrogateescape")
    assert proc.returncode in allow, (argv, proc.returncode, proc.stderr[:400])
    return proc.returncode, proc.stdout


@lru_cache(maxsize=4096)
def _resolve(name: str) -> str | None:
    """Peel to a commit, or None. rc!=0 is 'this name is not here', which is NOT
    the same answer as 'it is here but shares no history'."""
    rc, out = _git(["git", "rev-parse", "--verify", "--quiet", f"{name}^{{commit}}"],
                   allow=(0, 1, 128))
    return out.strip() or None if rc == 0 else None


@lru_cache(maxsize=4096)
def _history_via_merge_base(name: str) -> str:
    """'common' | 'none' | 'unresolvable', decided by git's own exit code. One
    subprocess per name, so this is the ruler for a sample, not for a store."""
    rc, out = _git(["git", "merge-base", "--all", BASE, name], allow=(0, 1, 128))
    if rc == 0 and out.strip():
        return "common"
    if rc == 1 and not out.strip():
        return "none"
    return "unresolvable"


def _shares_history(tip: str, parents: dict[str, list[str]],
                    reachable: frozenset[str]) -> bool:
    stack = [tip]
    seen: set[str] = set()
    while stack:
        commit = stack.pop()
        if commit in seen:
            continue
        seen.add(commit)
        if commit in reachable:
            return True
        stack.extend(parents.get(commit, ()))
    return False


@lru_cache(maxsize=1)
def _dag_answerable() -> frozenset[str]:
    """Names whose lineage the single ``rev-list --parents --all --reflog`` pass
    can answer. A name the store will not enumerate an object for is exactly the
    rc=128 shape, and the DAG ruler must not silently call that 'no common
    history' -- the per-name merge-base ruler still has to answer for it."""
    answerable: set[str] = set()
    universe = _dag_universe()
    for name in _ref_names():
        tip = _ref_tip(name)
        if tip is not None and tip in universe[0]:
            answerable.add(name)
    return frozenset(answerable)


@lru_cache(maxsize=1)
def _dag_universe() -> tuple[dict[str, list[str]], frozenset[str]]:
    _, out = _git(["git", "rev-list", "--parents", "--all", "--reflog"])
    parents: dict[str, list[str]] = {}
    for line in out.splitlines():
        fields = line.split()
        if fields:
            parents.setdefault(fields[0], []).extend(fields[1:])
    baseline_tip = _resolve(BASE)
    reachable: set[str] = set()
    if baseline_tip is not None:
        stack = [baseline_tip]
        while stack:
            commit = stack.pop()
            if commit in reachable:
                continue
            reachable.add(commit)
            stack.extend(parents.get(commit, ()))
    return parents, frozenset(reachable)


@lru_cache(maxsize=4096)
def _history_state(name: str) -> str:
    """The lineage answer for a ref name: reachability computed from one DAG
    pass where that pass can see the object, the per-name git ruler otherwise.
    Both rulers are checked against each other on every registered name."""
    if name not in _dag_answerable():
        return _history_via_merge_base(name)
    parents, reachable = _dag_universe()
    return ("common" if _shares_history(_ref_tip(name), parents, reachable)
            else "none")


@lru_cache(maxsize=1)
def _ref_rows() -> tuple[tuple[str, str, str], ...]:
    """(refname, objectname, peeled) for every ref in one call. The third field
    is what makes annotated tags count: ``case-01-head`` and the commit it peels
    to are the same lineage, and a census keyed on objectname alone reports the
    tag and the branch as two lines of work."""
    _, out = _git(["git", "for-each-ref",
                   "--format=%(refname)%09%(objectname)%09%(*objectname)"])
    rows = []
    for line in out.splitlines():
        fields = line.split("\t")
        if len(fields) >= 2:
            rows.append((fields[0], fields[1], fields[2] if len(fields) > 2 else ""))
    return tuple(sorted(rows))


def _ref_names() -> tuple[str, ...]:
    return tuple(sorted(name for name, _o, _p in _ref_rows()))


def _ref_tip(name: str) -> str | None:
    """The commit a name denotes, peeling tag objects the way
    ``rev-parse name^{commit}`` does. None means the name is not in the store,
    which is git's rc=128 answer -- not rc=1's 'orphan'."""
    for ref_name, obj, peeled in _ref_rows():
        if ref_name == name:
            return (peeled or obj) or None
    return None


@lru_cache(maxsize=256)
def _tree(rev: str) -> frozenset[str]:
    _, out = _git(["git", "ls-tree", "-r", "--name-only", rev])
    return frozenset(out.split())


@lru_cache(maxsize=512)
def _show(rev: str, path: str) -> str:
    _, out = _git(["git", "show", f"{rev}:{path}"])
    return out


@lru_cache(maxsize=256)
def _defs_by_file(rev: str, anchored: bool = True) -> dict[str, frozenset[str]]:
    """path -> defined test names. ``-n`` is not cosmetic: without it git drops
    the line-number field and the 4-field parse below yields an empty census."""
    _, raw = _git(["git", "grep", "-n", "-e", "def test_", rev, "--", "*.py"],
                  allow=(0, 1))
    out: dict[str, set[str]] = {}
    dropped = 0
    for line in raw.splitlines():
        parts = line.split(":", 3)
        if len(parts) != 4:
            dropped += 1
            continue
        hit = (_ANCHORED_DEF if anchored else _LOOSE_DEF).search(parts[3])
        if hit:
            out.setdefault(parts[1], set()).add(hit.group(1))
    # an empty census from a non-empty grep is a broken ruler, not a clean repo
    if raw and not out:
        raise AssertionError(
            f"def census found 0 names in {len(raw.splitlines())} grep hits for {rev}; "
            f"{dropped} lines failed the field parse -- the ruler is blind")
    return {k: frozenset(v) for k, v in out.items()}


#: Files that carry the claims this gate re-measures. They are off every ruler:
#: a grep that may answer "is this name in master?" from the register's own
#: prose lets the register close its own gaps by writing them down, which is
#: exactly how P8 went red on ``3f493ea`` -- see the docstring's sixth ruler.
SELF_WITNESS = ("evidence/branch_reconciliation.py",
                "docs/operations/DEEP_OPTIMIZATION_PLAN.md")


@lru_cache(maxsize=4096)
def _grep_word(word: str, rev: str, paths: tuple[str, ...] = ()) -> bool:
    argv = ["git", "grep", "-q", "-w", "-e", word, rev, "--"]
    argv += [*paths, *(f":(exclude){p}" for p in SELF_WITNESS)]
    rc, _ = _git(argv, allow=(0, 1))
    return rc == 0


def _sql_symbols(text: str) -> set[str]:
    found: set[str] = set()
    for ruler in _SQL_NAMES:
        found |= set(ruler.findall(text))
    return found


def _job_ids(rev: str, path: str) -> set[str]:
    text = _show(rev, path)
    if not text.strip():
        return set()
    data = yaml.safe_load(text)
    jobs = data.get("jobs") if isinstance(data, dict) else None
    return {str(k) for k in jobs} if isinstance(jobs, dict) else set()


def _registered_names(register) -> tuple[str, ...]:
    return tuple(sorted(n for names in register.ORPHAN_COMMITS.values() for n in names))


def _key_commit(register, key: str) -> str:
    """Which orphan lineage a register key adjudicates. Keys carry a short commit
    prefix, not a full sha: a prefix matching 0 registered commits is a ghost and
    a prefix matching 2 is an ambiguity. Either way the verdict no longer points
    at anything, so it is an assertion failure -- not a key to be skipped."""
    prefix = key.split(":", 1)[0]
    hits = sorted(c for c in register.ORPHAN_COMMITS if c.startswith(prefix))
    assert len(hits) == 1, (
        f"register key {key!r} names commit prefix {prefix!r}, which resolves to "
        f"{len(hits)} of the registered orphan commits {hits} -- a verdict has to "
        "name exactly one lineage")
    return hits[0]


def _keys_under(register, mapping: dict, commit: str) -> list[str]:
    return sorted(k for k in mapping if _key_commit(register, k) == commit)


def _workflow_paths(rev: str) -> list[str]:
    return sorted(p for p in _tree(rev)
                  if p.startswith(".github/workflows/") and p.endswith(".yml"))


@lru_cache(maxsize=1)
def _measured_orphan_commits() -> tuple[str, ...]:
    """The lineages the *store* says share no history with ``BASE``, peeled.

    Several legs used to iterate ``register.ORPHAN_COMMITS`` as their driver, so
    an emptied register shrank the denominator instead of going red. Anything
    that counts files or names across the orphan lines of work counts them over
    this, which git answers and the register cannot talk out of.
    """
    return sorted({_resolve(name) for name in _ref_names()
                   if _history_state(name) == "none" and _resolve(name)})


def _require_refs_measurable(register) -> None:
    """Skip rather than certify when the registered refs are simply not in this
    clone (a ``fetch-depth: 1`` job cannot re-measure an orphan branch).

    A register that declares *no* names is not that case: "the census is empty"
    is a claim about the repository, and it has to fall through to the legs and
    be measured against the store. Laundering a collapsed census into six skips
    is the same shape as the read failure this lane keeps tripping over -- 'I
    cannot read it' delivered as 'there is nothing there'.
    """
    names = _registered_names(register)
    if not names:
        return
    resolved = [n for n in names if _resolve(n)]
    if resolved:
        return
    pytest.skip(
        f"0 of {len(names)} registered ref names resolve in this clone -- the "
        "reconciliation cannot be re-measured here, and 'cannot measure' is not "
        "'measured clean'")


# ══════════════════════════════════════════════════════════════════════════
# P1 -- the three failure states must not collapse into one another
# ══════════════════════════════════════════════════════════════════════════

def test_a_missing_register_is_not_an_empty_census():
    state, module, reason = _register()
    assert state == PRESENT, (
        f"register state={state} ({reason}); the census of refs with no common "
        "history has never been recorded in this repository. That is not the same "
        "finding as 'the repository has no orphan refs'.")
    assert module.BASE_REF == BASE, (
        f"the register declares BASE_REF={module.BASE_REF!r} but every ruler in "
        "this gate measures against the literal 'origin/master'; a register may "
        "not re-point its own baseline underneath the measurement")
    assert re.fullmatch(r"[0-9a-f]{40}", module.MEASURED_AT), (
        f"MEASURED_AT={module.MEASURED_AT!r} is not a 40-hex commit, so the census "
        "cannot be traced to the tree it ran against")
    rc, _ = _git(["git", "merge-base", "--is-ancestor", module.MEASURED_AT, "HEAD"],
                 allow=(0, 1, 128))
    assert rc == 0, (
        f"MEASURED_AT={module.MEASURED_AT[:12]} is not an ancestor of HEAD, so the "
        "register was authored against a tree this branch does not contain")


# ══════════════════════════════════════════════════════════════════════════
# P2 -- population, peeling, and the rc=1 / rc=128 distinction
# ══════════════════════════════════════════════════════════════════════════

def test_the_ref_population_is_measured_not_remembered():
    register = _reg()
    all_names = _ref_names()
    assert len(all_names) >= 20, (
        f"for-each-ref returned {len(all_names)} refs -- a census over so few names "
        "cannot establish the orphan population; this is a broken ruler, not a "
        "clean repository")
    remote_refs = [n for n in all_names if n.startswith("refs/remotes/")]
    assert remote_refs, (
        "0 refs under refs/remotes/ -- the orphan branches live only in remote-"
        "tracking refs, so nothing can be re-measured here")

    measured_none = sorted(n for n in all_names if _history_state(n) == "none")
    unresolvable = sorted(n for n in all_names if _history_state(n) == "unresolvable")
    assert not unresolvable, (
        f"{len(unresolvable)} ref names in the store answer merge-base with rc "
        f"other than 0/1: {unresolvable[:5]} -- the ruler cannot tell 'orphan' from "
        "'broken object'")

    registered = sorted(_registered_names(register))
    # Existence first: a registered name the store does not have at all is
    # git's rc=128 answer, and it must not be reported as a lineage problem.
    unregistered_but_dead = [n for n in registered if _resolve(n) is None]
    assert not unregistered_but_dead, (
        f"{len(unregistered_but_dead)} registered names do not resolve at all: "
        f"{unregistered_but_dead} -- 'that ref is not in this clone' is not "
        "'that ref has no common history' (merge-base rc 1 vs rc 128); the register "
        "must be corrected, not credited")

    assert registered == measured_none, (
        f"registered orphan names {registered} != measured names-with-no-common-"
        f"history {measured_none} (measured {len(measured_none)}); a new orphan "
        "branch is a new line of work that needs its own disposition, and a name "
        "that no longer shares no history needs its verdict re-read")

    # Two rulers must agree, or the population was censused by a different
    # measurement than the one git itself answers with. The DAG pass reads the
    # whole store in one call; merge-base is per name and is asked here only for
    # the names the register depends on plus a deterministic sample.
    cross_checked = sorted(set(registered) | set(all_names[:2]) | set(all_names[-2:]))
    disagreements = [
        (name, _history_state(name), _history_via_merge_base(name))
        for name in cross_checked
        if _history_state(name) != _history_via_merge_base(name)]
    assert not disagreements, (
        f"{len(disagreements)} of {len(cross_checked)} names the DAG ruler and "
        f"git's own merge-base disagree: {disagreements[:4]} -- one of the two is "
        "measuring reachability wrong, and the census would have to be re-run "
        "with the other one")
    fell_back = sorted(set(all_names) - set(_dag_answerable()))
    assert len(_dag_answerable()) * 5 >= len(all_names), (
        f"the DAG pass can answer only {len(_dag_answerable())} of "
        f"{len(all_names)} ref names ({fell_back[:4]}); below 4/5 coverage the "
        "fast ruler is decorative and the census is being paid for per name "
        "again -- check that rev-list --all --reflog still sees this store's refs")

    peeled: dict[str, list[str]] = {}
    for name in registered:
        peeled.setdefault(_resolve(name), []).append(name)
    measured_commits = sorted(peeled)
    assert measured_commits == sorted(register.ORPHAN_COMMITS), (
        f"registered orphan commits {measured_commits[:1]}... != peeled commits of "
        f"the registered names {measured_commits}; the register keys lineages by "
        "commit, which is where merge-base actually answers")
    for commit, names in sorted(peeled.items()):
        assert sorted(register.ORPHAN_COMMITS[commit]) == names, (
            f"commit {commit[:12]} is reached by {names} in the repo but registered "
            f"as {sorted(register.ORPHAN_COMMITS[commit])}")

    multi = {c: n for c, n in peeled.items() if len(n) > 1}
    assert len(registered) > len(measured_commits), (
        f"names={len(registered)} and commits={len(measured_commits)} -- the gate "
        "expects at least one lineage reachable by 2 names, because that is the "
        f"measured shape here ({ {c[:12]: n for c, n in multi.items()} }); if the "
        "repo no longer has such a pair, the register's 'N branches' sentence has "
        "to be re-written by a human")


# ══════════════════════════════════════════════════════════════════════════
# P3 -- every branch-only file, closed vocabulary, reasons carry numbers
# ══════════════════════════════════════════════════════════════════════════

def test_every_branch_only_file_has_a_verdict_from_the_closed_vocabulary():
    register = _reg()
    _require_refs_measurable(register)
    base_tree = _tree(BASE)
    measured_total = 0
    for commit in _measured_orphan_commits():
        only_here = _tree(commit) - base_tree
        measured_total += len(only_here)
        keys = _keys_under(register, register.FILE_DISPOSITIONS, commit)
        registered_paths = sorted(k.split(":", 1)[1] for k in keys)
        assert registered_paths == sorted(only_here), (
            f"commit {commit[:12]}: registered {len(registered_paths)} dispositions "
            f"{registered_paths} != measured {len(only_here)} branch-only paths "
            f"{sorted(only_here)} -- a file with no verdict is a file nobody decided "
            "about")
        for key in keys:
            entry = register.FILE_DISPOSITIONS[key]
            assert entry["verdict"] in register.VERDICTS, (
                f"{key} verdict={entry['verdict']!r} outside the closed vocabulary "
                f"{sorted(register.VERDICTS)}")
            assert _HAS_A_NUMBER.search(str(entry["reason"])), (
                f"{key} reason carries no measured number: {entry['reason']!r} -- a "
                "verdict that cannot be re-measured is an opinion")

    assert measured_total == len(register.FILE_DISPOSITIONS), (
        f"measured {measured_total} branch-only files across "
        f"{len(register.ORPHAN_COMMITS)} commits but the register holds "
        f"{len(register.FILE_DISPOSITIONS)} dispositions")


# ══════════════════════════════════════════════════════════════════════════
# P4 -- successors are checked against master's current tree
# ══════════════════════════════════════════════════════════════════════════

def test_declared_successors_still_exist_in_master():
    register = _reg()
    _require_refs_measurable(register)
    base_tree = _tree(BASE)
    dead_paths, dead_symbols = [], []
    declared = 0
    for key, entry in sorted(register.FILE_DISPOSITIONS.items()):
        paths = tuple(entry["successor_paths"])
        symbols = tuple(entry["successor_symbols"])
        declared += len(paths)
        for path in paths:
            if path not in base_tree:
                dead_paths.append(f"{key} -> {path}")
        if symbols and not paths:
            dead_symbols.append(f"{key} declares symbols but no path to look in")
        for sym in symbols:
            if not _grep_word(sym, BASE, paths):
                dead_symbols.append(f"{key} -> {sym} not in {paths}")
    assert not dead_paths, (
        f"{len(dead_paths)} declared successor paths are gone from {BASE}: "
        f"{dead_paths} -- the reconciliation was true against an older master")
    assert not dead_symbols, (
        f"{len(dead_symbols)} declared successor symbols no longer land in the "
        f"declared successor paths: {dead_symbols} -- {declared} paths and their "
        "content were the evidence for these verdicts")


# ══════════════════════════════════════════════════════════════════════════
# P5 -- the FAILED reversal must still be a reversal
# ══════════════════════════════════════════════════════════════════════════

def test_the_failed_terminal_reversal_still_holds():
    register = _reg()
    _require_refs_measurable(register)
    key = next((k for k in register.FILE_DISPOSITIONS
                if k.endswith("storage/migrations/002_failed_terminal.sql")), "")
    assert key, (
        "the register carries no disposition for the branch's 002_failed_terminal"
        ".sql -- that migration is the one place where master and the orphan branch "
        "answered the same question differently, so its absence means the "
        "reconciliation stopped looking")
    assert register.FILE_DISPOSITIONS[key]["verdict"] == "reversed_by_master", (
        f"{key} verdict={register.FILE_DISPOSITIONS[key]['verdict']!r}; the branch "
        "did not fail to land this file, master overturned it -- moving the verdict "
        "to not_landed would invite someone to port it")

    mysql = _show(BASE, "storage/mysql.py")
    match = re.search(r'"FAILED":\s*\{([^}]*)\}', mysql)
    assert match, (
        f"no \"FAILED\" row was measured in {BASE}:storage/mysql.py -- the reversal "
        "verdict rests on that table and the ruler is now blind")
    outgoing = sorted(set(re.findall(r'"([A-Z_]+)"', match.group(1))))
    branch_text = _show(_key_commit(register, key), key.split(":", 1)[1])
    claims_terminal = "terminal" in branch_text.lower()
    assert claims_terminal, (
        "the branch migration no longer claims FAILED is terminal, so the reversal "
        "this leg pins may no longer exist -- re-read the file")
    if outgoing:
        assert "QUEUED" in outgoing, (
            f"master's FAILED has {len(outgoing)} outgoing edges {outgoing} but none "
            "named QUEUED -- the branch's 'retry creates a new job_id' rule is what "
            "was reversed; if master removed retry-on-the-same-row the verdict needs "
            "re-adjudicating, not this assert loosened")
    else:
        pytest.fail(
            "master now gives FAILED 0 outgoing edges, i.e. master agrees with the "
            "branch: the reversed_by_master verdict is stale and the migration may "
            "in fact be missing -- re-adjudicate #1548 instead of editing this leg")


# ══════════════════════════════════════════════════════════════════════════
# P6 -- rename pairs on both sides, and the rest counted
# ══════════════════════════════════════════════════════════════════════════

def _split_rename_key(key: str) -> tuple[str, str, str]:
    head, _, branch_name = key.partition("::")
    sha_prefix, _, path = head.partition(":")
    return sha_prefix, path, branch_name


def _measured_name_census() -> dict[str, int]:
    base_names = {n for names in _defs_by_file(BASE).values() for n in names}
    base_tree = _tree(BASE)
    shared = branch_only = 0
    for commit in _measured_orphan_commits():
        for path, names in _defs_by_file(commit).items():
            gone = names - base_names
            if not gone:
                continue
            if path in base_tree:
                shared += len(gone)
            else:
                branch_only += len(gone)
    return {"total": shared + branch_only, "shared_file": shared,
            "branch_only_file": branch_only}


def test_the_rename_pairs_are_real_on_both_sides_and_the_rest_is_counted():
    register = _reg()
    _require_refs_measurable(register)
    base_defs = _defs_by_file(BASE)
    base_names = {n for names in base_defs.values() for n in names}
    by_commit = {c: _defs_by_file(c) for c in _measured_orphan_commits()}

    broken_branch_side, broken_master_side, already_explained = [], [], []
    for key, master_name in sorted(register.RENAMED_TESTS.items()):
        sha12, path, branch_name = _split_rename_key(key)
        commit = next((c for c in by_commit if c.startswith(sha12)), "")
        if not commit:
            broken_branch_side.append(f"{key}: no registered commit starts with {sha12}")
            continue
        names = by_commit[commit].get(path, frozenset())
        if branch_name not in names:
            broken_branch_side.append(f"{key}: {branch_name} is not a def in that commit")
        if branch_name in base_names:
            already_explained.append(key)
        if master_name not in base_defs.get(path, frozenset()):
            broken_master_side.append(
                f"{key} -> {master_name} is not a def in {BASE}:{path}")

    assert not broken_branch_side, (
        f"{len(broken_branch_side)} registered rename pairs lost their branch side: "
        f"{broken_branch_side} -- a rename is only a rename while both files exist")
    assert not broken_master_side, (
        f"{len(broken_master_side)} registered renames have no master side: "
        f"{broken_master_side} -- the claim 'this name became that name' is now "
        "unsupported by measurement")
    assert not already_explained, (
        f"{len(already_explained)} rename keys are no longer orphan names because "
        f"master now defines them: {already_explained} -- delete the pairs, do not "
        "let them age into the unexplained count")

    measured = _measured_name_census()
    registered_census = dict(register.NAME_ONLY_CENSUS)
    for field in ("total", "shared_file", "branch_only_file"):
        assert registered_census[field] == measured[field], (
            f"NAME_ONLY_CENSUS[{field!r}]={registered_census[field]} but measured "
            f"{measured[field]} -- the 58 name-level differences were explained by "
            "file ownership, and that explanation moves when master does")

    explained = len(register.RENAMED_TESTS) - len(already_explained)
    unexplained = measured["shared_file"] - explained
    assert registered_census["unexplained_after_renames"] == unexplained, (
        f"register says {registered_census['unexplained_after_renames']} shared-file "
        f"names stay unexplained; measured {measured['shared_file']} shared-file "
        f"- {explained} registered renames = {unexplained} -- the residue is the "
        "part of the merge that nobody has accounted for yet")


# ══════════════════════════════════════════════════════════════════════════
# P7 -- the def ruler says where it disagrees with itself
# ══════════════════════════════════════════════════════════════════════════

def test_the_def_census_names_its_ruler():
    register = _reg()
    anchored = _defs_by_file(BASE, anchored=True)
    loose = _defs_by_file(BASE, anchored=False)
    anchored_names = {n for names in anchored.values() for n in names}
    loose_names = {n for names in loose.values() for n in names}
    assert anchored_names <= loose_names, (
        f"the anchored ruler found {len(anchored_names)} names and the loose ruler "
        f"{len(loose_names)}; anchored ⊆ loose must hold, otherwise the census is "
        "reading two different trees")

    prose_only = loose_names - anchored_names

    blind: dict[str, set[str]] = {}
    per_file_blind: dict[str, set[str]] = {}
    for path, names in loose.items():
        missed_here = names - anchored.get(path, frozenset())
        if missed_here:
            per_file_blind[path] = missed_here
        # The name-level census defect is a name the loose ruler prints that the
        # anchored ruler cannot find ANYWHERE in the tree: prose counted as a
        # test. A name missed only in this file but defined for real in another
        # file does not change the census total.
        fake = names & prose_only
        if fake:
            blind[path] = fake

    registered = {k: set(v) for k, v in register.DEF_CENSUS_BLIND_SPOTS.items()}
    missing = sorted(set(registered) - set(blind))
    added = sorted(set(blind) - set(registered))
    assert not missing and not added, (
        f"def-census blind spots disagree: registered-only {missing[:6]} "
        f"({len(missing)}), measured-only {added[:6]} ({len(added)}). The loose "
        f"\\bdef ruler currently over-counts by {len(prose_only)} names "
        f"{sorted(prose_only)}; #1547's census carried that number, so the "
        "population it printed was fixture prose counted as tests")
    for path in sorted(set(registered) & set(blind)):
        assert registered[path] == blind[path], (
            f"{path}: registered {sorted(registered[path])} but measured "
            f"{sorted(blind[path])} -- the file started inventing (or stopped "
            "inventing) prose-only test names")
    assert {n for names in registered.values() for n in names} == prose_only, (
        f"the register's blind spots name "
        f"{len({n for names in registered.values() for n in names})} prose-only "
        f"test names but the tree has {len(prose_only)}: {sorted(prose_only)} -- "
        "an unregistered prose name is one the census still counts as a test")
    # one-way on purpose: every prose-only name is also a name the anchored
    # ruler misses in that same file, so the register's population has to sit
    # inside the per-file population. The reverse inclusion is deliberately NOT
    # claimed -- see the docstring boundary.
    assert set(blind) <= set(per_file_blind), (
        f"{sorted(set(blind) - set(per_file_blind))[:4]} are registered as "
        "prose-only but the per-file ruler finds nothing there -- the two rulers "
        "are reading different trees")



# ══════════════════════════════════════════════════════════════════════════
# P8 -- gaps are re-derived, in both directions
# ══════════════════════════════════════════════════════════════════════════

def test_registered_gaps_are_exactly_the_measured_absences():
    register = _reg()
    _require_refs_measurable(register)
    base_tree = _tree(BASE)

    measured_gaps: set[str] = set()

    # (1) SQL names the branch migrations declared that master never took,
    #     measured from the branch trees rather than from the register's own
    #     file list -- a gap hidden by deleting a disposition must not be able
    #     to hide a second time by not being mentioned here.
    for commit in _measured_orphan_commits():
        for path in sorted(_tree(commit) - base_tree):
            if not path.endswith(".sql"):
                continue
            for symbol in sorted(_sql_symbols(_show(commit, path))):
                if not _grep_word(symbol, BASE):
                    measured_gaps.add(symbol)

    # (2) job ids the orphan branches' own workflow files declare that no master
    #     workflow job id takes, minus the ones a registered rename accounts for
    branch_jobs: set[str] = set()
    for commit in _measured_orphan_commits():
        for path in _workflow_paths(commit):
            if path in base_tree:
                continue
            branch_jobs |= _job_ids(commit, path)
    master_jobs: set[str] = set()
    for path in _workflow_paths(BASE):
        master_jobs |= _job_ids(BASE, path)
    assert branch_jobs and master_jobs, (
        f"the YAML job-id ruler read {len(branch_jobs)} branch and "
        f"{len(master_jobs)} master job ids -- an empty denominator makes every "
        "gap disappear, which is a blind ruler and not a clean repository")
    measured_gaps |= branch_jobs - master_jobs - set(register.RENAMED_JOBS)

    # (3) files whose own verdict is that nothing landed
    measured_gaps |= {key.split(":", 1)[1] for key, entry
                      in register.FILE_DISPOSITIONS.items()
                      if entry["verdict"] == "not_landed"}

    registered_gaps = set(register.REGISTERED_GAPS)
    assert registered_gaps == measured_gaps, (
        f"registered gaps ({len(registered_gaps)}) != measured absences "
        f"({len(measured_gaps)}): registered-only "
        f"{sorted(registered_gaps - measured_gaps)}, measured-only "
        f"{sorted(measured_gaps - registered_gaps)} -- a gap deleted from the "
        "register reads exactly like a gap that was fixed")

    for token, reason in sorted(register.REGISTERED_GAPS.items()):
        assert _HAS_A_NUMBER.search(str(reason)), (
            f"gap {token!r} is explained without a measurement: {reason!r}")

    for old_name, new_name in sorted(register.RENAMED_JOBS.items()):
        assert old_name in branch_jobs, (
            f"{old_name} is not among the {len(branch_jobs)} job ids the orphan "
            "workflows actually declare")
        assert new_name in master_jobs, (
            f"{old_name} -> {new_name} is registered as a rename but {new_name} is "
            f"not one of master's {len(master_jobs)} workflow job ids: "
            f"{sorted(master_jobs)}")
