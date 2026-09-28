"""#126 — a refusal must say who chose the schema, not just what it was.

The `--collect-only` red on CI printed `MYSQL_DATABASE='specproof_test'` and
stopped there, which invited the wrong conclusion: the workflow file names no
MySQL at all, so that value was not "the runner's" — the parent conftest wrote
it into `os.environ` when it decided `redirected`, and the child inherited it.
Reading the environment cannot separate those two facts, because the rewrite is
indistinguishable from an inherited setting.

So the rewrite now leaves a trail: `enforce_test_database()` records the value
it replaced in `SPECPROOF_MYSQL_DATABASE_REWRITTEN_FROM`, and the guard captures
`(MYSQL_DATABASE, that variable)` at its own entry — before this process can
have changed either. `mysql_database_provenance()` turns the pair into the
sentence that goes into the session-ending refusal and into the #53 tagging
assertion.

Every case here drives the real guard (or the real decision function), not a
hand-set record: a provenance the test wrote itself would prove nothing about
where production reads it.
"""
from __future__ import annotations

import os

import pytest
from _pytest.outcomes import Exit

import tests.conftest as contract


class _Config:
    """Answers only the option the guard actually asks for.

    pytest's `getoption` returns a default silently for an unknown name, so a
    permissive stub would hide a wrong spelling instead of reporting it.
    """

    def __init__(self, collectonly: bool = False) -> None:
        self._values = {"collectonly": collectonly}

    def getoption(self, name: str, default: object = None) -> object:
        if name not in self._values:
            raise ValueError(f"no option named {name!r}")
        return self._values[name]


@pytest.fixture
def guard_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """A known starting environment and a guard that touches no server."""
    monkeypatch.delenv("MYSQL_DATABASE", raising=False)
    monkeypatch.delenv(contract.MYSQL_DATABASE_REWRITTEN_FROM, raising=False)
    monkeypatch.setattr(contract, "MYSQL_DATABASE_HANDED_TO", (None, None))
    monkeypatch.setattr(contract, "MYSQL_ISOLATION", ("unresolved", "", None))
    monkeypatch.setattr(contract, "prepare_test_schema", lambda state, db: None)
    monkeypatch.setattr(contract, "count_product_test_rows", lambda: None)
    # Nothing in these cases is allowed to reach for a real server: an answer of
    # "ready" here would make the guard rewrite the session's own environment.
    monkeypatch.setattr(contract, "probe_database", lambda database: "unreachable")
    return monkeypatch


def _run_guard(guard_env: pytest.MonkeyPatch, **overrides: str) -> str:
    for key, value in overrides.items():
        if value == "<unset>":
            guard_env.delenv(key, raising=False)
        else:
            guard_env.setenv(key, value)
    contract._apply_mysql_isolation(_Config())
    return contract.mysql_database_provenance()


def test_an_unset_environment_is_reported_as_the_default_not_as_a_rewrite(
    guard_env: pytest.MonkeyPatch,
) -> None:
    sentence = _run_guard(guard_env, MYSQL_DATABASE="<unset>")
    assert contract.PRODUCT_MYSQL_DATABASE in sentence, (
        "an unset MYSQL_DATABASE is the case #79 exists for — the sentence must "
        f"name the schema the guard falls back to; got {sentence}"
    )
    assert "no ancestor conftest rewrote it" in sentence, (
        f"nothing rewrote anything here; got {sentence}"
    )


def test_a_dedicated_name_from_the_runner_says_the_runner_handed_it_over(
    guard_env: pytest.MonkeyPatch,
) -> None:
    sentence = _run_guard(guard_env, MYSQL_DATABASE="ci_scratch")
    assert "'ci_scratch'" in sentence and "as this process was handed it" in sentence, (
        f"got {sentence}"
    )
    assert "rewrote it from" not in sentence, (
        f"the marker is absent, so nobody rewrote anything; got {sentence}"
    )


def test_a_child_of_a_redirecting_conftest_is_told_who_set_its_schema(
    guard_env: pytest.MonkeyPatch,
) -> None:
    sentence = _run_guard(
        guard_env,
        MYSQL_DATABASE="specproof_test",
        **{contract.MYSQL_DATABASE_REWRITTEN_FROM: contract.PRODUCT_MYSQL_DATABASE},
    )
    assert "'specproof_test'" in sentence, f"got {sentence}"
    assert (
        "an ancestor conftest rewrote it from "
        f"{contract.PRODUCT_MYSQL_DATABASE!r}" in sentence
    ), (
        "this is exactly the CI question that the old message could not answer — "
        f"got {sentence}"
    )


def test_the_process_that_rewrites_the_schema_leaves_the_trail_it_handed_over(
    guard_env: pytest.MonkeyPatch,
) -> None:
    """The marker is written at the rewrite itself, not by whoever reads it."""
    guard_env.setenv("MYSQL_DATABASE", contract.PRODUCT_MYSQL_DATABASE)
    guard_env.setenv("SPECPROOF_TEST_MYSQL_DATABASE", "specproof_test")
    guard_env.setattr(contract, "probe_database", lambda database: "ready")

    state, database = contract.enforce_test_database()

    assert (state, database) == ("redirected", "specproof_test")
    assert os.environ["MYSQL_DATABASE"] == "specproof_test", (
        "the redirect has to reach the environment or it is not a redirect"
    )
    assert (
        os.environ.get(contract.MYSQL_DATABASE_REWRITTEN_FROM)
        == contract.PRODUCT_MYSQL_DATABASE
    ), (
        "a child must be able to say which value was replaced; without this the "
        "provenance sentence is decoration (got "
        f"{os.environ.get(contract.MYSQL_DATABASE_REWRITTEN_FROM)!r})"
    )


def test_the_session_ending_refusal_carries_the_provenance(
    guard_env: pytest.MonkeyPatch,
) -> None:
    """The message a contributor reads at the failure must answer 'who set it'."""

    def unusable() -> tuple[str, str]:
        raise RuntimeError("test schema 'specproof_test' is not usable")

    guard_env.setenv("MYSQL_DATABASE", "specproof_test")
    guard_env.setenv(
        contract.MYSQL_DATABASE_REWRITTEN_FROM, contract.PRODUCT_MYSQL_DATABASE
    )
    guard_env.setattr(contract, "enforce_test_database", unusable)

    with pytest.raises(Exit) as raised:
        contract._apply_mysql_isolation(_Config())

    message = str(raised.value)
    assert "MySQL test isolation check failed" in message
    assert "an ancestor conftest rewrote it from" in message, (
        f"the refusal still cannot say who chose the schema; got {message!r}"
    )
