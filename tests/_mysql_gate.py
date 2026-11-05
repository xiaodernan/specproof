"""#600 — one owner for "this case needs a database this session does not have".

``tests/conftest.py`` (#75) decides the session's MySQL isolation verdict inside
``pytest_configure``, which runs before collection, and publishes it as
``MYSQL_ISOLATION``. Reading the verdict is one thing; turning it into a skip was
another. ``test_contract_compiler.py`` (#499) typed a ``skipif`` for its two
cases, six other files probe the socket at run time and call ``pytest.skip``
themselves, and ``test_the_aggregate_plane_answers_the_demo_question.py`` (#542)
shipped a live-database leg with neither — which is how ``tests-no-infra``, the
job whose whole promise is that no database is there, went red on a healthy
product.

The mark lives here so the decision is made once:

* ``REACHABLE_VERDICTS`` — which verdicts mean "a server answers";
* the reason sentence — which has to name the isolation verdict, because
  ``test_ci_jobs_can_run_the_repo_gates.py`` G2 reads that phrase out of a child
  run's report. A case skipped for any other reason would pass for "there is no
  database", and the green job would be hiding the red that only appears where a
  database does exist.

The run-time probes are still out there and are rostered, with their count
pinned, by
``tests/unit/test_the_no_infra_job_holds_its_no_database_promise.py``.
"""

from __future__ import annotations

import os

import pytest

import tests.conftest as _isolation

#: The verdicts in which a MySQL server answers and the isolation contract has
#: handed this session a schema it may write. The others — ``unreachable``,
#: ``unresolved`` — both mean the same thing to a case: a statement against the
#: database cannot run here, so the case must skip rather than report a defect.
REACHABLE_VERDICTS: frozenset[str] = frozenset({"dedicated", "redirected"})

#: This session's verdict, read at import time. A module-level mark is evaluated
#: during collection, and ``pytest_configure`` has decided the verdict before
#: then, so the value is final here — the same reason #499 could write it inline.
MYSQL_VERDICT = _isolation.MYSQL_ISOLATION[0]

MYSQL_IS_REACHABLE = MYSQL_VERDICT in REACHABLE_VERDICTS


def requires_mysql(what_reaches_the_database: str) -> pytest.MarkDecorator:
    """The ``skipif`` for one case, with that case's own route to MySQL named.

    ``what_reaches_the_database`` is the claim the case makes — "the dashboard
    snapshot writes to MySQL" — so the skip says *which* path needs the server
    instead of only that the case skipped. The verdict clause is fixed here:
    every skip this marker produces answers with the same words, and G2 checks
    them.
    """
    return pytest.mark.skipif(
        not MYSQL_IS_REACHABLE,
        reason=(
            f"{what_reaches_the_database}, and this session's isolation verdict "
            f"is {MYSQL_VERDICT!r}: there is no reachable database, so the case "
            "would fail instead of skipping"
        ),
    )


def dead_database_env() -> dict[str, str]:
    """The environment for a CHILD session that must have no database.

    A gate cannot judge "what happens when there is no MySQL" from inside a
    session that has one, so it spawns a child with this environment. Port 1 is
    refused instantly on every platform, which teaches the child "no database"
    without a timeout — the same refusal a CI runner without infrastructure
    hands it.

    The keys popped are the ones that would otherwise let this machine's own
    ``.env``, or a wrapper's option string, hand the child a reachable schema:
    the witness would then watch a case PASS and report that it skipped.
    """
    env = dict(os.environ)
    env["MYSQL_HOST"] = "127.0.0.1"
    env["MYSQL_PORT"] = "1"
    env.pop("MYSQL_DATABASE", None)
    env.pop("SPECPROOF_TEST_MYSQL_DATABASE", None)
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_CURRENT_TEST", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env
