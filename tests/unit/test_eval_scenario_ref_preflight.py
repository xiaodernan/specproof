"""Scenario-ref preflight (#243) must be a real, tested contract.

`specproof eval` refuses to run -- and tells the operator exactly why -- when a
case's `base_ref` / `head_ref` does not resolve in `--repo`. Before #243 this
failed mid-pipeline as a `NOT_RUN` (or worse, a silent miss) and the operator
had to reverse-engineer the cause from a mid-run message. The preflight turns
that into an up-front, named failure.

These tests pin the two helpers behind that contract:

- `_ref_problems(repo, case_dirs)` -> list of human-readable problem lines.
- `_ensure_scenario_refs(repo, case_dirs)` -> raises `click.ClickException`
  before the run when a ref is unresolvable (and is a quiet no-op when `--repo`
  is not a git checkout at all).

They run against throwaway git repos. The direct-invocation block at the bottom
bypasses pytest's teardown (this environment's safe-delete guard hangs on temp
dir cleanup); the `test_*` wrappers keep the file collectable by pytest too.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from click.exceptions import ClickException

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cli.specproof.commands.eval import (  # noqa: E402
    _ensure_scenario_refs,
    _ref_problems,
)


def _make_git_repo(repo: Path) -> None:
    """A git repo whose `base` and `head-v1` refs both resolve."""
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "t@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "tester"], check=True
    )
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "init"], check=True
    )
    subprocess.run(["git", "-C", str(repo), "branch", "base"], check=True)
    subprocess.run(["git", "-C", str(repo), "branch", "head-v1"], check=True)


def _mk_case(cases: Path, name: str, *, scenario: str | None, spec: bool = True) -> Path:
    case = cases / name
    case.mkdir(parents=True, exist_ok=True)
    if spec:
        (case / "spec.md").write_text("# spec\n", encoding="utf-8")
    if scenario is not None:
        (case / "scenario.json").write_text(scenario, encoding="utf-8")
    return case


# --- _ref_problems ---------------------------------------------------------


def _ref_problems_empty_when_refs_resolve(d: Path, mp) -> None:
    repo = d / "repo"
    _make_git_repo(repo)
    cases = d / "cases"
    _mk_case(cases, "ok", scenario='{"base_ref": "base", "head_ref": "head-v1"}')
    problems = _ref_problems(str(repo), [cases / "ok"])
    assert problems == [], problems


def _ref_problems_reports_missing_ref(d: Path, mp) -> None:
    repo = d / "repo"
    _make_git_repo(repo)
    cases = d / "cases"
    _mk_case(cases, "bad", scenario='{"base_ref": "does-not-exist"}')
    problems = _ref_problems(str(repo), [cases / "bad"])
    assert len(problems) == 1, problems
    assert "bad" in problems[0]
    assert "base_ref" in problems[0]
    assert "does-not-exist" in problems[0]


def _ref_problems_skips_cases_without_spec(d: Path, mp) -> None:
    repo = d / "repo"
    _make_git_repo(repo)
    cases = d / "cases"
    # No spec.md -> the loop skips it, so even a bogus ref is not reported.
    _mk_case(cases, "nospec", scenario='{"base_ref": "does-not-exist"}', spec=False)
    problems = _ref_problems(str(repo), [cases / "nospec"])
    assert problems == [], problems


def _ref_problems_malformed_scenario_is_not_a_ref_problem(d: Path, mp) -> None:
    repo = d / "repo"
    _make_git_repo(repo)
    cases = d / "cases"
    # Broken JSON -> scenario parsed as {} -> defaults (base/head-v1) which resolve.
    _mk_case(cases, "broken", scenario="{not valid json")
    problems = _ref_problems(str(repo), [cases / "broken"])
    assert problems == [], problems


def _ref_problems_default_refs_resolve_without_scenario(d: Path, mp) -> None:
    repo = d / "repo"
    _make_git_repo(repo)
    cases = d / "cases"
    _mk_case(cases, "nodefault", scenario=None)  # uses base / head-v1 defaults
    problems = _ref_problems(str(repo), [cases / "nodefault"])
    assert problems == [], problems


# --- _ensure_scenario_refs -------------------------------------------------


def _ensure_quiet_when_non_git_repo(d: Path, mp) -> None:
    repo = d / "repo"
    repo.mkdir(parents=True, exist_ok=True)  # NOT a git repo
    cases = d / "cases"
    _mk_case(cases, "bad", scenario='{"base_ref": "does-not-exist"}')
    # Must not raise even though the ref is unresolvable: --repo is not git,
    # the pipeline will report the real problem instead.
    _ensure_scenario_refs(str(repo), [cases / "bad"])


def _ensure_quiet_when_all_refs_resolve(d: Path, mp) -> None:
    repo = d / "repo"
    _make_git_repo(repo)
    cases = d / "cases"
    _mk_case(cases, "ok", scenario='{"base_ref": "base", "head_ref": "head-v1"}')
    _ensure_scenario_refs(str(repo), [cases / "ok"])


def _ensure_raises_on_missing_ref(d: Path, mp) -> None:
    repo = d / "repo"
    _make_git_repo(repo)
    cases = d / "cases"
    _mk_case(cases, "bad", scenario='{"base_ref": "does-not-exist"}')
    raised = False
    try:
        _ensure_scenario_refs(str(repo), [cases / "bad"])
    except ClickException as exc:
        raised = True
        assert "bad" in str(exc)
        assert "does-not-exist" in str(exc)
    assert raised, "expected ClickException for unresolvable ref"


# --- pytest collection wrappers -------------------------------------------


def test_ref_problems_empty_when_refs_resolve(tmp_path, monkeypatch):
    _ref_problems_empty_when_refs_resolve(tmp_path, monkeypatch)


def test_ref_problems_reports_missing_ref(tmp_path, monkeypatch):
    _ref_problems_reports_missing_ref(tmp_path, monkeypatch)


def test_ref_problems_skips_cases_without_spec(tmp_path, monkeypatch):
    _ref_problems_skips_cases_without_spec(tmp_path, monkeypatch)


def test_ref_problems_malformed_scenario_is_not_a_ref_problem(tmp_path, monkeypatch):
    _ref_problems_malformed_scenario_is_not_a_ref_problem(tmp_path, monkeypatch)


def test_ref_problems_default_refs_resolve_without_scenario(tmp_path, monkeypatch):
    _ref_problems_default_refs_resolve_without_scenario(tmp_path, monkeypatch)


def test_ensure_quiet_when_non_git_repo(tmp_path, monkeypatch):
    _ensure_quiet_when_non_git_repo(tmp_path, monkeypatch)


def test_ensure_quiet_when_all_refs_resolve(tmp_path, monkeypatch):
    _ensure_quiet_when_all_refs_resolve(tmp_path, monkeypatch)


def test_ensure_raises_on_missing_ref(tmp_path, monkeypatch):
    _ensure_raises_on_missing_ref(tmp_path, monkeypatch)


if __name__ == "__main__":
    # Direct invocation: bypasses pytest teardown (safe-delete guard hangs here).
    from _pytest.monkeypatch import MonkeyPatch

    tests = [
        _ref_problems_empty_when_refs_resolve,
        _ref_problems_reports_missing_ref,
        _ref_problems_skips_cases_without_spec,
        _ref_problems_malformed_scenario_is_not_a_ref_problem,
        _ref_problems_default_refs_resolve_without_scenario,
        _ensure_quiet_when_non_git_repo,
        _ensure_quiet_when_all_refs_resolve,
        _ensure_raises_on_missing_ref,
    ]
    failures = 0
    for fn in tests:
        base = Path(tempfile.mkdtemp(prefix="refpre-"))
        mp = MonkeyPatch()
        try:
            fn(base, mp)
            print("PASS", fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print("FAIL", fn.__name__, "->", type(exc).__name__, str(exc)[:300])
        finally:
            mp.undo()
        # deliberately NOT deleting base: safe-delete guard hangs on bulk delete
    print("RESULT:", "ALL PASS" if failures == 0 else f"{failures} FAILED")
    sys.exit(1 if failures else 0)
