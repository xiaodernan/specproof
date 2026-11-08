"""Offline contract tests for scripts/backup_stores.py.

These tests never touch docker, MySQL or MongoDB. They lock the safety
properties of the drill tool:
  * scratch names are fixed; the product database is refused everywhere;
  * the dump/restore command lines carry the flags the drill relies on;
  * count-parsing and count-comparison logic behaves on synthetic data;
  * the CLI refuses the two dangerous invocations before any subprocess runs.
"""

import subprocess

import pytest

from scripts import backup_stores


class TestScratchNameGuard:
    def test_allows_the_two_fixed_scratch_names(self):
        assert backup_stores.assert_scratch_allowed("specproof_restore_drill", "mysql")
        assert backup_stores.assert_scratch_allowed("specproof_drill_scratch", "mongo")

    @pytest.mark.parametrize("kind,name", [
        ("mysql", "specproof_phase0"),
        ("mysql", "specproof_test"),
        ("mysql", "mysql"),
        ("mysql", "tmp_backup_probe"),
        ("mongo", "specproof_phase0"),
        ("mongo", "admin"),
        ("mongo", "drill_docs"),
    ])
    def test_refuses_everything_else(self, kind, name):
        with pytest.raises(ValueError):
            backup_stores.assert_scratch_allowed(name, kind)


class TestCommandLines:
    def test_mysql_dump_pins_single_transaction_and_db(self):
        argv = backup_stores.build_mysql_dump_argv("specproof_test")
        joined = " ".join(argv)
        assert "mysqldump" in argv
        assert "--single-transaction" in argv
        assert "--routines" in argv and "--triggers" in argv
        assert "--set-gtid-purged=OFF" in argv
        assert argv[-1] == "specproof_test"
        assert "specproof_phase0" not in joined

    def test_mysql_restore_invokes_mysql_client_with_db(self):
        argv = backup_stores.build_mysql_restore_argv("specproof_restore_drill")
        assert argv[:3] == ["docker", "exec", "-i"]
        assert argv[-1] == "specproof_restore_drill"

    def test_mongo_dump_and_restore_pin_archive_gzip(self):
        dump = backup_stores.build_mongo_dump_argv("specproof_drill_scratch")
        assert dump[-4:] == ["--db", "specproof_drill_scratch", "--archive", "--gzip"]
        restore = backup_stores.build_mongo_restore_argv()
        assert "--archive" in restore and "--gzip" in restore

    def test_product_backup_never_offered_as_drill_source(self):
        # main() refuses --source specproof_phase0 before any subprocess call.
        result = backup_stores.main(["--stores", "mysql", "--source", "specproof_phase0"])
        assert result == 2


class TestCountParsing:
    def test_parse_mysql_counts_from_stub_output(self):
        text = "audit_logs 5174\noutbox 2\nschema_migrations 17\n\n"
        assert backup_stores.parse_mysql_counts(text) == {
            "audit_logs": 5174,
            "outbox": 2,
            "schema_migrations": 17,
        }

    def test_compare_count_maps_detects_mismatch_and_missing_table(self):
        src = {"a": 1, "b": 2}
        restored_ok = {"a": 1, "b": 2}
        restored_bad = {"a": 1, "b": 3, "c": 1}
        assert backup_stores.compare_count_maps(src, restored_ok) == []
        problems = backup_stores.compare_count_maps(src, restored_bad)
        assert any("b" in p for p in problems)
        assert any("c" in p for p in problems)


class TestCliRefusals:
    def test_scratch_with_both_stores_is_refused(self):
        result = backup_stores.main(["--stores", "both", "--scratch", "specproof_restore_drill"])
        assert result == 2

    def test_no_subprocess_is_spawned_for_refused_invocations(self, monkeypatch):
        called: list[list[str]] = []

        def fake_run(args, *a, **kw):
            called.append(list(args))
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert backup_stores.main(["--source", "specproof_phase0"]) == 2
        assert backup_stores.main(["--stores", "both", "--scratch", "x"]) == 2
        assert called == []
