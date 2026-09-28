"""#120 — the run must say which tests need MySQL, and that block must not lie.

The full merge gate swings between 1293s and 1704s on this machine, so the total
alone cannot decide whether the change is load or structure. `tests/conftest.py`
now prints the MySQL-backed test files it finds in the source, which of them ran,
and what they cost. Every claim below is about that behaviour:

  * the census is a scan of the real tree, and each name it returns really does
    build a store — it cannot be right by accident;
  * the scan also works on a tree it has never seen, because a scan that reads
    nothing looks exactly like a scan that finds nothing;
  * a session where none of them ran says so, and an empty census calls itself
    blind instead of printing the same blank screen as a clean run.
"""

from __future__ import annotations

from pathlib import Path

import tests.conftest as contract


def test_the_census_finds_the_files_this_repo_documents_as_db_backed() -> None:
    census = contract.mysql_backed_test_files()
    assert census, "the scan found no MySQL-backed test file at all — it is blind"
    assert len(census) < 60, f"{len(census)} files matched: the pattern is matching too much"
    for documented in ("tests/unit/test_storage.py", "tests/unit/test_job_state_machine.py"):
        assert documented in census, (
            f"{documented} builds a MySQLStore, so a census that misses it is describing "
            "a different codebase than the one that runs"
        )


def test_every_name_the_census_returns_really_builds_a_store() -> None:
    for name in contract.mysql_backed_test_files():
        text = (contract._PROJECT_ROOT / name).read_text(encoding="utf-8")
        assert "MySQLStore(" in text or "MySQLConfig(" in text, (
            f"{name} was returned by the census but contains no MySQL construction — "
            "the scan is matching something other than what it claims"
        )


def test_the_scan_reads_a_tree_it_has_never_seen(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_uses_store.py").write_text("store = MySQLStore()\n", encoding="utf-8")
    (tests_dir / "test_uses_config.py").write_text("cfg = MySQLConfig()\n", encoding="utf-8")
    (tests_dir / "test_plain.py").write_text("def test_x():\n    assert 1\n", encoding="utf-8")
    assert contract.mysql_backed_test_files(root=tests_dir) == [
        "tests/test_uses_config.py",
        "tests/test_uses_store.py",
    ]


def test_a_session_where_none_of_them_ran_says_so() -> None:
    lines = contract.format_mysql_usage(["tests/unit/a.py", "tests/unit/b.py"], {}, {}, 100.0)
    assert any("2" in line for line in lines), "the census size must be on screen"
    assert any("none of them ran" in line for line in lines)
    assert any("0 of 2" in line for line in lines)


def test_a_fake_store_is_not_a_mysql_dependency(tmp_path: Path) -> None:
    """`FakeMySQLStore()` needs no database, and the word boundary keeps it out.

    Measured at #120: three unit files build a fake (`test_api_errors.py`,
    `test_api_governance.py`, `test_envelope_retryable.py`) and none of them needs
    MySQL. A census that counted them would answer "who needs MySQL" with three
    files that deliberately do not, so the boundary is a claim, not a detail.
    """
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_fake.py").write_text("return FakeMySQLStore()\n", encoding="utf-8")
    assert contract.mysql_backed_test_files(root=tests_dir) == []
    for name in (
        "tests/unit/test_api_errors.py",
        "tests/unit/test_api_governance.py",
        "tests/unit/test_envelope_retryable.py",
    ):
        assert name not in contract.mysql_backed_test_files(), (
            f"{name} builds a FakeMySQLStore — it does not need MySQL"
        )


def test_an_empty_census_calls_itself_blind_instead_of_clean() -> None:
    lines = contract.format_mysql_usage([], {}, {}, 100.0)
    assert any("blind" in line for line in lines), (
        "an empty scan and a session with no DB-backed tests must not print the same thing"
    )


def test_the_slowest_mysql_file_is_listed_first_and_subtotaled() -> None:
    lines = contract.format_mysql_usage(
        ["tests/unit/slow.py", "tests/unit/fast.py"],
        {"tests/unit/slow.py": 30.0, "tests/unit/fast.py": 10.0},
        {"tests/unit/slow.py": 3, "tests/unit/fast.py": 1},
        200.0,
    )
    body = [line for line in lines if line.startswith("  ")]
    assert body[0].startswith("  tests/unit/slow.py")
    assert "40.0s of 200.0s" in body[-1]
    assert "20%" in body[-1]
    assert "2 of 2 census files ran" in body[-1]
