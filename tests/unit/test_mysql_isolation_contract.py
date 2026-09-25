"""#75 — the MySQL isolation contract is a decision, so test the decision.

`tests/conftest.py` now chooses which schema DB-backed tests may write, applies
that choice to the environment, and reports what it found. Every claim here is
about that behaviour, not about the shape of the code:

  * the product schema is never the write target, and a redirect actually
    reaches `os.environ` (a decision nobody applies is not a decision);
  * "no MySQL" is reported as `unreachable`, not as `isolated`;
  * a row count that could not be read stays None — reporting an unreadable
    count as 0 would turn a failure into a clean bill of health;
  * the session-finish line calls a breach a breach.

The module under test lives in conftest because it must run before any test
writes anything; `tests/` is a package, so it is importable as
`tests.conftest`.
"""

from __future__ import annotations

import pytest

import tests.conftest as contract


@pytest.fixture
def mysql_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Start every case from a plain 'developer machine' environment."""
    monkeypatch.delenv("MYSQL_DATABASE", raising=False)
    monkeypatch.delenv("SPECPROOF_TEST_MYSQL_DATABASE", raising=False)
    return monkeypatch


class _Recorder:
    def __init__(self, answers: dict[str, str]) -> None:
        self.answers = answers
        self.calls: list[str] = []

    def __call__(self, database: str) -> str:
        self.calls.append(database)
        return self.answers[database]


class _FakeCursor:
    def __init__(self, owner: _FakeConnection) -> None:
        self.owner = owner

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.owner.executed.append((" ".join(sql.split()), params))

    def fetchone(self) -> object:
        return self.owner.row


class _FakeConnection:
    def __init__(self, row: object) -> None:
        self.executed: list[tuple[str, object]] = []
        self.row = row
        self.closed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def close(self) -> None:
        self.closed = True


class TestTargetIsNeverTheProductSchema:
    def test_default_target_is_a_non_product_name(self) -> None:
        assert contract.DEFAULT_TEST_MYSQL_DATABASE != contract.PRODUCT_MYSQL_DATABASE

    def test_environment_may_not_name_the_product_schema_as_the_test_one(
        self, mysql_env: pytest.MonkeyPatch
    ) -> None:
        mysql_env.setenv("SPECPROOF_TEST_MYSQL_DATABASE", contract.PRODUCT_MYSQL_DATABASE)
        with pytest.raises(RuntimeError, match="non-product"):
            contract.chosen_test_database()

    def test_blank_target_is_refused_rather_than_collided(
        self, mysql_env: pytest.MonkeyPatch
    ) -> None:
        mysql_env.setenv("SPECPROOF_TEST_MYSQL_DATABASE", "   ")
        with pytest.raises(RuntimeError, match="non-product"):
            contract.chosen_test_database()


class TestEnforceDecides:
    def test_redirect_is_applied_to_the_environment(
        self, mysql_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(contract, "probe_database", _Recorder({"specproof_test": "ready"}))
        state, database = contract.enforce_test_database()
        assert (state, database) == ("redirected", "specproof_test")
        assert contract.os.environ["MYSQL_DATABASE"] == "specproof_test"

    def test_product_schema_alone_blocks_instead_of_being_written(
        self, mysql_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorder = _Recorder(
            {"specproof_test": "absent", contract.PRODUCT_MYSQL_DATABASE: "ready"}
        )
        monkeypatch.setattr(contract, "probe_database", recorder)
        state, _ = contract.enforce_test_database()
        assert state == "blocked"
        assert "MYSQL_DATABASE" not in contract.os.environ, (
            "pointing the environment at the product schema 'because we could' is "
            "exactly what this contract forbids"
        )

    def test_no_answer_is_unreachable_not_isolated(
        self, mysql_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            contract,
            "probe_database",
            _Recorder(
                {
                    "specproof_test": "unreachable",
                    contract.PRODUCT_MYSQL_DATABASE: "unreachable",
                }
            ),
        )
        state, database = contract.enforce_test_database()
        assert state == "unreachable"
        assert database == contract.PRODUCT_MYSQL_DATABASE
        assert "MYSQL_DATABASE" not in contract.os.environ, (
            "no MySQL is a coverage fact; rewriting the environment here would "
            "claim an isolation that never happened"
        )

    def test_an_already_dedicated_environment_is_left_alone(
        self, mysql_env: pytest.MonkeyPatch, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mysql_env.setenv("MYSQL_DATABASE", "ci_scratch")
        recorder = _Recorder({})
        monkeypatch.setattr(contract, "probe_database", recorder)
        state, database = contract.enforce_test_database()
        assert (state, database) == ("dedicated", "ci_scratch")
        assert recorder.calls == [], "the operator named a schema; do not second-guess it"


class TestProbeIsReadOnlyAndSpecific:
    def test_absent_and_unreachable_are_different_facts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[str] = []

        def fake_connect(database: str, timeout: int) -> object:
            seen.append(database)
            if database == "exists_here":
                return _FakeConnection(None)

            class _MySQLError(Exception):
                args = (1049, "Unknown database")

            raise _MySQLError()

        monkeypatch.setattr(contract, "_connect", fake_connect)
        assert contract.probe_database("exists_here") == "ready"
        assert contract.probe_database("nope") == "absent"
        assert seen == ["exists_here", "nope"]

    def test_a_server_that_refuses_is_not_reported_as_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_connect(database: str, timeout: int) -> object:
            class _MySQLError(Exception):
                args = (2003, "Can't connect to MySQL server")

            raise _MySQLError()

        monkeypatch.setattr(contract, "_connect", fake_connect)
        assert contract.probe_database("specproof_test") == "unreachable"


class TestResidueCountIsMeasured:
    def test_count_asks_the_product_schema_for_test_shaped_rows(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conn = _FakeConnection({"n": 42})
        targets: list[str] = []

        def fake_connect(database: str, timeout: int) -> _FakeConnection:
            targets.append(database)
            return conn

        monkeypatch.setattr(contract, "_connect", fake_connect)
        assert contract.count_product_test_rows() == 42
        assert targets == [contract.PRODUCT_MYSQL_DATABASE]
        sql, params = conn.executed[0]
        assert "repo_path LIKE %s" in sql
        assert params == (contract.TEST_REPO_PATH_PATTERN,)
        assert conn.closed is True

    def test_an_unreadable_count_stays_unknown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_connect(database: str, timeout: int) -> object:
            raise OSError("socket closed")

        monkeypatch.setattr(contract, "_connect", fake_connect)
        assert contract.count_product_test_rows() is None, (
            "0 would read as 'no test rows', which is the opposite of 'I could "
            "not look'"
        )

    def test_a_row_that_is_not_a_mapping_still_counts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conn = _FakeConnection((7,))
        monkeypatch.setattr(contract, "_connect", lambda db, t: conn)
        assert contract.count_product_test_rows() == 7


class TestWhatTheSessionTellsTheOperator:
    def test_header_states_the_state_and_the_measured_number(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            contract, "MYSQL_ISOLATION", ("redirected", "specproof_test", 177)
        )
        header = contract.pytest_report_header(None)
        assert "redirected" in header and "specproof_test" in header and "177" in header

    def test_header_says_so_when_the_guard_skipped_everything(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(contract, "MYSQL_ISOLATION", ("unresolved", "", None))
        assert "not evaluated" in contract.pytest_report_header(None)

    def test_moved_rows_are_reported_as_a_breach(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            contract, "MYSQL_ISOLATION", ("redirected", "specproof_test", 100)
        )
        monkeypatch.setattr(contract, "count_product_test_rows", lambda: 103)
        contract.pytest_sessionfinish(None, 0)
        out = capsys.readouterr().out
        assert "ISOLATION BREACH" in out and "3" in out

    def test_unchanged_rows_are_reported_as_clean(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            contract, "MYSQL_ISOLATION", ("dedicated", "ci_scratch", 100)
        )
        monkeypatch.setattr(contract, "count_product_test_rows", lambda: 100)
        contract.pytest_sessionfinish(None, 0)
        out = capsys.readouterr().out
        assert "no test row landed in the product schema" in out

    def test_an_unknown_count_is_not_reported_as_clean(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(
            contract, "MYSQL_ISOLATION", ("redirected", "specproof_test", None)
        )

        def explode() -> None:
            raise AssertionError("must not re-read when the baseline is unknown")

        monkeypatch.setattr(contract, "count_product_test_rows", explode)
        contract.pytest_sessionfinish(None, 0)
        assert capsys.readouterr().out == ""

    def test_the_blocked_message_names_the_remedy(self) -> None:
        assert contract.PRODUCT_MYSQL_DATABASE in contract.BLOCKED_MESSAGE
        assert "create_test_database.ps1" in contract.BLOCKED_MESSAGE


class TestSchemaPreparation:
    def test_only_a_writable_target_is_touched(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import storage.mysql as mysql_module

        calls: list[str] = []

        class FakeStore:
            def __init__(self) -> None:
                pass

            def ensure_tables(self) -> None:
                calls.append("ensure_tables")

        monkeypatch.setattr(mysql_module, "MySQLStore", FakeStore)
        contract.prepare_test_schema("unreachable", contract.PRODUCT_MYSQL_DATABASE)
        assert calls == [], (
            "migrating the PRODUCT schema from a test session is the very thing "
            "#75 exists to stop"
        )
        contract.prepare_test_schema("redirected", "specproof_test")
        assert calls == ["ensure_tables"]

    def test_a_schema_that_cannot_be_prepared_is_a_hard_stop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import storage.mysql as mysql_module

        class BrokenStore:
            def ensure_tables(self) -> None:
                raise RuntimeError("access denied")

        monkeypatch.setattr(mysql_module, "MySQLStore", BrokenStore)
        # The retry sleeps 5s/10s/15s; the test asserts the verdict, not the clock.
        monkeypatch.setattr("time.sleep", lambda seconds: None)
        with pytest.raises(RuntimeError, match="not usable"):
            contract.prepare_test_schema("redirected", "specproof_test")


def test_the_contract_runs_before_any_test_writes() -> None:
    """_apply_mysql_isolation must be wired into pytest_configure, not a fixture.

    A fixture can be bypassed (and ordering with autouse fixtures is not a
    guarantee worth trusting); configure-time is the only point before which no
    test has run.
    """
    import inspect

    source = inspect.getsource(contract.pytest_configure)
    assert "_apply_mysql_isolation()" in source
