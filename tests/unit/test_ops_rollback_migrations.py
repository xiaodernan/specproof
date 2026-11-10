"""Tests for `specproof ops rollback-migrations` CLI subcommand.

Safety-critical: only specproof_test* databases can be touched without
--i-am-sure-rolling-back. Dry-run is a pure read, so we exercise it with
a real MySQL connection redirected to specproof_test.
"""

from __future__ import annotations

from click.testing import CliRunner

from cli.specproof.commands.ops import ops_cmd

MYSQL_TEST_DB = "specproof_test"


def _dry_run_against_real(to_version: int) -> str:
    runner = CliRunner()
    return runner.invoke(
        ops_cmd,
        ["rollback-migrations", "--to", str(to_version), "--dry-run"],
        env={"MYSQL_DATABASE": MYSQL_TEST_DB},
    )


def test_dry_run_against_specproof_test_prints_plan_and_exits_zero() -> None:
    """The plan for rolling back the last three migrations."""
    result = _dry_run_against_real(14)
    assert result.exit_code == 0, result.output
    assert "[dry] rollback 0017" in result.output
    assert "[dry] rollback 0016" in result.output
    assert "[dry] rollback 0015" in result.output


def test_dry_run_to_zero_lists_every_reversible_version() -> None:
    """Migrations 0017..0005 all have down-files; the command reports them."""
    result = _dry_run_against_real(4)
    assert result.exit_code == 0, result.output
    for v in ("0017", "0016", "0015", "0010", "0005"):
        assert f"[dry] rollback {v}" in result.output, result.output


def test_dry_run_target_below_oldest_reversible_refuses() -> None:
    """Undo below the oldest down-sql boundary must refuse — never silently skip."""
    runner = CliRunner()
    result = runner.invoke(
        ops_cmd,
        ["rollback-migrations", "--to", "0", "--dry-run"],
        env={"MYSQL_DATABASE": MYSQL_TEST_DB},
    )
    assert result.exit_code != 0


def test_non_test_database_refuses_live_but_dry_run_is_allowed() -> None:
    """Production-named MySQL is refused live; dry-run is a pure read."""
    runner = CliRunner()
    result_dry = runner.invoke(
        ops_cmd,
        ["rollback-migrations", "--to", "14", "--dry-run"],
        env={"MYSQL_DATABASE": "specproof_phase0"},
    )
    assert result_dry.exit_code == 0, result_dry.output

    result_live = runner.invoke(
        ops_cmd,
        ["rollback-migrations", "--to", "14"],
        env={"MYSQL_DATABASE": "specproof_phase0"},
    )
    assert result_live.exit_code != 0
    # Combined command output and exception both carry the refusal wording
    combined = (result_live.output or "") + (
        str(result_live.exception) if result_live.exception else ""
    )
    assert "specproof_test" in combined or "refusing" in combined.lower()
