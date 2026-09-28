"""#126 — answering "which tests exist" must not need a live MySQL.

Measured, not theorised. ``tests/conftest.py::pytest_configure`` is a load-time
guard that every pytest process in this repo runs, including the
``--collect-only`` children the #53 tagging lock spawns. On CI the parent
guard rewrites ``os.environ["MYSQL_DATABASE"]`` to the dedicated test schema
(the ``redirected`` branch of ``enforce_test_database``), so a child inherits
``state == "dedicated"`` — the one branch that calls ``prepare_test_schema()``,
which retries ``ensure_tables()`` three times and then ends the whole session
with ``pytest.exit``. Two ``test_slow_marker_tagging`` reds printed exactly that
body: ``MySQL test isolation check failed: test schema 'specproof_test' is not
usable: OperationalError(2003, ... Connection refused)``.

The same refusal is reproducible on a machine with no MySQL at all, so the gate
does not have to wait for CI:

    MYSQL_DATABASE=specproof_test MYSQL_HOST=127.0.0.1 MYSQL_PORT=3399 \\
        pytest -o addopts= tests/unit/test_baseline.py --collect-only   # exit 1

A collection executes no fixture and writes no row, so the exemption is cut
narrow: only ``prepare_test_schema`` is skipped, and nothing about the isolation
decision itself — it still runs, and the fail-closed ``blocked`` verdict still
ends the session (that verdict is about configuration, not connectivity).

Cost, measured with this file green: ``4 passed in 8.33s``, of which the one
child is 7.83s (the same child standalone is 9s warm; 43s cold, right after an
edit). That is why the module is NOT in ``SLOW_TEST_MODULES`` — it belongs in the
contributor fast loop, unlike the modules it protects.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from _pytest.outcomes import Exit

import tests.conftest as contract

REPO_ROOT = Path(__file__).resolve().parents[2]

#: A schema name that is already dedicated, so ``enforce_test_database`` answers
#: without probing, on a port nothing listens on. This is the environment a CI
#: child inherits after the parent redirected it — minus the server.
DEAD_DB_ENV = {
    "MYSQL_DATABASE": "specproof_test",
    "MYSQL_HOST": "127.0.0.1",
    "MYSQL_PORT": "3399",
}

REFUSAL = "MySQL test isolation check failed"


class _Config:
    """pytest's option table, mirrored rather than improvised.

    ``Config.getoption(name, default=...)`` returns the default silently for a
    name it does not know, so a stub that answered any spelling asked of it
    would let a wrong option name pass here and fail in production. This stub
    knows only the spellings measured against the installed pytest (9.1.1: the
    dest is ``collectonly``, and ``--collect-only`` resolves through pytest's
    own alias table) and refuses anything else.
    """

    _ALIASES = {"--collect-only": "collectonly", "--co": "collectonly"}

    def __init__(self, collectonly: bool) -> None:
        self._values = {"collectonly": collectonly}

    def getoption(self, name: str, default: object = None) -> object:
        dest = self._ALIASES.get(name, name)
        if dest not in self._values:
            raise ValueError(f"no option named {name!r}")
        return self._values[dest]


@pytest.fixture
def steps(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record which of the guard's two steps the exemption let through."""
    calls: list[str] = []

    def enforce() -> tuple[str, str]:
        calls.append("enforce_test_database")
        return "dedicated", "specproof_test"

    def prepare(state: str, database: str) -> None:
        calls.append(f"prepare_test_schema({state}, {database})")

    monkeypatch.setattr(contract, "enforce_test_database", enforce)
    monkeypatch.setattr(contract, "prepare_test_schema", prepare)
    monkeypatch.setattr(contract, "count_product_test_rows", lambda: None)
    monkeypatch.setattr(contract, "MYSQL_ISOLATION", ("unresolved", "", None))
    return calls


def test_a_collect_only_run_does_not_ask_a_server_for_the_schema(steps) -> None:
    contract._apply_mysql_isolation(_Config(collectonly=True))
    assert steps == ["enforce_test_database"], (
        "--collect-only must still make the isolation decision (a child of this "
        "process inherits its environment), and must not run the migration step "
        f"that needs a live server; steps that ran: {steps}"
    )


def test_a_real_run_still_prepares_the_dedicated_schema(steps) -> None:
    contract._apply_mysql_isolation(_Config(collectonly=False))
    assert steps == ["enforce_test_database", "prepare_test_schema(dedicated, specproof_test)"], (
        "the exemption is for collection only — a run that executes fixtures has "
        f"to land on a migrated schema; steps: {steps}"
    )


def test_the_blocked_verdict_still_ends_a_collect_only_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A narrowing must not leak into the fail-closed half of the guard."""
    calls: list[str] = []

    def enforce() -> tuple[str, str]:
        calls.append("enforce_test_database")
        return "blocked", "specproof_test"

    monkeypatch.setattr(contract, "enforce_test_database", enforce)
    monkeypatch.setattr(contract, "prepare_test_schema", lambda s, d: calls.append("prepare"))
    monkeypatch.setattr(contract, "MYSQL_ISOLATION", ("unresolved", "", None))

    with pytest.raises(Exit) as raised:
        contract._apply_mysql_isolation(_Config(collectonly=True))

    assert raised.value.returncode == pytest.ExitCode.USAGE_ERROR, (
        "blocked means the product schema is the only writable one; that is a "
        "configuration verdict, so collecting must not talk it down"
    )
    assert calls == ["enforce_test_database"], (
        f"blocked must be decided before any server step; steps: {calls}"
    )


def test_a_child_collect_only_survives_a_dead_dedicated_schema() -> None:
    """The load-bearing case: it proves the hook really reads the option.

    The in-process cases above feed a stub ``getoption``, so they cannot tell a
    correct option name from a invented one that silently defaults to False;
    only a real child that ends its own session can.
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/unit/test_baseline.py",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, **DEAD_DB_ENV, "PYTHONIOENCODING": "utf-8"},
        timeout=300,
    )
    report = proc.stdout + proc.stderr
    assert report.strip(), "a child that said nothing measured nothing"
    assert REFUSAL not in report, (
        f"exit={proc.returncode} with a dead MySQL on the dedicated schema; "
        f"the child still asked a server for it:\n{report[-1500:]}"
    )
    assert proc.returncode == 0, (
        f"--collect-only ended the session for another reason; "
        f"exit={proc.returncode}\n{report[-1500:]}"
    )
