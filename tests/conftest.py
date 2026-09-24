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
