"""The evaluation says where it writes (#370).

An evaluation is a MEASUREMENT: what it writes (object-metadata rows
keyed ``eval-*``) belongs in the TEST schema, not in the product's.
When a test schema is configured and reachable, that is where the rows
go; otherwise the ambient schema is used — and the run says which one
it used, because a run that writes into the product's tables without
saying so is a hygiene problem nobody sees.

The choice is a pure function of (environment, probe) so it can be
pinned without a database.
"""

from __future__ import annotations

from typing import Any

from cli.specproof.commands.eval import _choose_write_schema


def _probe(reachable: set[str]) -> Any:
    def _probe_one(database: str) -> bool:
        return database in reachable

    return _probe_one


def test_a_configured_and_reachable_test_schema_is_used() -> None:
    schema, reason = _choose_write_schema(
        {
            "MYSQL_DATABASE": "specproof_phase0",
            "SPECPROOF_TEST_MYSQL_DATABASE": "specproof_test",
        },
        _probe({"specproof_test"}),
    )
    assert schema == "specproof_test"
    assert "TEST schema" in reason


def test_without_a_test_schema_the_ambient_one_is_used_and_said() -> None:
    schema, reason = _choose_write_schema(
        {"MYSQL_DATABASE": "specproof_phase0"}, _probe(set()),
    )
    assert schema == "specproof_phase0"
    assert "no test schema is configured" in reason


def test_a_configured_but_unreachable_test_schema_is_not_used() -> None:
    """A run that cannot write anywhere must say so — not point at a
    schema it cannot reach."""
    schema, reason = _choose_write_schema(
        {
            "MYSQL_DATABASE": "specproof_phase0",
            "SPECPROOF_TEST_MYSQL_DATABASE": "specproof_test",
        },
        _probe(set()),
    )
    assert schema == "specproof_phase0"
    assert "NOT reachable" in reason


def test_the_ambient_schema_is_never_probed_as_its_own_test_schema() -> None:
    """Naming the same schema twice is not a test schema — and probing
    it must not happen."""
    probed: list[str] = []

    def _probe_one(database: str) -> bool:
        probed.append(database)
        return True

    schema, reason = _choose_write_schema(
        {
            "MYSQL_DATABASE": "specproof_test",
            "SPECPROOF_TEST_MYSQL_DATABASE": "specproof_test",
        },
        _probe_one,
    )
    assert schema == "specproof_test"
    assert probed == []
    assert "no test schema is configured" in reason
