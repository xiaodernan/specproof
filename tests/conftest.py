"""Shared test fixtures and configuration."""

import ast
import os
import sys
import uuid
from collections.abc import Generator
from pathlib import Path

import pytest

# SpecProof targets Python 3.12+. Several application modules use PEP 695
# generic syntax (e.g. ``def run_with_cancel_checks[T](...)``) that a 3.11
# interpreter cannot even parse. Because tests import those modules
# transitively, running on an older Python produces a confusing wall of
# ``SyntaxError`` collection failures that makes a fresh clone look broken
# rather than telling the developer the real, one-line cause. So on an old
# interpreter we scan the source tree, count the modules that genuinely need
# 3.12, and stop with a single actionable message instead of dozens of errors.
# Under 3.12+ the scan finds nothing and pytest proceeds normally.
_MIN_PYTHON = (3, 12)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCAN_DIRS = ("agent", "api", "craft", "experiments", "providers", "storage")


def _modules_needing_newer_python(root: Path) -> list[str]:
    """Return relative paths of source files this interpreter cannot parse."""
    bad: list[str] = []
    for sub in _SCAN_DIRS:
        base = root / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            try:
                ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (SyntaxError, UnicodeDecodeError):
                bad.append(str(path.relative_to(root)))
    return bad


def pytest_configure(config):
    if sys.version_info >= _MIN_PYTHON:
        _apply_mysql_isolation()
        return
    offending = _modules_needing_newer_python(_PROJECT_ROOT)
    running = ".".join(str(x) for x in sys.version_info[:3])
    msg = (
        f"SpecProof requires Python {_MIN_PYTHON[0]}.{_MIN_PYTHON[1]}+ to run its "
        f"tests, but pytest is executing on Python {running}."
    )
    if offending:
        msg += (
            f" {len(offending)} source module(s) use newer syntax "
            "(e.g. PEP 695 generics) and cannot be imported here — "
            f"examples: {', '.join(offending[:5])}."
        )
    msg += (
        " Install Python 3.12 and re-run. On Windows: `py -3.12 -m pytest` "
        "(or `uv run --python 3.12 pytest`)."
    )
    pytest.exit(msg, returncode=pytest.ExitCode.USAGE_ERROR)


# Unit modules measured (via `pytest --durations`) to dominate wall-clock because
# they simulate a full agent runtime / multi-step LLM loop / benchmark harness.
# Auto-tagged `slow` so contributors can run a fast inner loop with
# `-m 'not integration and not slow'`; CI does NOT deselect these, so the merge
# gate keeps their coverage.
SLOW_TEST_MODULES: frozenset[str] = frozenset({
    "test_agent_runtime.py",
    "test_bench_aider.py",
    "test_bench_mutation.py",
    "test_craft_accept.py",
    "test_craft_llm.py",
    "test_craft_loop.py",
    "test_craft_loop_jobs.py",
    "test_craft_loop_metrics.py",
    "test_craft_memory.py",
    "test_craft_stream.py",
    "test_craft_tools.py",
    "test_craft_verify.py",
    "test_edit_anchor_and_verify_target.py",
    "test_edit_test_guard.py",
    "test_kind_threading.py",
    "test_swebench_harness.py",
    "test_swebench_llm.py",
    "test_swebench_llm_fixes.py",
    "test_swebench_v10_fixes.py",
    "test_swebench_v11_fixes.py",
    "test_verify_criterion_anchor.py",
})


# ── #75: DB-backed tests must never write the product schema ──────
#
# `MySQLConfig` defaults `database` to the PRODUCTION schema and `password` to
# the production app credential, and `from_env()` falls back to both — so an
# unset environment still reaches production tables. Measured here: 13 test
# files build a real `MySQLStore()`, and `verification_jobs` held 177 rows of
# which 177 were `repo_path = '/test/repo'` — the product job table was written
# entirely by the unit suite, and the Dashboard counts those rows as real
# verification jobs. This is not a cleanliness preference: #73 and #76 both
# began from a row a test left behind.
#
# Scope, stated plainly: this contract covers MySQL only. `MongoDBConfig`
# defaults its `database` to the same name and is untouched here.
PRODUCT_MYSQL_DATABASE = "specproof_phase0"
#: One-time creation (additive; grants only on this schema):
#:     powershell scripts/create_test_database.ps1
DEFAULT_TEST_MYSQL_DATABASE = "specproof_test"
TEST_REPO_PATH_PATTERN = "/test/%"

#: (state, database, product-schema test-row count at session start)
MYSQL_ISOLATION: tuple[str, str, int | None] = ("unresolved", "", None)

#: 'blocked' stops the session on purpose: one actionable message beats
#: thousands of tests silently writing the wrong database.
BLOCKED_MESSAGE = (
    "SpecProof's tests must not write the product MySQL schema "
    f"({PRODUCT_MYSQL_DATABASE}), but that is the only schema reachable: "
    "MYSQL_DATABASE names it (or is unset, which defaults to it) and the "
    "isolated test schema is not usable. Create it once with "
    "`powershell scripts/create_test_database.ps1`, or point "
    "SPECPROOF_TEST_MYSQL_DATABASE at an existing non-product schema. "
    "Carrying on would put test rows in the same table as real verification "
    "jobs — 177 of 177 rows were test rows the last time this was counted."
)


def chosen_test_database() -> str:
    """The schema DB-backed tests may write. Never the product one."""
    named = (
        os.getenv("SPECPROOF_TEST_MYSQL_DATABASE") or DEFAULT_TEST_MYSQL_DATABASE
    ).strip()
    if not named or named == PRODUCT_MYSQL_DATABASE:
        raise RuntimeError(
            "SPECPROOF_TEST_MYSQL_DATABASE must name a non-product schema; "
            f"got {named!r}"
        )
    return named


def _connect(database: str, timeout: int):  # noqa: ANN202 — pymysql has no stubs
    import pymysql

    from storage.mysql import MySQLConfig

    config = MySQLConfig.from_env()
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=database,
        charset="utf8mb4",
        connect_timeout=timeout,
        read_timeout=timeout,
        write_timeout=timeout,
    )


def probe_database(database: str) -> str:
    """'ready' | 'absent' | 'unreachable' — read-only, never creates anything."""
    try:
        connection = _connect(database, 3)
    except Exception as exc:  # noqa: BLE001 — the code, not the message, decides
        code = getattr(exc, "args", (None,))[0]
        # 1044/1049: the server answered and this schema is not ours to use.
        return "absent" if code in (1044, 1045, 1049) else "unreachable"
    connection.close()
    return "ready"


def count_product_test_rows() -> int | None:
    """Rows in the PRODUCT schema that look like test residue; None if unreadable."""
    try:
        connection = _connect(PRODUCT_MYSQL_DATABASE, 5)
    except Exception:  # noqa: BLE001 — reporting must never break a run
        return None
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM verification_jobs WHERE repo_path LIKE %s",
                (TEST_REPO_PATH_PATTERN,),
            )
            row = cursor.fetchone()
        values = tuple(row.values()) if isinstance(row, dict) else tuple(row)
        return int(values[0])
    except Exception:  # noqa: BLE001
        return None
    finally:
        connection.close()


def enforce_test_database() -> tuple[str, str]:
    """Decide (and apply) which schema DB-backed tests write. Fail closed.

    states:
      'dedicated'   — the environment already named a non-product schema;
      'redirected'  — it named the product schema and the test schema answers,
                      so MYSQL_DATABASE now names the test schema;
      'unreachable' — no MySQL answers, so DB-backed tests skip as they always
                      have (that is a coverage fact, not isolation);
      'blocked'     — the product schema is the only writable one.
    """
    current = (os.getenv("MYSQL_DATABASE") or "").strip() or PRODUCT_MYSQL_DATABASE
    if current != PRODUCT_MYSQL_DATABASE:
        return "dedicated", current
    target = chosen_test_database()
    if probe_database(target) == "ready":
        os.environ["MYSQL_DATABASE"] = target
        return "redirected", target
    if probe_database(PRODUCT_MYSQL_DATABASE) != "ready":
        return "unreachable", PRODUCT_MYSQL_DATABASE
    return "blocked", target


def prepare_test_schema(state: str, database: str) -> None:
    """Apply the schema migrations to the redirected target.

    11 of the 13 DB-backed test files never call `ensure_tables()` — they relied
    on the product schema already having its tables, so a bare redirect would
    turn them into 'table doesn't exist' errors.
    """
    if state not in ("dedicated", "redirected"):
        return
    import time

    from storage.mysql import MySQLStore

    # Retried on purpose: this machine measured a transient
    # `InterfaceError(0, '')` from `ensure_tables()` under load (connect
    # timeout is 5s), and a one-shot check would fail-close a whole session on
    # a stutter. A real missing privilege fails three times too.
    last: Exception | None = None
    for attempt in range(3):
        try:
            MySQLStore().ensure_tables()
            return
        except Exception as exc:  # noqa: BLE001 — the retry decides, not the type
            last = exc
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"test schema {database!r} is not usable: {last!r}")


def _apply_mysql_isolation() -> None:
    global MYSQL_ISOLATION
    try:
        state, database = enforce_test_database()
        prepare_test_schema(state, database)
    except Exception as exc:  # noqa: BLE001 — a broken check must be loud
        pytest.exit(f"MySQL test isolation check failed: {exc}", returncode=1)
    if state == "blocked":
        pytest.exit(BLOCKED_MESSAGE, returncode=4)  # ExitCode.USAGE_ERROR
    MYSQL_ISOLATION = (state, database, count_product_test_rows())


def pytest_report_header(config) -> str:  # noqa: ARG001 — pytest hook signature
    state, database, before = MYSQL_ISOLATION
    if state == "unresolved":
        return "MySQL isolation: not evaluated (Python version guard fired)"
    residue = "unknown" if before is None else str(before)
    return (
        f"MySQL test isolation: {state} -> {database} "
        f"(product schema {PRODUCT_MYSQL_DATABASE} holds {residue} "
        "'/test/%' job rows at session start)"
    )


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001 — hook signature
    state, database, before = MYSQL_ISOLATION
    if state not in ("dedicated", "redirected") or before is None:
        return
    after = count_product_test_rows()
    if after is None:
        return
    delta = after - before
    verdict = (
        "no test row landed in the product schema"
        if delta == 0
        else f"ISOLATION BREACH: {delta} new /test/% rows in the product schema"
    )
    print(
        f"\nMySQL test isolation ({state} -> {database}): product schema "
        f"'/test/%' rows {before} -> {after}; {verdict}"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-tag tests under tests/integration and tests/e2e as `integration`.

    Those paths drive real subprocesses, git tags, Maven and live infra, so they
    are slow and non-hermetic. Tagging by directory lets contributors and CI run
    a fast unit path with `pytest -m 'not integration'` without decorating every
    file by hand.

    It also tags a measured set of slow UNIT modules (full agent-runtime /
    LLM-loop / benchmark simulations) as `slow`, so contributors get a
    sub-minute-to-few-minute inner loop via `-m 'not integration and not slow'`.
    CI still runs them (its job does not deselect `slow`), so this never drops
    coverage from the merge gate — it only reorders convenience. The module list
    is derived from `pytest --durations` on this repo, not guessed; see the
    test_slow_marker_tagging regression lock.
    """
    rootdir = str(Path(config.rootdir).resolve()).replace("\\", "/").rstrip("/")
    for item in items:
        fpath = str(Path(item.fspath).resolve()).replace("\\", "/")
        rel = fpath[len(rootdir) + 1:] if fpath.startswith(rootdir) else fpath
        if rel.startswith(("tests/integration/", "tests/e2e/")):
            item.add_marker(pytest.mark.integration)
        elif Path(rel).name in SLOW_TEST_MODULES:
            item.add_marker(pytest.mark.slow)


@pytest.fixture
def temp_job_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture(autouse=True)
def clean_env(tmp_path: Path) -> Generator[None, None, None]:
    """Ensure no real API keys leak into test environment."""
    sensitive = [
        "LLM_API_KEY",
        "MYSQL_PASSWORD",
        "MONGODB_PASSWORD",
        "ES_PASSWORD",
        "REDIS_PASSWORD",
        "RABBITMQ_PASSWORD",
        "MINIO_ROOT_PASSWORD",
    ]
    saved = {}
    for key in sensitive:
        saved[key] = os.environ.pop(key, None)
    # Never load private local model credentials during unit tests.
    saved["SPECPROOF_MODEL_CONFIG"] = os.environ.get("SPECPROOF_MODEL_CONFIG")
    os.environ["SPECPROOF_MODEL_CONFIG"] = str(tmp_path / "unconfigured-model.json")
    # §A task 7: keep the object metadata store hermetic in tests — the
    # default backend must never touch ~/.specproof/*.sqlite3 here.
    saved["SPECPROOF_OBJECT_METADATA_BACKEND"] = os.environ.pop(
        "SPECPROOF_OBJECT_METADATA_BACKEND", None
    )
    os.environ["SPECPROOF_OBJECT_METADATA_BACKEND"] = "memory"
    # The worker announces terminal verdicts over the webhook connector (#65),
    # which is built from these three variables. A developer machine that has
    # them configured must not turn a unit run into real outbound posts.
    for key in (
        "SPECPROOF_NOTIFY_WEBHOOK_URL",
        "SPECPROOF_NOTIFY_WEBHOOK_SECRET",
        "SPECPROOF_NOTIFY_WEBHOOK_KIND",
    ):
        saved[key] = os.environ.pop(key, None)

    yield

    for key, val in saved.items():
        if val is not None:
            os.environ[key] = val
        else:
            os.environ.pop(key, None)
